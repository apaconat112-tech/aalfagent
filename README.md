# 🤖 Telegram Chat Summarizer Bot

AI Agent autonomous berbasis Telegram yang membaca riwayat obrolan grup dan membuat ringkasan komprehensif berbobot tinggi (Topik Utama, Keputusan, Action Items + PIC, dan Link penting) menggunakan model **Claude 3.5 Sonnet** dari Anthropic.

---

## 🎯 Solusi & Manfaat
- **Mengatasi Chat Menumpuk**: Tidak perlu lagi menghabiskan waktu 15–30 menit sehari hanya untuk *scrolling* ratusan pesan grup.
- **Tindak Lanjut Jelas**: Setiap keputusan dan *action item* langsung diidentifikasi lengkap dengan PIC yang bertanggung jawab.
- **Hemat Waktu**: Membaca rangkuman lengkap selesai dalam **di bawah 2 menit**.

---

## 📋 Fitur Utama
1. **Penyimpanan Histori Otomatis**: Menyimpan pesan grup ke database SQLite (`database.py`) secara *asynchronous* dan efisien.
2. **On-Demand Summary (`/summary`)**:
   - `/summary` — Meringkas obrolan sejak ringkasan terakhir (atau 24 jam terakhir secara *default*).
   - `/summary 6h` / `/summary 2d` — Meringkas obrolan dalam rentang waktu tertentu.
3. **Ringkasan Terjadwal (`/schedule <jam>`)**:
   - Contoh: `/schedule 4` — Bot akan mengirimkan ringkasan berkala setiap 4 jam secara otomatis ke grup.
   - `/unschedule` — Menonaktifkan jadwal otomatis.
4. **Hierarchical / Map-Reduce Chunking**: Mampu menangani volume chat tinggi (ratusan hingga ribuan pesan) tanpa batasan token context LLM.
5. **Auto-Cleanup**: Pembersihan otomatis pesan lama di atas 30 hari untuk menjaga database tetap ringan.

---

## 🏗 Struktur Project
```text
c:\aiagent\
├── bot.py             # Entry point bot Telegram & event handlers
├── database.py        # Database engine SQLite & manajemen pesan (aiosqlite)
├── summarizer.py      # Integrasi Anthropic Claude API, chunking, & prompt engine
├── config.py          # Pengaturan & validasi environment variables
├── requirements.txt   # Daftar dependensi Python
├── .env.example       # Template konfigurasi environment
├── test_bot.py        # Unit tests untuk validasi fungsi database & transcript
└── README.md          # Panduan instalasi dan penggunaan
```

---

## 🚀 Panduan Setup Langkah Demi Langkah

### Alternatif Node.js

Versi Node.js tersedia di `bot.js` dan menggunakan file `.env` serta database SQLite yang sama.

```bash
npm install
npm start
```

Untuk validasi sintaks dan menjalankan simulator:

```bash
npm run check
npm run simulate -- --chat-id -100123456789 --topic "Persiapan rilis produk" --turns 6 --delay 3
```

Node.js 20 atau yang lebih baru direkomendasikan. Fitur utama bot sudah dipindahkan: penyimpanan histori, `/summary`, `/schedule`, `/unschedule`, `/groups`, `/model`, chat interaktif, terjemahan reply, chunking ringkasan, dan cleanup database. `userbot_summarizer.py` masih memakai Telethon Python karena login MTProto/session Telegram memerlukan alur terpisah.

