const { Bot, GrammyError } = require('grammy');
const config = require('./config');
const database = require('./database');
const summarizer = require('./summarizer');

const [valid, error] = config.validateConfig();
if (!valid) { console.error(`[ERROR] ${error}`); process.exitCode = 1; return; }
const bot = new Bot(config.telegramBotToken);
const schedules = new Map();

function parseTimeframe(raw) {
  if (!raw) return null;
  const match = String(raw).toLowerCase().match(/^(\d+)\s*(h|jam|d|hari)?$/);
  if (!match) return null;
  const amount = Number(match[1]);
  return (match[2] === 'd' || match[2] === 'hari') ? amount * 24 * 60 * 60 * 1000 : amount * 60 * 60 * 1000;
}
function splitMessage(text, max = 4000) {
  if (text.length <= max) return [text];
  const result = []; let current = '';
  for (const line of text.split('\n')) {
    if (current.length + line.length + 1 > max && current) { result.push(current); current = ''; }
    current += `${line}\n`;
  }
  if (current.trim()) result.push(current);
  return result;
}
async function sendLong(ctx, text, replyTo) {
  for (const [index, part] of splitMessage(text).entries()) await ctx.api.sendMessage(ctx.chat.id, part, { reply_parameters: index === 0 && replyTo ? { message_id: replyTo } : undefined });
}
async function performSummary(chatId, ctx, duration, replyTo) {
  const now = Date.now();
  const last = database.getLastSummaryTime(chatId);
  const since = duration ? now - duration : last ? new Date(last).getTime() : now - config.defaultSummaryHours * 3600000;
  const label = duration ? `${Math.round(duration / 3600000)} jam terakhir` : last ? 'sejak ringkasan terakhir' : `${config.defaultSummaryHours} jam terakhir (default)`;
  const messages = database.getMessagesSince(chatId, since);
  if (!messages.length) return ctx.reply(`ℹ️ Belum ada pesan obrolan baru yang tersimpan untuk periode ${label}.`, { reply_parameters: replyTo ? { message_id: replyTo } : undefined });
  const status = await ctx.reply(`🤖 Sedang membaca ${messages.length} pesan dan merangkum dengan ${config.aiProvider}...`);
  try { await sendLong(ctx, await summarizer.summarizeMessages(messages, label), replyTo); database.updateLastSummaryTime(chatId, now); await ctx.api.deleteMessage(chatId, status.message_id); }
  catch (err) { await ctx.api.editMessageText(chatId, status.message_id, `❌ Gagal membuat ringkasan: ${err.message}`); }
}
function scheduledContext(chatId) {
  return {
    api: bot.api,
    chat: { id: chatId },
    reply: (text, options) => bot.api.sendMessage(chatId, text, options)
  };
}

function extractUrls(ctx) {
  const text = ctx.message?.text || ctx.message?.caption || '';
  const urls = [];
  const entities = ctx.message?.entities || ctx.message?.caption_entities || [];
  for (const ent of entities) {
    if (ent.type === 'url') urls.push(text.substring(ent.offset, ent.offset + ent.length));
    else if (ent.type === 'text_link' && ent.url) urls.push(ent.url);
  }
  const regex = /(?:https?:\/\/|www\.|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\/?)[^\s]*/g;
  let match;
  while ((match = regex.exec(text)) !== null) {
    if (!urls.includes(match[0])) urls.push(match[0]);
  }
  return urls;
}
function extractDomain(url) {
  let clean = url.trim().toLowerCase();
  if (!clean.startsWith('http://') && !clean.startsWith('https://')) clean = 'http://' + clean;
  try {
    const u = new URL(clean);
    let dom = u.hostname;
    if (dom.startsWith('www.')) dom = dom.slice(4);
    return dom;
  } catch (e) {
    return clean.split('/')[0];
  }
}
async function isUserAdmin(ctx) {
  if (ctx.chat?.type === 'private') return true;
  if (ctx.message?.sender_chat?.id === ctx.chat?.id) return true;
  if (!ctx.from?.id) return false;
  try {
    const member = await ctx.api.getChatMember(ctx.chat.id, ctx.from.id);
    return ['administrator', 'creator'].includes(member.status);
  } catch (e) {
    return false;
  }
}

