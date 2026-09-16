@echo off
title Telegram UserBot Listener Mode
echo Starting Telegram UserBot Listener Mode...
.\venv\Scripts\python.exe userbot_summarizer.py --listen %*
pause
