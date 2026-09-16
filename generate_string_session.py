import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
import config

async def main():
    api_id_str = config.TELEGRAM_API_ID
    api_hash = config.TELEGRAM_API_HASH
    
    if not api_id_str or not api_hash:
        print("TELEGRAM_API_ID dan TELEGRAM_API_HASH harus ada di .env")
        return

    print("Membuka sesi Telethon untuk menghasilkan TELEGRAM_STRING_SESSION...")
    
    # Gunakan file sesi yang sudah login jika ada
    try:
        file_client = TelegramClient("userbot_session", int(api_id_str), api_hash)
        await file_client.connect()
        if await file_client.is_user_authorized():
            string_session = StringSession.save(file_client.session)
            print("\nTELEGRAM_STRING_SESSION Berhasil Dibuat dari sesi lokal Anda!\n")
            print("=========================================================")
            print(string_session)
            print("=========================================================\n")
            print("Salin kode di atas ke file .env Anda:")
            print(f"TELEGRAM_STRING_SESSION={string_session}\n")
            await file_client.disconnect()
            return
        await file_client.disconnect()
    except Exception as e:
        print(f"Info: {e}")

    # Buat StringSession baru secara interaktif jika belum ada
    async with TelegramClient(StringSession(), int(api_id_str), api_hash) as client:
        print("\nTELEGRAM_STRING_SESSION Berhasil Dibuat!\n")
        session_str = client.session.save()
        print("=========================================================")
        print(session_str)
        print("=========================================================\n")
        print("Salin kode di atas ke file .env Anda:")
        print(f"TELEGRAM_STRING_SESSION={session_str}\n")

if __name__ == "__main__":
    asyncio.run(main())