bot.command(['start', 'help'], ctx => ctx.reply('👋 Saya adalah Telegram AI Assistant, Group Satpam & Summarizer Bot.\n\nPerintah: /summary [6h|2d], /satpam [on|off|mode|add|del|list], /schedule <jam>, /unschedule, /groups, /model [gemini|anthropic|hermes].\n\nDi DM, kirim pesan untuk chat AI. Di grup, mention bot atau reply pesan bot untuk bertanya.'));
bot.command('summary', ctx => performSummary(ctx.chat.id, ctx, parseTimeframe(ctx.match?.trim()), ctx.msg.message_id));
bot.command(['groups', 'grup'], async ctx => { const chats = database.getAllTrackedChats(); await ctx.reply(chats.length ? `📋 Chat yang dipantau:\n${chats.map(id => `• ${id}`).join('\n')}` : 'ℹ️ Belum ada obrolan yang tersimpan.'); });
bot.command('model', ctx => ctx.reply(`🤖 Provider aktif: ${config.aiProvider}\nModel: ${config[`${config.aiProvider}Model`] || config.hermesModel}`));
bot.command('schedule', async ctx => {
  const hours = Number.parseInt(ctx.match?.trim(), 10);
  if (!Number.isInteger(hours) || hours < 1 || hours > 168) return ctx.reply('⚠️ Gunakan /schedule <jam>, antara 1 sampai 168.');
  const chatId = ctx.chat.id; database.setChatSchedule(chatId, hours); if (schedules.has(chatId)) clearInterval(schedules.get(chatId));
  schedules.set(chatId, setInterval(() => performSummary(chatId, scheduledContext(chatId), null), hours * 3600000));
  await ctx.reply(`✅ Ringkasan terjadwal aktif setiap ${hours} jam.`);
});
bot.command('unschedule', async ctx => { const chatId = ctx.chat.id; database.setChatSchedule(chatId, 0); if (schedules.has(chatId)) clearInterval(schedules.get(chatId)); schedules.delete(chatId); await ctx.reply('🛑 Ringkasan terjadwal dimatikan.'); });

bot.command('satpam', async ctx => {
  if (ctx.chat?.type === 'private') return ctx.reply('⚠️ Fitur Satpam Grup hanya dapat digunakan di Grup Telegram.');
  const args = ctx.match?.trim().split(/\s+/) || [];
  const subcommand = args[0]?.toLowerCase() || 'status';
  const isAdmin = await isUserAdmin(ctx);

  if (['on', 'off', 'mode', 'add', 'del'].includes(subcommand) && !isAdmin) {
    return ctx.reply('⛔ Hanya Admin Grup yang berhak mengubah pengaturan Satpam Grup.');
  }

  const cfg = database.getSatpamSettings(ctx.chat.id);
  if (['status', 'info'].includes(subcommand)) {
    const wl = database.getWhitelistDomains(ctx.chat.id);
    return ctx.reply(`🛡 STATUS SATPAM GRUP:\n• Status: ${cfg.enabled ? '🟢 AKTIF' : '🔴 NON-AKTIF'}\n• Mode: ${cfg.mode}\n• Whitelist: ${wl.join(', ') || 'Belum ada'}\n\nPenggunaan: /satpam [on|off], /satpam mode [admin|whitelist], /satpam add <domain>, /satpam del <domain>, /satpam list`);
  } else if (subcommand === 'on') {
    database.setSatpamSettings(ctx.chat.id, true, cfg.mode);
    return ctx.reply('🟢 Satpam Grup DIAKTIFKAN!');
  } else if (subcommand === 'off') {
    database.setSatpamSettings(ctx.chat.id, false, cfg.mode);
    return ctx.reply('🔴 Satpam Grup DIMATIKAN.');
  } else if (subcommand === 'mode') {
    const newMode = args[1]?.toLowerCase() === 'whitelist' ? 'whitelist' : 'admin_only';
    database.setSatpamSettings(ctx.chat.id, cfg.enabled, newMode);
    return ctx.reply(`⚙️ Mode Satpam diubah ke: ${newMode}`);
  } else if (subcommand === 'add') {
    if (!args[1]) return ctx.reply('⚠️ Masukkan domain. Contoh: /satpam add github.com');
    database.addWhitelistDomain(ctx.chat.id, args[1]);
    return ctx.reply(`✅ Domain ${args[1]} ditambahkan ke Whitelist.`);
  } else if (subcommand === 'del') {
    if (!args[1]) return ctx.reply('⚠️ Masukkan domain. Contoh: /satpam del github.com');
    database.removeWhitelistDomain(ctx.chat.id, args[1]);
    return ctx.reply(`🗑 Domain ${args[1]} dihapus dari Whitelist.`);
  } else if (subcommand === 'list') {
    const wl = database.getWhitelistDomains(ctx.chat.id);
    return ctx.reply(`📋 WHITELIST DOMAIN:\n${wl.map(d => `• ${d}`).join('\n') || 'Kosong'}`);
  }
});

