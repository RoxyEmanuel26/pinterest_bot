"""
modules/notifier.py
====================
Modul notifikasi Telegram untuk Pinterest Auto-Upload Bot.
Mengirim pesan ke Telegram saat program mulai, ganti akun,
selesai, atau terjadi error kritis.

Notifikasi bersifat opsional — jika bot_token atau chat_id kosong,
semua fungsi akan skip secara silent tanpa error.
"""

import requests
from datetime import datetime


def send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    """
    Kirim pesan teks ke Telegram via Bot API.
    
    Args:
        bot_token: Token bot Telegram (dari @BotFather)
        chat_id: Chat ID tujuan (user atau group)
        message: Pesan yang akan dikirim
    
    Returns:
        True jika berhasil, False jika gagal atau tidak dikonfigurasi
    """
    if not bot_token or not chat_id:
        return False
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"[WARNING] Gagal kirim notifikasi Telegram: {e}")
        return False


def notify_start(bot_token: str, chat_id: str, total_foto: int, 
                 total_akun: int, akun_pertama: str) -> bool:
    """
    Kirim notifikasi saat program mulai berjalan.
    
    Args:
        bot_token: Token bot Telegram
        chat_id: Chat ID tujuan
        total_foto: Jumlah foto yang akan diupload
        total_akun: Jumlah akun yang tersedia
        akun_pertama: Email akun pertama yang digunakan
    
    Returns:
        True jika berhasil
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = (
        "🚀 <b>Pinterest Bot Started</b>\n\n"
        f"📅 Waktu: {now}\n"
        f"📸 Total foto: {total_foto}\n"
        f"👤 Total akun: {total_akun}\n"
        f"▶️ Akun aktif: {akun_pertama}\n\n"
        "Bot mulai mengupload pin..."
    )
    return send_telegram(bot_token, chat_id, message)


def notify_switch(bot_token: str, chat_id: str, akun_lama: str, 
                  akun_baru: str, upload_count: int) -> bool:
    """
    Kirim notifikasi saat ganti akun.
    
    Args:
        bot_token: Token bot Telegram
        chat_id: Chat ID tujuan
        akun_lama: Email akun yang baru selesai
        akun_baru: Email akun berikutnya
        upload_count: Jumlah upload akun yang baru selesai
    
    Returns:
        True jika berhasil
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = (
        "🔄 <b>Ganti Akun</b>\n\n"
        f"📅 Waktu: {now}\n"
        f"❌ Akun selesai: {akun_lama} ({upload_count} pin)\n"
        f"✅ Akun baru: {akun_baru}\n"
    )
    return send_telegram(bot_token, chat_id, message)


def notify_done(bot_token: str, chat_id: str, total_sukses: int,
                total_gagal: int, durasi: str, akun_digunakan: list[str]) -> bool:
    """
    Kirim notifikasi saat program selesai dengan summary.
    
    Args:
        bot_token: Token bot Telegram
        chat_id: Chat ID tujuan
        total_sukses: Total pin yang berhasil diupload
        total_gagal: Total pin yang gagal
        durasi: Durasi total program berjalan (format string)
        akun_digunakan: List email akun yang digunakan
    
    Returns:
        True jika berhasil
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    akun_list = "\n".join([f"  • {a}" for a in akun_digunakan])
    message = (
        "✅ <b>Pinterest Bot Selesai</b>\n\n"
        f"📅 Waktu: {now}\n"
        f"⏱ Durasi: {durasi}\n"
        f"✅ Sukses: {total_sukses} pin\n"
        f"❌ Gagal: {total_gagal} pin\n\n"
        f"👤 Akun yang digunakan:\n{akun_list}"
    )
    return send_telegram(bot_token, chat_id, message)


def notify_error(bot_token: str, chat_id: str, error_msg: str,
                 akun: str = "") -> bool:
    """
    Kirim notifikasi saat terjadi error kritis.
    
    Args:
        bot_token: Token bot Telegram
        chat_id: Chat ID tujuan
        error_msg: Pesan error
        akun: Email akun yang sedang aktif (opsional)
    
    Returns:
        True jika berhasil
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    akun_info = f"\n👤 Akun: {akun}" if akun else ""
    message = (
        "⚠️ <b>Pinterest Bot Error</b>\n\n"
        f"📅 Waktu: {now}{akun_info}\n"
        f"❗ Error: {error_msg}\n\n"
        "Program membutuhkan perhatian."
    )
    return send_telegram(bot_token, chat_id, message)
