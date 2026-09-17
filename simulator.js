const { Bot } = require('grammy');
const config = require('./config');
const database = require('./database');
const summarizer = require('./summarizer');

const personas = [
  ['siti_pm', 'Siti Rahma', 'Product Manager'], ['budi_dev', 'Budi Santoso', 'Senior Backend Lead'],
  ['andi_qa', 'Andi Wijaya', 'QA Lead'], ['dewi_design', 'Dewi Lestari', 'UI/UX Designer'], ['eko_devops', 'Eko Prasetyo', 'DevOps Engineer']
];
async function main() {
  const args = process.argv.slice(2); const value = key => args[args.indexOf(`--${key}`) + 1];
  const chatId = Number(value('chat-id')); const topic = value('topic') || 'Persiapan rilis fitur payment gateway'; const turns = Number(value('turns') || 6); const delay = Number(value('delay') || 3);
  if (!chatId || !config.telegramBotToken) throw new Error('Gunakan --chat-id dan isi TELEGRAM_BOT_TOKEN di .env');
  const bot = new Bot(config.telegramBotToken); let context = `Topik diskusi: ${topic}`;
  for (let i = 0; i < turns; i++) {
    const [username, name, role] = personas[i % personas.length]; const reply = await summarizer.chatReply(`Bertindak sebagai ${name}, ${role}. Lanjutkan diskusi tim tentang "${topic}" dalam 1-3 kalimat.\nKonteks:\n${context}`);
    const sent = await bot.api.sendMessage(chatId, reply); database.saveMessage({ chatId, messageId: sent.message_id, userId: i + 1001, username, fullName: name, text: reply, timestamp: Date.now() }); context += `\n${name}: ${reply}`; console.log(`[${i + 1}/${turns}] ${name}: ${reply}`);
    if (i < turns - 1) await new Promise(resolve => setTimeout(resolve, delay * 1000));
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });