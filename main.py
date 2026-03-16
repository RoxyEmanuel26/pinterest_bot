"""
main.py
========
File utama Pinterest Auto-Upload Bot.
Mengorkestrasi seluruh proses upload pin secara otomatis:
baca config → cek session → scan foto → watermark → optimasi → upload → logging.

Fitur utama:
- Multi-akun dengan rotasi otomatis
- Session state resume (session_state.json) untuk crash recovery
- Account blacklist sementara (error/limit/banned → skip otomatis)
- Signal handler untuk Ctrl+C dan SIGTERM
- Detail logging ke upload_log.csv + error_log.txt
- Notifikasi Telegram + Discord

Penggunaan:
    python main.py

Konfigurasi:
    Edit config.json sebelum menjalankan program.
"""

import os
import sys
import json
import time
import signal
from datetime import datetime, timedelta

from rich.console import Console
from rich.prompt import Prompt, Confirm

from modules.browser import create_driver, close_driver, random_delay
from modules.pinterest import is_logged_in, login, logout, upload_pin, upload_with_retry
from modules.file_manager import scan_photos, prepare_photo
from modules.hashtag import generate_title, generate_hashtags, build_description, gabungkan_hashtag
from modules.logger import (
    UploadLogger, SessionState, create_progress_bar,
    display_status_table, display_initial_info, display_summary,
    display_all_accounts_down, write_error_log,
    print_success, print_error, print_warning, print_info, console,
)
from modules.notifier import send_all_notifications


# ============================================================
# PATH DEFAULTS
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOG_PATH = os.path.join(BASE_DIR, "upload_log.csv")
SESSION_STATE_PATH = os.path.join(BASE_DIR, "session_state.json")
ERROR_LOG_PATH = os.path.join(BASE_DIR, "error_log.txt")


# ============================================================
# GLOBAL STATE (untuk signal handler)
# ============================================================
_bot_state = {
    "session": None,
    "driver": None,
    "foto_index": 0,
    "akun_index": 0,
    "upload_count_per_akun": {},
    "total_sukses": 0,
    "total_gagal": 0,
    "foto_terakhir": "",
    "status_terakhir": "",
    "akun_status": {},
    "putaran_ke": 1,
    "config": None,
}


def _save_state_now():
    session = _bot_state["session"]
    if session:
        session.save(
            foto_index=_bot_state["foto_index"],
            akun_index=_bot_state["akun_index"],
            upload_count_per_akun=_bot_state["upload_count_per_akun"],
            total_sukses=_bot_state["total_sukses"],
            total_gagal=_bot_state["total_gagal"],
            foto_terakhir=_bot_state["foto_terakhir"],
            status_terakhir=_bot_state["status_terakhir"],
            akun_status=_bot_state["akun_status"],
            putaran_ke=_bot_state["putaran_ke"],
        )


def _signal_handler(signum, frame):
    print_warning("\n⚠️ Program dihentikan. Progress tersimpan di session_state.json")
    _save_state_now()
    driver = _bot_state.get("driver")
    if driver:
        try:
            close_driver(driver)
        except Exception:
            pass
    sys.exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ============================================================
# CONFIG
# ============================================================

def load_config(config_path: str) -> dict:
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

    required_fields = ["foto_folder", "accounts"]
    for field in required_fields:
        if field not in config:
            print_error(f"Field '{field}' wajib ada di config.json")
            sys.exit(1)

    if not config["accounts"]:
        print_error("Minimal 1 akun harus dikonfigurasi di config.json")
        sys.exit(1)

    # Default global
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
    config.setdefault("discord_webhook_url", "")

    # Default per akun
    for acc in config["accounts"]:
        acc.setdefault("judul_template", "")
        acc.setdefault("hashtag_custom", [])
        acc.setdefault("link_url", "")
        acc.setdefault("deskripsi_template", "")
        acc.setdefault("topics", [])   # ← topics/tag Pinterest, maks 10

    return config


# ============================================================
# PHOTO HELPERS
# ============================================================

def get_pending_photos(foto_folder: str, logger: UploadLogger) -> list[str]:
    all_photos = scan_photos(foto_folder)
    pending = []
    for photo_path in all_photos:
        filename = os.path.basename(photo_path)
        if not logger.is_uploaded(filename):
            pending.append(photo_path)
    return pending


