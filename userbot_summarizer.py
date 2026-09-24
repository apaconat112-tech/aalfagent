import argparse
import asyncio
import logging
import re
import socket
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

# Force IPv4 resolution to fix Windows IPv6 unreachable route issues
_original_getaddrinfo = socket.getaddrinfo
def _ipv4_only_getaddrinfo(*args, **kwargs):
    results = _original_getaddrinfo(*args, **kwargs)
    ipv4_results = [r for r in results if r[0] == socket.AF_INET]
    return ipv4_results if ipv4_results else results
socket.getaddrinfo = _ipv4_only_getaddrinfo

# UTF-8 output encoding for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import httpx
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User

import config
import database
from summarizer import ChatSummarizer, format_messages_transcript

# Konfigurasi Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("userbot_summarizer")

# Path file sesi login Telethon
SESSION_NAME = "userbot_session"

async def get_telethon_client() -> TelegramClient:
    """Inisialisasi & login Telethon Client (Mendukung StringSession atau File Session)."""
    api_id_str = config.TELEGRAM_API_ID
    api_hash = config.TELEGRAM_API_HASH

    if not api_id_str or not api_hash:
        print("\n❌ ERROR: TELEGRAM_API_ID dan TELEGRAM_API_HASH belum diatur di file .env!")
        sys.exit(1)

    try:
        api_id = int(api_id_str)
    except ValueError:
        print(f"❌ TELEGRAM_API_ID harus berupa angka (diterima: '{api_id_str}')!")
        sys.exit(1)

    if config.TELEGRAM_STRING_SESSION:
        client = TelegramClient(StringSession(config.TELEGRAM_STRING_SESSION), api_id, api_hash, receive_updates=False)
        await client.connect()
        return client

    if not client or not await client.is_user_authorized():
        print("\n🔐 Login Pertama Kali Telegram UserBot:")
        phone = input("Masukkan Nomor HP Telegram Anda (contoh: +628123456789): ").strip()
        await client.send_code_request(phone)
        code = input("Masukkan Kode OTP dari Telegram: ").strip()
        try:
            await client.sign_in(phone, code)
        except Exception as e:
            if "2FA" in str(e) or "Password" in str(e):
                pwd = input("Masukkan Password 2FA (Verifikasi 2 Langkah) Anda: ").strip()
                await client.sign_in(password=pwd)
            else:
                raise e
        print("✅ Login Berhasil! Sesi disimpan di 'userbot_session.session'.\n")

    return client

def parse_timeframe_and_group(raw_target: str) -> tuple[Optional[timedelta], str]:
    """Parse timeframe (seperti '3h', '3jam', '2d', '2hari', '3') dan nama/ID grup secara akurat."""
    if not raw_target or not raw_target.strip():
        return None, ""

    sub_words = raw_target.strip().split()
    group_words = []
    timeframe_delta = None

    for idx, w in enumerate(sub_words):
        w_lower = w.lower()

        # 1. Format eksplisit dengan satuan (3h, 3jam, 2d, 2hari)
        m_h = re.match(r"^(\d+)(h|jam)$", w_lower)
        m_d = re.match(r"^(\d+)(d|hari)$", w_lower)

        if m_h and not timeframe_delta:
            timeframe_delta = timedelta(hours=int(m_h.group(1)))
        elif m_d and not timeframe_delta:
            timeframe_delta = timedelta(days=int(m_d.group(1)))
        # 2. Dua kata terpisah ("3 jam", "3 h", "2 hari", "2 d")
        elif w_lower in ["jam", "h"] and group_words and group_words[-1].isdigit() and not timeframe_delta:
            val = int(group_words.pop())
            timeframe_delta = timedelta(hours=val)
        elif w_lower in ["hari", "d"] and group_words and group_words[-1].isdigit() and not timeframe_delta:
            val = int(group_words.pop())
            timeframe_delta = timedelta(days=val)
        # 3. Angka murni di akhir argumen multi-kata (misal ".sum Nama Grup 3")
        elif w_lower.isdigit() and group_words and idx == len(sub_words) - 1 and not timeframe_delta:
            timeframe_delta = timedelta(hours=int(w_lower))
        else:
            group_words.append(w)

    target_group = " ".join(group_words).strip()
    return timeframe_delta, target_group