### 1. Buat Bot di Telegram (@BotFather)
1. Buka Telegram dan cari akun **[@BotFather](https://t.me/BotFather)**.
2. Ketik `/newbot`, lalu ikuti petunjuk untuk memberikan nama bot dan username (misal: `my_summarizer_bot`).
3. Simpan **Bot Token** (contoh: `7123456789:ABCDefgh-1234...`).
4. **PENTING (Group Privacy Mode):**
   - Agar bot bisa membaca seluruh pesan dalam grup (bukan hanya saat di-mention), jalankan perintah:
     ```text
     /setprivacy -> Pilih Bot Anda -> Disable
     ```
   - BotFather akan merespons: `Success! The new status is: DISABLED.`

---

### 2. Dapatkan API Key AI

#### Pilihan A: Google Gemini API (**100% GRATIS** - Rekomendasi)
1. Kunjungi [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Login dengan akun Google/Gmail biasa.
3. Klik **Create API Key**, lalu salin API key Anda.
4. Tanpa perlu kartu kredit!

#### Pilihan B: Anthropic Claude
1. Kunjungi [Anthropic Console](https://console.anthropic.com/).
2. Buat akun / login, lalu buka menu **API Keys**.
3. Klik **Create Key** dan salin token API Key Anda (`sk-ant-api03-...`).

---

### 3. Setup Lingkungan & Dependensi
Pastikan Anda telah menginstal **Python 3.11+**.

```bash
# Masuk ke direktori project
cd c:\aiagent

# (Opsional tapi direkomendasikan) Buat virtual environment
python -m venv venv

# Aktifkan virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Install dependensi yang dibutuhkan
pip install -r requirements.txt
```

---

### 4. Konfigurasi `.env`
Salin template `.env.example` menjadi `.env`:

```bash
copy .env.example .env
```

Buka file `.env` dan masukkan token Anda:
```env
TELEGRAM_BOT_TOKEN=7123456789:ABCDefgh-1234...
ANTHROPIC_API_KEY=sk-ant-api03-...
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
DEFAULT_SUMMARY_HOURS=24
DATABASE_PATH=chat_history.db
MAX_MESSAGES_PER_CHUNK=150
```

---

### 5. Menjalankan Bot
Jalankan bot dengan perintah:
```bash
python bot.py
```

Jika berhasil, akan muncul log:
```text
INFO - Database initialized successfully at chat_history.db
INFO - Restoring 0 active schedules...
INFO - Starting Chat Summarizer Bot with model: claude-3-5-sonnet-20241022
```

---

## 📱 Cara Penggunaan di Telegram

1. **Tambahkan bot ke grup Telegram Anda**.
2. Berikan izin standar bagi bot untuk membaca dan mengirim pesan.
3. Bot akan mulai mencatat riwayat obrolan secara otomatis.

### Perintah Tersedia:
| Perintah | Deskripsi |
| :--- | :--- |
| `/summary` | Meringkas obrolan sejak ringkasan terakhir (atau 24 jam terakhir). |
| `/summary 4h` | Meringkas obrolan 4 jam terakhir. |
| `/summary 2d` | Meringkas obrolan 2 hari terakhir. |
| `/schedule <jam>` | Mengaktifkan ringkasan berkala tiap `<jam>` jam (contoh: `/schedule 6`). |
| `/unschedule` | Mematikan ringkasan terjadwal di grup tersebut. |
| `/help` | Menampilkan panduan bantuan bot. |

---

## 🧪 Multi-Bot Live Simulator (Pengujian Obrolan Grup)

Untuk menguji fitur `/summary` pada grup Telegram tanpa perlu menunggu obrolan asli dari user, Anda dapat menggunakan skrip **Multi-Bot Live Simulator** (`multi_bot_simulator.py`).

Skrip ini mensimulasikan obrolan antar beberapa karakter tim secara *live* di grup Telegram Anda dan mencatatnya ke database secara otomatis.

### Karakter Simulasi:
- 👩‍💼 **Siti Rahma** (`@siti_pm`) — Product Manager
- 👨‍💻 **Budi Santoso** (`@budi_dev`) — Senior Backend Lead
- 👨‍🔬 **Andi Wijaya** (`@andi_qa`) — QA Lead
- 👩‍🎨 **Dewi Lestari** (`@dewi_design`) — UI/UX Designer
- 👨‍💻 **Eko Prasetyo** (`@eko_devops`) — DevOps Engineer

### Cara Penggunaan Simulator:

```bash
# 1. Jalankan simulator dengan Skenario Sprint Planning (default)
python multi_bot_simulator.py --chat-id -100123456789 --scenario sprint

# 2. Skenario Penanganan Penanganan Insiden Server (Incident Response)
python multi_bot_simulator.py --chat-id -100123456789 --scenario incident

# 3. Skenario Custom dengan Generasi Obrolan AI
python multi_bot_simulator.py --chat-id -100123456789 --topic "Diskusi persiapan peluncuran produk baru minggu depan"

# 4. Tampilkan daftar Chat ID yang tersimpan di database
python multi_bot_simulator.py --list-chats
```

> 💡 **Opsi Multi-Token (Opsional)**: Jika Anda memiliki beberapa Token Bot dari BotFather, Anda bisa menambahkannya di file `.env`:
> `SIMULATOR_BOT_TOKENS=token1,token2,token3`

---

## 🤫 UserBot Private Summarizer (Meringkas Grup Rahasia Tanpa Perlu Undang Bot ke Grup)

Jika Anda ingin **meringkas grup obrolan asli tanpa mengundang bot ke grup** (100% rahasia, anggota grup lain tidak akan pernah tahu):

1. **Dapatkan API ID & HASH (Gratis dari Telegram)**:
   - Login di **[https://my.telegram.org](https://my.telegram.org)** dengan nomor Telegram Anda.
   - Buka **API development tools**, buat App (bebas nama), lalu salin `api_id` dan `api_hash` ke `.env`:
     ```env
     TELEGRAM_API_ID=12345678
     TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
     ```

2. **Cara Penggunaan**:
   ```bash
   # Lihat daftar semua grup yang Anda ikuti
   .\run_userbot.bat --list-groups

   # Meringkas grup secara rahasia (ringkasan otomatis dikirim ke "Saved Messages" Anda!)
   .\run_userbot.bat --group "Nama Atau ID Grup"
   ```

---

## 📄 Contoh Output Ringkasan

```markdown
📊 RINGKASAN CHAT GRUP
🕒 Periode: 6 jam terakhir
💬 Total Pesan: 48 pesan

📌 TOPIK UTAMA
- Evaluasi bug login di platform mobile versi 2.1.
- Pembagian tugas rilis hotfix ke production hari ini.

✅ KEPUTUSAN & KESEPAKATAN
- Hotfix v2.1.1 akan dideploy sore ini pukul 17:00 WIB setelah lolos staging QA.
- QA regression testing difokuskan pada auth flow OAuth Google.

📋 ACTION ITEMS & TINDAK LANJUT
- Merge PR #142 dan trigger staging build — PIC: @budi_backend
- Testing OAuth flow di Android & iOS — PIC: @siti_qa
- Buat changelog & release note untuk publik — PIC: @andi_pm

🔗 LINK & REFERENSI PENTING
- PR Fix Token Expiry: https://github.com/org/repo/pull/142
- Google Meet Staging Sync: https://meet.google.com/xyz-abcd-efg

— Dibuat otomatis oleh Chat Summarizer Bot
```
