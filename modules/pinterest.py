"""
modules/pinterest.py
=====================
Upload pin ke Pinterest secara INSTAN menggunakan JavaScript injection.
Tidak ada human_type, tidak ada short_delay yang tidak perlu.
"""

import os
import time
import random

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementNotInteractableException,
    WebDriverException,
)

from modules.browser import human_type, short_delay, random_delay
from modules.logger import print_success, print_error, print_warning, print_info

PINTEREST_HOME       = "https://id.pinterest.com/"
PINTEREST_LOGIN      = "https://id.pinterest.com/login/"
PINTEREST_CREATE_PIN = "https://id.pinterest.com/pin-creation-tool/"
PINTEREST_LOGOUT     = "https://id.pinterest.com/logout/"

# ─────────────────────────────────────────────
#  JS INJECT — isi field instan tanpa ngetik
# ─────────────────────────────────────────────
_JS_FILL_INPUT = """
var el  = arguments[0];
var val = arguments[1];
var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value')
          || Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value');
if (setter) { setter.set.call(el, val); }
else        { el.value = val; }
el.dispatchEvent(new Event('input',  {bubbles:true}));
el.dispatchEvent(new Event('change', {bubbles:true}));
el.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true}));
"""

_JS_FILL_DIV = """
var el  = arguments[0];
var val = arguments[1];
el.focus();
el.innerText = val;
el.dispatchEvent(new Event('input',  {bubbles:true}));
el.dispatchEvent(new Event('change', {bubbles:true}));
el.dispatchEvent(new KeyboardEvent('keyup', {bubbles:true}));
"""


def _fill(driver, el, text: str) -> None:
    """Isi elemen secara instan via JavaScript. Fallback ke send_keys."""
    try:
        tag = el.tag_name.lower()
        if tag in ('input', 'textarea'):
            driver.execute_script(_JS_FILL_INPUT, el, text)
        else:
            driver.execute_script(_JS_FILL_DIV, el, text)
    except Exception:
        try:
            el.clear()
            el.send_keys(text)
        except Exception:
            pass


def _find(driver, css_list: list, xpath: str = None):
    """Cari elemen visible dari list CSS selector. Tanpa WebDriverWait."""
    for css in css_list:
        try:
            el = driver.find_element(By.CSS_SELECTOR, css)
            if el.is_displayed():
                return el
        except Exception:
            continue
    if xpath:
        try:
            el = driver.find_element(By.XPATH, xpath)
            if el.is_displayed():
                return el
        except Exception:
            pass
    return None


def _wait_for(driver, css_list: list, timeout: int = 25):
    """Tunggu sampai salah satu elemen dari css_list muncul di DOM."""
    end = time.time() + timeout
    while time.time() < end:
        for css in css_list:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, css)
                if els and els[0].is_displayed():
                    return els[0]
            except Exception:
                continue
        time.sleep(0.3)
    return None


# ─────────────────────────────────────────────
#  LOGIN / LOGOUT / CEK SESI
# ─────────────────────────────────────────────

def is_logged_in(driver) -> bool:
    """Cek apakah sesi Pinterest masih aktif."""
    try:
        driver.get(PINTEREST_HOME)
        time.sleep(2)
        if "/login" in driver.current_url:
            return False
        indicators = [
            '[data-test-id="header-avatar"]',
            '[data-test-id="headerUserMenuButton"]',
            '[data-test-id="create-button"]',
        ]
        for sel in indicators:
            try:
                if driver.find_element(By.CSS_SELECTOR, sel):
                    return True
            except NoSuchElementException:
                continue
        return "/login" not in driver.current_url
    except Exception as e:
        print_warning(f"Error cek login: {e}")
        return False


