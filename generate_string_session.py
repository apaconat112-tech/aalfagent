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
        session_str = client.session.save()
        print("=========================================================")
        print(session_str)
        print("=========================================================\n")
        
        # Simpan otomatis ke .env
        env_path = "c:/aiagent/.env"
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                env_content = f.read()

            # Cari nomor index berikutnya
            idx = 2
            while f"TELEGRAM_STRING_SESSION_{idx}=" in env_content:
                idx += 1

            if "TELEGRAM_STRING_SESSION=" not in env_content or not config.TELEGRAM_STRING_SESSION:
                key_name = "TELEGRAM_STRING_SESSION"
            else:
                key_name = f"TELEGRAM_STRING_SESSION_{idx}"

            with open(env_path, "a", encoding="utf-8") as f:
                f.write(f"\n{key_name}={session_str}\n")
            print(f"✅ Sesi baru berhasil disimpan otomatis ke file .env sebagai '{key_name}'!\n")
        except Exception as save_err:
            print(f"Salin kode di atas secara manual ke file .env Anda:\nTELEGRAM_STRING_SESSION={session_str}\n")

if __name__ == "__main__":
    asyncio.run(main())
