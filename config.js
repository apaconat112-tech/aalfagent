const path = require('node:path');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const env = (name, fallback = '') => (process.env[name] || fallback).trim();
const number = (name, fallback) => Number.parseInt(env(name, String(fallback)), 10);

const config = {
  telegramBotToken: env('TELEGRAM_BOT_TOKEN'),
  aiProvider: env('AI_PROVIDER', 'gemini').toLowerCase(),
  geminiApiKey: env('GEMINI_API_KEY'),
  geminiModel: env('GEMINI_MODEL', 'gemini-3.6-flash'),
  anthropicApiKey: env('ANTHROPIC_API_KEY'),
  anthropicModel: env('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022'),
  hermesApiKey: env('HERMES_API_KEY'),
  hermesModel: env('HERMES_MODEL', 'nousresearch/hermes-3-llama-3.1-8b:free'),
  hermesBaseUrl: env('HERMES_BASE_URL', 'https://openrouter.ai/api/v1'),
  defaultSummaryHours: number('DEFAULT_SUMMARY_HOURS', 24),
  databasePath: env('DATABASE_PATH', 'chat_history.db'),
  maxMessagesPerChunk: number('MAX_MESSAGES_PER_CHUNK', 150)
};

if (!['gemini', 'anthropic', 'hermes'].includes(config.aiProvider)) config.aiProvider = 'gemini';
if (config.hermesApiKey && !config.geminiApiKey && !config.anthropicApiKey) config.aiProvider = 'hermes';
if (config.geminiApiKey && !config.anthropicApiKey && !config.hermesApiKey && config.aiProvider !== 'hermes') config.aiProvider = 'gemini';
if (config.anthropicApiKey && !config.geminiApiKey && !config.hermesApiKey && config.aiProvider !== 'hermes') config.aiProvider = 'anthropic';

function validateConfig() {
  if (!config.telegramBotToken) return [false, 'TELEGRAM_BOT_TOKEN belum diatur di file .env!'];
  const key = config.aiProvider === 'gemini' ? config.geminiApiKey : config.aiProvider === 'anthropic' ? config.anthropicApiKey : config.hermesApiKey;
  if (!key && !(config.aiProvider === 'hermes' && !config.hermesBaseUrl.toLowerCase().includes('openrouter'))) {
    return [false, `API key untuk provider ${config.aiProvider} belum diatur di file .env!`];
  }
  return [true, 'Config valid.'];
}

module.exports = config;
module.exports.validateConfig = validateConfig;