def login(driver, email: str, password: str) -> bool:
    """Login ke Pinterest. Gunakan human_type agar tidak terdeteksi bot."""
    try:
        print_info(f"Memulai login untuk {email}...")
        driver.get(PINTEREST_LOGIN)
        time.sleep(3)
        wait = WebDriverWait(driver, 15)

        try:
            email_field = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'input[id="email"], input[name="id"]')))
        except TimeoutException:
            if is_logged_in(driver):
                print_success("Sudah login (Chrome Profile aktif)")
                return True
            print_error("Tidak bisa menemukan form login")
            return False

        email_field.clear()
        time.sleep(0.3)
        human_type(email_field, email)
        time.sleep(0.5)

        try:
            pwd = driver.find_element(By.CSS_SELECTOR, 'input[id="password"]')
        except NoSuchElementException:
            pwd = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')

        pwd.clear()
        time.sleep(0.3)
        human_type(pwd, password)
        time.sleep(0.5)

        try:
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        except NoSuchElementException:
            pwd.send_keys(Keys.RETURN)

        time.sleep(5)

        src = driver.page_source.lower()
        url = driver.current_url
        if "challenge" in url or "captcha" in src or "verify" in url:
            print_warning("⚠️ CAPTCHA terdeteksi! Selesaikan manual.")
            input("Tekan ENTER setelah CAPTCHA selesai...")
            time.sleep(2)

        time.sleep(3)
        if is_logged_in(driver):
            print_success(f"Login berhasil: {email}")
            return True

        time.sleep(5)
        if "/login" not in driver.current_url:
            print_success(f"Login berhasil: {email}")
            return True

        print_error(f"Login gagal: {email}")
        return False
    except Exception as e:
        print_error(f"Error login: {e}")
        return False


def logout(driver) -> bool:
    """Logout dari Pinterest."""
    try:
        driver.get(PINTEREST_LOGOUT)
        time.sleep(3)
        print_info("Logout berhasil")
        return True
    except Exception as e:
        print_warning(f"Error logout: {e}")
        return False


# ─────────────────────────────────────────────
#  PILIH BOARD
# ─────────────────────────────────────────────

def _select_board(driver, board_name: str) -> bool:
    """Pilih board Pinterest. Delay minimal."""
    try:
        wait = WebDriverWait(driver, 10)

        board_btn = None
        for sel in [
            'button[data-test-id="board-dropdown-select-button"]',
            'button[data-test-id="boardDropdownSelectButton"]',
            'div[data-test-id="board-dropdown-select-button"]',
        ]:
            try:
                board_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                board_btn.click()
                time.sleep(0.5)
                break
            except (TimeoutException, NoSuchElementException):
                continue

        if not board_btn:
            try:
                els = driver.find_elements(By.XPATH,
                    '//button[contains(text(),"Choose a board")]'
                    '|//button[contains(text(),"Pilih papan")]')
                if els:
                    els[0].click()
                    time.sleep(0.5)
            except Exception:
                pass

        # Cari search field board
        sf = _find(driver, [
            'input[data-test-id="board-search-input"]',
            'input[placeholder*="Search"]',
            'input[placeholder*="Cari"]',
            'input[id="pickerSearchField"]',
        ])
        if sf:
            sf.clear()
            sf.send_keys(board_name)
            time.sleep(0.8)

        # Klik nama board
        try:
            opts = driver.find_elements(By.XPATH,
                f'//div[text()="{board_name}"]|//span[text()="{board_name}"]')
            for opt in opts:
                if opt.is_displayed():
                    opt.click()
                    time.sleep(0.3)
                    return True
        except Exception:
            pass

        # Fallback klik opsi pertama
        time.sleep(0.3)
        for sel in [
            'div[data-test-id="boardWithoutSection"]',
            'div[role="option"]',
            'ul[role="listbox"] li',
        ]:
            try:
                opts = driver.find_elements(By.CSS_SELECTOR, sel)
                if opts:
                    opts[0].click()
                    time.sleep(0.3)
                    return True
            except Exception:
                continue

        return True
    except Exception as e:
        print_warning(f"Error pilih board: {e}")
        return False


# ─────────────────────────────────────────────
#  UPLOAD PIN — INSTAN
# ─────────────────────────────────────────────

