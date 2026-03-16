# 📌 Pinterest Auto-Upload Bot

Bot otomatis untuk mengupload pin ke Pinterest menggunakan Selenium WebDriver.
Mendukung multi-akun, watermark otomatis, auto-hashtag, dan banyak fitur lainnya.

## 🚀 Fitur Utama

- ✅ **Multi-Akun dengan Rotasi Otomatis** — Ganti akun otomatis saat batas upload tercapai
- ✅ **Chrome Profile per Akun** — Sesi login tersimpan permanen, tidak perlu login ulang
- ✅ **Auto-Watermark** — Teks watermark otomatis ditambahkan ke pojok kanan bawah foto
- ✅ **Optimasi Gambar** — Resize & kompresi otomatis, konversi PNG/WEBP ke JPEG
- ✅ **Auto-Hashtag** — Ekstrak hashtag otomatis dari nama file foto
- ✅ **Anti-Deteksi Bot** — Undetected ChromeDriver, rotasi User-Agent, random delay
- ✅ **Retry Mechanism** — Upload gagal dicoba ulang hingga 3 kali
- ✅ **Resume Upload** — Jika program dihentikan, lanjutkan dari foto terakhir
- ✅ **Dashboard CLI Real-Time** — Progress bar & tabel status dengan warna
- ✅ **Notifikasi Telegram** — Kirim notifikasi ke Telegram (opsional)
- ✅ **Logging CSV** — Semua upload tercatat di `upload_log.csv`

## 📋 Persyaratan Sistem

- **Python** 3.10 atau lebih baru
- **Google Chrome** terinstal (versi terbaru disarankan)
- **Windows 10/11** (disarankan, bisa juga di Linux/Mac)
- **Koneksi internet** yang stabil

## 📦 Instalasi

### 1. Clone atau Download Project

```bash
cd "e:\00 projek rumah\antigravity\pinterest auto\pinterest_bot"
```

### 2. Buat Virtual Environment (Disarankan)

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Konfigurasi

Edit file `config.json` sesuai kebutuhan Anda:

```json
{
  "foto_folder": "C:/Users/NamaAnda/Pictures/PinterestUpload",
  "max_upload_per_akun": 50,
  "delay_min": 8,
  "delay_max": 20,
  "headless_mode": false,
  "max_hashtag": 10,
  "deskripsi_mode": "auto",
  "watermark_text": "www.roxy.my.id",
  "watermark_opacity": 0.8,
  "telegram_bot_token": "",
  "telegram_chat_id": "",
  "accounts": [
    {
      "email": "emailanda@gmail.com",
      "password": "passwordanda",
      "board": "Nama Board Pinterest",
      "chrome_profile_path": "C:/ChromeProfiles/akun1",
      "deskripsi_template": "Follow untuk konten lebih lanjut!"
    }
  ]
}
```

## ⚙️ Penjelasan Konfigurasi

| Field | Deskripsi | Default |
|-------|-----------|---------|
| `foto_folder` | Path folder yang berisi foto-foto untuk diupload | *(wajib)* |
| `max_upload_per_akun` | Batas maksimum upload per akun sebelum rotasi | `50` |
| `delay_min` | Delay minimum antar upload (detik) | `8` |
| `delay_max` | Delay maksimum antar upload (detik) | `20` |
| `headless_mode` | Jalankan Chrome tanpa tampilan (true/false) | `false` |
| `max_hashtag` | Jumlah maksimum hashtag per pin | `10` |
| `deskripsi_mode` | Mode deskripsi: `"auto"` atau `"manual"` | `"auto"` |
| `watermark_text` | Teks watermark yang ditambahkan ke foto | `"www.roxy.my.id"` |
| `watermark_opacity` | Transparansi watermark (0.0 - 1.0) | `0.8` |
| `telegram_bot_token` | Token bot Telegram (kosongkan jika tidak menggunakan) | `""` |
| `telegram_chat_id` | Chat ID Telegram (kosongkan jika tidak menggunakan) | `""` |

### Konfigurasi Per Akun

| Field | Deskripsi |
|-------|-----------|
| `email` | Email akun Pinterest |
| `password` | Password akun Pinterest |
| `board` | Nama board tujuan upload |
| `chrome_profile_path` | Path folder Chrome Profile untuk menyimpan sesi |
| `deskripsi_template` | Template deskripsi yang ditambahkan di setiap pin |

