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
    Edit config.json dan .env sebelum menjalankan program.
"""

import os
import sys
import json
import random
import time
import signal
from datetime import datetime, timedelta

from dotenv import load_dotenv

from rich.console import Console
from rich.prompt import Prompt, Confirm

from modules.models import Account, Config, BotState
from modules.account_manager import AccountManager
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
JUDUL_POOL_PATH = os.path.join(BASE_DIR, "judul_pool.txt")  # default fallback

# Cache judul pool agar tidak baca file berulang kali
_judul_pool_cache: list[str] | None = None


def load_judul_pool(pool_file: str = "") -> list[str]:
    """Baca file judul pool dan kembalikan list judul (skip baris kosong)."""
    global _judul_pool_cache
    if _judul_pool_cache is not None:
        return _judul_pool_cache

    # Tentukan path file pool
    if pool_file:
        if os.path.isabs(pool_file):
            pool_path = pool_file
        else:
            pool_path = os.path.join(BASE_DIR, pool_file)
    else:
        pool_path = JUDUL_POOL_PATH

    if not os.path.exists(pool_path):
        print_warning(f"File judul pool tidak ditemukan: {pool_path}")
        _judul_pool_cache = []
        return _judul_pool_cache

    with open(pool_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        print_warning(f"{os.path.basename(pool_path)} kosong, akan fallback ke generate_title()")

    _judul_pool_cache = lines
    print_info(f"Loaded {len(lines)} judul dari {os.path.basename(pool_path)}")
    return _judul_pool_cache


def get_random_judul(filename: str, config, account=None) -> str:
    """
    Pilih judul berdasarkan title_mode di config:
      - "pool"     → random dari judul_pool_file
      - "template" → pakai judul_template dari akun
      - "auto"     → generate dari nama file
    """
    mode = getattr(config, "title_mode", "auto").lower()

    if mode == "pool":
        pool = load_judul_pool(getattr(config, "judul_pool_file", ""))
        if pool:
            return random.choice(pool)
        # Fallback ke auto jika pool kosong
        return generate_title(filename)

    elif mode == "template":
        if account and account.judul_template:
            return account.judul_template
        return generate_title(filename)

    else:  # "auto" atau mode tidak dikenal
        return generate_title(filename)


# ============================================================
# GLOBAL STATE (untuk signal handler)
# ============================================================
_bot_state = BotState()
_session: SessionState | None = None
_driver = None
_config: Config | None = None


def _save_state_now():
    if _session:
        _session.save(
            foto_index=_bot_state.foto_index,
            akun_index=_bot_state.akun_index,
            upload_count_per_akun=_bot_state.upload_count_per_akun,
            total_sukses=_bot_state.total_sukses,
            total_gagal=_bot_state.total_gagal,
            foto_terakhir=_bot_state.foto_terakhir,
            status_terakhir=_bot_state.status_terakhir,
            akun_status=_bot_state.akun_status,
            putaran_ke=_bot_state.putaran_ke,
            foto_folder=_bot_state.foto_folder,
        )


def _signal_handler(signum, frame):
    print_warning("\n⚠️ Program dihentikan. Progress tersimpan di session_state.json")
    _save_state_now()
    global _driver
    if _driver:
        try:
            close_driver(_driver)
        except Exception:
            pass
        _driver = None
    sys.exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ============================================================
# CONFIG
# ============================================================

def load_config(config_path: str) -> Config:
    """Baca dan validasi config.json, kembalikan Config dataclass."""
    if not os.path.exists(config_path):
        print_error(f"File config tidak ditemukan: {config_path}")
        print_info("Buat file config.json terlebih dahulu. Lihat README.md untuk template.")
        sys.exit(1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        print_error(f"Format config.json tidak valid: {e}")
        sys.exit(1)

    required_fields = ["foto_folder", "accounts"]
    for field in required_fields:
        if field not in raw:
            print_error(f"Field '{field}' wajib ada di config.json")
            sys.exit(1)

    if not raw["accounts"]:
        print_error("Minimal 1 akun harus dikonfigurasi di config.json")
        sys.exit(1)

    return Config.from_dict(raw)


def inject_secrets_from_env(config: Config) -> None:
    """
    Inject kredensial dari environment variables (.env) ke Config.

    Environment variables yang dibaca:
    - ACCOUNT_<N>_PASSWORD  → config.accounts[N-1].password
    - TELEGRAM_BOT_TOKEN    → config.telegram_bot_token
    - TELEGRAM_CHAT_ID      → config.telegram_chat_id
    - DISCORD_WEBHOOK_URL   → config.discord_webhook_url
    """
    for i, acc in enumerate(config.accounts, start=1):
        env_key = f"ACCOUNT_{i}_PASSWORD"
        password = os.environ.get(env_key, "")
        if not password:
            print_warning(f"Environment variable {env_key} tidak ditemukan atau kosong!")
        acc.password = password

    config.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    config.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    config.discord_webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "")


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
                      config: Config) -> dict[str, str]:
    processed_map = {}
    config_dict = config.to_dict()
    progress = create_progress_bar()
    with progress:
        task = progress.add_task(
            "⚙️  Memproses foto (watermark + optimasi)...",
            total=len(pending_photos)
        )
        for photo_path in pending_photos:
            try:
                processed_path = prepare_photo(photo_path, foto_folder, config_dict)
                processed_map[photo_path] = processed_path
                progress.update(task, advance=1)
            except Exception as e:
                filename = os.path.basename(photo_path)
                print_warning(f"Gagal memproses {filename}: {e}")
                processed_map[photo_path] = photo_path
                progress.update(task, advance=1)
    return processed_map


# ============================================================
# SPLIT FUNCTIONS
# ============================================================

def _initialize_session(config: Config, logger: UploadLogger,
                        session: SessionState, acct_mgr: AccountManager
                        ) -> tuple[list[str], dict[str, str], int, int, int, str | None]:
    """
    STEP 1-6: Load config, scan foto, preprocess, session resume, konfirmasi user.

    Returns:
        (pending_photos, processed_map, resume_foto_index, resume_akun_index, putaran_ke, manual_description)
    """
    resume_from_session = False
    resume_foto_index = 0
    resume_akun_index = 0
    putaran_ke = 1
    _bot_state.foto_folder = config.foto_folder

    # --- Cek session sebelumnya ---
    if session.exists():
        prev_state = session.load()
        if prev_state:
            session.display_summary()
            lanjutkan = Confirm.ask("  🔄 Lanjutkan sesi sebelumnya?", default=True)
            if lanjutkan:
                # --- Deteksi perubahan folder ---
                saved_folder = prev_state.get("foto_folder", "")
                current_folder = os.path.normpath(config.foto_folder)
                saved_folder_norm = os.path.normpath(saved_folder) if saved_folder else ""
                folder_changed = saved_folder_norm and saved_folder_norm != current_folder

                if folder_changed:
                    print_warning(f"Folder foto berubah!")
                    print_info(f"   Sesi lama : {saved_folder}")
                    print_info(f"   Folder baru: {config.foto_folder}")
                    print_info("   → Foto direset ke awal, posisi akun tetap dilanjutkan.")

                resume_from_session = True
                resume_akun_index = prev_state.get("akun_index", 0)
                # Bounds check — jika akun dihapus dari config
                if resume_akun_index >= len(config.accounts):
                    resume_akun_index = 0
                putaran_ke = prev_state.get("putaran_ke", 1)
                _bot_state.putaran_ke = putaran_ke
                _bot_state.foto_folder = config.foto_folder
                acct_mgr.restore_status(prev_state.get("akun_status", {}))

                # Restore upload count per akun agar rotasi berjalan benar
                saved_counts = prev_state.get("upload_count_per_akun", {})
                for email, count in saved_counts.items():
                    if email in acct_mgr.session_upload_count:
                        acct_mgr.session_upload_count[email] = count

                akun_email = config.accounts[resume_akun_index].email
                if folder_changed:
                    # Folder berubah → reset statistik, posisi akun tetap
                    _bot_state.total_sukses = 0
                    _bot_state.total_gagal = 0
                    print_success(f"Folder berubah, foto direset. Lanjut akun: {akun_email}")
                else:
                    # Folder sama → lanjutkan statistik + posisi akun
                    # Foto yang sudah sukses otomatis di-skip oleh upload_log.csv
                    _bot_state.total_sukses = prev_state.get("total_sukses", 0)
                    _bot_state.total_gagal = prev_state.get("total_gagal", 0)
                    print_success(f"Melanjutkan sesi, akun: {akun_email}")
            else:
                session.delete()
                _bot_state.foto_folder = config.foto_folder
                print_info("Session dihapus. Memulai dari awal.")

    # --- Scan foto ---
    print_info(f"Memindai folder foto: {config.foto_folder}")
    try:
        pending_photos = get_pending_photos(config.foto_folder, logger)
    except FileNotFoundError as e:
        print_error(str(e))
        sys.exit(1)

    if not pending_photos:
        print_warning("Tidak ada foto baru yang perlu diupload!")
        print_info("Semua foto sudah pernah diupload (tercatat di upload_log.csv)")
        if session.exists():
            session.delete()
        sys.exit(0)

    total_foto = len(pending_photos)
    print_success(f"Ditemukan {total_foto} foto baru untuk diupload")

    # --- Watermark + Optimasi ---
    print_info("Memproses foto (watermark + optimasi)...")
    processed_map = preprocess_photos(pending_photos, config.foto_folder, config)

    # --- Tampilkan info awal ---
    avg_delay = (config.delay_min + config.delay_max) / 2
    estimasi_menit = (len(pending_photos) * avg_delay) / 60

    accounts_dicts = [a.to_dict() for a in config.accounts]
    display_initial_info(
        total_foto=len(pending_photos),
        total_akun=len(config.accounts),
        accounts=accounts_dicts,
        estimasi_menit=estimasi_menit,
    )

    # --- Konfirmasi user ---
    if not Confirm.ask("  🚀 Mulai upload?", default=True):
        print_info("Upload dibatalkan oleh user.")
        sys.exit(0)

    manual_description = None
    if config.deskripsi_mode == "manual":
        manual_description = Prompt.ask("  ✏️  Masukkan deskripsi untuk semua pin")

    return pending_photos, processed_map, resume_foto_index, resume_akun_index, putaran_ke, manual_description


def _ensure_driver_and_login(
    driver, account: Account, headless: bool,
    acct_mgr: AccountManager, filename: str,
    remaining: int
) -> tuple:
    """
    Pastikan Chrome driver aktif dan akun sudah login.

    Returns:
        (driver, login_ok: bool, should_skip_idx: int)
        - should_skip_idx >= 0 berarti harus pindah ke akun tersebut
        - should_skip_idx == -1 berarti semua akun habis
        - should_skip_idx == None berarti OK, lanjut upload
    """
    global _driver

    if driver is None:
        # --- Buka driver baru ---
        chrome_profile = account.chrome_profile_path
        print_info(f"Membuka Chrome dengan profil: {chrome_profile}")
        try:
            driver = create_driver(
                chrome_profile_path=chrome_profile,
                headless=headless,
            )
            _driver = driver
        except Exception as e:
            print_error(f"Gagal membuat Chrome driver: {e}")
            write_error_log(ERROR_LOG_PATH, account.email, filename,
                            f"Chrome driver error: {e}")
            return None, False, -2  # Fatal error

        # --- Logout dulu jika ada sesi lain, lalu login ---
        if is_logged_in(driver):
            print_info("Logout akun sebelumnya terlebih dahulu...")
            try:
                logout(driver)
                time.sleep(1)
            except Exception:
                pass

        print_info(f"Login ke akun: {account.email}")
        login_success = _login_with_retry(driver, account)
        if not login_success:
            print_error(f"Login gagal untuk {account.email}")
            close_driver(driver)
            _driver = None
            next_idx = acct_mgr.skip(account.email, "banned", foto_gagal=filename)
            if next_idx == -1:
                display_all_accounts_down(acct_mgr.status, remaining)
            return None, False, next_idx

    else:
        # --- Cek sesi masih aktif ---
        if not is_logged_in(driver):
            print_warning(f"Sesi expired untuk {account.email}, re-login...")
            login_success = _login_with_retry(driver, account)
            if not login_success:
                print_error(f"Re-login 2x gagal untuk {account.email}, tandai banned")
                write_error_log(ERROR_LOG_PATH, account.email, filename,
                                "Re-login 2x gagal, akun ditandai banned")
                close_driver(driver)
                _driver = None
                next_idx = acct_mgr.skip(account.email, "banned", foto_gagal=filename)
                if next_idx == -1:
                    display_all_accounts_down(acct_mgr.status, remaining)
                return None, False, next_idx

    return driver, True, None  # OK


def _login_with_retry(driver, account: Account, max_retries: int = 2) -> bool:
    """Login dengan retry otomatis."""
    for attempt in range(max_retries):
        success = login(driver, account.email, account.password)
        if success:
            return True
        if attempt < max_retries - 1:
            print_warning("Login gagal, mencoba ulang...")
            time.sleep(3)
    return False


def _handle_account_rotation(
    driver, i: int, filename: str, acct_mgr: AccountManager,
    config: Config, current_account_idx: int,
    pending_photos: list[str]
) -> tuple:
    """
    Cek batas upload, rotasi akun, dan handle putaran baru.

    Returns:
        (driver, current_account_idx, should_break, should_continue)
    """
    global _driver
    accounts = config.accounts
    remaining = len(pending_photos) - i

    # --- Cek semua akun non-active ---
    if acct_mgr.all_inactive():
        if acct_mgr.has_limit_only():
            # Mulai putaran baru!
            _bot_state.putaran_ke += 1
            print_info(f"🔄 Semua akun selesai! Memulai putaran ke-{_bot_state.putaran_ke}...")
            acct_mgr.reset_limits()
            _bot_state.upload_count_per_akun = {e: 0 for e in _bot_state.upload_count_per_akun}
            current_account_idx = acct_mgr.find_next_active(0)
            if current_account_idx == -1:
                return driver, current_account_idx, True, False

            # Logout akun lama agar bisa login ulang dari akun pertama
            if driver:
                try:
                    logout(driver)
                except Exception:
                    pass
                time.sleep(1)
                _login_with_retry(driver, accounts[current_account_idx])
        else:
            display_all_accounts_down(acct_mgr.status, remaining)
            config_dict = config.to_dict()
            send_all_notifications(config_dict, "error",
                error_msg="Semua akun tidak dapat digunakan, program berhenti",
                akun="semua akun non-aktif")
            return driver, current_account_idx, True, False

    # --- Cek akun saat ini masih aktif ---
    account = accounts[current_account_idx]
    if acct_mgr.status.get(account.email) != "active":
        next_idx = acct_mgr.find_next_active(0)
        if next_idx == -1:
            display_all_accounts_down(acct_mgr.status, remaining)
            return driver, current_account_idx, True, False
        current_account_idx = next_idx
        account = accounts[current_account_idx]

    # --- Cek batas upload ---
    if acct_mgr.get_upload_count(account.email) >= config.max_upload_per_akun:
        prev_profile = account.chrome_profile_path
        next_idx = acct_mgr.skip(account.email, "limit_reached", foto_gagal=filename)
        if next_idx == -1:
            # Semua akun sudah di-skip — cek apakah bisa mulai putaran baru
            if acct_mgr.has_limit_only():
                _bot_state.putaran_ke += 1
                print_info(f"🔄 Semua akun limit! Memulai putaran ke-{_bot_state.putaran_ke}...")
                acct_mgr.reset_limits()
                _bot_state.upload_count_per_akun = {e: 0 for e in _bot_state.upload_count_per_akun}
                current_account_idx = acct_mgr.find_next_active(0)
                if current_account_idx == -1:
                    display_all_accounts_down(acct_mgr.status, remaining)
                    return driver, current_account_idx, True, False

                new_account = accounts[current_account_idx]
                # Logout akun lama, login akun baru
                if driver:
                    try:
                        logout(driver)
                    except Exception:
                        pass
                    time.sleep(1)
                    login_success = _login_with_retry(driver, new_account)
                    if not login_success:
                        print_error(f"Login gagal untuk {new_account.email}")
                        close_driver(driver)
                        driver = None
                        _driver = None
                return driver, current_account_idx, False, False
            else:
                display_all_accounts_down(acct_mgr.status, remaining)
                return driver, current_account_idx, True, False

        current_account_idx = next_idx
        new_account = accounts[current_account_idx]
        new_profile = new_account.chrome_profile_path

        if driver and prev_profile == new_profile:
            # Profile SAMA → logout lalu login akun baru tanpa tutup Chrome
            print_info(f"Logout & login ke akun baru: {new_account.email}")
            try:
                logout(driver)
            except Exception:
                pass
            time.sleep(1)
            login_success = _login_with_retry(driver, new_account)
            if not login_success:
                print_error(f"Login gagal untuk {new_account.email}, skip akun")
                write_error_log(ERROR_LOG_PATH, new_account.email, filename,
                                "Login gagal 2x")
                next_idx = acct_mgr.skip(new_account.email, "banned", foto_gagal=filename)
                if next_idx == -1:
                    display_all_accounts_down(acct_mgr.status, remaining)
                    return driver, current_account_idx, True, False
                current_account_idx = next_idx
                return driver, current_account_idx, False, True
        elif driver:
            # Profile BEDA → tutup Chrome lama, buka baru
            close_driver(driver)
            driver = None
            _driver = None

    return driver, current_account_idx, False, False


def _upload_single_photo(
    driver, photo_path: str, processed_path: str,
    account: Account, config: Config,
    acct_mgr: AccountManager, logger: UploadLogger,
    manual_description: str | None,
) -> tuple[bool, float]:
    """
    Generate metadata + upload satu foto + log hasil.

    Returns:
        (success, durasi_upload)
    """
    filename = os.path.basename(photo_path)

    # --- Generate judul + deskripsi + hashtag ---
    title = get_random_judul(filename, config, account)

    hashtag_auto = generate_hashtags(filename, max_count=config.max_hashtag)
    hashtags = gabungkan_hashtag(hashtag_auto, account.hashtag_custom,
                                 max_total=config.max_hashtag)
    hashtag_str = " ".join(hashtags)

    if config.deskripsi_mode == "manual" and manual_description:
        description = build_description(manual_description, hashtags)
    else:
        description = build_description(account.deskripsi_template, hashtags)

    link_url = account.link_url

    # --- Upload pin ---
    print_info(f"📤 Uploading: {filename}")
    print_info(f"   Judul: {title}")
    print_info(f"   Board: {account.board}")
    if link_url:
        print_info(f"   Link: {link_url}")

    upload_start = time.time()

    success = upload_with_retry(
        driver=driver,
        image_path=processed_path,
        title=title,
        description=description,
        board_name=account.board,
        link_url=link_url,
        max_retries=3,
    )

    upload_durasi = time.time() - upload_start

    try:
        file_size_kb = os.path.getsize(processed_path) / 1024
    except OSError:
        file_size_kb = 0.0

    # --- Log ---
    status = "success" if success else "failed"
    alasan_gagal = "" if success else "Upload gagal setelah 3x retry"

    logger.log_upload(
        filename=filename,
        filepath=processed_path,
        akun=account.email,
        board=account.board,
        judul=title,
        hashtag=hashtag_str,
        link_url=link_url,
        status=status,
        alasan_gagal=alasan_gagal,
        durasi_upload_detik=upload_durasi,
        ukuran_file_kb=file_size_kb,
        putaran_ke=_bot_state.putaran_ke,
    )

    return success, upload_durasi


def _generate_summary(
    start_time: datetime, total_foto: int,
    total_sukses: int, total_gagal: int,
    akun_digunakan: set[str], acct_mgr: AccountManager,
    config: Config,
):
    """STEP 8: Hitung durasi, tampilkan summary, kirim notifikasi selesai."""
    end_time = datetime.now()
    total_secs = int((end_time - start_time).total_seconds())
    durasi_str = f"{total_secs//3600}j {(total_secs%3600)//60}m {total_secs%60}d"
    foto_sisa = max(0, total_foto - (total_sukses + total_gagal))
    akun_diskip = [e for e, s in acct_mgr.status.items() if s != "active"]

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

    config_dict = config.to_dict()
    send_all_notifications(config_dict, "done",
        total_sukses=total_sukses,
        total_gagal=total_gagal,
        durasi=durasi_str,
        akun_digunakan=list(akun_digunakan),
        total_foto=total_foto,
        foto_sisa=foto_sisa,
        akun_diskip=akun_diskip,
    )

    print_success("Program selesai! 🎉")


# ============================================================
# MAIN BOT FUNCTION (Orchestrator)
# ============================================================

def run_bot():
    """Orchestrator utama — memanggil fungsi-fungsi kecil secara berurutan."""
    global _bot_state, _session, _driver, _config
    start_time = datetime.now()

    # ===== STEP 1: Baca Config + Secrets =====
    print_info("Membaca konfigurasi...")
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    config = load_config(CONFIG_PATH)
    inject_secrets_from_env(config)
    _config = config

    logger = UploadLogger(LOG_PATH)
    session = SessionState(SESSION_STATE_PATH)
    _session = session

    config_dict = config.to_dict()
    acct_mgr = AccountManager(config.accounts, config_dict)
    _bot_state.akun_status = acct_mgr.status

    # ===== STEP 2-6: Initialize session =====
    (pending_photos, processed_map, resume_foto_index,
     resume_akun_index, putaran_ke, manual_description) = _initialize_session(
        config, logger, session, acct_mgr
    )
    _bot_state.putaran_ke = putaran_ke

    total_foto = len(pending_photos) + resume_foto_index

    # ===== STEP 7: Mulai upload =====
    console.print()
    print_info("Memulai proses upload...")

    estimasi_str = f"{(len(pending_photos) * (config.delay_min + config.delay_max) / 2) / 60:.1f} menit"
    send_all_notifications(config_dict, "start",
        total_foto=len(pending_photos),
        total_akun=len(config.accounts),
        akun_pertama=config.accounts[0].email,
        foto_folder=config.foto_folder,
        estimasi=estimasi_str,
    )

    current_account_idx = acct_mgr.find_next_active(resume_akun_index)
    if current_account_idx == -1:
        print_warning("Semua akun sudah di-skip atau mencapai batas!")
        display_all_accounts_down(acct_mgr.status, len(pending_photos))
        send_all_notifications(config_dict, "error",
            error_msg="Semua akun tidak aktif saat program dimulai")
        sys.exit(0)

    driver = None
    akun_digunakan: set[str] = set()
    foto_global_index = resume_foto_index

    try:
        progress = create_progress_bar()
        with progress:
            upload_task = progress.add_task(
                "📤 Uploading pins...",
                total=len(pending_photos)
            )

            for i, photo_path in enumerate(pending_photos):
                filename = os.path.basename(photo_path)
                processed_path = processed_map.get(photo_path, photo_path)

                _bot_state.foto_index = foto_global_index + i
                _bot_state.foto_terakhir = filename

                # --- Rotasi akun ---
                (driver, current_account_idx,
                 should_break, should_continue) = _handle_account_rotation(
                    driver, i, filename, acct_mgr,
                    config, current_account_idx, pending_photos
                )
                if should_break:
                    break
                if should_continue:
                    continue

                account = config.accounts[current_account_idx]
                akun_digunakan.add(account.email)
                _bot_state.akun_index = current_account_idx

                # --- Driver + Login ---
                remaining = len(pending_photos) - i
                driver, login_ok, skip_idx = _ensure_driver_and_login(
                    driver, account, config.headless_mode,
                    acct_mgr, filename, remaining
                )
                if skip_idx == -2:  # Fatal driver error
                    send_all_notifications(config_dict, "error",
                        error_msg="Gagal membuat Chrome driver",
                        akun=account.email)
                    break
                if skip_idx is not None:
                    if skip_idx == -1:
                        break
                    current_account_idx = skip_idx
                    continue

                # --- Upload ---
                success, _ = _upload_single_photo(
                    driver, photo_path, processed_path,
                    account, config, acct_mgr, logger,
                    manual_description,
                )

                if success:
                    _bot_state.total_sukses += 1
                    acct_mgr.record_success(account.email)
                    print_success(f"Berhasil upload: {filename}")
                else:
                    _bot_state.total_gagal += 1
                    acct_mgr.record_failure(account.email)
                    print_error(f"Gagal upload: {filename}")
                    write_error_log(ERROR_LOG_PATH, account.email, filename,
                                    "Upload gagal setelah 3x retry")

                    if acct_mgr.has_too_many_fails(account.email):
                        print_error(f"Akun {account.email} gagal 3x berturut-turut!")
                        close_driver(driver)
                        driver = None
                        _driver = None
                        next_idx = acct_mgr.skip(
                            account.email, "error", foto_gagal=filename
                        )
                        if next_idx == -1:
                            display_all_accounts_down(
                                acct_mgr.status, len(pending_photos) - (i + 1))
                            break
                        current_account_idx = next_idx

                # --- Update state ---
                _bot_state.status_terakhir = "success" if success else "failed"
                _bot_state.upload_count_per_akun[account.email] = \
                    acct_mgr.get_upload_count(account.email)
                _save_state_now()

                akun_upload_count = acct_mgr.get_upload_count(account.email)
                sisa_foto = len(pending_photos) - (i + 1)

                display_status_table(
                    akun_aktif=account.email,
                    chrome_profile=account.chrome_profile_path or "N/A",
                    upload_ke=akun_upload_count,
                    max_upload=config.max_upload_per_akun,
                    sisa_foto=sisa_foto,
                    total_sukses=_bot_state.total_sukses,
                    total_gagal=_bot_state.total_gagal,
                )

                progress.update(upload_task, advance=1)

                if _bot_state.total_sukses > 0 and _bot_state.total_sukses % 10 == 0:
                    send_all_notifications(config_dict, "progress",
                        akun_aktif=account.email,
                        upload_count=akun_upload_count,
                        max_upload=config.max_upload_per_akun,
                        sisa_foto=sisa_foto,
                        board=account.board,
                    )

                if i < len(pending_photos) - 1:
                    delay = random_delay(config.delay_min, config.delay_max)

    except KeyboardInterrupt:
        print_warning("\n⚠️ Program dihentikan oleh user (Ctrl+C)")
        _save_state_now()

    except Exception as e:
        print_error(f"Error tidak terduga: {e}")
        current_email = ""
        if current_account_idx < len(config.accounts):
            current_email = config.accounts[current_account_idx].email
        write_error_log(ERROR_LOG_PATH, current_email,
                        _bot_state.foto_terakhir, str(e))
        send_all_notifications(config_dict, "error",
            error_msg=str(e),
            akun=current_email,
            foto_terakhir=_bot_state.foto_terakhir)
        _save_state_now()

    finally:
        if driver:
            try:
                close_driver(driver)
            except Exception:
                pass
            _driver = None

    # ===== STEP 8: Summary =====
    _generate_summary(
        start_time, total_foto,
        _bot_state.total_sukses, _bot_state.total_gagal,
        akun_digunakan, acct_mgr, config,
    )

    # Hapus session jika semua foto selesai diupload
    foto_sisa = total_foto - (_bot_state.total_sukses + _bot_state.total_gagal)
    if foto_sisa <= 0 and session.exists():
        session.delete()
        print_info("✨ Session dihapus — semua foto telah selesai diproses.")


if __name__ == "__main__":
    run_bot()