bot.on('message:text', async ctx => {
  const text = ctx.message.text; const user = ctx.from; const chat = ctx.chat;

  if (chat.type !== 'private') {
    const cfg = database.getSatpamSettings(chat.id);
    if (cfg.enabled) {
      const urls = extractUrls(ctx);
      if (urls.length > 0) {
        const isAdmin = await isUserAdmin(ctx);
        if (!isAdmin) {
          let prohibited = false;
          if (cfg.mode === 'whitelist') {
            const wl = database.getWhitelistDomains(chat.id);
            prohibited = urls.some(u => {
              const dom = extractDomain(u);
              return !wl.some(w => dom === w || dom.endsWith('.' + w));
            });
          } else {
            prohibited = true;
          }
          if (prohibited) {
            try { await ctx.api.deleteMessage(chat.id, ctx.message.message_id); } catch (e) {}
            try {
              const warn = await ctx.reply(`⚠️ @${user?.username || user?.first_name}, link tidak diizinkan di grup ini!`);
              setTimeout(() => ctx.api.deleteMessage(chat.id, warn.message_id).catch(() => {}), 10000);
            } catch (e) {}
            return;
          }
        }
      }
    }
  }

  database.saveMessage({ chatId: chat.id, messageId: ctx.message.message_id, userId: user?.id, username: user?.username, fullName: [user?.first_name, user?.last_name].filter(Boolean).join(' '), text, timestamp: ctx.message.date * 1000 });
  const botInfo = await bot.api.getMe(); const mentioned = text.toLowerCase().includes(`@${botInfo.username.toLowerCase()}`); const replied = ctx.message.reply_to_message?.from?.id === botInfo.id;
  if (chat.type !== 'private' && !mentioned && !replied) return;
  let prompt = text.replace(new RegExp(`@${botInfo.username}`, 'ig'), '').trim() || 'Halo!';
  const translation = /^(bahasa\s+)?(indonesia|inggris|english|indonesian)$/i.test(prompt) && ctx.message.reply_to_message?.text;
  try { const reply = translation ? await summarizer.translateText(ctx.message.reply_to_message.text, /inggris|english/i.test(prompt) ? 'Bahasa Inggris' : 'Bahasa Indonesia') : await summarizer.chatReply(prompt); await sendLong(ctx, reply, ctx.message.message_id); }
  catch (err) { await ctx.reply(`❌ Gagal memproses pesan: ${err.message}`); }
});

for (const schedule of database.getAllActiveSchedules()) {
  schedules.set(schedule.chat_id, setInterval(() => performSummary(schedule.chat_id, scheduledContext(schedule.chat_id), null), schedule.schedule_hours * 3600000));
}
setInterval(() => console.log(`Database cleanup: ${database.cleanupOldMessages(30)} pesan dihapus`), 86400000);
bot.catch(err => console.error('Telegram update error:', err.error instanceof GrammyError ? err.error.description : err.error));
console.log(`Starting Node.js bot with provider ${config.aiProvider}`);
bot.start({ drop_pending_updates: false });