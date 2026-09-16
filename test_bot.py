import asyncio
import os
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Override DB path for test
os.environ["DATABASE_PATH"] = "test_chat.db"
os.environ["TELEGRAM_BOT_TOKEN"] = "dummy_token"
os.environ["ANTHROPIC_API_KEY"] = "dummy_key"

import database
from summarizer import format_messages_transcript, chunk_messages
import config

class TestChatSummarizerBot(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Inisialisasi DB testing
        await database.init_db()

    async def asyncTearDown(self):
        # Hapus file database testing setelah selesai
        db_file = Path("test_chat.db")
        if db_file.exists():
            try:
                db_file.unlink()
            except Exception:
                pass

    async def test_database_message_flow(self):
        """Uji alur simpan dan ambil pesan dari database."""
        chat_id = -100123456789
        now = datetime.now(timezone.utc)
        
        # Simpan 3 pesan sampel
        await database.save_message(
            chat_id=chat_id,
            message_id=1,
            user_id=101,
            username="budi_dev",
            full_name="Budi Santoso",
            text="Halo semua, sprint planning jam 2 siang ya.",
            timestamp=now - timedelta(minutes=30)
        )
        
        await database.save_message(
            chat_id=chat_id,
            message_id=2,
            user_id=102,
            username="siti_pm",
            full_name="Siti Rahma",
            text="Siap, link meeting di https://meet.google.com/abc-defg-hij",
            timestamp=now - timedelta(minutes=15)
        )

        await database.save_message(
            chat_id=chat_id,
            message_id=3,
            user_id=103,
            username="andi_qa",
            full_name="Andi QA",
            text="Saya akan siapkan test report sprint lalu.",
            timestamp=now - timedelta(minutes=5)
        )

        # Ambil pesan 1 jam terakhir
        since_time = now - timedelta(hours=1)
        messages = await database.get_messages_since(chat_id, since_time)
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["username"], "budi_dev")
        self.assertEqual(messages[1]["username"], "siti_pm")
        self.assertEqual(messages[2]["username"], "andi_qa")

        # Uji format transcript
        transcript = format_messages_transcript(messages)
        self.assertIn("Budi Santoso (@budi_dev): Halo semua, sprint planning", transcript)
        self.assertIn("https://meet.google.com/abc-defg-hij", transcript)

        # Uji chunking
        chunks = chunk_messages(messages, chunk_size=2)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[0]), 2)
        self.assertEqual(len(chunks[1]), 1)

    async def test_chat_metadata_and_schedule(self):
        """Uji pengelolaan metadata ringkasan dan jadwal."""
        chat_id = -100987654321
        now = datetime.now(timezone.utc)
        
        # Test summary time update
        await database.update_last_summary_time(chat_id, now)
        last_time = await database.get_last_summary_time(chat_id)
        self.assertIsNotNone(last_time)
        self.assertEqual(last_time.isoformat(), now.isoformat())

        # Test schedule set
        await database.set_chat_schedule(chat_id, 6)
        active = await database.get_all_active_schedules()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["chat_id"], chat_id)
        self.assertEqual(active[0]["schedule_hours"], 6)

        # Turn off schedule
        await database.set_chat_schedule(chat_id, 0)
        active_after = await database.get_all_active_schedules()
        self.assertEqual(len(active_after), 0)

    async def test_hermes_provider_init(self):
        """Uji inisialisasi dan konfigurasi provider Hermes AI."""
        from summarizer import ChatSummarizer
        config.AI_PROVIDER = "hermes"
        config.HERMES_MODEL = "nousresearch/hermes-3-llama-3.1-8b:free"
        
        summarizer = ChatSummarizer()
        self.assertEqual(summarizer.provider, "hermes")
        self.assertEqual(summarizer.model, "nousresearch/hermes-3-llama-3.1-8b:free")

    async def test_multi_bot_simulator_scenarios(self):
        """Uji skenario preset pada Multi-Bot Simulator."""
        from multi_bot_simulator import PRESET_SCENARIOS, PERSONAS
        self.assertIn("sprint", PRESET_SCENARIOS)
        self.assertIn("incident", PRESET_SCENARIOS)
        self.assertIn("design", PRESET_SCENARIOS)
        self.assertIn("casual", PRESET_SCENARIOS)
        
        # Pastikan persona index valid
        for sc_name, dialogue in PRESET_SCENARIOS.items():
            self.assertGreater(len(dialogue), 0)
            for item in dialogue:
                self.assertLess(item["persona_idx"], len(PERSONAS))

if __name__ == "__main__":
    unittest.main()