async def find_telegram_group(client: TelegramClient, target_group: str) -> Any:
    """Cari entitas Telegram berdasarkan ID numerik, nama persis, atau kata kunci nama grup."""
    if not target_group:
        return None

    # Try 1: Telethon get_entity (jika ID numerik atau username/link)
    try:
        target_id = int(target_group)
        try:
            return await client.get_entity(target_id)
        except Exception:
            pass
    except ValueError:
        pass

    # Try 2: Iterasi dialogs (mencari berdasarkan ID numerik atau Nama Grup)
    async for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            d_id = str(getattr(dialog.entity, "id", ""))
            d_dialog_id = str(getattr(dialog, "id", ""))

            # Cocokkan ID (baik positive maupun negative)
            if target_group in (d_id, d_dialog_id, f"-100{d_id}"):
                return dialog.entity

            # Cocokkan Nama/Title Grup
            if target_group.lower() in dialog.name.lower():
                return dialog.entity

    return None

async def list_user_groups() -> None:
    """Menampilkan daftar semua grup Telegram yang Anda ikuti."""
    client = await get_telethon_client()
    try:
        print("\n📋 Daftar Grup Telegram yang Anda ikuti:")
        print("---------------------------------------------------------")
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                entity = dialog.entity
                chat_id = dialog.id
                title = dialog.name
                print(f"  • ID: {chat_id:<16} | Title: {title}")
        print("---------------------------------------------------------\n")
    finally:
        await client.disconnect()

async def send_long_message(client: TelegramClient, entity: str, text: str) -> None:
    """Membagi pesan panjang menjadi beberapa bagian max 3800 karakter untuk Telegram."""
    MAX_LEN = 3800
    if len(text) <= MAX_LEN:
        try:
            await client.send_message(entity, text, parse_mode="Markdown")
        except Exception:
            await client.send_message(entity, text)
        return

    chunks = []
    current_chunk = ""
    for line in text.split("\n"):
        if len(current_chunk) + len(line) + 1 > MAX_LEN:
            chunks.append(current_chunk)
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"
    if current_chunk.strip():
        chunks.append(current_chunk)

    for idx, chunk in enumerate(chunks, 1):
        chunk_header = f"*(Bagian {idx}/{len(chunks)})*\n" if len(chunks) > 1 else ""
        send_text = f"{chunk_header}{chunk}"
        try:
            await client.send_message(entity, send_text, parse_mode="Markdown")
        except Exception:
            await client.send_message(entity, send_text)
        await asyncio.sleep(1)

