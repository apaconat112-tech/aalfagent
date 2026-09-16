import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from telegram import Update, constants
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

import config
import database
from summarizer import ChatSummarizer

# Konfigurasi Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Inisialisasi Summarizer
summarizer = ChatSummarizer()

def parse_timeframe_args(args: list[str]) -> Optional[timedelta]:
    """Parse argumen waktu seperti '6h', '24h', '3d', atau '12' (default jam)."""
    if not args:
        return None
    raw = args[0].strip().lower()
    
    # Format misal '6h' atau '6'
    match_h = re.match(r"^(\d+)(h|jam)?$", raw)
    if match_h:
        return timedelta(hours=int(match_h.group(1)))
        
    # Format misal '2d' atau '2hari'
    match_d = re.match(r"^(\d+)(d|hari)$", raw)
    if match_d:
        return timedelta(days=int(match_d.group(1)))
        
    return None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler untuk perintah /start dan /help."""
    if config.AI_PROVIDER == "gemini":
        ai_name = "Google Gemini AI"
    elif config.AI_PROVIDER == "anthropic":
        ai_name = f"Claude ({config.ANTHROPIC_MODEL})"
    else:
        ai_name = f"Nous-Hermes ({config.HERMES_MODEL})"

    text = (
        "👋 *Halo! Saya adalah Telegram AI Assistant & Summarizer Bot.*\n\n"
        f"Saya siap membantu Anda menjawab pertanyaan, mengobrol (*interactive chat*), "
        f"dan merangkum obrolan grup secara otomatis bertenaga AI (*{ai_name}*).\n\n"
        "📌 *Fitur Utama:*\n"
        "• *Chat Interaktif*: Kirim pesan langsung di sini untuk mengobrol atau bertanya kepada AI!\n"
        "• *Ringkasan Grup*: Merangkum topik, keputusan, action items (PIC), dan link penting di grup Telegram.\n"
        "• *Ringkasan Terjadwal*: Mengirimkan ringkasan berkala secara otomatis di grup.\n\n"
        "🛠 *Daftar Perintah:*\n"
        "• `/summary` — Meringkas chat grup sejak ringkasan terakhir (atau 24 jam terakhir).\n"
        "• `/summary 6h` — Meringkas pesan 6 jam terakhir (bisa juga `12h`, `2d`, dll).\n"
        "• `/schedule <jam>` — Aktifkan ringkasan terjadwal tiap X jam (contoh: `/schedule 6`).\n"
        "• `/unschedule` — Matikan ringkasan terjadwal di grup ini.\n"
        "• `/help` — Menampilkan pesan bantuan ini.\n\n"
        "💡 *Tips Chat:* Di chat grup, sebut nama bot (`@username`) atau reply pesan bot untuk bertanya langsung!"
    )
    if update.effective_message:
        await update.effective_message.reply_text(
            text,
            parse_mode=constants.ParseMode.MARKDOWN
        )

async def message_logger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menyimpan pesan ke DB dan membalas obrolan secara interaktif (DM atau saat di-mention/reply di grup)."""
    msg = update.effective_message
    if not msg or not msg.text or not update.effective_chat:
        return

    chat = update.effective_chat
    chat_id = chat.id
    user = update.effective_user

    user_id = user.id if user else None
    username = user.username if user else None
    full_name = user.full_name if user else None

    # Menggunakan date dari message Telegram (UTC)
    timestamp = msg.date if msg.date else datetime.now(timezone.utc)

    # 1. Simpan setiap pesan teks masuk ke database SQLite
    await database.save_message(
        chat_id=chat_id,
        message_id=msg.message_id,
        user_id=user_id,
        username=username,
        full_name=full_name,
        text=msg.text,
        timestamp=timestamp
    )

    # 2. Cek apakah ini chat pribadi (DM) atau bot di-mention / di-reply di grup
    is_private = (chat.type == constants.ChatType.PRIVATE)
    bot_username = context.bot.username if context.bot else ""
    is_mentioned = bool(bot_username and f"@{bot_username.lower()}" in msg.text.lower())
    is_reply_to_bot = bool(
        msg.reply_to_message 
        and msg.reply_to_message.from_user 
        and msg.reply_to_message.from_user.id == context.bot.id
    )

    if is_private or is_mentioned or is_reply_to_bot:
        # Kirim status typing
        await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
        
        # Bersihkan text dari mention @botname jika ada
        user_text = msg.text
        if bot_username:
            user_text = re.sub(rf"@{re.escape(bot_username)}", "", user_text, flags=re.IGNORECASE).strip()

        if not user_text:
            user_text = "Halo!"

        reply_text = await summarizer.chat_reply(user_message=user_text)
        await send_split_message(chat_id, reply_text, context, reply_to_id=msg.message_id)

