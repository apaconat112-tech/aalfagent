const config = require('./config');

const SYSTEM_PROMPT = `Anda adalah asisten AI Telegram profesional bernama Chat Summarizer.
Gunakan Bahasa Indonesia yang padat, spesifik, dan cerdas. Jangan tampilkan reasoning.
Selalu gunakan format:
📌 *TOPIK UTAMA*
• poin utama
✅ *KEPUTUSAN & KESEPAKATAN*
• keputusan atau Tidak ada keputusan khusus
📋 *ACTION ITEMS & TINDAK LANJUT*
• tugas dan @username PIC atau Tidak ada action item
🔗 *LINK & REFERENSI PENTING*
• keterangan dan URL atau Tidak ada tautan dibagikan`;

function formatTranscript(messages) {
  return messages.map(message => {
    const sender = message.full_name || message.username || `User_${message.user_id || ''}`;
    const username = message.username ? ` (@${message.username})` : '';
    const date = new Date(message.timestamp);
    const stamp = Number.isNaN(date.getTime()) ? message.timestamp : date.toLocaleString('id-ID', { timeZone: 'UTC', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    return `[${stamp}] ${sender}${username}: ${String(message.text || '').replace(/\n/g, ' ')}`;
  }).join('\n');
}

function cleanOutput(text) {
  let result = String(text || '').trim();
  const marker = result.indexOf('📌');
  if (marker >= 0) result = result.slice(marker);
  result = result.replace(/\[(https?:\/\/[^\s\]]+)\]\(\1\)/g, '$1');
  result = result.replace(/^\s*[\*-]\s*[\*-]\s*/gm, '• ');
  result = result.replace(/^\s*[\*-]\s+/gm, '• ');
  result = result.replace(/📌\s*\*?TOPIK UTAMA\*?:?/g, '📌 *TOPIK UTAMA*');
  result = result.replace(/✅\s*\*?KEPUTUSAN\s*(?:&|DAN)?\s*KESEPAKATAN\*?:?/g, '✅ *KEPUTUSAN & KESEPAKATAN*');
  result = result.replace(/📋\s*\*?ACTION ITEMS\s*(?:&|DAN)?\s*TINDAK LANJUT\*?:?/g, '📋 *ACTION ITEMS & TINDAK LANJUT*');
  result = result.replace(/🔗\s*\*?LINK\s*(?:&|DAN)?\s*REFERENSI PENTING\*?:?/g, '🔗 *LINK & REFERENSI PENTING*');
  return result.trim();
}

async function openAiCompatible(prompt, system = SYSTEM_PROMPT) {
  const headers = { 'Content-Type': 'application/json' };
  if (config.hermesApiKey) headers.Authorization = `Bearer ${config.hermesApiKey}`;
  const response = await fetch(`${config.hermesBaseUrl.replace(/\/$/, '')}/chat/completions`, {
    method: 'POST', headers,
    body: JSON.stringify({ model: config.hermesModel, messages: [{ role: 'system', content: system }, { role: 'user', content: prompt }], temperature: 0.3, max_tokens: 2048 })
  });
  if (!response.ok) throw new Error(`Hermes API ${response.status}: ${await response.text()}`);
  const data = await response.json();
  return data.choices?.[0]?.message?.content || data.choices?.[0]?.message?.reasoning || '';
}

async function generate(prompt, system = SYSTEM_PROMPT) {
  if (config.aiProvider === 'gemini') {
    const { GoogleGenAI } = require('@google/genai');
    const client = new GoogleGenAI({ apiKey: config.geminiApiKey });
    const response = await client.models.generateContent({ model: config.geminiModel, contents: prompt, config: { systemInstruction: system, maxOutputTokens: 2048, temperature: 0.3 } });
    return response.text || '';
  }
  if (config.aiProvider === 'anthropic') {
    const Anthropic = require('@anthropic-ai/sdk');
    const client = new Anthropic({ apiKey: config.anthropicApiKey });
    const response = await client.messages.create({ model: config.anthropicModel, max_tokens: 2048, system, messages: [{ role: 'user', content: prompt }] });
    return response.content?.[0]?.text || '';
  }
  return openAiCompatible(prompt, system);
}

async function summarizeMessages(messages, timeframeInfo = '') {
  if (!messages.length) return '⚠️ Tidak ada pesan baru untuk diringkas.';
  const chunks = [];
  for (let index = 0; index < messages.length; index += config.maxMessagesPerChunk) chunks.push(messages.slice(index, index + config.maxMessagesPerChunk));
  let content;
  if (chunks.length === 1) {
    content = await generate(`Berikut transkrip obrolan grup Telegram:\n\n${formatTranscript(chunks[0])}\n\nBuat ringkasan lengkap sesuai format standar.`);
  } else {
    const partials = await Promise.all(chunks.map(chunk => generate(`Berikut transkrip obrolan grup Telegram:\n\n${formatTranscript(chunk)}\n\nRangkum topik, keputusan, action items, dan link secara padat.`, SYSTEM_PROMPT)));
    content = await generate(`Gabungkan poin berikut menjadi satu ringkasan lengkap tanpa duplikasi:\n\n${partials.join('\n\n')}`);
  }
  const label = config.aiProvider === 'gemini' ? `Google Gemini AI (${config.geminiModel})` : config.aiProvider === 'anthropic' ? `Claude (${config.anthropicModel})` : `Nous-Hermes (${config.hermesModel})`;
  return `📊 *RINGKASAN CHAT GRUP*\n${timeframeInfo ? `🕒 Periode: _${timeframeInfo}_\n` : ''}💬 Total Pesan: *${messages.length} pesan*\n\n${cleanOutput(content)}\n\n_— Diringkas otomatis dengan ${label}_`;
}

async function chatReply(userMessage) {
  return generate(userMessage, 'Anda adalah asisten Telegram yang ramah dan cerdas. Jawab langsung dalam Bahasa Indonesia tanpa perkenalan yang tidak diminta.');
}

async function translateText(text, targetLanguage) {
  return generate(`Terjemahkan teks berikut ke ${targetLanguage}. Pertahankan makna, tautan, heading, dan format Markdown. Keluarkan hanya terjemahan.\n\n${text}`, `Anda adalah penerjemah profesional ke ${targetLanguage}. Keluarkan hanya hasil terjemahan.`);
}

module.exports = { summarizeMessages, chatReply, translateText, formatTranscript };