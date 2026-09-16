import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

# UTF-8 output encoding for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

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
        target_entity = None
        try:
            target_id = int(target_group)
            target_entity = await client.get_entity(target_id)
        except (ValueError, Exception):
            # Cari berdasarkan string/nama
            async for dialog in client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    if target_group.lower() in dialog.name.lower():
                        target_entity = dialog.entity
                        break

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
                try:
                    sender = await msg.get_sender()
                except Exception:
                    sender = getattr(msg, "sender", None)
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

async def run_saved_messages_listener() -> None:
    """Mode Listener: Mendengarkan perintah langsung dari Pesan Tersimpan (Saved Messages) Telegram Anda."""
    api_id = int(config.TELEGRAM_API_ID)
    api_hash = config.TELEGRAM_API_HASH
    
    session_obj = StringSession(config.TELEGRAM_STRING_SESSION) if config.TELEGRAM_STRING_SESSION else SESSION_NAME
    client = TelegramClient(session_obj, api_id, api_hash, receive_updates=True)
    await client.start()

    print("\n=========================================================")
    print("🤫 TELEGRAM USERBOT LISTEN MODE (TERHUBUNG)")
    print("=========================================================")
    print("📌 Anda sekarang bisa langsung mengontrol UserBot dari HP Anda!")
    print("📌 Buka 'Pesan Tersimpan' (Saved Messages) di Telegram & ketik:")
    print("   • /rangkum Nama Grup   -> Membaca & meringkas 1000 pesan grup")
    print("   • /grup                -> Menampilkan daftar grup Anda")
    print("=========================================================\n")

    try:
        await client.send_message("me", 
            "🤖 *UserBot Private Summarizer Aktif!*\n\n"
            "Ketik perintah di bawah ini di Pesan Tersimpan Anda:\n"
            "• `/rangkum Nama Grup` — Meringkas 1000 pesan grup secara rahasia\n"
            "• `/grup` — Lihat daftar nama grup Anda",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    @client.on(events.NewMessage(chats="me"))
    async def handler(event):
        text = event.text.strip() if event.text else ""
        if not text:
            return

        if text.startswith("/grup") or text.startswith("/groups"):
            msg_lines = ["📋 *Daftar Grup Telegram Anda:*"]
            async for dialog in client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    msg_lines.append(f"• `{dialog.name}`")
            await send_long_message(client, "me", "\n".join(msg_lines))
            return

        if text.startswith("/rangkum") or text.startswith("/summarize"):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await client.send_message("me", "⚠️ Format salah! Gunakan: `/rangkum Nama Grup`", parse_mode="Markdown")
                return

            target_group = parts[1].strip()
            await client.send_message("me", f"⏳ *Membaca & meringkas obrolan grup '{target_group}'...*", parse_mode="Markdown")

            target_entity = None
            try:
                target_id = int(target_group)
                target_entity = await client.get_entity(target_id)
            except (ValueError, Exception):
                async for dialog in client.iter_dialogs():
                    if dialog.is_group or dialog.is_channel:
                        if target_group.lower() in dialog.name.lower():
                            target_entity = dialog.entity
                            break

            if not target_entity:
                await client.send_message("me", f"❌ Grup '{target_group}' tidak ditemukan!\nKetik `/grup` untuk melihat nama grup Anda.", parse_mode="Markdown")
                return

            group_title = getattr(target_entity, "title", str(target_group))
            group_id = target_entity.id

            formatted_messages = []
            user_cache = {}
            async for msg in client.iter_messages(target_entity, limit=1000):
                if not msg.text or not msg.text.strip():
                    continue
                msg_date = msg.date.astimezone(timezone.utc) if msg.date else datetime.now(timezone.utc)
                sender_id = msg.sender_id
                if sender_id and sender_id in user_cache:
                    sender = user_cache[sender_id]
                else:
                    try:
                        sender = await msg.get_sender()
                    except Exception:
                        sender = getattr(msg, "sender", None)
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
                await client.send_message("me", f"ℹ️ Tidak ditemukan pesan baru di grup '{group_title}'.")
                return

            summarizer = ChatSummarizer()
            try:
                summary_result = await summarizer.summarize_messages(formatted_messages, timeframe_info=f"{len(formatted_messages)} pesan terbaru")
            except Exception as e:
                summary_result = f"❌ Terjadi kesalahan saat memproses ringkasan: {str(e)}"

            header = f"🤫 *RINGKASAN RAHASIA GRUP: {group_title}*\n"
            full_msg = f"{header}\n{summary_result}"
            await send_long_message(client, "me", full_msg)

    await client.run_until_disconnected()

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
