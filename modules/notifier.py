"""
modules/notifier.py
====================
Modul notifikasi Telegram dan Discord untuk Pinterest Auto-Upload Bot.
Mengirim pesan ke Telegram dan/atau Discord saat program mulai, ganti akun,
selesai, progress update, atau terjadi error kritis.

Notifikasi bersifat opsional — jika token/URL kosong,
semua fungsi akan skip secara silent tanpa error.
"""

import html

import requests
from datetime import datetime, timezone


def _esc(text) -> str:
    """Escape string untuk HTML Telegram agar mencegah injection."""
    return html.escape(str(text))


# ============================================================
# TELEGRAM FUNCTIONS
# ============================================================

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
        f"▶️ Akun aktif: {_esc(akun_pertama)}\n\n"
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
        f"❌ Akun selesai: {_esc(akun_lama)} ({upload_count} pin)\n"
        f"✅ Akun baru: {_esc(akun_baru)}\n"
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
    akun_list = "\n".join([f"  • {_esc(a)}" for a in akun_digunakan])
    message = (
        "✅ <b>Pinterest Bot Selesai</b>\n\n"
        f"📅 Waktu: {now}\n"
        f"⏱ Durasi: {_esc(durasi)}\n"
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
    akun_info = f"\n👤 Akun: {_esc(akun)}" if akun else ""
    message = (
        "⚠️ <b>Pinterest Bot Error</b>\n\n"
        f"📅 Waktu: {now}{akun_info}\n"
        f"❗ Error: {_esc(error_msg)}\n\n"
        "Program membutuhkan perhatian."
    )
    return send_telegram(bot_token, chat_id, message)


# ============================================================
# DISCORD FUNCTIONS
# ============================================================

# Warna embed Discord
DISCORD_COLOR_GREEN = 3066993     # Sukses
DISCORD_COLOR_RED = 15158332      # Error
DISCORD_COLOR_YELLOW = 16776960   # Warning
DISCORD_COLOR_BLUE = 3447003      # Info


def send_discord(webhook_url: str, title: str, message: str,
                 color: int = DISCORD_COLOR_BLUE,
                 fields: list[dict] | None = None) -> bool:
    """
    Kirim embed message ke Discord via Webhook.
    
    Args:
        webhook_url: URL Discord Webhook
        title: Judul embed
        message: Deskripsi/pesan utama embed
        color: Warna embed (integer decimal Discord)
               - Hijau (sukses)  = 3066993
               - Merah (error)   = 15158332
               - Kuning (warning)= 16776960
               - Biru (info)     = 3447003
        fields: List dict field embed Discord, format:
                [{"name": str, "value": str, "inline": bool}]
    
    Returns:
        True jika berhasil, False jika gagal atau tidak dikonfigurasi
    """
    if not webhook_url:
        return False
    
    try:
        embed = {
            "title": title,
            "description": message,
            "color": color,
            "footer": {"text": "Pinterest Bot by www.kumpulenak.web.id"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        if fields:
            embed["fields"] = fields
        
        payload = {"embeds": [embed]}
        
        response = requests.post(webhook_url, json=payload, timeout=10)
        return response.status_code in (200, 204)
    except Exception as e:
        print(f"[WARNING] Gagal kirim notifikasi Discord: {e}")
        return False


# ============================================================
# UNIFIED NOTIFICATION WRAPPER
# ============================================================

def send_all_notifications(config: dict, event: str, **kwargs) -> None:
    """
    Kirim notifikasi ke Telegram DAN Discord sekaligus.
    
    Ini adalah wrapper tunggal yang memanggil kedua platform notifikasi
    berdasarkan event type. Main.py cukup memanggil fungsi ini saja.
    
    Args:
        config: Dictionary konfigurasi dari config.json (berisi token/URL)
        event: Jenis event, salah satu dari:
               - "start": Program mulai
               - "switch": Ganti akun
               - "progress": Progress update (tiap 10 pin)
               - "done": Program selesai
               - "error": Error kritis
        **kwargs: Parameter tambahan sesuai event:
            start: total_foto, total_akun, akun_pertama, foto_folder, estimasi
            switch: akun_lama, akun_baru, upload_count
            progress: akun_aktif, upload_count, max_upload, sisa_foto, board
            done: total_sukses, total_gagal, durasi, akun_digunakan
            error: error_msg, akun, foto_terakhir
    """
    tg_token = config.get("telegram_bot_token", "")
    tg_chat_id = config.get("telegram_chat_id", "")
    discord_url = config.get("discord_webhook_url", "")
    
    if event == "start":
        total_foto = kwargs.get("total_foto", 0)
        total_akun = kwargs.get("total_akun", 0)
        akun_pertama = kwargs.get("akun_pertama", "")
        foto_folder = kwargs.get("foto_folder", "")
        estimasi = kwargs.get("estimasi", "")
        
        # Telegram
        notify_start(tg_token, tg_chat_id, total_foto, total_akun, akun_pertama)
        
        # Discord
        send_discord(
            discord_url,
            title="🤖 Pinterest Bot Dimulai",
            message="Bot mulai mengupload pin ke Pinterest.",
            color=DISCORD_COLOR_BLUE,
            fields=[
                {"name": "📁 Folder Foto", "value": foto_folder or "-", "inline": True},
                {"name": "📸 Total Foto", "value": str(total_foto), "inline": True},
                {"name": "👤 Total Akun", "value": str(total_akun), "inline": True},
                {"name": "⏱️ Estimasi Durasi", "value": estimasi or "-", "inline": True},
            ],
        )
    
    elif event == "switch":
        akun_lama = kwargs.get("akun_lama", "")
        akun_baru = kwargs.get("akun_baru", "")
        upload_count = kwargs.get("upload_count", 0)
        
        # Telegram
        notify_switch(tg_token, tg_chat_id, akun_lama, akun_baru, upload_count)
        
        # Discord
        send_discord(
            discord_url,
            title="🔄 Ganti Akun Pinterest",
            message="Akun mencapai batas upload, beralih ke akun berikutnya.",
            color=DISCORD_COLOR_YELLOW,
            fields=[
                {"name": "❌ Akun Sebelumnya", "value": akun_lama, "inline": True},
                {"name": "✅ Akun Baru", "value": akun_baru, "inline": True},
                {"name": "📤 Upload Akun Sebelumnya", "value": f"{upload_count} pin", "inline": True},
            ],
        )
    
    elif event == "progress":
        akun_aktif = kwargs.get("akun_aktif", "")
        upload_count = kwargs.get("upload_count", 0)
        max_upload = kwargs.get("max_upload", 50)
        sisa_foto = kwargs.get("sisa_foto", 0)
        board = kwargs.get("board", "")
        
        # Discord only (tiap 10 pin, tidak perlu Telegram)
        send_discord(
            discord_url,
            title="✅ Progress Upload",
            message="Update progress upload pin Pinterest.",
            color=DISCORD_COLOR_GREEN,
            fields=[
                {"name": "👤 Akun Aktif", "value": akun_aktif, "inline": True},
                {"name": "📤 Upload", "value": f"{upload_count}/{max_upload}", "inline": True},
                {"name": "📸 Sisa Foto", "value": f"{sisa_foto} foto", "inline": True},
                {"name": "📋 Board", "value": board, "inline": True},
            ],
        )
    
    elif event == "skip":
        akun_skip = kwargs.get("akun_skip", "")
        alasan = kwargs.get("alasan", "unknown")
        akun_baru = kwargs.get("akun_baru", "tidak ada")
        foto_gagal = kwargs.get("foto_gagal", "")
        
        # Telegram
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        tg_message = (
            f"⚠️ <b>Akun Di-Skip</b>\n\n"
            f"📅 Waktu: {now}\n"
            f"👤 Akun: {_esc(akun_skip)}\n"
            f"❗ Alasan: {_esc(alasan)}\n"
            f"➡️ Akun berikutnya: {_esc(akun_baru)}\n"
        )
        if foto_gagal:
            tg_message += f"📸 Foto gagal: {_esc(foto_gagal)}\n"
        send_telegram(tg_token, tg_chat_id, tg_message)
        
        # Discord (warna kuning = warning)
        fields = [
            {"name": "👤 Email Akun", "value": akun_skip, "inline": True},
            {"name": "❗ Alasan Skip", "value": alasan, "inline": True},
            {"name": "➡️ Akun Berikutnya", "value": akun_baru, "inline": True},
        ]
        if foto_gagal:
            fields.append({"name": "📸 Foto Gagal", "value": foto_gagal, "inline": True})
        
        send_discord(
            discord_url,
            title="⚠️ Akun Di-Skip",
            message="Akun tidak bisa digunakan, dilompati ke akun berikutnya.",
            color=DISCORD_COLOR_YELLOW,
            fields=fields,
        )
    
    elif event == "done":
        total_sukses = kwargs.get("total_sukses", 0)
        total_gagal = kwargs.get("total_gagal", 0)
        durasi = kwargs.get("durasi", "")
        akun_digunakan = kwargs.get("akun_digunakan", [])
        total_foto = kwargs.get("total_foto", 0)
        foto_sisa = kwargs.get("foto_sisa", 0)
        akun_diskip = kwargs.get("akun_diskip", [])
        
        # Telegram
        notify_done(tg_token, tg_chat_id, total_sukses, total_gagal, 
                   durasi, akun_digunakan)
        
        # Discord (enhanced)
        akun_str = ", ".join(akun_digunakan) if akun_digunakan else "-"
        fields = [
            {"name": "✅ Total Sukses", "value": str(total_sukses), "inline": True},
            {"name": "❌ Total Gagal", "value": str(total_gagal), "inline": True},
            {"name": "⏱️ Durasi", "value": durasi, "inline": True},
            {"name": "👤 Akun Digunakan", "value": akun_str, "inline": False},
        ]
        if total_foto:
            fields.insert(0, {"name": "📸 Total Foto", 
                             "value": f"{total_sukses + total_gagal}/{total_foto}", "inline": True})
        if foto_sisa > 0:
            fields.append({"name": "📸 Foto Belum Upload", 
                          "value": f"{foto_sisa} foto", "inline": True})
        if akun_diskip:
            fields.append({"name": "⚠️ Akun Di-Skip", 
                          "value": ", ".join(akun_diskip), "inline": False})
        
        send_discord(
            discord_url,
            title="🎉 Pinterest Bot Selesai",
            message="Semua pin telah selesai diproses.",
            color=DISCORD_COLOR_GREEN,
            fields=fields,
        )
    
    elif event == "error":
        error_msg = kwargs.get("error_msg", "Unknown error")
        akun = kwargs.get("akun", "")
        foto_terakhir = kwargs.get("foto_terakhir", "")
        
        # Telegram
        notify_error(tg_token, tg_chat_id, error_msg, akun)
        
        # Discord
        fields = [
            {"name": "❗ Jenis Error", "value": error_msg, "inline": False},
        ]
        if akun:
            fields.append({"name": "👤 Akun Aktif", "value": akun, "inline": True})
        if foto_terakhir:
            fields.append({"name": "📸 Foto Terakhir", "value": foto_terakhir, "inline": True})
        
        send_discord(
            discord_url,
            title="❌ Error Pinterest Bot",
            message="Terjadi error saat menjalankan bot.",
            color=DISCORD_COLOR_RED,
            fields=fields,
        )
