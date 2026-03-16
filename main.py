"""
main.py
========
File utama Pinterest Auto-Upload Bot.
Mengorkestrasi seluruh proses upload pin secara otomatis:
baca config → scan foto → watermark → optimasi → upload → logging.

Penggunaan:
    python main.py

Konfigurasi:
    Edit config.json sebelum menjalankan program.
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta

from rich.console import Console
from rich.prompt import Prompt, Confirm

from modules.browser import create_driver, close_driver, random_delay
from modules.pinterest import is_logged_in, login, logout, upload_pin, upload_with_retry
from modules.file_manager import scan_photos, prepare_photo
from modules.hashtag import generate_title, generate_hashtags, build_description
from modules.logger import (
    UploadLogger, create_progress_bar,
    display_status_table, display_initial_info, display_summary,
    print_success, print_error, print_warning, print_info, console,
)
from modules.notifier import notify_start, notify_switch, notify_done, notify_error


# Path default
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upload_log.csv")


def load_config(config_path: str) -> dict:
    """
    Baca dan validasi file konfigurasi JSON.
    
    Args:
        config_path: Path ke file config.json
    
    Returns:
        Dictionary berisi semua konfigurasi
    
    Raises:
        FileNotFoundError: Jika config.json tidak ditemukan
        json.JSONDecodeError: Jika format JSON tidak valid
    """
    if not os.path.exists(config_path):
        print_error(f"File config tidak ditemukan: {config_path}")
        print_info("Buat file config.json terlebih dahulu. Lihat README.md untuk template.")
        sys.exit(1)
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print_error(f"Format config.json tidak valid: {e}")
        sys.exit(1)
    
    # Validasi field wajib
    required_fields = ["foto_folder", "accounts"]
    for field in required_fields:
        if field not in config:
            print_error(f"Field '{field}' wajib ada di config.json")
            sys.exit(1)
    
    if not config["accounts"]:
        print_error("Minimal 1 akun harus dikonfigurasi di config.json")
        sys.exit(1)
    
    # Set default values
    config.setdefault("max_upload_per_akun", 50)
    config.setdefault("delay_min", 8)
    config.setdefault("delay_max", 20)
    config.setdefault("headless_mode", False)
    config.setdefault("max_hashtag", 10)
    config.setdefault("deskripsi_mode", "auto")
    config.setdefault("watermark_text", "www.roxy.my.id")
    config.setdefault("watermark_opacity", 0.8)
    config.setdefault("telegram_bot_token", "")
    config.setdefault("telegram_chat_id", "")
    
    return config


def get_pending_photos(foto_folder: str, logger: UploadLogger) -> list[str]:
    """
    Scan folder foto dan filter yang belum pernah diupload.
    
    Args:
        foto_folder: Path folder yang berisi foto-foto
        logger: Instance UploadLogger untuk cek upload_log.csv
    
    Returns:
        List path foto yang belum diupload
    """
    all_photos = scan_photos(foto_folder)
    pending = []
    
    for photo_path in all_photos:
        filename = os.path.basename(photo_path)
        if not logger.is_uploaded(filename):
            pending.append(photo_path)
    
    return pending


def preprocess_photos(pending_photos: list[str], foto_folder: str, 
                      config: dict) -> dict[str, str]:
    """
    Proses semua foto pending: watermark + optimasi.
    Mengembalikan mapping dari foto asli ke foto yang sudah diproses.
    
    Args:
        pending_photos: List path foto yang akan diproses
        foto_folder: Path folder foto utama
        config: Dictionary konfigurasi
    
    Returns:
        Dictionary mapping {path_asli: path_processed}
    """
    processed_map = {}
    
    progress = create_progress_bar()
    with progress:
        task = progress.add_task("⚙️  Memproses foto (watermark + optimasi)...", 
                                total=len(pending_photos))
        
        for photo_path in pending_photos:
            try:
                processed_path = prepare_photo(photo_path, foto_folder, config)
                processed_map[photo_path] = processed_path
                progress.update(task, advance=1)
            except Exception as e:
                filename = os.path.basename(photo_path)
                print_warning(f"Gagal memproses {filename}: {e}")
                # Gunakan foto asli jika gagal diproses
                processed_map[photo_path] = photo_path
                progress.update(task, advance=1)
    
    return processed_map


def run_bot():
    """
    Fungsi utama yang menjalankan seluruh alur bot.
    
    Alur:
    1. Baca config.json
    2. Scan folder foto, filter yang belum diupload
    3. Watermark + optimasi semua foto pending
    4. Tampilkan info awal + minta konfirmasi
    5. Loop upload dengan rotasi akun
    6. Summary akhir + notifikasi Telegram
    """
    start_time = datetime.now()
    
    # ===== STEP 1: Baca Config =====
    print_info("Membaca konfigurasi...")
    config = load_config(CONFIG_PATH)
    
    foto_folder = config["foto_folder"]
    max_upload = config["max_upload_per_akun"]
    delay_min = config["delay_min"]
    delay_max = config["delay_max"]
    headless = config["headless_mode"]
    max_hashtag = config["max_hashtag"]
    deskripsi_mode = config.get("deskripsi_mode", "auto")
    telegram_token = config.get("telegram_bot_token", "")
    telegram_chat_id = config.get("telegram_chat_id", "")
    accounts = config["accounts"]
    
    # ===== STEP 2: Scan Foto =====
    print_info(f"Memindai folder foto: {foto_folder}")
    logger = UploadLogger(LOG_PATH)
    
    try:
        pending_photos = get_pending_photos(foto_folder, logger)
    except FileNotFoundError as e:
        print_error(str(e))
        sys.exit(1)
    
    if not pending_photos:
        print_warning("Tidak ada foto baru yang perlu diupload!")
        print_info("Semua foto sudah pernah diupload (tercatat di upload_log.csv)")
        sys.exit(0)
    
    print_success(f"Ditemukan {len(pending_photos)} foto baru untuk diupload")
    
    # ===== STEP 3: Watermark + Optimasi =====
    print_info("Memproses foto (watermark + optimasi)...")
    processed_map = preprocess_photos(pending_photos, foto_folder, config)
    
    # ===== STEP 4: Tampilkan Info Awal =====
    avg_delay = (delay_min + delay_max) / 2
    estimasi_menit = (len(pending_photos) * avg_delay) / 60
    
    display_initial_info(
        total_foto=len(pending_photos),
        total_akun=len(accounts),
        accounts=accounts,
        estimasi_menit=estimasi_menit,
    )
    
    # ===== STEP 5: Konfirmasi User =====
    if not Confirm.ask("  🚀 Mulai upload?", default=True):
        print_info("Upload dibatalkan oleh user.")
        sys.exit(0)
    
    # Tanya mode deskripsi jika 'manual'
    manual_description = None
    if deskripsi_mode == "manual":
        manual_description = Prompt.ask("  ✏️  Masukkan deskripsi untuk semua pin")
    
    # ===== STEP 6: Mulai Upload =====
    console.print()
    print_info("Memulai proses upload...")
    
    # Kirim notifikasi Telegram - program mulai
    notify_start(
        telegram_token, telegram_chat_id,
        total_foto=len(pending_photos),
        total_akun=len(accounts),
        akun_pertama=accounts[0]["email"],
    )
    
    # State variables
    current_account_idx = 0
    total_sukses = 0
    total_gagal = 0
    driver = None
    akun_digunakan = set()
    
    # Cari akun yang masih punya kuota
    for idx, acc in enumerate(accounts):
        count = logger.get_account_upload_count(acc["email"])
        if count < max_upload:
            current_account_idx = idx
            break
    else:
        print_warning("Semua akun sudah mencapai batas upload!")
        notify_error(telegram_token, telegram_chat_id, 
                    "Semua akun sudah mencapai batas upload")
        sys.exit(0)
    
    try:
        # Progress bar untuk upload
        progress = create_progress_bar()
        
        with progress:
            upload_task = progress.add_task(
                "📤 Uploading pins...", 
                total=len(pending_photos)
            )
            
            for i, photo_path in enumerate(pending_photos):
                filename = os.path.basename(photo_path)
                processed_path = processed_map.get(photo_path, photo_path)
                
                # ----- 6a: Cek batas upload akun aktif -----
                current_account = accounts[current_account_idx]
                akun_email = current_account["email"]
                akun_upload_count = logger.get_account_upload_count(akun_email)
                
                if akun_upload_count >= max_upload:
                    # Tutup driver akun lama
                    print_warning(f"Akun {akun_email} mencapai batas ({max_upload} pin)")
                    
                    if driver:
                        close_driver(driver)
                        driver = None
                    
                    # Cari akun berikutnya yang masih punya kuota
                    found_next = False
                    for next_idx in range(current_account_idx + 1, len(accounts)):
                        next_email = accounts[next_idx]["email"]
                        next_count = logger.get_account_upload_count(next_email)
                        if next_count < max_upload:
                            # Kirim notifikasi ganti akun
                            notify_switch(
                                telegram_token, telegram_chat_id,
                                akun_lama=akun_email,
                                akun_baru=next_email,
                                upload_count=akun_upload_count,
                            )
                            current_account_idx = next_idx
                            current_account = accounts[current_account_idx]
                            akun_email = current_account["email"]
                            found_next = True
                            print_info(f"Beralih ke akun: {akun_email}")
                            break
                    
                    if not found_next:
                        print_warning("Semua akun sudah mencapai batas upload!")
                        notify_error(telegram_token, telegram_chat_id,
                                    "Semua akun mencapai batas upload, program berhenti")
                        break
                
                akun_digunakan.add(akun_email)
                
                # ----- Inisialisasi driver jika belum ada -----
                if driver is None:
                    chrome_profile = current_account.get("chrome_profile_path", "")
                    print_info(f"Membuka Chrome dengan profil: {chrome_profile}")
                    
                    try:
                        driver = create_driver(
                            chrome_profile_path=chrome_profile,
                            headless=headless,
                        )
                    except Exception as e:
                        print_error(f"Gagal membuat Chrome driver: {e}")
                        notify_error(telegram_token, telegram_chat_id,
                                    f"Gagal membuat Chrome driver: {e}", akun_email)
                        break
                
                # ----- 6b: Cek sesi login -----
                if not is_logged_in(driver):
                    print_warning(f"Sesi expired untuk {akun_email}, melakukan re-login...")
                    
                    login_success = login(
                        driver, 
                        current_account["email"], 
                        current_account["password"]
                    )
                    
                    if not login_success:
                        print_error(f"Login gagal untuk {akun_email}")
                        print_warning("⚠️ Mungkin ada CAPTCHA atau masalah lain.")
                        
                        # Minta input manual dari user
                        user_input = Prompt.ask(
                            "Pilih aksi: [r]etry login, [s]kip akun, [q]uit",
                            choices=["r", "s", "q"],
                            default="r"
                        )
                        
                        if user_input == "r":
                            login_success = login(driver, current_account["email"], 
                                                 current_account["password"])
                            if not login_success:
                                print_error("Login tetap gagal, skip akun ini")
                                close_driver(driver)
                                driver = None
                                current_account_idx += 1
                                if current_account_idx >= len(accounts):
                                    print_error("Tidak ada akun yang tersisa")
                                    break
                                continue
                        elif user_input == "s":
                            close_driver(driver)
                            driver = None
                            current_account_idx += 1
                            if current_account_idx >= len(accounts):
                                print_error("Tidak ada akun yang tersisa")
                                break
                            continue
                        elif user_input == "q":
                            print_info("Program dihentikan oleh user")
                            break
                
                # ----- 6c: Generate judul + deskripsi + hashtag -----
                title = generate_title(filename)
                hashtags = generate_hashtags(filename, max_count=max_hashtag)
                hashtag_str = " ".join(hashtags)
                
                if deskripsi_mode == "manual" and manual_description:
                    description = build_description(manual_description, hashtags)
                else:
                    template = current_account.get("deskripsi_template", "")
                    description = build_description(template, hashtags)
                
                # ----- 6d: Upload pin dengan retry -----
                print_info(f"📤 Uploading: {filename}")
                print_info(f"   Judul: {title}")
                print_info(f"   Board: {current_account['board']}")
                
                success = upload_with_retry(
                    driver=driver,
                    image_path=processed_path,
                    title=title,
                    description=description,
                    board_name=current_account["board"],
                    max_retries=3,
                )
                
                # ----- 6e: Catat ke log -----
                status = "success" if success else "failed"
                logger.log_upload(
                    filename=filename,
                    account=akun_email,
                    board=current_account["board"],
                    hashtags=hashtag_str,
                    status=status,
                )
                
                if success:
                    total_sukses += 1
                    print_success(f"Berhasil upload: {filename}")
                else:
                    total_gagal += 1
                    print_error(f"Gagal upload: {filename}")
                
                # ----- 6f: Update dashboard -----
                akun_upload_count = logger.get_account_upload_count(akun_email)
                sisa_foto = len(pending_photos) - (i + 1)
                
                display_status_table(
                    akun_aktif=akun_email,
                    chrome_profile=current_account.get("chrome_profile_path", "N/A"),
                    upload_ke=akun_upload_count,
                    max_upload=max_upload,
                    sisa_foto=sisa_foto,
                    total_sukses=total_sukses,
                    total_gagal=total_gagal,
                )
                
                # Update progress bar
                progress.update(upload_task, advance=1)
                
                # ----- 6g: Random delay -----
                if i < len(pending_photos) - 1:  # Tidak perlu delay di upload terakhir
                    delay = random_delay(delay_min, delay_max)
    
    except KeyboardInterrupt:
        print_warning("\n⚠️ Program dihentikan oleh user (Ctrl+C)")
    
    except Exception as e:
        print_error(f"Error tidak terduga: {e}")
        notify_error(telegram_token, telegram_chat_id, str(e),
                    accounts[current_account_idx]["email"] if current_account_idx < len(accounts) else "")
    
    finally:
        # Tutup driver jika masih terbuka
        if driver:
            close_driver(driver)
    
    # ===== STEP 7: Summary Akhir =====
    end_time = datetime.now()
    durasi = end_time - start_time
    durasi_str = str(durasi).split(".")[0]  # Hapus microseconds
    
    display_summary(
        total_sukses=total_sukses,
        total_gagal=total_gagal,
        durasi=durasi_str,
        akun_digunakan=list(akun_digunakan),
    )
    
    # ===== STEP 8: Notifikasi Telegram =====
    notify_done(
        telegram_token, telegram_chat_id,
        total_sukses=total_sukses,
        total_gagal=total_gagal,
        durasi=durasi_str,
        akun_digunakan=list(akun_digunakan),
    )
    
    print_success("Program selesai! 🎉")


if __name__ == "__main__":
    run_bot()
