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

bot.command(['start', 'help'], ctx => ctx.reply('👋 Saya adalah Telegram AI Assistant & Summarizer Bot.\n\nPerintah: /summary [6h|2d], /schedule <jam>, /unschedule, /groups, /model [gemini|anthropic|hermes].\n\nDi DM, kirim pesan untuk chat AI. Di grup, mention bot atau reply pesan bot untuk bertanya.'));
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

bot.on('message:text', async ctx => {
  const text = ctx.message.text; const user = ctx.from; const chat = ctx.chat;
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