import os
import sys
import subprocess
import threading
import signal
import time

# Force UTF-8 encoding for Windows console output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def stream_output(process, prefix):
    """Membaca output dari subprocess baris per baris dan mencetak dengan prefix."""
    try:
        for line in iter(process.stdout.readline, ''):
            if not line:
                break
            print(f"[{prefix}] {line.rstrip()}", flush=True)
    except Exception as e:
        print(f"[{prefix}] Error membaca output: {e}", flush=True)

def main():
    print("=" * 65)
    print("   🤖 N.I.E.R AI - MASTER BOT RUNNER (ONLINE & RAHASIA)")
    print("=" * 65)
    print("  • [BOT ONLINE]  : bot.py (Telegram Bot Public / Command /satpam dll)")
    print("  • [BOT RAHASIA] : userbot_summarizer.py --listen (Silent Listener Grup)")
    print("=" * 65 + "\n")

    python_executable = sys.executable
    script_dir = os.path.dirname(os.path.abspath(__file__))

    bot_py = os.path.join(script_dir, "bot.py")
    userbot_py = os.path.join(script_dir, "userbot_summarizer.py")

    if not os.path.exists(bot_py) or not os.path.exists(userbot_py):
        print("❌ Error: bot.py atau userbot_summarizer.py tidak ditemukan!")
        sys.exit(1)

    processes = []

    # Command dengan opsi -u agar log tercetak real-time tanpa buffering
    commands = [
        ("BOT ONLINE", [python_executable, "-u", bot_py]),
        ("BOT RAHASIA", [python_executable, "-u", userbot_py, "--listen"])
    ]

    for name, cmd in commands:
        print(f"▶️ Menjalankan {name}...")
        proc = subprocess.Popen(
            cmd,
            cwd=script_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1
        )
        processes.append((name, proc))

        t = threading.Thread(target=stream_output, args=(proc, name), daemon=True)
        t.start()

    print("\n=========================================================")
    print("✅ KEDUA BOT BERHASIL DIJALANKAN SECARA BERSAMAAN!")
    print("📌 Tekan Ctrl+C untuk menghentikan seluruh bot.")
    print("=========================================================\n")

    def handle_signal(sig, frame):
        print("\n🛑 Mematikan semua layanan bot...")
        for name, proc in processes:
            print(f"   Menghentikan {name}...")
            try:
                proc.terminate()
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while True:
            time.sleep(2)
            for name, proc in processes:
                poll = proc.poll()
                if poll is not None:
                    print(f"⚠️ WARNING: [{name}] terhenti (Exit Code: {poll})")
    except KeyboardInterrupt:
        handle_signal(None, None)

if __name__ == "__main__":
    main()
