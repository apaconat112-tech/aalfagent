import argparse
import asyncio
import logging
import random
import re
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

# UTF-8 output encoding for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder,
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
logger = logging.getLogger("autonomous_group_bots")

# Definisi Karakter Tim & Persona AI Pintar
PERSONA_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "id": "siti_pm",
        "username": "siti_pm",
        "full_name": "Siti Rahma",
        "role": "Product Manager",
        "emoji": "👩‍💼",
        "user_id": 1001,
        "system_prompt": (
            "Nama Anda adalah Siti Rahma, seorang Product Manager (PM) profesional di tim software engineering. "
            "Karakter Anda: tegas namun ramah, fokus pada tenggat waktu (sprint deadline), penetapan PIC/tugas, "
            "prioritas fitur, dan koordinasi antar anggota tim (Backend, QA, Design, DevOps). "
            "Balaslah pesan pengguna dengan gaya bahasa Indonesia santai namun profesional layaknya seorang PM di Slack/Telegram."
        )
    },
    {
        "id": "budi_dev",
        "username": "budi_dev",
        "full_name": "Budi Santoso",
        "role": "Senior Backend Lead",
        "emoji": "👨‍💻",
        "user_id": 1002,
        "system_prompt": (
            "Nama Anda adalah Budi Santoso, seorang Senior Backend Engineer. "
            "Karakter Anda: teknis, solutif, berpengalaman tentang API REST/GraphQL, database PostgreSQL/Redis, "
            "performance tuning, dan Pull Request (PR). "
            "Balaslah pesan pengguna dengan istilah teknis backend yang natural dan membantu."
        )
    },
    {
        "id": "andi_qa",
        "username": "andi_qa",
        "full_name": "Andi Wijaya",
        "role": "QA Lead",
        "emoji": "👨‍🔬",
        "user_id": 1003,
        "system_prompt": (
            "Nama Anda adalah Andi Wijaya, seorang QA Lead. "
            "Karakter Anda: teliti, fokus pada bug reporting, regression test, staging environment, "
            "dan kriteria penerimaan fitur (acceptance criteria). "
            "Balaslah pesan pengguna dengan perspektif pengujian kualitas software."
        )
    },
    {
        "id": "dewi_design",
        "username": "dewi_design",
        "full_name": "Dewi Lestari",
        "role": "UI/UX Designer",
        "emoji": "👩‍🎨",
        "user_id": 1004,
        "system_prompt": (
            "Nama Anda adalah Dewi Lestari, seorang UI/UX Designer. "
            "Karakter Anda: kreatif, peduli pada pengalaman pengguna (user experience), Figma mockup, "
            "dark mode, konsistensi warna, dan aksesibilitas (WCAG). "
            "Balaslah pesan pengguna dengan gaya desainer produk modern."
        )
    },
    {
        "id": "eko_devops",
        "username": "eko_devops",
        "full_name": "Eko Prasetyo",
        "role": "DevOps Engineer",
        "emoji": "👨‍💻",
        "user_id": 1005,
        "system_prompt": (
            "Nama Anda adalah Eko Prasetyo, seorang DevOps Engineer. "
            "Karakter Anda: tanggap masalah server, CI/CD pipeline, Docker, Kubernetes, AWS, "
            "monitoring CPU/memory, dan p99 latency. "
            "Balaslah pesan pengguna dengan gaya infrastruktur & sysadmin yang sigap."
        )
    }
]

class AutonomousBotManager:
    def __init__(self):
        self.summarizer = ChatSummarizer()
        self.tokens = config.SIMULATOR_BOT_TOKENS
        self.personas = PERSONA_DEFINITIONS

    async def generate_persona_reply(self, persona: Dict[str, Any], user_message: str, chat_context: str = "") -> str:
        """Menghasilkan respon cerdas khas karakter persona berbasis AI."""
        prompt = f"Pesan dari pengguna di grup Telegram:\n'{user_message}'\n\n"
        if chat_context:
            prompt = f"Konteks obrolan sebelumnya:\n{chat_context}\n\n{prompt}"
        prompt += f"Jawablah pesan di atas sebagai {persona['full_name']} ({persona['role']}) secara singkat, pintar, dan natural (1-3 kalimat)."

        try:
            # Gunakan system prompt persona khusus
            if config.AI_PROVIDER == "gemini":
                from google.genai import types
                if not self.summarizer.gemini_client:
                    from google import genai
                    self.summarizer.gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
                resp = await self.summarizer.gemini_client.aio.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=persona["system_prompt"],
                        temperature=0.7,
                        max_output_tokens=300
                    )
                )
                return resp.text.strip() if resp.text else f"Siap, dicatat oleh {persona['full_name']}."
            elif config.AI_PROVIDER == "anthropic":
                resp = await self.summarizer.anthropic_client.messages.create(
                    model=config.ANTHROPIC_MODEL,
                    max_tokens=300,
                    system=persona["system_prompt"],
                    messages=[{"role": "user", "content": prompt}]
                )
                return resp.content[0].text.strip()
            else:
                return await self.summarizer._call_hermes(prompt=prompt, system_instruction=persona["system_prompt"])
        except Exception as e:
            logger.warning("Gagal memanggil AI untuk persona %s: %s", persona['full_name'], e)
            return f"Siap mas/mba, noted dari {persona['full_name']}."

    def select_best_persona(self, message_text: str) -> Dict[str, Any]:
        """Memilih persona yang paling cocok untuk merespons berdasarkan topik obrolan."""
        text_lower = message_text.lower()

        if any(w in text_lower for w in ["pm", "sprint", "backlog", "pic", "deadline", "target", "jadwal", "fitur"]):
            return self.personas[0]  # Siti PM
        elif any(w in text_lower for w in ["api", "backend", "db", "database", "query", "python", "code", "pr", "fix", "error"]):
            return self.personas[1]  # Budi Dev
        elif any(w in text_lower for w in ["qa", "test", "testing", "bug", "staging", "regression", "tc"]):
            return self.personas[2]  # Andi QA
        elif any(w in text_lower for w in ["design", "ui", "ux", "figma", "layout", "warna", "mockup", "tampilan"]):
            return self.personas[3]  # Dewi Design
        elif any(w in text_lower for w in ["devops", "server", "deploy", "docker", "pipeline", "cpu", "latency", "prod"]):
            return self.personas[4]  # Eko DevOps
        else:
            return random.choice(self.personas)

