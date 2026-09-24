import os
from pathlib import Path
from dotenv import load_dotenv

# Muat file .env jika ada
PROJECT_ROOT = Path(__file__).resolve().parent
env_path = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=env_path)

# Token Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Credentials Telegram Client API (UserBot Rahasia Tanpa Bot di Grup)
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "").strip()
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "").strip()

def get_all_string_sessions() -> list[str]:
    """Mendapatkan daftar seluruh StringSession Telegram yang dikonfigurasi di .env (Mendukung Multi-Account)."""
    sessions = []
    main_sess = os.getenv("TELEGRAM_STRING_SESSION", "").strip()
    if main_sess:
        sessions.append(main_sess)
    
    raw_list = os.getenv("TELEGRAM_STRING_SESSIONS", "").strip()
    if raw_list:
        for s in raw_list.split(","):
            s = s.strip()
            if s and s not in sessions:
                sessions.append(s)

    for k, v in os.environ.items():
        if k.startswith("TELEGRAM_STRING_SESSION_") and v.strip():
            val = v.strip()
            if val not in sessions:
                sessions.append(val)

    return sessions

# Token tambahan untuk Simulator Multi-Bot (dipisahkan koma)
SIMULATOR_BOT_TOKENS_RAW = os.getenv("SIMULATOR_BOT_TOKENS", "").strip()
SIMULATOR_BOT_TOKENS = [t.strip() for t in SIMULATOR_BOT_TOKENS_RAW.split(",") if t.strip()]
if not SIMULATOR_BOT_TOKENS and TELEGRAM_BOT_TOKEN:
    SIMULATOR_BOT_TOKENS = [TELEGRAM_BOT_TOKEN]

# Provider AI: "gemini" (Gratis), "openai" (GPT-4o/mini), "anthropic" (Claude), atau "hermes" (Nous-Hermes via OpenRouter/Ollama)
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()

# Konfigurasi Google Gemini (GRATIS di https://aistudio.google.com/)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()

# Konfigurasi OpenAI GPT
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()

# Konfigurasi Anthropic Claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022").strip()

# Konfigurasi Hermes AI (Nous-Hermes via OpenRouter / Ollama / OpenAI-compatible endpoint)
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "").strip()
HERMES_MODEL = os.getenv("HERMES_MODEL", "nex-agi/nex-n2.5-mini:free").strip()
HERMES_BASE_URL = os.getenv("HERMES_BASE_URL", "https://openrouter.ai/api/v1").strip()

def reload_config():
    """BACA ULANG file .env agar perubahan variabel langsung aktif di memori tanpa perlu restart."""
    load_dotenv(dotenv_path=env_path, override=True)
    global TELEGRAM_BOT_TOKEN, TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_STRING_SESSION
    global AI_PROVIDER, GEMINI_API_KEY, GEMINI_MODEL, OPENAI_API_KEY, OPENAI_MODEL
    global ANTHROPIC_API_KEY, ANTHROPIC_MODEL, HERMES_API_KEY, HERMES_MODEL, HERMES_BASE_URL
    
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022").strip()
    HERMES_API_KEY = os.getenv("HERMES_API_KEY", "").strip()
    HERMES_MODEL = os.getenv("HERMES_MODEL", "nex-agi/nex-n2.5-mini:free").strip()
    HERMES_BASE_URL = os.getenv("HERMES_BASE_URL", "https://openrouter.ai/api/v1").strip()
    AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()

# Normalisasi alias provider
if AI_PROVIDER in ["gpt", "chatgpt", "openai"]:
    AI_PROVIDER = "openai"

# Penyesuaian provider otomatis jika hanya satu key yang diisi dan AI_PROVIDER belum spesifik
if AI_PROVIDER not in ["gemini", "openai", "anthropic", "hermes"]:
    AI_PROVIDER = "gemini"

if OPENAI_API_KEY and not GEMINI_API_KEY and not ANTHROPIC_API_KEY and not HERMES_API_KEY:
    AI_PROVIDER = "openai"
elif HERMES_API_KEY and not GEMINI_API_KEY and not ANTHROPIC_API_KEY and not OPENAI_API_KEY:
    AI_PROVIDER = "hermes"
elif GEMINI_API_KEY and not ANTHROPIC_API_KEY and not HERMES_API_KEY and not OPENAI_API_KEY and AI_PROVIDER != "hermes":
    AI_PROVIDER = "gemini"
elif ANTHROPIC_API_KEY and not GEMINI_API_KEY and not HERMES_API_KEY and not OPENAI_API_KEY and AI_PROVIDER != "hermes":
    AI_PROVIDER = "anthropic"

# Konfigurasi ringkasan dan database
DEFAULT_SUMMARY_HOURS = int(os.getenv("DEFAULT_SUMMARY_HOURS", "24"))
_database_value = os.getenv("DATABASE_PATH", "chat_history.db").strip()
DATABASE_PATH = str((PROJECT_ROOT / _database_value).resolve()) if not Path(_database_value).is_absolute() else _database_value
MAX_MESSAGES_PER_CHUNK = int(os.getenv("MAX_MESSAGES_PER_CHUNK", "80"))
FAST_SUMMARY_MAX_MESSAGES = int(os.getenv("FAST_SUMMARY_MAX_MESSAGES", "80"))
MAX_USERBOT_MESSAGES = int(os.getenv("MAX_USERBOT_MESSAGES", "300"))

def validate_config() -> tuple[bool, str]:
    """Validasi apakah environment variable utama sudah diisi."""
    if not TELEGRAM_BOT_TOKEN:
        return False, "TELEGRAM_BOT_TOKEN belum diatur di file .env!"
    
    if AI_PROVIDER == "gemini" and not GEMINI_API_KEY:
        if not ANTHROPIC_API_KEY and not HERMES_API_KEY and not OPENAI_API_KEY:
            return False, "GEMINI_API_KEY belum diatur di file .env! Dapatkan gratis di https://aistudio.google.com/"
    elif AI_PROVIDER == "openai" and not OPENAI_API_KEY:
        if not GEMINI_API_KEY and not ANTHROPIC_API_KEY and not HERMES_API_KEY:
            return False, "OPENAI_API_KEY belum diatur di file .env!"
    elif AI_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        if not GEMINI_API_KEY and not HERMES_API_KEY and not OPENAI_API_KEY:
            return False, "ANTHROPIC_API_KEY belum diatur di file .env!"
    elif AI_PROVIDER == "hermes" and not HERMES_API_KEY:
        # Jika menggunakan endpoint lokal seperti Ollama (misal http://localhost:11434/v1), API key bisa opsional, tapi untuk OpenRouter wajib
        if "openrouter" in HERMES_BASE_URL.lower() and not HERMES_API_KEY:
            return False, "HERMES_API_KEY belum diatur di file .env untuk OpenRouter!"

    return True, "Config valid."
