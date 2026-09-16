# 🚀 Panduan Deploy UserBot 24/7 (Laptop Mati Tetap Nyala)

Dokumen ini berisi panduan langkah demi langkah untuk menjalankan Telegram UserBot Anda secara **24 jam nonstop di Cloud (Server)** sehingga Anda bisa mengontrolnya dari HP kapan saja tanpa perlu laptop menyala.

---

### 🔑 Environment Variables Yang Dibutuhkan di Cloud:
Di platform Cloud apa pun yang Anda pilih, masukkan variabel dari file `.env` Anda:

| Variable | Nilai / Value |
|---|---|
| `TELEGRAM_API_ID` | `<TELEGRAM_API_ID_ANDA>` |
| `TELEGRAM_API_HASH` | `<TELEGRAM_API_HASH_ANDA>` |
| `TELEGRAM_STRING_SESSION` | `<TELEGRAM_STRING_SESSION_ANDA>` |
| `AI_PROVIDER` | `hermes` |
| `HERMES_API_KEY` | `<OPENROUTER_API_KEY_ANDA>` |
| `HERMES_MODEL` | `openrouter/auto` |
| `HERMES_BASE_URL` | `https://openrouter.ai/api/v1` |

---

## ⚡ PILIHAN 1: Deploy Gratis di Koyeb.com / Render.com (Paling Mudah)

1. **Upload / Push** folder project ini ke akun GitHub Anda.
2. Buka [Koyeb.com](https://www.koyeb.com/) atau [Render.com](https://render.com/) (Daftar Gratis).
3. Buat Service baru -> Pilih **GitHub Repository** yang berisi kodingan Anda.
4. Pilih **Dockerfile** (otomatis terdeteksi dari `Dockerfile` di project).
5. Masukkan **Environment Variables** dari tabel di atas.
6. Klik **Deploy**! 

🎉 **Selesai!** UserBot Anda akan aktif 24/7 di Cloud. Anda bisa matikan laptop kapan saja.

---

## 🖥️ PILIHAN 2: Deploy di VPS Ubuntu / Debian (Docker)

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

Buka Telegram di HP Anda -> Buka **Pesan Tersimpan (Saved Messages)**:
- Ketik `/grup` -> Untuk melihat daftar grup Anda.
- Ketik `/rangkum NamaGrup` -> Meringkas 1000 pesan grup secara rahasia!
