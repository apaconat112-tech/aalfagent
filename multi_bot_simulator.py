import argparse
import asyncio
import logging
import random
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# Enforce UTF-8 output encoding for Windows PowerShell / CMD
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from telegram import Bot
import config
import database
from summarizer import ChatSummarizer

# Konfigurasi Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("multi_bot_simulator")

# Personas Karakter Pengguna Simulasi
PERSONAS: List[Dict[str, Any]] = [
    {
        "user_id": 1001,
        "username": "siti_pm",
        "full_name": "Siti Rahma",
        "role": "Product Manager",
        "emoji": "👩‍💼"
    },
    {
        "user_id": 1002,
        "username": "budi_dev",
        "full_name": "Budi Santoso",
        "role": "Senior Backend Lead",
        "emoji": "👨‍💻"
    },
    {
        "user_id": 1003,
        "username": "andi_qa",
        "full_name": "Andi Wijaya",
        "role": "QA Lead",
        "emoji": "👨‍🔬"
    },
    {
        "user_id": 1004,
        "username": "dewi_design",
        "full_name": "Dewi Lestari",
        "role": "UI/UX Designer",
        "emoji": "👩‍🎨"
    },
    {
        "user_id": 1005,
        "username": "eko_devops",
        "full_name": "Eko Prasetyo",
        "role": "DevOps Engineer",
        "emoji": "👨‍💻"
    }
]

# Scenario Dialogues Preset
PRESET_SCENARIOS: Dict[str, List[Dict[str, Any]]] = {
    "sprint": [
        {
            "persona_idx": 0,  # Siti PM
            "text": "👋 Halo team! Pagi ini kita sync sprint planning untuk rilis fitur Payment Gateway Callback & Multi-Currency support."
        },
        {
            "persona_idx": 1,  # Budi Dev
            "text": "Pagi Bu Siti. Untuk API callback Midtrans PR #145 sudah siap disubmit, sedang menunggu QA regression check."
        },
        {
            "persona_idx": 2,  # Andi QA
            "text": "Siap Mas @budi_dev. Staging environment sudah up. Nanti sore jam 15:00 saya eksekusi automated test suite-nya."
        },
        {
            "persona_idx": 3,  # Dewi Design
            "text": "Mockup UI pilihan mata uang di halaman checkout v2 sudah disetujui di Figma: https://figma.com/file/checkout-v2-preview"
        },
        {
            "persona_idx": 4,  # Eko DevOps
            "text": "Mantap! Pipeline CI/CD staging & autoscaling pod Kubernetes sudah terkonfigurasi aman."
        },
        {
            "persona_idx": 0,  # Siti PM
            "text": "Oke kesimpulannya: Target rilis staging pukul 17:00 WIB. PIC testing @andi_qa, review PR @budi_dev. Mari kita selesaikan sprint ini! 🚀"
        }
    ],
    "incident": [
        {
            "persona_idx": 4,  # Eko DevOps
            "text": "🚨 ALERT PAGERDUTY: Server `prod-api-02` mengalami high CPU load (>96%). Latency p99 melonjak ke 4.8 detik!"
        },
        {
            "persona_idx": 1,  # Budi Dev
            "text": "Sedang dicek log APM. Terlihat ada leak di connection pool PostgreSQL setelah deployment v2.4 jam 14:00 WIB tadi."
        },
        {
            "persona_idx": 0,  # Siti PM
            "text": "Apakah ada user yang error saat transaksi checkout mas @budi_dev @eko_devops?"
        },
        {
            "persona_idx": 4,  # Eko DevOps
            "text": "Ada sekitar 4% request payment timeout di gateway. Traffic dipindahkan sementara ke server backup `prod-api-01`."
        },
        {
            "persona_idx": 1,  # Budi Dev
            "text": "Root cause ketemu: Missing index pada tabel `orders` & unclosed DB session di `payment_service.py`."
        },
        {
            "persona_idx": 1,  # Budi Dev
            "text": "PR Hotfix ready untuk di-merge: https://github.com/company/core-api/pull/208"
        },
        {
            "persona_idx": 2,  # Andi QA
            "text": "Hotfix PR #208 sudah dites di local staging, query speed membaik dari 2.1 detik jadi 12 ms."
        },
        {
            "persona_idx": 4,  # Eko DevOps
            "text": "Hotfix v2.4.1 sudah dideploy ke production. Metrics CPU kembali stabil di angka 18%. Error rate 0%."
        },
        {
            "persona_idx": 0,  # Siti PM
            "text": "Terima kasih penanganan cepatnya team! Post-mortem meeting kita gelar besok pagi jam 10:00 WIB. PIC laporan @eko_devops."
        }
    ],
    "design": [
        {
            "persona_idx": 3,  # Dewi Design
            "text": "Halo tim, mohon feedbacknya untuk revamp Dashboard Analytics versi 3.0: https://figma.com/file/dashboard-v3-revamp"
        },
        {
            "persona_idx": 0,  # Siti PM
            "text": "Suka sekali dengan layout widget barunya mba @dewi_design! Jauh lebih intuitive untuk kustomer enterprise."
        },
        {
            "persona_idx": 1,  # Budi Dev
            "text": "Widget Realtime Active User butuh streaming data SSE. Nanti saya siapkan endpoint `/api/v1/stats/live`."
        },
        {
            "persona_idx": 2,  # Andi QA
            "text": "Untuk kontras warna Dark Mode apakah sudah memenuhi standar aksesibilitas WCAG AA?"
        },
        {
            "persona_idx": 3,  # Dewi Design
            "text": "Sudah diuji kontrasnya (rasio 4.5:1). Assets SVG dan Icon set juga sudah di-export ke repository UI components."
        }
    ],
    "casual": [
        {
            "persona_idx": 1,  # Budi Dev
            "text": "Siang teman-teman! Makan siang hari ini di mana nih?"
        },
        {
            "persona_idx": 0,  # Siti PM
            "text": "Nasi Padang Sederhana depan kantor yuk! Lagi pengen ayam pop."
        },
        {
            "persona_idx": 2,  # Andi QA
            "text": "Ikut mba Siti! Rendangnya juga juara di sana."
        },
        {
            "persona_idx": 4,  # Eko DevOps
            "text": "Nanti sore ada yang mau main badminton jam 18:00 WIB di Gor biasa?"
        },
        {
            "persona_idx": 3,  # Dewi Design
            "text": "Saya ikutan badminton mas Eko! Bawa raket cadangan ya."
        }
    ]
}

