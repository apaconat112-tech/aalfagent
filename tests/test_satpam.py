import unittest
import asyncio
import os
import sys

# Ensure root dir is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database
from bot import extract_domain, extract_urls

class TestSatpamLogic(unittest.TestCase):

    def test_extract_domain(self):
        self.assertEqual(extract_domain("https://github.com/openai/gpt-3"), "github.com")
        self.assertEqual(extract_domain("http://www.google.com/search?q=test"), "google.com")
        self.assertEqual(extract_domain("t.me/mygroup"), "t.me")
        self.assertEqual(extract_domain("sub.example.co.id/path"), "sub.example.co.id")

    def test_extract_urls_regex(self):
        class DummyMsg:
            text = "Silakan kunjungi https://github.com atau www.google.com untuk informasi lebih lanjut."
            caption = None
            entities = []
            caption_entities = []

        urls = extract_urls(DummyMsg())
        self.assertIn("https://github.com", urls)
        self.assertIn("www.google.com", urls)

    def test_database_satpam(self):
        async def run_async_tests():
            # Inisialisasi DB
            await database.init_db()
            test_chat_id = -99912345

            # Reset settings
            await database.set_satpam_settings(test_chat_id, enabled=True, mode="whitelist")
            cfg = await database.get_satpam_settings(test_chat_id)
            self.assertTrue(cfg["enabled"])
            self.assertEqual(cfg["mode"], "whitelist")

            # Add domain whitelist
            res_add = await database.add_whitelist_domain(test_chat_id, "github.com")
            self.assertTrue(res_add)

            domains = await database.get_whitelist_domains(test_chat_id)
            self.assertIn("github.com", domains)

            # Delete domain whitelist
            res_del = await database.remove_whitelist_domain(test_chat_id, "github.com")
            self.assertTrue(res_del)

            domains_after = await database.get_whitelist_domains(test_chat_id)
            self.assertNotIn("github.com", domains_after)

            # Turn off satpam
            await database.set_satpam_settings(test_chat_id, enabled=False, mode="admin_only")
            cfg_off = await database.get_satpam_settings(test_chat_id)
            self.assertFalse(cfg_off["enabled"])

        asyncio.run(run_async_tests())

if __name__ == "__main__":
    unittest.main()