## 🎯 Cara Penggunaan

### 1. Siapkan Foto

Letakkan foto-foto yang ingin diupload ke folder yang sudah dikonfigurasi di `foto_folder`.
Format yang didukung: **JPG, JPEG, PNG, WEBP, GIF**.

### 2. Jalankan Program

```bash
python main.py
```

### 3. Alur Program

1. Program membaca `config.json`
2. Memindai folder foto dan memfilter yang sudah pernah diupload
3. Menambahkan watermark dan mengoptimasi semua foto
4. Menampilkan informasi upload dan meminta konfirmasi
5. Mulai upload dengan rotasi akun otomatis
6. Menampilkan summary di akhir

## 📁 Struktur File

```
pinterest_bot/
├── main.py                → File utama menjalankan program
├── config.json            → Konfigurasi akun dan pengaturan
├── upload_log.csv         → Log semua upload (auto-dibuat)
├── requirements.txt       → Daftar library Python
├── README.md              → Dokumentasi (file ini)
└── modules/
    ├── __init__.py        → Package init
    ├── browser.py         → Chrome driver + stealth + profile
    ├── pinterest.py       → Login, logout, upload pin
    ├── file_manager.py    → Scan foto + watermark + optimasi
    ├── hashtag.py         → Auto-hashtag dari nama file
    ├── logger.py          → Logging CSV + dashboard CLI
    └── notifier.py        → Notifikasi Telegram
```

## 📸 Proses Foto

Sebelum diupload, setiap foto melewati pipeline:

```
Foto Asli → Watermark → Optimasi → Upload
```

- **Watermark**: Teks ditambahkan di pojok kanan bawah dengan shadow hitam
- **Optimasi**: Resize jika > 10MB, konversi PNG/WEBP ke JPEG
- Foto asli **TIDAK** dimodifikasi
- Hasil disimpan di subfolder `watermarked/` dan `optimized/`

## 🏷️ Auto-Hashtag

Hashtag diekstrak otomatis dari nama file:

```
File   : sunset_beach_bali_golden_hour.jpg
Judul  : Sunset Beach Bali Golden Hour
Hashtag: #sunset #beach #bali #golden #hour
```

Kata umum seperti "the", "and", "img", "photo" otomatis difilter.

## 🔔 Notifikasi Telegram (Opsional)

1. Buat bot Telegram via [@BotFather](https://t.me/BotFather)
2. Dapatkan `bot_token` dan `chat_id`
3. Isi di `config.json`:

```json
{
  "telegram_bot_token": "123456:ABC-DEF...",
  "telegram_chat_id": "123456789"
}
```

Notifikasi dikirim saat:
- Program mulai berjalan
- Ganti akun
- Program selesai (dengan summary)
- Terjadi error kritis

## ⚠️ Catatan Penting

1. **Keamanan**: Password disimpan dalam plaintext di `config.json`. 
   Jangan share file ini!
2. **Pinterest ToS**: Bot ini melakukan browser automation yang mungkin 
   melanggar Terms of Service Pinterest. Gunakan dengan risiko sendiri.
3. **CAPTCHA**: Jika Pinterest menampilkan CAPTCHA, program akan pause 
   dan meminta Anda menyelesaikannya secara manual.
4. **Chrome Profile**: Setiap akun menggunakan Chrome Profile terpisah. 
   Pastikan path-nya berbeda untuk setiap akun.
5. **Rate Limit**: Gunakan delay yang wajar (minimal 8-20 detik) untuk 
   menghindari deteksi bot.

## 🐛 Troubleshooting

| Masalah | Solusi |
|---------|--------|
| Chrome tidak terbuka | Pastikan Google Chrome terinstal dan versi terbaru |
| Login gagal | Cek email/password di config.json, selesaikan CAPTCHA manual |
| Upload gagal terus | Cek koneksi internet, coba tambah delay |
| Foto tidak terdeteksi | Pastikan format foto didukung (JPG/PNG/WEBP/GIF) |
| ModuleNotFoundError | Jalankan `pip install -r requirements.txt` |
| ChromeDriver error | Update Chrome ke versi terbaru, hapus folder Chrome Profile |

## 📄 Lisensi

Project ini dibuat untuk keperluan pribadi. Gunakan dengan bijak dan 
tanggung jawab sendiri.

---

**Dibuat oleh**: [roxy.my.id](https://www.roxy.my.id)
