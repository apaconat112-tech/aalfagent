# 🚀 Panduan Deploy Telegram Bot 24/7 di Railway

Dokumen ini berisi panduan untuk menjalankan Bot Online (`bot.py`) dan Bot Rahasia (`userbot_summarizer.py`) secara **24 jam nonstop di Railway / Docker**, menggunakan Master Runner (`run_all.py`).

---

### 🔑 Environment Variables Yang Dibutuhkan di Cloud:
Di platform Cloud apa pun yang Anda pilih, masukkan variabel dari file `.env` Anda:

| Variable | Nilai / Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | `<TOKEN_BOTFATHER_ANDA>` |
| `TELEGRAM_API_ID` | `<TELEGRAM_API_ID_ANDA>` |
| `TELEGRAM_API_HASH` | `<TELEGRAM_API_HASH_ANDA>` |
| `TELEGRAM_STRING_SESSION` | `<TELEGRAM_STRING_SESSION_ANDA>` |
| `AI_PROVIDER` | `gemini` atau `hermes` |
| `GEMINI_API_KEY` | `<GEMINI_API_KEY_ANDA>` jika memakai Gemini |
| `GEMINI_MODEL` | `gemini-3.6-flash` |
| `HERMES_API_KEY` | `<OPENROUTER_API_KEY_ANDA>` jika memakai Hermes |
| `HERMES_MODEL` | `nex-agi/nex-n2.5-mini:free` |
| `HERMES_BASE_URL` | `https://openrouter.ai/api/v1` |

---

## ⚡ Deploy di Railway

1. **Upload / Push** folder project ini ke akun GitHub Anda.
2. Buka [Railway](https://railway.com/), pilih **New Project** lalu **Deploy from GitHub Repo**.
3. Pilih repository project ini. Railway akan mendeteksi `Dockerfile` secara otomatis.
4. Buka service -> **Variables**, lalu masukkan variabel dari tabel di atas.
5. Deploy/redeploy service. Log akan menampilkan `[BOT ONLINE]` dan `[BOT RAHASIA]` yang berjalan bersamaan.

🎉 **Selesai!** Kedua bot Anda aktif 24/7 di cloud dan laptop boleh dimatikan.

### Catatan penting Railway

- Service ini mendengarkan long-polling Telegram dan Telethon listener secara simultan via `run_all.py`.
- `chat_history.db` di filesystem Railway dapat hilang saat redeploy. Tambahkan Railway Volume jika histori database harus persisten.
- Jangan menjalankan service kedua dengan token bot yang sama.

---

## 🖥️ Alternatif: Deploy di VPS Ubuntu / Debian (Docker)

Jika Anda memiliki VPS (seperti DigitalOcean, Biznet, Linode, dll):

1. Salin seluruh folder project ke VPS.
2. Build Docker container:
   ```bash
   docker build -t telegram-userbot .
   ```
3. Jalankan container 24/7 di background:
   ```bash
   docker run -d --name userbot --restart always telegram-userbot
   ```

---

## 📲 Cara Menggunakan Dari HP (Setelah Deploy):

- **Bot Online (DM / Grup)**:
  - `/start` -> Memulai bot & panduan.
  - `/summary` -> Ringkaskan pesan grup.
  - `/satpam` -> Cek / kelola proteksi grup.

- **Bot Rahasia (Saved Messages / Silent)**:
  - `.sum NamaGrup` -> Ringkas obrolan grup rahasia dari HP.
  - `.grup` -> Daftar grup yang diikuti akun Telegram Anda.