async def run_smart_multi_bot_simulation(
    chat_id: int,
    topic: str,
    turns: int = 6,
    delay_seconds: float = 3.0
) -> None:
    """Mensimulasikan obrolan antar beberapa bot pintar yang saling berdiskusi topik bebas dengan AI."""
    await database.init_db()
    manager = AutonomousBotManager()
    tokens = config.SIMULATOR_BOT_TOKENS

    print(f"\n🧠 Memulai Simulasi Group Chat PINTAR berbasis AI")
    print(f"📌 Chat ID    : {chat_id}")
    print(f"💬 Topik Diskusi: '{topic}'")
    print(f"🤖 Bot Tokens   : {len(tokens)} token aktif\n")

    bots = [Bot(token=t) for t in tokens]
    conversation_history = f"Topik Diskusi Utama: {topic}\n"

    for step in range(turns):
        # Pilih persona bergiliran atau sesuai konteks
        persona = manager.personas[step % len(manager.personas)]
        
        # Panggil AI untuk menghasilkan pesan cerdas berikutnya dalam obrolan
        reply_text = await manager.generate_persona_reply(
            persona=persona,
            user_message=f"Lanjutkan diskusi tim tentang '{topic}' secara alami.",
            chat_context=conversation_history
        )

        bot_idx = step % len(bots)
        active_bot = bots[bot_idx]

        # Format pesan
        if len(bots) == 1:
            display_text = f"{persona['emoji']} *[{persona['full_name']} - {persona['role']}]*\n{reply_text}"
        else:
            display_text = reply_text

        msg_timestamp = datetime.now(timezone.utc)
        sent_msg_id = random.randint(1000, 99999)

        # 1. Kirim ke Telegram
        try:
            if len(bots) == 1:
                try:
                    sent_msg = await active_bot.send_message(chat_id=chat_id, text=display_text, parse_mode="Markdown")
                except Exception:
                    sent_msg = await active_bot.send_message(chat_id=chat_id, text=display_text)
            else:
                sent_msg = await active_bot.send_message(chat_id=chat_id, text=display_text)
            sent_msg_id = sent_msg.message_id
            logger.info("[%d/%d] Sent -> %s: %s", step+1, turns, persona['full_name'], reply_text[:40])
        except Exception as e:
            logger.warning("[%d/%d] Gagal kirim pesan live (%s), tetap catat ke DB.", step+1, turns, e)

        # 2. Catat ke database
        await database.save_message(
            chat_id=chat_id,
            message_id=sent_msg_id,
            user_id=persona["user_id"],
            username=persona["username"],
            full_name=persona["full_name"],
            text=reply_text,
            timestamp=msg_timestamp
        )

        conversation_history += f"{persona['full_name']}: {reply_text}\n"
        print(f"  [{step+1}/{turns}] {persona['emoji']} {persona['full_name']} ({persona['role']}): {reply_text}")

        if step < turns - 1:
            await asyncio.sleep(delay_seconds)

    print(f"\n✅ Simulasi AI Selesai! {turns} pesan obrolan pintar telah dikirim ke grup.")
    print(f"👉 Sekarang Anda dapat mengetik `/summary` di grup Telegram untuk menguji ringkasan AI!\n")

def main():
    parser = argparse.ArgumentParser(description="Autonomous Smart Multi-Bot Telegram Simulator")
    parser.add_argument("--chat-id", type=int, required=True, help="Target Telegram Group Chat ID (contoh: -1005036107344)")
    parser.add_argument("--topic", type=str, default="Persiapan rilis fitur payment gateway & evaluasi sistem", help="Topik obrolan AI yang akan didiskusikan")
    parser.add_argument("--turns", type=int, default=6, help="Jumlah putaran obrolan AI yang akan dikirim (default: 6)")
    parser.add_argument("--delay", type=float, default=3.0, help="Delay antar pesan dalam detik (default: 3.0)")

    args = parser.parse_args()

    asyncio.run(run_smart_multi_bot_simulation(
        chat_id=args.chat_id,
        topic=args.topic,
        turns=args.turns,
        delay_seconds=args.delay
    ))

if __name__ == "__main__":
    main()
