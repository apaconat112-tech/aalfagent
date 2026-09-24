@echo off
title Install Telegram Bots Auto-Start (Online & Rahasia)
echo Installing Telegram Bots Auto-Start for Windows Startup...

powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut(\"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\TelegramUserBot.lnk\"); $Shortcut.TargetPath = \"c:\aiagent\start_invisible.vbs\"; $Shortcut.WorkingDirectory = \"c:\aiagent\"; $Shortcut.Save()"

echo.
echo =========================================================
echo ✅ BERHASIL! Bot Online & Bot Rahasia telah ditambahkan ke Windows Startup.
echo.
echo 📌 Setiap kali laptop menyala/booting, KEDUA BOT akan otomatis
echo    berjalan di latar belakang (tanpa jendela terminal).
echo.
echo 📌 Bot Online  : Siap merespons perintah Telegram (/satpam, /summary, dll)
echo 📌 Bot Rahasia : Silent listener membaca obrolan grup secara otomatis
echo =========================================================
echo.
pause