async def generate_ai_scenario(topic: str) -> List[Dict[str, Any]]:
    """Generasi percakapan dinamis berbasis AI untuk topik custom."""
    logger.info("Generating dynamic AI chat scenario for topic: %s", topic)
    summarizer = ChatSummarizer()
    
    prompt = (
        f"Buatkan percakapan grup tim kerja realistis dalam bahasa Indonesia dengan topik: '{topic}'.\n\n"
        "Format output HARUS berupa baris-baris dialog seperti ini (pilih dari peran: Siti PM, Budi Dev, Andi QA, Dewi Design, Eko DevOps):\n"
        "Siti PM: <pesan>\n"
        "Budi Dev: <pesan>\n"
        "Andi QA: <pesan>\n"
        "Dewi Design: <pesan>\n"
        "Eko DevOps: <pesan>\n\n"
        "Buat 6-8 baris percakapan yang natural, menyertakan kesepakatan, tugas/PIC, atau link jika relevan."
    )
    
    try:
        raw_text = await summarizer.chat_reply(user_message=prompt)
        dialogue = []
        name_map = {
            "siti": 0,
            "budi": 1,
            "andi": 2,
            "dewi": 3,
            "eko": 4
        }
        
        for line in raw_text.strip().split("\n"):
            line = line.strip()
            if ":" in line:
                speaker, text = line.split(":", 1)
                speaker = speaker.strip().lower()
                text = text.strip()
                if not text:
                    continue
                
                idx = 0
                for key, val in name_map.items():
                    if key in speaker:
                        idx = val
                        break
                dialogue.append({"persona_idx": idx, "text": text})
                
        if dialogue:
            return dialogue

    except Exception as e:
        logger.warning("Gagal menggenerate obrolan AI (%s), memuat fallback skenario 'sprint'.", e)
        
    return PRESET_SCENARIOS["sprint"]

