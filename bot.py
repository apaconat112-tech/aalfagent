import logging
import re
import socket
from datetime import datetime, timezone, timedelta
from typing import Optional

# Force IPv4 resolution to fix Windows IPv6 unreachable route issues
_original_getaddrinfo = socket.getaddrinfo
def _ipv4_only_getaddrinfo(*args, **kwargs):
    results = _original_getaddrinfo(*args, **kwargs)
    ipv4_results = [r for r in results if r[0] == socket.AF_INET]
    return ipv4_results if ipv4_results else results
socket.getaddrinfo = _ipv4_only_getaddrinfo

from telegram import Update, constants
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from telegram.request import HTTPXRequest

import config
import database
from summarizer import ChatSummarizer
from userbot_summarizer import check_all_quotas

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
        ai_name = f"Google Gemini AI ({config.GEMINI_MODEL})"
    elif config.AI_PROVIDER == "anthropic":
        ai_name = f"Claude ({config.ANTHROPIC_MODEL})"
    else:
        ai_name = f"Nous-Hermes ({config.HERMES_MODEL})"

    text = (
        "👋 *Halo! Saya adalah Telegram AI Assistant & Summarizer Bot (@Nier_12bot).*\n\n"
        f"Saya siap membantu Anda menjawab pertanyaan, mengobrol (*interactive chat*), "
        f"dan merangkum obrolan grup secara otomatis bertenaga AI (*{ai_name}*).\n\n"
        "📌 *FITUR UTAMA:*\n"
        "• *Chat Interaktif*: Kirim pesan langsung di DM untuk bertanya atau berdiskusi dengan AI!\n"
        "• *Ringkasan Grup*: Merangkum topik, keputusan, action items (PIC), dan link penting di grup Telegram.\n"
        "• *Check Kuota AI & List Grup*: Pantau status model AI, sisa kuota (%), dan grup yang dipantau.\n"
        "• *Ringkasan Terjadwal*: Mengirimkan ringkasan berkala secara otomatis di grup.\n\n"
        "🛠 *DAFTAR PERINTAH LENGKAP:*\n"
        "• `/summary` — Meringkas chat grup sejak ringkasan terakhir (atau 24 jam terakhir).\n"
        "• `/summary 3h` — Meringkas pesan 3 jam terakhir (bisa juga `6h`, `12h`, `2d`, dll).\n"
        "• `/grup` atau `/groups` — Menampilkan daftar grup Telegram yang dipantau bot.\n"
        "• `/model` — Cek status provider AI aktif, sisa kuota (%), atau ganti model (`/model hermes`, `/model gemini`, `/model claude`).\n"
        "• `/schedule <jam>` — Aktifkan ringkasan terjadwal tiap X jam (contoh: `/schedule 6`).\n"
        "• `/unschedule` — Matikan ringkasan terjadwal di grup ini.\n"
        "• `/help` — Menampilkan pesan panduan lengkap ini.\n\n"
        "💡 *Tips Chat:* Di chat grup, sebut nama bot (`@username`) atau reply pesan bot untuk bertanya langsung!"
    )
    if update.effective_message:
        try:
            await update.effective_message.reply_text(
                text,
                parse_mode=constants.ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.warning("Markdown reply_text failed: %s", e)
            await update.effective_message.reply_text(text)

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
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
        except Exception as e:
            logger.warning("Gagal mengirim send_chat_action: %s", e)
        
        # Bersihkan text dari mention @botname jika ada
        user_text = msg.text
        if bot_username:
            user_text = re.sub(rf"@{re.escape(bot_username)}", "", user_text, flags=re.IGNORECASE).strip()

        if not user_text:
            user_text = "Halo!"

        # Permintaan bahasa yang membalas pesan bot berarti menerjemahkan pesan tersebut.
        language_request = re.fullmatch(
            r"(?:bahasa\s+)?(?:indonesia|inggris|english|indonesian)",
            user_text.strip(),
            flags=re.IGNORECASE
        )
        replied_text = (
            msg.reply_to_message.text
            if msg.reply_to_message and msg.reply_to_message.text
            else ""
        )
        if language_request and replied_text:
            target_language = "Bahasa Indonesia" if language_request.group(0).lower() not in {"inggris", "english"} else "Bahasa Inggris"
            reply_text = await summarizer.translate_text(
                text=replied_text,
                target_language=target_language
            )
        else:
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

async def perform_private_userbot_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, raw_input: str, reply_to_id: int) -> None:
    """Membaca pesan grup via Telethon dan mengirimkan ringkasan langsung di DM Bot."""
    from userbot_summarizer import get_telethon_client, parse_timeframe_and_group, find_telegram_group
    from telethon.tl.types import User

    timeframe_delta, target_group = parse_timeframe_and_group(raw_input)
    if not target_group:
        target_group = raw_input

    status_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"⏳ _Sedang membaca obrolan grup *{target_group}* & merangkum dengan AI..._",
        parse_mode=constants.ParseMode.MARKDOWN,
        reply_to_message_id=reply_to_id
    )

    try:
        client = await get_telethon_client()
        try:
            target_entity = await find_telegram_group(client, target_group)

            if not target_entity:
                await status_msg.edit_text(f"❌ Grup '{target_group}' tidak ditemukan pada akun Telegram Anda.")
                return

            group_title = getattr(target_entity, "title", target_group)
            now_utc = datetime.now(timezone.utc)
            cutoff = (now_utc - timeframe_delta) if timeframe_delta else None

            formatted_messages = []
            async for msg in client.iter_messages(target_entity, limit=1000):
                if not msg.text or not msg.text.strip():
                    continue
                msg_date = msg.date.astimezone(timezone.utc) if msg.date else now_utc
                if cutoff and msg_date < cutoff:
                    continue

                sender = msg.sender or getattr(msg, "sender", None)
                if isinstance(sender, User):
                    full_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip() or sender.username or f"User_{sender.id}"
                    username = sender.username
                    user_id = sender.id
                else:
                    full_name = getattr(sender, "title", None) or f"User_{msg.sender_id}"
                    username = getattr(sender, "username", None)
                    user_id = msg.sender_id

                formatted_messages.append({
                    "message_id": msg.id,
                    "user_id": user_id,
                    "username": username,
                    "full_name": full_name,
                    "text": msg.text,
                    "timestamp": msg_date.isoformat(),
                    "dt_obj": msg_date
                })

            formatted_messages.reverse()

            if not formatted_messages:
                await status_msg.edit_text(f"ℹ️ Belum ada pesan obrolan baru di grup *{group_title}*.", parse_mode=constants.ParseMode.MARKDOWN)
                return

            tf_info = f"{int(timeframe_delta.total_seconds() // 3600)} jam terakhir" if timeframe_delta else f"{len(formatted_messages)} pesan terbaru"
            summary_result = await summarizer.summarize_messages(formatted_messages, timeframe_info=tf_info)

            try:
                await status_msg.delete()
            except Exception:
                pass

            full_msg = f"🤫 *RINGKASAN RAHASIA GRUP: {group_title}*\n\n{summary_result}"
            await send_split_message(update.effective_chat.id, full_msg, context, reply_to_id=reply_to_id)

        finally:
            await client.disconnect()

    except Exception as e:
        logger.exception("Private userbot summary error: %s", e)
        await status_msg.edit_text(f"❌ Gagal merangkum grup: {str(e)}")

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler perintah manual /summary [waktu/grup]."""
    if not update.effective_message or not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    reply_to_id = update.effective_message.message_id
    
    # Jika diketik di DM Bot dengan argumen nama grup
    if update.effective_chat.type == constants.ChatType.PRIVATE and context.args and config.TELEGRAM_STRING_SESSION:
        raw_input = " ".join(context.args)
        await perform_private_userbot_summary(update, context, raw_input, reply_to_id)
        return

    delta = parse_timeframe_args(context.args) if context.args else None
    await perform_summary(chat_id, context, hours_delta=delta, reply_to_id=reply_to_id)

async def grup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler perintah /grup dan /groups untuk menampilkan daftar grup."""
    if not update.effective_message or not update.effective_chat:
        return

    # Jika diketik di DM Bot, tampilkan daftar grup akun pengguna via Telethon
    if update.effective_chat.type == constants.ChatType.PRIVATE and config.TELEGRAM_STRING_SESSION:
        try:
            from userbot_summarizer import get_telethon_client
            client = await get_telethon_client()
            try:
                msg_lines = ["📋 *DAFTAR SELURUH GRUP TELEGRAM ANDA:*\n"]
                async for dialog in client.iter_dialogs():
                    if dialog.is_group or dialog.is_channel:
                        msg_lines.append(f"• `{dialog.name}`")
                if len(msg_lines) > 1:
                    await send_split_message(update.effective_chat.id, "\n".join(msg_lines), context, reply_to_id=update.effective_message.message_id)
                    return
            finally:
                await client.disconnect()
        except Exception as e:
            logger.warning("Failed to fetch user groups via Telethon in DM: %s", e)
    
    tracked_chat_ids = await database.get_all_tracked_chats()
    if not tracked_chat_ids:
        await update.effective_message.reply_text(
            "ℹ️ Belum ada obrolan grup yang tersimpan di database.",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return

    msg_lines = ["📋 *DAFTAR GRUP TELEGRAM YANG DIPANTAU BOT:*\n"]
    count = 0
    for cid in tracked_chat_ids:
        try:
            chat = await context.bot.get_chat(cid)
            if chat.type in [constants.ChatType.GROUP, constants.ChatType.SUPERGROUP, constants.ChatType.CHANNEL]:
                title = chat.title or f"Grup_{cid}"
                msg_lines.append(f"• *{title}* (`ID: {cid}`)")
                count += 1
        except Exception:
            pass

    if count == 0:
        await update.effective_message.reply_text(
            "ℹ️ Belum ada obrolan grup publik/terlacak yang aktif saat ini.",
            parse_mode=constants.ParseMode.MARKDOWN
        )
        return

    await send_split_message(update.effective_chat.id, "\n".join(msg_lines), context, reply_to_id=update.effective_message.message_id)

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler perintah /model untuk cek sisa kuota (%) & ganti provider/model AI."""
    if not update.effective_message:
        return
    
    if context.args:
        arg = context.args[0].lower()
        if arg in ["gemini", "hermes", "claude", "anthropic"]:
            target_prov = "anthropic" if arg == "claude" else arg
            config.AI_PROVIDER = target_prov
            mod_name = config.HERMES_MODEL if target_prov == "hermes" else (config.GEMINI_MODEL if target_prov == "gemini" else config.ANTHROPIC_MODEL)
            await update.effective_message.reply_text(
                f"✅ *Provider AI berhasil diubah ke: {target_prov.upper()}* (`{mod_name}`)",
                parse_mode=constants.ParseMode.MARKDOWN
            )
            return

    cur_prov = config.AI_PROVIDER.upper()
    cur_mod = config.HERMES_MODEL if config.AI_PROVIDER == "hermes" else (config.GEMINI_MODEL if config.AI_PROVIDER == "gemini" else config.ANTHROPIC_MODEL)
    
    quota_status = await check_all_quotas()

    msg = (
        f"🤖 *STATUS & PENGATURAN MODEL AI:*\n\n"
        f"• Provider Utama Aktif: *{cur_prov}*\n"
        f"• Model Spesifik: `{cur_mod}`\n\n"
        f"{quota_status}\n\n"
        "⚙️ *Cara Ganti Provider AI:*\n"
        "• `/model hermes` — Ganti ke Nous-Hermes (Gratis / OpenRouter)\n"
        "• `/model gemini` — Ganti ke Google Gemini AI (Gratis)\n"
        "• `/model claude` — Ganti ke Anthropic Claude"
    )
    await update.effective_message.reply_text(
        msg,
        parse_mode=constants.ParseMode.MARKDOWN
    )

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

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Error yang disebabkan oleh Update."""
    logger.error("Exception saat memproses update %s: %s", update, context.error, exc_info=context.error)

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
    
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0, pool_timeout=30.0)
    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).request(request).post_init(post_init).build()
    app.add_error_handler(error_handler)

    # Daftarkan handler perintah
    app.add_handler(CommandHandler(["start", "help"], start_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler(["grup", "groups"], grup_command))
    app.add_handler(CommandHandler(["model", "models"], model_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("unschedule", unschedule_command))

    # Daftarkan handler pesan teks untuk logging histori
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_logger))

    # Jalankan polling bot dengan retries otomatis jika ada masalah jaringan sementara
    app.run_polling(bootstrap_retries=-1, drop_pending_updates=False)

if __name__ == "__main__":
    main()
