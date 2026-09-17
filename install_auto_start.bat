@echo off
title Install Telegram UserBot Auto-Start
echo Installing Telegram UserBot Auto-Start for Windows Startup...

powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut(\"$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\TelegramUserBot.lnk\"); $Shortcut.TargetPath = \"c:\aiagent\start_invisible.vbs\"; $Shortcut.WorkingDirectory = \"c:\aiagent\"; $Shortcut.Save()"

echo.
echo =========================================================
echo ✅ BERHASIL! UserBot Telegram telah ditambahkan ke Windows Startup.
echo.
echo 📌 Setiap kali laptop menyala/booting, UserBot akan otomatis
echo    berjalan di latar belakang (tanpa jendela hitam/terminal).
echo.
echo 📌 Anda tinggal buka Telegram dari HP & ketik:
echo    • /rangkum NamaGrup
echo    • /grup
echo =========================================================
echo.
pause
