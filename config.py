import os
from pathlib import Path
from dotenv import load_dotenv

# Muat file .env jika ada
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

# Token Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Credentials Telegram Client API (UserBot Rahasia Tanpa Bot di Grup)
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "").strip()
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "").strip()
TELEGRAM_STRING_SESSION = os.getenv("TELEGRAM_STRING_SESSION", "").strip()

# Token tambahan untuk Simulator Multi-Bot (dipisahkan koma)
SIMULATOR_BOT_TOKENS_RAW = os.getenv("SIMULATOR_BOT_TOKENS", "").strip()
SIMULATOR_BOT_TOKENS = [t.strip() for t in SIMULATOR_BOT_TOKENS_RAW.split(",") if t.strip()]
if not SIMULATOR_BOT_TOKENS and TELEGRAM_BOT_TOKEN:
    SIMULATOR_BOT_TOKENS = [TELEGRAM_BOT_TOKEN]

# Provider AI: "gemini" (Gratis), "anthropic" (Claude), atau "hermes" (Nous-Hermes via OpenRouter/Ollama)
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()

# Konfigurasi Google Gemini (GRATIS di https://aistudio.google.com/)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()

# Konfigurasi Anthropic Claude
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022").strip()

# Konfigurasi Hermes AI (Nous-Hermes via OpenRouter / Ollama / OpenAI-compatible endpoint)
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "").strip()
HERMES_MODEL = os.getenv("HERMES_MODEL", "nousresearch/hermes-3-llama-3.1-8b:free").strip()
HERMES_BASE_URL = os.getenv("HERMES_BASE_URL", "https://openrouter.ai/api/v1").strip()

# Penyesuaian provider otomatis jika hanya satu key yang diisi dan AI_PROVIDER belum spesifik
if AI_PROVIDER not in ["gemini", "anthropic", "hermes"]:
    AI_PROVIDER = "gemini"

if HERMES_API_KEY and not GEMINI_API_KEY and not ANTHROPIC_API_KEY:
    AI_PROVIDER = "hermes"
elif GEMINI_API_KEY and not ANTHROPIC_API_KEY and not HERMES_API_KEY and AI_PROVIDER != "hermes":
    AI_PROVIDER = "gemini"
elif ANTHROPIC_API_KEY and not GEMINI_API_KEY and not HERMES_API_KEY and AI_PROVIDER != "hermes":
    AI_PROVIDER = "anthropic"

# Konfigurasi ringkasan dan database
DEFAULT_SUMMARY_HOURS = int(os.getenv("DEFAULT_SUMMARY_HOURS", "24"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "chat_history.db").strip()
MAX_MESSAGES_PER_CHUNK = int(os.getenv("MAX_MESSAGES_PER_CHUNK", "300"))

def validate_config() -> tuple[bool, str]:
    """Validasi apakah environment variable utama sudah diisi."""
    if not TELEGRAM_BOT_TOKEN:
        return False, "TELEGRAM_BOT_TOKEN belum diatur di file .env!"
    
    if AI_PROVIDER == "gemini" and not GEMINI_API_KEY:
        if not ANTHROPIC_API_KEY and not HERMES_API_KEY:
            return False, "GEMINI_API_KEY belum diatur di file .env! Dapatkan gratis di https://aistudio.google.com/"
    elif AI_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        if not GEMINI_API_KEY and not HERMES_API_KEY:
            return False, "ANTHROPIC_API_KEY belum diatur di file .env!"
    elif AI_PROVIDER == "hermes" and not HERMES_API_KEY:
        # Jika menggunakan endpoint lokal seperti Ollama (misal http://localhost:11434/v1), API key bisa opsional, tapi untuk OpenRouter wajib
        if "openrouter" in HERMES_BASE_URL.lower() and not HERMES_API_KEY:
            return False, "HERMES_API_KEY belum diatur di file .env untuk OpenRouter!"

    return True, "Config valid."