def upload_pin(driver, image_path: str, title: str,
               description: str, board_name: str,
               link_url: str = "") -> bool:
    """
    Upload pin ke Pinterest secara instan.
    Semua field diisi via JavaScript injection — tidak ada ngetik per karakter.
    Estimasi: 15-25 detik per pin termasuk upload gambar.
    """
    try:
        # ── 1. Buka halaman create pin ──────────────────────────────
        driver.get(PINTEREST_CREATE_PIN)

        # Tunggu input[type=file] muncul (max 15 detik)
        file_input = _wait_for(driver, [
            'input[type="file"]',
            'input[accept*="image"]',
        ], timeout=15)

        if not file_input:
            print_error("Halaman create pin tidak termuat")
            return False

        # ── 2. Upload gambar ────────────────────────────────────────
        file_input.send_keys(os.path.abspath(image_path))
        print_info(f"   Mengirim file: {os.path.basename(image_path)}")

        # Tunggu field judul muncul = tanda gambar sudah diproses
        title_appeared = _wait_for(driver, [
            'input[data-test-id="pin-draft-title"]',
            'input[placeholder="Tambahkan judul"]',
            'input[placeholder="Add a title"]',
            'input[placeholder*="judul" i]',
            'input[placeholder*="title" i]',
        ], timeout=30)

        if not title_appeared:
            print_warning("Field judul tidak muncul, lanjutkan...")
            time.sleep(3)

        # ── 3. Isi Judul — instan ───────────────────────────────────
        tf = _find(driver, [
            'input[data-test-id="pin-draft-title"]',
            'input[placeholder="Tambahkan judul"]',
            'input[placeholder="Add a title"]',
            'input[placeholder*="judul" i]',
            'input[placeholder*="title" i]',
        ])
        if tf and title:
            tf.click()
            _fill(driver, tf, title)

        # ── 4. Isi Deskripsi — instan ───────────────────────────────
        df = _find(driver, [
            'textarea[data-test-id="pin-draft-description"]',
            'textarea[placeholder="Ceritakan lebih banyak"]',
            'textarea[placeholder*="Ceritakan" i]',
            'textarea[placeholder*="Tell" i]',
            'div[data-test-id="pin-draft-description"] [contenteditable="true"]',
        ], xpath='//textarea[contains(@placeholder,"Ceritakan") or contains(@placeholder,"Tell")]')
        if df and description:
            df.click()
            _fill(driver, df, description)

        # ── 5. Isi Link/Tautan — instan ─────────────────────────────
        if link_url:
            lf = _find(driver, [
                'input[data-test-id="pin-draft-link"]',
                'input[placeholder="Tambahkan tautan"]',
                'input[placeholder="Add a destination link"]',
                'input[placeholder*="tautan" i]',
                'input[placeholder*="destination" i]',
                'input[placeholder*="link" i]',
            ])
            if lf:
                lf.click()
                _fill(driver, lf, link_url)
            else:
                print_warning("Field tautan tidak ditemukan")

        # ── 6. Pilih Board ──────────────────────────────────────────
        _select_board(driver, board_name)

        # ── 7. Klik Publish ─────────────────────────────────────────
        wait10 = WebDriverWait(driver, 10)
        published = False

        for sel in [
            'button[data-test-id="board-dropdown-save-button"]',
            'button[data-test-id="create-pin-save-button"]',
            'div[data-test-id="pin-draft-save-button"] button',
            'button[aria-label="Terbitkan"]',
            'button[aria-label="Simpan"]',
            'button[aria-label="Publish"]',
            'button[aria-label="Save"]',
        ]:
            try:
                btn = wait10.until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
                if btn.is_displayed():
                    btn.click()
                    published = True
                    break
            except (TimeoutException, NoSuchElementException,
                    ElementNotInteractableException):
                continue

        if not published:
            for btn in driver.find_elements(By.TAG_NAME, 'button'):
                try:
                    if btn.text.strip().lower() in ('terbitkan','simpan','publish','save'):
                        if btn.is_displayed() and btn.is_enabled():
                            btn.click()
                            published = True
                            break
                except Exception:
                    continue

        if not published:
            print_error("Tombol Publish/Terbitkan tidak ditemukan")
            return False

        # ── 8. Tunggu selesai lalu lanjut ───────────────────────────
        time.sleep(3)
        return True

    except Exception as e:
        print_error(f"Error upload pin: {e}")
        return False


def upload_with_retry(driver, image_path: str, title: str,
                      description: str, board_name: str,
                      link_url: str = "",
                      max_retries: int = 3) -> bool:
    """Upload pin dengan retry. Backoff delay tiap percobaan gagal."""
    for attempt in range(1, max_retries + 1):
        try:
            print_info(f"Upload attempt {attempt}/{max_retries}: {os.path.basename(image_path)}")
            if upload_pin(driver, image_path, title, description, board_name, link_url):
                return True
            if attempt < max_retries:
                backoff = attempt * random.uniform(4.0, 7.0)
                print_warning(f"Gagal, retry dalam {backoff:.0f} detik...")
                time.sleep(backoff)
        except Exception as e:
            print_error(f"Error attempt {attempt}: {e}")
            if attempt < max_retries:
                time.sleep(attempt * 5)

    print_error(f"Upload gagal setelah {max_retries}x: {os.path.basename(image_path)}")
    return False