async def summarize_group_silently(
    target_group: str,
    limit_messages: int = 1000,
    hours: int = 0,
    send_to_me: bool = True
) -> None:
    """Membaca isi chat grup secara rahasia dan meringkasnya dengan AI."""
    client = await get_telethon_client()
    try:
        # Cari entitas grup berdasarkan ID atau Nama
        target_entity = await find_telegram_group(client, target_group)

        if not target_entity:
            print(f"\n❌ Grup '{target_group}' tidak ditemukan!")
            print("Gunakan perintah 'python userbot_summarizer.py --list-groups' untuk melihat daftar grup Anda.\n")
            return

        group_title = getattr(target_entity, "title", str(target_group))
        group_id = target_entity.id
        print(f"\n🕵️‍♂️ Membaca hingga {limit_messages} obrolan terbaru di grup '{group_title}' secara RAHASIA...")

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours) if hours > 0 else None
        formatted_messages: List[Dict[str, Any]] = []

        user_cache: Dict[int, Any] = {}

        # Ambil histori pesan dari grup
        async for msg in client.iter_messages(target_entity, limit=limit_messages):
            if not msg.text or not msg.text.strip():
                continue
            
            msg_date = msg.date.astimezone(timezone.utc) if msg.date else datetime.now(timezone.utc)
            if cutoff_time and msg_date < cutoff_time:
                continue

            sender_id = msg.sender_id
            if sender_id and sender_id in user_cache:
                sender = user_cache[sender_id]
            else:
                sender = msg.sender or getattr(msg, "sender", None)
                if sender_id:
                    user_cache[sender_id] = sender

            if isinstance(sender, User):
                full_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip() or sender.username or f"User_{sender.id}"
                username = sender.username
                user_id = sender.id
            else:
                full_name = getattr(sender, "title", None) or f"User_{sender_id}"
                username = getattr(sender, "username", None)
                user_id = sender_id

            formatted_messages.append({
                "message_id": msg.id,
                "user_id": user_id,
                "username": username,
                "full_name": full_name,
                "text": msg.text,
                "timestamp": msg_date.isoformat(),
                "dt_obj": msg_date
            })

        # Urutkan kronologis
        formatted_messages.reverse()

        if not formatted_messages:
            time_str = f"{hours} jam terakhir" if hours > 0 else "terbaru"
            print(f"ℹ️ Tidak ditemukan pesan baru dalam periode {time_str} di grup '{group_title}'.\n")
            return

        # Simpan ke DB lokal setelah iterasi Telethon selesai (mencegah DB lock)
        for item in formatted_messages:
            try:
                await database.save_message(
                    chat_id=group_id,
                    message_id=item["message_id"],
                    user_id=item["user_id"],
                    username=item["username"],
                    full_name=item["full_name"],
                    text=item["text"],
                    timestamp=item["dt_obj"]
                )
            except Exception:
                pass

        print(f"🤖 Memproses {len(formatted_messages)} pesan dengan AI Summarizer ({config.AI_PROVIDER.upper()})...\n")

        summarizer = ChatSummarizer()
        timeframe_info = f"{hours} jam terakhir ({len(formatted_messages)} pesan)" if hours > 0 else f"{len(formatted_messages)} pesan terbaru"
        try:
            summary_result = await summarizer.summarize_messages(formatted_messages, timeframe_info=timeframe_info)
        except Exception as e:
            summary_result = f"❌ Terjadi kesalahan saat memproses ringkasan: {str(e)}"

        print("=========================================================")
        print(f"📊 RINGKASAN RAHASIA GRUP: {group_title}")
        print("=========================================================")
        print(summary_result)
        print("=========================================================\n")

        # Kirim hasil ringkasan ke Telegram "Saved Messages" (Pesan Tersimpan) Anda sendiri
        if send_to_me:
            header = f"🤫 *RINGKASAN RAHASIA GRUP: {group_title}*\n"
            full_msg = f"{header}\n{summary_result}"
            await send_long_message(client, "me", full_msg)
            print("✅ Ringkasan telah dikirimkan secara RAHASIA ke 'Saved Messages' (Pesan Tersimpan) Telegram Anda!\n")

    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

async def check_all_quotas() -> str:
    """Mengecek sisa kuota & status live untuk semua provider AI."""
    lines = ["📊 *STATUS & SISA KUOTA AI:*"]
    
    # 1. OpenRouter (Hermes)
    if config.HERMES_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                r = await http_client.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={"Authorization": f"Bearer {config.HERMES_API_KEY}"}
                )
                if r.status_code == 200:
                    data = r.json().get("data", {})
                    free_info = data.get("free_model_daily_requests")
                    if free_info and isinstance(free_info, dict):
                        limit = free_info.get("limit", 50)
                        rem = free_info.get("remaining", 50)
                        used = free_info.get("used", 0)
                        pct = int((rem / limit) * 100) if limit > 0 else 100
                        lines.append(f"• *OpenRouter*: Sisa *{pct}%* (`{rem}/{limit}` req | Terpakai: {used})")
                    else:
                        usage = data.get("usage", 0)
                        lines.append(f"• *OpenRouter*: Aktif (Penggunaan: ${usage:.4f})")
                else:
                    lines.append("• *OpenRouter*: Key Valid")
        except Exception:
            lines.append("• *OpenRouter*: Key Valid")
    else:
        lines.append("• *OpenRouter*: Key Belum Diisi")

    # 2. Google Gemini
    if config.GEMINI_API_KEY:
        lines.append(f"• *Google Gemini*: Aktif (`{config.GEMINI_MODEL}`)")
    else:
        lines.append("• *Google Gemini*: Key Belum Diisi")

    # 3. OpenAI GPT
    if config.OPENAI_API_KEY:
        lines.append(f"• *OpenAI GPT*: Aktif (`{config.OPENAI_MODEL}`)")
    else:
        lines.append("• *OpenAI GPT*: Key Belum Diisi")

    # 4. Anthropic Claude
    if config.ANTHROPIC_API_KEY:
        lines.append(f"• *Anthropic Claude*: Aktif (`{config.ANTHROPIC_MODEL}`)")
    else:
        lines.append("• *Anthropic Claude*: Key Belum Diisi")

    return "\n".join(lines)