def preprocess_photos(pending_photos: list[str], foto_folder: str,
                      config: dict) -> dict[str, str]:
    processed_map = {}
    progress = create_progress_bar()
    with progress:
        task = progress.add_task(
            "⚙️  Memproses foto (watermark + optimasi)...",
            total=len(pending_photos)
        )
        for photo_path in pending_photos:
            try:
                processed_path = prepare_photo(photo_path, foto_folder, config)
                processed_map[photo_path] = processed_path
                progress.update(task, advance=1)
            except Exception as e:
                filename = os.path.basename(photo_path)
                print_warning(f"Gagal memproses {filename}: {e}")
                processed_map[photo_path] = photo_path
                progress.update(task, advance=1)
    return processed_map


# ============================================================
# ACCOUNT STATUS HELPERS
# ============================================================

def find_next_active_account(accounts: list[dict], akun_status: dict[str, str],
                              start_idx: int = 0) -> int:
    for idx in range(start_idx, len(accounts)):
        email = accounts[idx]["email"]
        if akun_status.get(email, "active") == "active":
            return idx
    return -1


def all_accounts_inactive(akun_status: dict[str, str]) -> bool:
    return all(s != "active" for s in akun_status.values())


def skip_account(akun_email: str, alasan: str, akun_status: dict,
                 accounts: list[dict], config: dict,
                 foto_gagal: str = "") -> int:
    akun_status[akun_email] = alasan

    current_idx = next(i for i, a in enumerate(accounts) if a["email"] == akun_email)
    next_idx = find_next_active_account(accounts, akun_status, current_idx + 1)
    if next_idx == -1:
        next_idx = find_next_active_account(accounts, akun_status, 0)

    next_email = accounts[next_idx]["email"] if next_idx != -1 else "tidak ada"

    print_warning(f"Akun {akun_email} di-skip [alasan: {alasan}]")
    if next_idx != -1:
        print_info(f"   Lanjut ke akun berikutnya: {next_email}")

    send_all_notifications(config, "skip",
        akun_skip=akun_email,
        alasan=alasan,
        akun_baru=next_email,
        foto_gagal=foto_gagal,
    )
    return next_idx


# ============================================================
# MAIN BOT FUNCTION
# ============================================================