async def send_split_message(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE, reply_to_id: Optional[int] = None) -> None:
    """Mengirim pesan panjang dengan membaginya jika melebihi batas 4000 karakter Telegram."""
    max_len = 4000
    if len(text) <= max_len:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_to_message_id=reply_to_id
            )
        except Exception:
            # Fallback jika entity Markdown gagal di-parse oleh Telegram
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_to_message_id=reply_to_id
            )
        return

    # Split per paragraf/newline
    parts = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > max_len:
            parts.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        parts.append(current)

    for part in parts:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=part,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text=part
            )

async def perform_summary(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    hours_delta: Optional[timedelta] = None,
    reply_to_id: Optional[int] = None
) -> None:
    """Logika inti untuk mengambil chat, memanggil Claude, dan mengirim hasil ringkasan."""
    now = datetime.now(timezone.utc)
    
    if hours_delta:
        since_time = now - hours_delta
        timeframe_label = f"{int(hours_delta.total_seconds() // 3600)} jam terakhir"
    else:
        last_summary = await database.get_last_summary_time(chat_id)
        if last_summary:
            since_time = last_summary
            diff_hours = max(1, int((now - last_summary).total_seconds() // 3600))
            timeframe_label = f"sejak ringkasan terakhir ({diff_hours} jam lalu)"
        else:
            since_time = now - timedelta(hours=config.DEFAULT_SUMMARY_HOURS)
            timeframe_label = f"{config.DEFAULT_SUMMARY_HOURS} jam terakhir (default)"

    # Ambil pesan dari DB
    messages = await database.get_messages_since(chat_id, since_time)
    
    if not messages:
        msg_text = f"ℹ️ Belum ada pesan obrolan baru yang tersimpan untuk periode {timeframe_label}."
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg_text,
                parse_mode=constants.ParseMode.MARKDOWN,
                reply_to_message_id=reply_to_id
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg_text,
                reply_to_message_id=reply_to_id
            )
        return

    # Kirim status typing
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    if config.AI_PROVIDER == "gemini":
        ai_provider_name = "Gemini AI"
    elif config.AI_PROVIDER == "anthropic":
        ai_provider_name = "Claude AI"
    else:
        ai_provider_name = "Hermes AI"

    loading_text = f"🤖 _Sedang membaca {len(messages)} pesan & merangkum dengan {ai_provider_name}..._"
    try:
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=loading_text,
            parse_mode=constants.ParseMode.MARKDOWN,
            reply_to_message_id=reply_to_id
        )
    except Exception:
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🤖 Sedang membaca {len(messages)} pesan & merangkum dengan {ai_provider_name}...",
            reply_to_message_id=reply_to_id
        )

    try:
        summary_result = await summarizer.summarize_messages(messages, timeframe_info=timeframe_label)
        # Perbarui last summary timestamp
        await database.update_last_summary_time(chat_id, now)
        
        # Hapus pesan status loading
        try:
            await status_msg.delete()
        except Exception:
            pass

        # Kirim ringkasan
        await send_split_message(chat_id, summary_result, context, reply_to_id=reply_to_id)
    except Exception as e:
        logger.exception("Gagal menghasilkan ringkasan untuk chat %s: %s", chat_id, e)
        await status_msg.edit_text(
            f"❌ Terjadi kesalahan saat membuat ringkasan: {str(e)}",
            parse_mode=constants.ParseMode.MARKDOWN
        )

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler perintah manual /summary [waktu]."""
    chat_id = update.effective_chat.id
    reply_to_id = update.effective_message.message_id
    
    # Cek apakah user menambahkan argumen waktu
    delta = parse_timeframe_args(context.args) if context.args else None
    await perform_summary(chat_id, context, hours_delta=delta, reply_to_id=reply_to_id)

async def scheduled_job_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback yang dipanggil secara otomatis oleh JobQueue untuk ringkasan berkala."""
    if not context.job:
        return
    chat_id = context.job.chat_id
    if not chat_id:
        return
    logger.info("Executing scheduled summary for chat_id: %s", chat_id)
    await perform_summary(chat_id, context)

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler perintah /schedule <jam> untuk mengatur jadwal ringkasan otomatis."""
    if not update.effective_chat or not update.effective_message:
        return
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.effective_message.reply_text(
            "⚠️ Format salah. Gunakan: `/schedule <jumlah_jam>`\nContoh: `/schedule 6` (meringkas tiap 6 jam)",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return

    try:
        hours = int(context.args[0])
        if hours < 1 or hours > 168:
            await update.effective_message.reply_text(
                "⚠️ Interval waktu harus di antara 1 sampai 168 jam (7 hari).",
                parse_mode=constants.ParseMode.MARKDOWN
            )
            return
    except ValueError:
        await update.effective_message.reply_text(
            "⚠️ Harap masukkan angka yang valid untuk jam. Contoh: `/schedule 4`",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return

    # Simpan preferensi ke DB
    await database.set_chat_schedule(chat_id, hours)

    # Hapus job lama jika ada
    job_name = f"summary_job_{chat_id}"
    if context.job_queue:
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        for job in current_jobs:
            job.schedule_removal()

        # Tambahkan job baru ke queue
        interval_seconds = hours * 3600
        context.job_queue.run_repeating(
            callback=scheduled_job_callback,
            interval=interval_seconds,
            first=interval_seconds,
            chat_id=chat_id,
            name=job_name
        )

    await update.effective_message.reply_text(
        f"✅ *Ringkasan terjadwal berhasil diaktifkan!*\n"
        f"Bot akan otomatis mengirim ringkasan obrolan setiap *{hours} jam* sekali.",
        parse_mode=constants.ParseMode.MARKDOWN
    )

async def unschedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler perintah /unschedule untuk mematikan jadwal otomatis."""
    if not update.effective_chat or not update.effective_message:
        return
    chat_id = update.effective_chat.id
    
    # Update DB
    await database.set_chat_schedule(chat_id, 0)

    # Hapus dari JobQueue
    job_name = f"summary_job_{chat_id}"
    if context.job_queue:
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        if current_jobs:
            for job in current_jobs:
                job.schedule_removal()
            await update.effective_message.reply_text(
                "🛑 *Ringkasan terjadwal telah dimatikan.* Anda tetap bisa menggunakan `/summary` secara manual kapan saja.",
                parse_mode=constants.ParseMode.MARKDOWN
            )
            return

    await update.effective_message.reply_text(
        "ℹ️ Grup ini belum memiliki jadwal ringkasan aktif.",
        parse_mode=constants.ParseMode.MARKDOWN
    )