async def start_single_userbot(session_str: str, account_index: int = 1, total_accounts: int = 1) -> None:
    """Jalankan 1 instance Telethon Userbot secara independen untuk StringSession tertentu."""
    api_id = int(config.TELEGRAM_API_ID)
    api_hash = config.TELEGRAM_API_HASH
    
    session_obj = StringSession(session_str) if session_str else SESSION_NAME
    client = TelegramClient(session_obj, api_id, api_hash, receive_updates=True)
    await client.start()  # type: ignore

    try:
        me = await client.get_me()
        user_name = me.first_name or "Sobat"
        user_display = f"{me.first_name or ''} {me.last_name or ''}".strip() or me.username or f"User_{me.id}"
    except Exception:
        user_name = "Sobat"
    logger.info("Userbot [%d/%d] Terhubung: %s", account_index, total_accounts, user_display)

    @client.on(events.NewMessage)
    async def handler(event):
        if not event.out and getattr(event, "sender_id", None) != me.id:
            return

        # Abaikan pesan jika diketik di dalam chat room Bot Nier (karena bot.py yang membalas!)
        if config.TELEGRAM_BOT_TOKEN and ":" in config.TELEGRAM_BOT_TOKEN:
            try:
                bot_user_id = int(config.TELEGRAM_BOT_TOKEN.split(":")[0])
                if event.chat_id == bot_user_id:
                    return
            except Exception:
                pass

        text = event.text.strip() if event.text else ""
        if not text:
            return

        dest = event.chat_id if event.chat_id else "me"

        # ---------------------------------------------------------
        # Perintah .model: Cek Kuota % & Ganti Model AI (khusus UserBot)
        # ---------------------------------------------------------
        if text.startswith(".model"):
            parts = text.split(maxsplit=1)
            if len(parts) == 1:
                cur_prov = config.AI_PROVIDER.upper()
                if config.AI_PROVIDER == "openai":
                    cur_mod = config.OPENAI_MODEL
                elif config.AI_PROVIDER == "hermes":
                    cur_mod = config.HERMES_MODEL
                elif config.AI_PROVIDER == "anthropic":
                    cur_mod = config.ANTHROPIC_MODEL
                else:
                    cur_mod = config.GEMINI_MODEL
                
                quota_status = await check_all_quotas()

                msg = (
                    f"Halo {user_name}! Berikut status model AI yang sedang kita gunakan:\n\n"
                    f"🤖 *STATUS MODEL AI:*\n"
                    f"• Provider Utama: *{cur_prov}*\n"
                    f"• Model Aktif: `{cur_mod}`\n\n"
                    f"{quota_status}\n\n"
                    f"💡 *GANTI MODEL:* \n"
                    f"• `.model gpt` — Ganti ke OpenAI GPT (gpt-4o-mini)\n"
                    f"• `.model gemini` — Ganti ke Google Gemini\n"
                    f"• `.model hermes` — Ganti ke OpenRouter Hermes\n"
                    f"• `.model claude` — Ganti ke Anthropic Claude\n"
                    f"• `.model <nama_model_openrouter>` — Set model spesifik OpenRouter"
                )
                await client.send_message(dest, msg, parse_mode="Markdown")
                return

            param = parts[1].strip().lower()
            if param in ["gpt", "openai", "gpt4", "gpt-4o", "gpt-4o-mini"]:
                if not config.OPENAI_API_KEY:
                    await client.send_message(dest, f"Waduh {user_name}, `OPENAI_API_KEY` belum diisi di `.env` nih!", parse_mode="Markdown")
                else:
                    config.save_env_key("AI_PROVIDER", "openai")
                    if param in ["gpt-4o", "gpt-4o-mini"]:
                        config.OPENAI_MODEL = param
                    await client.send_message(dest, f"Siap {user_name}! AI Provider telah diubah ke *OPENAI GPT* (`{config.OPENAI_MODEL}`).", parse_mode="Markdown")
            elif param == "gemini":
                config.save_env_key("AI_PROVIDER", "gemini")
                await client.send_message(dest, f"Siap {user_name}! AI Provider telah diubah ke *GOOGLE GEMINI* (`{config.GEMINI_MODEL}`).", parse_mode="Markdown")
            elif param in ["hermes", "openrouter", "auto"]:
                config.save_env_key("AI_PROVIDER", "hermes")
                config.HERMES_MODEL = "nex-agi/nex-n2.5-mini:free"
                await client.send_message(dest, f"Siap {user_name}! AI Provider telah diubah ke *HERMES / OPENROUTER* (`{config.HERMES_MODEL}`).", parse_mode="Markdown")
            elif param == "claude":
                if not config.ANTHROPIC_API_KEY:
                    await client.send_message(dest, f"Waduh {user_name}, `ANTHROPIC_API_KEY` belum diisi di `.env` nih!", parse_mode="Markdown")
                else:
                    config.save_env_key("AI_PROVIDER", "anthropic")
                    await client.send_message(dest, f"Siap {user_name}! AI Provider telah diubah ke *CLAUDE* (`{config.ANTHROPIC_MODEL}`).", parse_mode="Markdown")
            else:
                # Custom model name for OpenRouter
                config.AI_PROVIDER = "hermes"
                config.HERMES_MODEL = parts[1].strip()
                await client.send_message(dest, f"Siap {user_name}! Model Hermes telah diset ke: `{config.HERMES_MODEL}`.", parse_mode="Markdown")
            return

        # ---------------------------------------------------------
        # Perintah .grup / .groups
        # ---------------------------------------------------------
        if text.startswith(".grup") or text.startswith(".groups"):
            msg_lines = [f"Berikut daftar grup Telegram yang kamu ikuti, {user_name}:\n"]
            async for dialog in client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    d_id = getattr(dialog.entity, "id", None) or getattr(dialog, "id", None)
                    id_str = f" `(ID: {d_id})`" if d_id else ""
                    msg_lines.append(f"• `{dialog.name}`{id_str}")
            await send_long_message(client, dest, "\n".join(msg_lines))
            return

        # ---------------------------------------------------------
        # Perintah .sum / .rangkum / .summarize
        # ---------------------------------------------------------
        is_sum_cmd = False
        for cmd in [".sum", ".rangkum", ".summarize"]:
            if text.startswith(cmd):
                is_sum_cmd = True
                break

        if not is_sum_cmd:
            return

        try:
            # Ekstrak flag provider jika ada (--gemini / --hermes / --claude)
            target_provider = None
            if "--gemini" in text:
                target_provider = "gemini"
                text = text.replace("--gemini", "").strip()
            elif "--hermes" in text:
                target_provider = "hermes"
                text = text.replace("--hermes", "").strip()
            elif "--claude" in text:
                target_provider = "claude"
                text = text.replace("--claude", "").strip()

            parts = text.split(maxsplit=1)
            raw_target = parts[1].strip() if len(parts) > 1 else ""

            # Parse filter waktu dan nama/ID grup
            timeframe_delta, target_group = parse_timeframe_and_group(raw_target)

            # Jika diketik di dalam grup tanpa argumen grup
            chat = await event.get_chat()
            if not target_group and isinstance(chat, (Channel, Chat)):
                target_group = str(chat.id)

            if not target_group:
                await client.send_message(dest, f"Cara pakainya cukup ketik: `.sum NamaGrup` atau `.sum` langsung di dalam grup ya {user_name}!", parse_mode="Markdown")
                return

            target_entity = await find_telegram_group(client, target_group)

            if not target_entity:
                await client.send_message(dest, f"Maaf {user_name}, grup '{target_group}' tidak ditemukan nih.\nCoba ketik `.grup` untuk cek nama grup yang pas ya!", parse_mode="Markdown")
                return

            group_title = getattr(target_entity, "title", str(target_group))
            
            # Notifikasi Ramah
            use_prov = target_provider or config.AI_PROVIDER
            await client.send_message(dest, f"Siap {user_name}! ⏳ Saya sedang membaca & menganalisis obrolan grup *{group_title}* dengan AI ({use_prov.upper()})...", parse_mode="Markdown")

            now_utc = datetime.now(timezone.utc)
            since_cutoff = (now_utc - timeframe_delta) if timeframe_delta else None

            formatted_messages = []
            user_cache = {}
            async for msg in client.iter_messages(target_entity, limit=1000):
                if not msg.text or not msg.text.strip():
                    continue
                msg_date = msg.date.astimezone(timezone.utc) if msg.date else now_utc
                if since_cutoff and msg_date < since_cutoff:
                    continue

                sender_id = msg.sender_id
                if sender_id and sender_id in user_cache:
                    sender = user_cache[sender_id]
                else:
                    sender = msg.sender or getattr(msg, "sender", None)
                    if sender_id:
                        user_cache[sender_id] = sender

                if isinstance(sender, User):
                    full_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip() or sender.username or f"User_{sender.id}"
                    username = sender.username
                    user_id = sender.id
                else:
                    full_name = getattr(sender, "title", None) or f"User_{sender_id}"
                    username = getattr(sender, "username", None)
                    user_id = sender_id

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
                time_lbl = f"{int(timeframe_delta.total_seconds() // 3600)} jam terakhir" if timeframe_delta else "terbaru"
                await client.send_message(dest, f"Belum ada obrolan baru nih di grup '{group_title}' untuk periode {time_lbl}, {user_name}.")
                return

            tf_label = f"{int(timeframe_delta.total_seconds() // 3600)} jam terakhir" if timeframe_delta else f"{len(formatted_messages)} pesan terbaru"
            summarizer = ChatSummarizer(provider=target_provider)
            try:
                summary_result = await summarizer.summarize_messages(formatted_messages, timeframe_info=tf_label)
            except Exception as e:
                summary_result = f"❌ Terjadi kesalahan saat memproses ringkasan: {str(e)}"

            full_msg = f"Halo {user_name}! 👋 Ini ringkasan obrolan grup *{group_title}* yang kamu minta:\n\n{summary_result}"
            await send_long_message(client, dest, full_msg)
        except Exception as cmd_err:
            logger.exception("Error executing .sum command: %s", cmd_err)
            await client.send_message(dest, f"❌ Terjadi kesalahan saat merangkum: {str(cmd_err)}")

    await client.run_until_disconnected()

