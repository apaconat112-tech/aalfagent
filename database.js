const Database = require('better-sqlite3');
const config = require('./config');

const db = new Database(config.databasePath);
db.pragma('journal_mode = WAL');
db.exec(`
  CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL,
    user_id INTEGER, username TEXT, full_name TEXT, text TEXT NOT NULL, timestamp TEXT NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_messages_chat_time ON messages (chat_id, timestamp);
  CREATE TABLE IF NOT EXISTS chat_metadata (
    chat_id INTEGER PRIMARY KEY, last_summary_time TEXT, schedule_hours INTEGER DEFAULT 0, updated_at TEXT NOT NULL
  );
`);

const statements = {
  save: db.prepare('INSERT INTO messages (chat_id, message_id, user_id, username, full_name, text, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)'),
  since: db.prepare('SELECT message_id, user_id, username, full_name, text, timestamp FROM messages WHERE chat_id = ? AND timestamp >= ? ORDER BY timestamp ASC'),
  lastSummary: db.prepare('SELECT last_summary_time FROM chat_metadata WHERE chat_id = ?'),
  schedules: db.prepare('SELECT chat_id, schedule_hours, last_summary_time FROM chat_metadata WHERE schedule_hours > 0'),
  chats: db.prepare('SELECT DISTINCT chat_id FROM messages')
};

function saveMessage(message) {
  if (!message.text || !message.text.trim()) return;
  statements.save.run(message.chatId, message.messageId, message.userId || null, message.username || null, message.fullName || null, message.text.trim(), new Date(message.timestamp || Date.now()).toISOString());
}
function getMessagesSince(chatId, since) { return statements.since.all(chatId, new Date(since).toISOString()); }
function getLastSummaryTime(chatId) { return statements.lastSummary.get(chatId)?.last_summary_time || null; }
function setMetadata(chatId, fields) {
  const current = db.prepare('SELECT last_summary_time, schedule_hours FROM chat_metadata WHERE chat_id = ?').get(chatId) || {};
  db.prepare(`INSERT INTO chat_metadata (chat_id, last_summary_time, schedule_hours, updated_at) VALUES (?, ?, ?, ?)
    ON CONFLICT(chat_id) DO UPDATE SET last_summary_time=excluded.last_summary_time, schedule_hours=excluded.schedule_hours, updated_at=excluded.updated_at`)
    .run(chatId, fields.lastSummaryTime ?? current.last_summary_time ?? null, fields.scheduleHours ?? current.schedule_hours ?? 0, new Date().toISOString());
}
function setChatSchedule(chatId, hours) { setMetadata(chatId, { scheduleHours: hours }); }
function updateLastSummaryTime(chatId, timestamp) { setMetadata(chatId, { lastSummaryTime: new Date(timestamp).toISOString() }); }
function getAllActiveSchedules() { return statements.schedules.all(); }
function cleanupOldMessages(days = 30) { return db.prepare("DELETE FROM messages WHERE timestamp < datetime('now', ?)").run(`-${days} days`).changes; }
function getAllTrackedChats() { return statements.chats.all().map(row => row.chat_id); }

module.exports = { saveMessage, getMessagesSince, getLastSummaryTime, setChatSchedule, updateLastSummaryTime, getAllActiveSchedules, cleanupOldMessages, getAllTrackedChats, close: () => db.close() };