async def run_simulation(
    chat_id: int,
    scenario_name: str = "sprint",
    custom_topic: Optional[str] = None,
    delay_seconds: float = 2.5
) -> None:
    """Menjalankan simulasi obrolan grup live ke Telegram & menyimpan ke database."""
    await database.init_db()
    
    tokens = config.SIMULATOR_BOT_TOKENS
    if not tokens:
        logger.error("Tidak ada TELEGRAM_BOT_TOKEN atau SIMULATOR_BOT_TOKENS yang terkonfigurasi!")
        return

    logger.info("Initializing %d simulator bot instance(s)...", len(tokens))
    bots = [Bot(token=t) for t in tokens]
    
    # Ambil skenario dialog
    if custom_topic:
        dialogue = await generate_ai_scenario(custom_topic)
    else:
        dialogue = PRESET_SCENARIOS.get(scenario_name.lower(), PRESET_SCENARIOS["sprint"])

    print(f"\n🚀 Memulai Simulasi Live Group Chat")
    print(f"📌 Chat ID   : {chat_id}")
    if chat_id > 0:
        print(f"⚠️  PERHATIAN: ID '{chat_id}' adalah ID Private DM (Chat Pribadi Anda dengan Bot).")
        print("    Jika Anda ingin bot ngechat di GRUP TELEGRAM, gunakan Chat ID Grup (diawali minus, contoh: -1001851834283).")
    print(f"💬 Total Chat: {len(dialogue)} pesan")
    print(f"⏱  Delay      : {delay_seconds} detik/pesan\n")

    base_time = datetime.now(timezone.utc)

    for i, item in enumerate(dialogue):
        persona = PERSONAS[item["persona_idx"]]
        text_content = item["text"]
        
        # Pilih bot instance
        bot_idx = i % len(bots)
        active_bot = bots[bot_idx]
        
        # Jika hanya ada 1 bot token, tambahkan badge nama persona agar pesan terlihat jelas di Telegram
        if len(bots) == 1:
            display_text = f"{persona['emoji']} *[{persona['full_name']} - {persona['role']}]*\n{text_content}"
        else:
            display_text = text_content

        msg_timestamp = datetime.now(timezone.utc)
        
        # 1. Kirim pesan ke grup Telegram secara live
        sent_msg_id = random.randint(1000, 99999)
        try:
            if len(bots) == 1:
                try:
                    sent_msg = await active_bot.send_message(
                        chat_id=chat_id,
                        text=display_text,
                        parse_mode="Markdown"
                    )
                except Exception:
                    sent_msg = await active_bot.send_message(
                        chat_id=chat_id,
                        text=display_text
                    )
            else:
                sent_msg = await active_bot.send_message(
                    chat_id=chat_id,
                    text=display_text
                )
            sent_msg_id = sent_msg.message_id
            logger.info("[%d/%d] Telegram Live -> %s: %s", i+1, len(dialogue), persona['full_name'], text_content[:40])
        except Exception as e:
            logger.warning("[%d/%d] Gagal kirim pesan live ke Telegram (%s), tetap menyimpan ke DB lokal.", i+1, len(dialogue), e)

        # 2. Simpan pesan langsung ke SQLite DB agar Summarizer Bot dapat membaca histori secara lengkap
        await database.save_message(
            chat_id=chat_id,
            message_id=sent_msg_id,
            user_id=persona["user_id"],
            username=persona["username"],
            full_name=persona["full_name"],
            text=text_content,
            timestamp=msg_timestamp
        )

        print(f"  [{i+1}/{len(dialogue)}] {persona['emoji']} {persona['full_name']} (@{persona['username']}): {text_content}")
        
        if i < len(dialogue) - 1:
            await asyncio.sleep(delay_seconds)

    print(f"\n✅ Simulasi Selesai! {len(dialogue)} pesan telah dikirim & disimpan di database.")
    print(f"👉 Sekarang Anda bisa mengetik `/summary` di grup Telegram untuk menguji bot summarizer!\n")

async def list_database_chats() -> None:
    """Menampilkan daftar chat ID yang tersimpan di database."""
    await database.init_db()
    import aiosqlite
    async with aiosqlite.connect(config.DATABASE_PATH) as db:
        async with db.execute("SELECT DISTINCT chat_id FROM messages") as cursor:
            rows = await cursor.fetchall()
            if not rows:
                print("\nℹ️ Belum ada histori chat di database.")
                return
            print("\n📋 Daftar Chat ID yang tersedia di Database:")
            for r in rows:
                print(f"  • Chat ID: {r[0]}")
            print()

def main():
    parser = argparse.ArgumentParser(description="Multi-Bot Telegram Live Group Chat Simulator")
    parser.add_argument("--chat-id", type=int, help="Target Telegram Group Chat ID (contoh: -100123456789)")
    parser.add_argument("--scenario", type=str, default="sprint", choices=["sprint", "incident", "design", "casual"], help="Pilihan skenario obrolan preset")
    parser.add_argument("--topic", type=str, help="Topik percakapan custom yang akan digenerate dengan AI")
    parser.add_argument("--delay", type=float, default=2.5, help="Delay antar pengiriman pesan (dalam detik)")
    parser.add_argument("--list-chats", action="store_true", help="Tampilkan daftar Chat ID yang ada di database")

    args = parser.parse_args()

    if args.list_chats:
        asyncio.run(list_database_chats())
        return

    if not args.chat_id:
        print("\n⚠️ Perhatian: Argumen --chat-id belum diisi.")
        asyncio.run(list_database_chats())
        try:
            val = input("Masukkan Target Chat ID (atau tekan Enter untuk keluar): ").strip()
            if not val:
                return
            target_chat_id = int(val)
        except ValueError:
            print("❌ Chat ID tidak valid.")
            return
    else:
        target_chat_id = args.chat_id

    asyncio.run(run_simulation(
        chat_id=target_chat_id,
        scenario_name=args.scenario,
        custom_topic=args.topic,
        delay_seconds=args.delay
    ))

if __name__ == "__main__":
    main()
