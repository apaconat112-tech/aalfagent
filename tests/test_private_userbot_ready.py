import asyncio
import importlib
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bot
import config


class FakeClient:
    def __init__(self, session, api_id, api_hash, receive_updates=False):
        self.session = session
        self.api_id = api_id
        self.api_hash = api_hash
        self.receive_updates = receive_updates

    async def connect(self):
        return None

    async def is_user_authorized(self):
        return True

    async def disconnect(self):
        return None


def test_private_userbot_ready(monkeypatch):
    monkeypatch.setattr(bot.config, "TELEGRAM_STRING_SESSION", "abc123")
    monkeypatch.setattr(bot.config, "TELEGRAM_API_ID", "123")
    monkeypatch.setattr(bot.config, "TELEGRAM_API_HASH", "hash")

    fake_telethon = types.SimpleNamespace(TelegramClient=FakeClient)
    fake_sessions = types.SimpleNamespace(StringSession=lambda value: value)

    monkeypatch.setitem(sys.modules, "telethon", fake_telethon)
    monkeypatch.setitem(sys.modules, "telethon.sessions", fake_sessions)

    assert asyncio.run(bot.private_userbot_ready()) is True


def test_summary_command_prefers_private_userbot_in_dm(monkeypatch):
    calls = {}

    class FakeChat:
        id = 101
        type = "private"

    class FakeMessage:
        message_id = 77

    async def fake_private_ready():
        return True

    async def fake_private_summary(update, context, raw_input, reply_to_id):
        calls["raw_input"] = raw_input
        calls["reply_to_id"] = reply_to_id

    monkeypatch.setattr(bot, "private_userbot_ready", fake_private_ready)
    monkeypatch.setattr(bot, "perform_private_userbot_summary", fake_private_summary)

    update = types.SimpleNamespace(
        effective_message=FakeMessage(),
        effective_chat=FakeChat(),
    )
    context = types.SimpleNamespace(args=[], bot=None)

    asyncio.run(bot.summary_command(update, context))

    assert calls == {"raw_input": "24h", "reply_to_id": 77}


def test_database_path_is_absolute_and_project_relative(monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", "chat_history.db")
    reloaded = importlib.reload(config)

    resolved = Path(reloaded.DATABASE_PATH)
    assert resolved.is_absolute()
    assert resolved.name == "chat_history.db"
    assert resolved.parent == Path(__file__).resolve().parents[1]

    importlib.reload(config)