async def cleanup_job_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job harian untuk membersihkan chat yang lebih dari 30 hari."""
    deleted = await database.cleanup_old_messages(days=30)
    logger.info("Daily database cleanup finished: %d old messages removed.", deleted)

async def post_init(application) -> None:
    """Inisialisasi database dan restore semua jadwal aktif saat bot menyala."""
    logger.info("Initializing database...")
    await database.init_db()

    # Restore schedules from database
    schedules = await database.get_all_active_schedules()
    logger.info("Restoring %d active schedules...", len(schedules))
    for item in schedules:
        chat_id = item["chat_id"]
        hours = item["schedule_hours"]
        job_name = f"summary_job_{chat_id}"
        interval_seconds = hours * 3600
        application.job_queue.run_repeating(
            callback=scheduled_job_callback,
            interval=interval_seconds,
            first=interval_seconds,
            chat_id=chat_id,
            name=job_name
        )

    # Jadwalkan pembersihan DB harian (setiap 24 jam)
    application.job_queue.run_repeating(
        callback=cleanup_job_callback,
        interval=86400,
        first=86400,
        name="daily_db_cleanup"
    )

def main() -> None:
    """Entry point utama untuk menjalankan Telegram Bot."""
    is_valid, err_msg = config.validate_config()
    if not is_valid:
        logger.error("Konfigurasi tidak lengkap: %s", err_msg)
        print(f"\n[ERROR] {err_msg}")
        print("Pastikan Anda telah menyalin .env.example menjadi .env dan mengisi API token yang sesuai.\n")
        return

    if config.AI_PROVIDER == "gemini":
        active_model = config.GEMINI_MODEL
    elif config.AI_PROVIDER == "anthropic":
        active_model = config.ANTHROPIC_MODEL
    else:
        active_model = config.HERMES_MODEL

    logger.info("Starting Chat Summarizer Bot with provider: %s (%s)", config.AI_PROVIDER, active_model)
    
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # Daftarkan handler perintah
    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("unschedule", unschedule_command))

    # Daftarkan handler pesan teks untuk logging histori
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_logger))

    # Jalankan polling bot dengan retries otomatis jika ada masalah jaringan sementara
    app.run_polling(bootstrap_retries=-1, drop_pending_updates=True)

if __name__ == "__main__":
    main()