async def run_saved_messages_listener() -> None:
    """Mode Listener Multi-Account: Mendengarkan perintah dari seluruh akun Telegram yang dikonfigurasi."""
    sessions = config.get_all_string_sessions()
    if not sessions:
        sessions = [""]

    total = len(sessions)
    print("\n=========================================================")
    print(f"🤫 TELEGRAM USERBOT MULTI-ACCOUNT MODE ({total} AKUN TERHUBUNG)")
    print("=========================================================")
    print("📌 Perintah siap digunakan via Telegram HP Anda:")
    print("   • .sum / .rangkum Nama Grup   -> Meringkas obrolan grup")
    print("   • .model                      -> Cek & ganti AI provider")
    print("   • .grup                       -> Menampilkan daftar grup Anda")
    print("=========================================================\n")

    await asyncio.gather(*[start_single_userbot(sess, idx, total) for idx, sess in enumerate(sessions, 1)])

def main():
    parser = argparse.ArgumentParser(description="Telegram Private UserBot Summarizer (Tanpa Perlu Undang Bot ke Grup)")
    parser.add_argument("--listen", action="store_true", help="Jalankan dalam mode Listener (Kontrol via Pesan Tersimpan di HP)")
    parser.add_argument("--list-groups", action="store_true", help="Tampilkan daftar semua grup Telegram yang Anda ikuti")
    parser.add_argument("--group", type=str, help="Nama atau ID Grup yang ingin dirangkum secara rahasia")
    parser.add_argument("--hours", type=int, default=0, help="Rentang waktu jam ke belakang (0 = tanpa batasan jam, default: 0)")
    parser.add_argument("--limit", type=int, default=1000, help="Batas maksimal jumlah pesan yang dibaca (default: 1000)")
    parser.add_argument("--no-send", action="store_true", help="Jangan kirim ke Saved Messages (hanya tampil di terminal)")

    args = parser.parse_args()

    if args.listen or len(sys.argv) == 1:
        asyncio.run(run_saved_messages_listener())
        return

    if args.list_groups:
        asyncio.run(list_user_groups())
        return

    if not args.group:
        print("\n⚠️ Silakan masukkan nama/ID grup yang ingin dirangkum.")
        print("Contoh: python userbot_summarizer.py --group \"Agung & para bot\"")
        print("Atau jalankan mode Listener: python userbot_summarizer.py --listen\n")
        return

    asyncio.run(summarize_group_silently(
        target_group=args.group,
        limit_messages=args.limit,
        hours=args.hours,
        send_to_me=not args.no_send
    ))

if __name__ == "__main__":
    main()
