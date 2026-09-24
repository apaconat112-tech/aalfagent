@echo off
title N.I.E.R AI - Launcher
color 0A
cls

echo ============================================================
echo   N.I.E.R AI - Starting All Services
echo ============================================================
echo.
echo [1/2] Menjalankan Telegram Bot (bot.py)...
start "NIER - Telegram Bot" cmd /k "cd /d %~dp0 && echo. && echo === NIER Telegram Bot === && echo. && .\venv\Scripts\python.exe bot.py"

timeout /t 2 /nobreak >nul

echo [2/2] Menjalankan UserBot Listener (userbot_summarizer.py --listen)...
start "NIER - UserBot Listener" cmd /k "cd /d %~dp0 && echo. && echo === NIER UserBot Listener === && echo. && .\venv\Scripts\python.exe userbot_summarizer.py --listen"

echo.
echo ============================================================
echo   Kedua layanan sudah berjalan di window terpisah!
echo.
echo   Window 1: Telegram Bot  (menerima perintah /summary dll)
echo   Window 2: UserBot       (silent listener grup private)
echo.
echo   Tutup window ini, atau tekan tombol apapun untuk keluar.
echo ============================================================
pause >nul