def run_bot():
    global _bot_state
    start_time = datetime.now()

    # ===== STEP 1: Baca Config =====
    print_info("Membaca konfigurasi...")
    config = load_config(CONFIG_PATH)
    _bot_state["config"] = config

    foto_folder        = config["foto_folder"]
    max_upload         = config["max_upload_per_akun"]
    delay_min          = config["delay_min"]
    delay_max          = config["delay_max"]
    headless           = config["headless_mode"]
    max_hashtag        = config["max_hashtag"]
    deskripsi_mode     = config.get("deskripsi_mode", "auto")
    accounts           = config["accounts"]

    logger  = UploadLogger(LOG_PATH)
    session = SessionState(SESSION_STATE_PATH)
    _bot_state["session"] = session

    akun_status = {acc["email"]: "active" for acc in accounts}
    _bot_state["akun_status"] = akun_status

    consecutive_fails = {acc["email"]: 0 for acc in accounts}

    # ===== STEP 2: Cek Session Sebelumnya =====
    resume_from_session = False
    resume_foto_index   = 0
    resume_akun_index   = 0
    putaran_ke          = 1

    if session.exists():
        prev_state = session.load()
        if prev_state:
            session.display_summary()
            lanjutkan = Confirm.ask("  🔄 Lanjutkan sesi sebelumnya?", default=True)
            if lanjutkan:
                resume_from_session = True
                resume_foto_index   = prev_state.get("foto_index", 0)
                resume_akun_index   = prev_state.get("akun_index", 0)
                putaran_ke          = prev_state.get("putaran_ke", 1)
                _bot_state["total_sukses"] = prev_state.get("total_sukses", 0)
                _bot_state["total_gagal"]  = prev_state.get("total_gagal", 0)
                _bot_state["putaran_ke"]   = putaran_ke
                for email, status in prev_state.get("akun_status", {}).items():
                    if email in akun_status:
                        akun_status[email] = status
                print_success(f"Melanjutkan dari foto ke-{resume_foto_index + 1}")
            else:
                session.delete()
                print_info("Session dihapus. Memulai dari awal.")

    # ===== STEP 3: Scan Foto =====
    print_info(f"Memindai folder foto: {foto_folder}")
    try:
        pending_photos = get_pending_photos(foto_folder, logger)
    except FileNotFoundError as e:
        print_error(str(e))
        sys.exit(1)

    if not pending_photos:
        print_warning("Tidak ada foto baru yang perlu diupload!")
        print_info("Semua foto sudah pernah diupload (tercatat di upload_log.csv)")
        sys.exit(0)

    total_foto = len(pending_photos)
    print_success(f"Ditemukan {total_foto} foto baru untuk diupload")

    if resume_from_session and resume_foto_index > 0:
        if resume_foto_index < total_foto:
            pending_photos = pending_photos[resume_foto_index:]
            print_info(f"Melompati {resume_foto_index} foto yang sudah diproses")
        else:
            print_warning("Semua foto sudah diproses di sesi sebelumnya!")
            session.delete()
            sys.exit(0)

    # ===== STEP 4: Watermark + Optimasi =====
    print_info("Memproses foto (watermark + optimasi)...")
    processed_map = preprocess_photos(pending_photos, foto_folder, config)

    # ===== STEP 5: Tampilkan Info Awal =====
    avg_delay       = (delay_min + delay_max) / 2
    estimasi_menit  = (len(pending_photos) * avg_delay) / 60
    estimasi_str    = f"{estimasi_menit:.1f} menit"

    display_initial_info(
        total_foto=len(pending_photos),
        total_akun=len(accounts),
        accounts=accounts,
        estimasi_menit=estimasi_menit,
    )

    # ===== STEP 6: Konfirmasi User =====
    if not Confirm.ask("  🚀 Mulai upload?", default=True):
        print_info("Upload dibatalkan oleh user.")
        sys.exit(0)

    manual_description = None
    if deskripsi_mode == "manual":
        manual_description = Prompt.ask("  ✏️  Masukkan deskripsi untuk semua pin")

    # ===== STEP 7: Mulai Upload =====
    console.print()
    print_info("Memulai proses upload...")

    send_all_notifications(config, "start",
        total_foto=len(pending_photos),
        total_akun=len(accounts),
        akun_pertama=accounts[0]["email"],
        foto_folder=foto_folder,
        estimasi=estimasi_str,
    )

    current_account_idx = resume_akun_index if resume_from_session else 0
    total_sukses        = _bot_state["total_sukses"]
    total_gagal         = _bot_state["total_gagal"]
    driver              = None
    akun_digunakan      = set()
    akun_diskip         = []

    active_idx = find_next_active_account(accounts, akun_status, current_account_idx)
    if active_idx == -1:
        active_idx = find_next_active_account(accounts, akun_status, 0)

    if active_idx == -1:
        print_warning("Semua akun sudah di-skip atau mencapai batas!")
        display_all_accounts_down(akun_status, len(pending_photos))
        send_all_notifications(config, "error",
            error_msg="Semua akun tidak aktif saat program dimulai")
        sys.exit(0)

    current_account_idx  = active_idx
    foto_global_index    = resume_foto_index if resume_from_session else 0

    try:
        progress = create_progress_bar()
        with progress:
            upload_task = progress.add_task(
                "📤 Uploading pins...",
                total=len(pending_photos)
            )

            for i, photo_path in enumerate(pending_photos):
                filename       = os.path.basename(photo_path)
                processed_path = processed_map.get(photo_path, photo_path)

                _bot_state["foto_index"]    = foto_global_index + i
                _bot_state["foto_terakhir"] = filename

                # ----- 7a: Cek semua akun non-active -----
                if all_accounts_inactive(akun_status):
                    sisa = len(pending_photos) - i
                    display_all_accounts_down(akun_status, sisa)
                    send_all_notifications(config, "error",
                        error_msg="Semua akun tidak dapat digunakan, program berhenti",
                        akun="semua akun non-aktif")
                    break

                # ----- 7b: Cek batas upload akun aktif -----
                current_account   = accounts[current_account_idx]
                akun_email        = current_account["email"]
                akun_upload_count = logger.get_account_upload_count(akun_email)

                if akun_status.get(akun_email) != "active":
                    next_idx = find_next_active_account(accounts, akun_status, 0)
                    if next_idx == -1:
                        display_all_accounts_down(akun_status, len(pending_photos) - i)
                        break
                    current_account_idx = next_idx
                    current_account     = accounts[current_account_idx]
                    akun_email          = current_account["email"]
                    akun_upload_count   = logger.get_account_upload_count(akun_email)

                if akun_upload_count >= max_upload:
                    if driver:
                        close_driver(driver)
                        driver = None
                    next_idx = skip_account(
                        akun_email, "limit_reached", akun_status,
                        accounts, config, foto_gagal=filename
                    )
                    if next_idx == -1:
                        display_all_accounts_down(akun_status, len(pending_photos) - i)
                        break
                    current_account_idx = next_idx
                    current_account     = accounts[current_account_idx]
                    akun_email          = current_account["email"]

                akun_digunakan.add(akun_email)
                _bot_state["akun_index"] = current_account_idx

                # ----- Buka driver jika belum ada -----
                if driver is None:
                    chrome_profile = current_account.get("chrome_profile_path", "")
                    print_info(f"Membuka Chrome dengan profil: {chrome_profile}")
                    try:
                        driver = create_driver(
                            chrome_profile_path=chrome_profile,
                            headless=headless,
                        )
                        _bot_state["driver"] = driver
                    except Exception as e:
                        print_error(f"Gagal membuat Chrome driver: {e}")
                        write_error_log(ERROR_LOG_PATH, akun_email, filename,
                                        f"Chrome driver error: {e}")
                        send_all_notifications(config, "error",
                            error_msg=f"Gagal membuat Chrome driver: {e}",
                            akun=akun_email)
                        break

                # ----- 7c: Cek sesi login -----
                if not is_logged_in(driver):
                    print_warning(f"Sesi expired untuk {akun_email}, re-login...")
                    login_success = login(driver, current_account["email"],
                                         current_account["password"])
                    if not login_success:
                        print_warning("Login gagal, mencoba ulang...")
                        time.sleep(3)
                        login_success = login(driver, current_account["email"],
                                              current_account["password"])
                    if not login_success:
                        print_error(f"Re-login 2x gagal untuk {akun_email}, tandai banned")
                        write_error_log(ERROR_LOG_PATH, akun_email, filename,
                                        "Re-login 2x gagal, akun ditandai banned")
                        close_driver(driver)
                        driver = None
                        _bot_state["driver"] = None
                        next_idx = skip_account(
                            akun_email, "banned", akun_status,
                            accounts, config, foto_gagal=filename
                        )
                        if next_idx == -1:
                            display_all_accounts_down(akun_status, len(pending_photos) - i)
                            break
                        current_account_idx = next_idx
                        continue

                # ----- 7d: Generate judul + deskripsi + hashtag -----
                judul_template = current_account.get("judul_template", "")
                title = judul_template if judul_template else generate_title(filename)

                hashtag_auto   = generate_hashtags(filename, max_count=max_hashtag)
                hashtag_custom = current_account.get("hashtag_custom", [])
                hashtags       = gabungkan_hashtag(hashtag_auto, hashtag_custom,
                                                   max_total=max_hashtag)
                hashtag_str    = " ".join(hashtags)

                if deskripsi_mode == "manual" and manual_description:
                    description = build_description(manual_description, hashtags)
                else:
                    template    = current_account.get("deskripsi_template", "")
                    description = build_description(template, hashtags)

                link_url = current_account.get("link_url", "")

                # ← TOPICS: ambil dari config akun, default list kosong
                topics = current_account.get("topics", [])

                # ----- 7e: Upload pin -----
                print_info(f"📤 Uploading: {filename}")
                print_info(f"   Judul: {title}")
                print_info(f"   Board: {current_account['board']}")
                if link_url:
                    print_info(f"   Link: {link_url}")
                if topics:
                    print_info(f"   Topik: {', '.join(topics)}")

                upload_start = time.time()

                success = upload_with_retry(
                    driver=driver,
                    image_path=processed_path,
                    title=title,
                    description=description,
                    board_name=current_account["board"],
                    link_url=link_url,
                    topics=topics,          # ← dikirim ke upload_with_retry
                    max_retries=3,
                )

                upload_durasi = time.time() - upload_start

                try:
                    file_size_kb = os.path.getsize(processed_path) / 1024
                except OSError:
                    file_size_kb = 0.0

                # ----- 7f: Log -----
                status       = "success" if success else "failed"
                alasan_gagal = "" if success else "Upload gagal setelah 3x retry"

                logger.log_upload(
                    filename=filename,
                    filepath=processed_path,
                    akun=akun_email,
                    board=current_account["board"],
                    judul=title,
                    hashtag=hashtag_str,
                    link_url=link_url,
                    status=status,
                    alasan_gagal=alasan_gagal,
                    durasi_upload_detik=upload_durasi,
                    ukuran_file_kb=file_size_kb,
                    putaran_ke=putaran_ke,
                )

                if success:
                    total_sukses += 1
                    consecutive_fails[akun_email] = 0
                    print_success(f"Berhasil upload: {filename}")
                else:
                    total_gagal += 1
                    consecutive_fails[akun_email] += 1
                    print_error(f"Gagal upload: {filename}")
                    write_error_log(ERROR_LOG_PATH, akun_email, filename, alasan_gagal)

                    if consecutive_fails[akun_email] >= 3:
                        print_error(f"Akun {akun_email} gagal 3x berturut-turut!")
                        close_driver(driver)
                        driver = None
                        _bot_state["driver"] = None
                        next_idx = skip_account(
                            akun_email, "error", akun_status,
                            accounts, config, foto_gagal=filename
                        )
                        if next_idx == -1:
                            display_all_accounts_down(akun_status, len(pending_photos) - (i+1))
                            break
                        current_account_idx = next_idx

                # ----- 7g: Update state -----
                _bot_state["total_sukses"]    = total_sukses
                _bot_state["total_gagal"]     = total_gagal
                _bot_state["status_terakhir"] = status
                _bot_state["upload_count_per_akun"][akun_email] = \
                    logger.get_account_upload_count(akun_email)

                _save_state_now()

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

                progress.update(upload_task, advance=1)

                if total_sukses > 0 and total_sukses % 10 == 0:
                    send_all_notifications(config, "progress",
                        akun_aktif=akun_email,
                        upload_count=akun_upload_count,
                        max_upload=max_upload,
                        sisa_foto=sisa_foto,
                        board=current_account["board"],
                    )

                if i < len(pending_photos) - 1:
                    delay = random_delay(delay_min, delay_max)

    except KeyboardInterrupt:
        print_warning("\n⚠️ Program dihentikan oleh user (Ctrl+C)")
        _save_state_now()

    except Exception as e:
        print_error(f"Error tidak terduga: {e}")
        current_email = ""
        if current_account_idx < len(accounts):
            current_email = accounts[current_account_idx]["email"]
        write_error_log(ERROR_LOG_PATH, current_email,
                        _bot_state.get("foto_terakhir", ""), str(e))
        send_all_notifications(config, "error",
            error_msg=str(e),
            akun=current_email,
            foto_terakhir=_bot_state.get("foto_terakhir", ""))
        _save_state_now()

    finally:
        if driver:
            try:
                close_driver(driver)
            except Exception:
                pass
            _bot_state["driver"] = None

    # ===== STEP 8: Summary =====
    end_time     = datetime.now()
    total_secs   = int((end_time - start_time).total_seconds())
    durasi_str   = f"{total_secs//3600}j {(total_secs%3600)//60}m {total_secs%60}d"
    foto_sisa    = max(0, total_foto - (total_sukses + total_gagal))
    akun_diskip  = [e for e, s in akun_status.items() if s != "active"]

    display_summary(
        total_sukses=total_sukses,
        total_gagal=total_gagal,
        durasi=durasi_str,
        akun_digunakan=list(akun_digunakan),
        total_foto=total_foto,
        foto_sisa=foto_sisa,
        akun_diskip=akun_diskip,
        session_saved=True,
    )

    _save_state_now()

    send_all_notifications(config, "done",
        total_sukses=total_sukses,
        total_gagal=total_gagal,
        durasi=durasi_str,
        akun_digunakan=list(akun_digunakan),
        total_foto=total_foto,
        foto_sisa=foto_sisa,
        akun_diskip=akun_diskip,
    )

    print_success("Program selesai! 🎉")


if __name__ == "__main__":
    run_bot()
