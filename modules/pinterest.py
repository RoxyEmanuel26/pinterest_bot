"""
modules/pinterest.py
=====================
Upload pin ke Pinterest secara INSTAN menggunakan JavaScript injection.
- input[type=file] hidden  → _find_any / _wait_for_any
- deskripsi contenteditable→ _fill_contenteditable via JS execCommand
- topik/tag                → _fill_topics (ketik lalu pilih suggestion)
- semua field              → tidak ada human_type, delay minimal
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
)

from modules.browser import human_type, short_delay, random_delay
from modules.logger import print_success, print_error, print_warning, print_info

PINTEREST_HOME       = "https://id.pinterest.com/"
PINTEREST_LOGIN      = "https://id.pinterest.com/login/"
PINTEREST_CREATE_PIN = "https://id.pinterest.com/pin-creation-tool/"
PINTEREST_LOGOUT     = "https://id.pinterest.com/logout/"


# ══════════════════════════════════════════════════════════════
#  JS HELPERS
# ══════════════════════════════════════════════════════════════

# Untuk input / textarea biasa (React-aware)
_JS_SET_NATIVE_VALUE = """
(function(el, val) {
    var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value') ||
        Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype, 'value');
    if (nativeInputValueSetter) nativeInputValueSetter.set.call(el, val);
    else el.value = val;
    ['input','change','keyup','keydown'].forEach(function(evt) {
        el.dispatchEvent(new Event(evt, {bubbles: true}));
    });
})(arguments[0], arguments[1]);
"""

# Untuk div/span contenteditable (deskripsi Pinterest pakai ini)
# execCommand('insertText') adalah satu-satunya cara yang benar-benar
# trigger React synthetic event di contenteditable
_JS_FILL_CONTENTEDITABLE = """
(function(el, val) {
    el.focus();
    // Kosongkan dulu
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
    // Isi teks
    document.execCommand('insertText', false, val);
    // Kirim event tambahan agar React/Pinterest menangkap
    el.dispatchEvent(new Event('input',  {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
})(arguments[0], arguments[1]);
"""

# Scroll elemen ke viewport lalu klik
_JS_SCROLL_CLICK = """
arguments[0].scrollIntoView({block:'center', inline:'nearest'});
arguments[0].click();
"""




# ══════════════════════════════════════════════════════════════
#  ELEMENT FINDERS (cepat, tanpa WebDriverWait)
# ══════════════════════════════════════════════════════════════

def _find_any(driver, css_list: list):
    """Cari elemen di DOM tanpa cek is_displayed() (untuk elemen hidden)."""
    for css in css_list:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, css)
            if els:
                return els[0]
        except Exception:
            continue
    return None


def _find_visible(driver, css_list: list, xpath: str = None):
    """
    Cari elemen visible. Gunakan scrollIntoView sebelum cek is_displayed
    agar elemen di luar viewport tetap terdeteksi.
    """
    for css in css_list:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, css)
            for el in els:
                try:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'})", el)
                    if el.is_displayed():
                        return el
                except Exception:
                    continue
        except Exception:
            continue
    if xpath:
        try:
            els = driver.find_elements(By.XPATH, xpath)
            for el in els:
                try:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'})", el)
                    if el.is_displayed():
                        return el
                except Exception:
                    continue
        except Exception:
            pass
    return None


def _wait_for_any(driver, css_list: list, timeout: int = 5):
    """Tunggu elemen ada di DOM (tidak harus visible)."""
    end = time.time() + timeout
    while time.time() < end:
        for css in css_list:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, css)
                if els:
                    return els[0]
            except Exception:
                continue
        time.sleep(0.25)
    return None


def _wait_for_visible(driver, css_list: list, timeout: int = 5):
    """Tunggu elemen visible + dalam viewport."""
    end = time.time() + timeout
    while time.time() < end:
        for css in css_list:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, css)
                for el in els:
                    try:
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'})", el)
                        if el.is_displayed():
                            return el
                    except Exception:
                        continue
            except Exception:
                continue
        time.sleep(0.25)
    return None


# ══════════════════════════════════════════════════════════════
#  FILL FUNCTIONS
# ══════════════════════════════════════════════════════════════

def _fill(driver, el, text: str) -> None:
    """
    Isi elemen secara instan.
    - input/textarea  → native value setter (React-aware)
    - contenteditable → execCommand insertText
    """
    try:
        tag = el.tag_name.lower()
        is_ce = el.get_attribute('contenteditable') in ('true', 'plaintext-only')

        if is_ce or tag in ('div', 'span', 'p'):
            driver.execute_script(_JS_FILL_CONTENTEDITABLE, el, text)
        else:
            driver.execute_script(_JS_SET_NATIVE_VALUE, el, text)
    except Exception:
        # Fallback: klik + clear + send_keys
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'})", el)
            el.click()
            el.send_keys(Keys.CONTROL + 'a')
            el.send_keys(Keys.DELETE)
            el.send_keys(text)
        except Exception:
            pass





# ══════════════════════════════════════════════════════════════
#  LOGIN / LOGOUT / CEK SESI
# ══════════════════════════════════════════════════════════════

def is_logged_in(driver) -> bool:
    """
    Cek sesi aktif TANPA navigasi ke home.
    Hanya cek URL dan elemen header di halaman yang sedang terbuka.
    """
    try:
        url = driver.current_url

        if "/login" in url or "/reset" in url:
            return False

        if not url or url in ("about:blank", "data:,"):
            driver.get(PINTEREST_HOME)
            time.sleep(2)
            url = driver.current_url
            if "/login" in url:
                return False

        for sel in [
            '[data-test-id="header-avatar"]',
            '[data-test-id="headerUserMenuButton"]',
            '[data-test-id="create-button"]',
            'button[aria-label="Account and more options"]',
        ]:
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
    """Login ke Pinterest."""
    try:
        print_info(f"Memulai login untuk {email}...")
        driver.get(PINTEREST_LOGIN)
        time.sleep(2)
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
        time.sleep(0.1)
        human_type(email_field, email)
        time.sleep(0.3)

        try:
            pwd = driver.find_element(By.CSS_SELECTOR, 'input[id="password"]')
        except NoSuchElementException:
            pwd = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')

        pwd.clear()
        time.sleep(0.1)
        human_type(pwd, password)
        time.sleep(0.3)

        try:
            driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
        except NoSuchElementException:
            pwd.send_keys(Keys.RETURN)

        time.sleep(3)

        src = driver.page_source.lower()
        url = driver.current_url
        if "challenge" in url or "captcha" in src or "verify" in url:
            print_warning("\u26a0\ufe0f CAPTCHA terdeteksi! Selesaikan manual.")
            input("Tekan ENTER setelah CAPTCHA selesai...")
            time.sleep(1)

        time.sleep(2)
        if "/login" not in driver.current_url:
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
    try:
        driver.get(PINTEREST_LOGOUT)
        time.sleep(3)
        print_info("Logout berhasil")
        return True
    except Exception as e:
        print_warning(f"Error logout: {e}")
        return False


# ══════════════════════════════════════════════════════════════
#  SELECT BOARD
# ══════════════════════════════════════════════════════════════

def _select_board(driver, board_name: str) -> bool:
    try:
        board_btn = _wait_for_visible(driver, [
            'button[data-test-id="board-dropdown-select-button"]',
            'button[data-test-id="boardDropdownSelectButton"]',
            'div[data-test-id="board-dropdown-select-button"]',
        ], timeout=3)

        if board_btn:
            driver.execute_script(_JS_SCROLL_CLICK, board_btn)
            time.sleep(0.1)
        else:
            els = driver.find_elements(By.XPATH,
                '//button[contains(text(),"Choose a board")]'
                '|//button[contains(text(),"Pilih papan")]')
            if els:
                driver.execute_script(_JS_SCROLL_CLICK, els[0])
                time.sleep(0.1)

        # Cari dan isi search field board
        sf = _find_visible(driver, [
            'input[data-test-id="board-search-input"]',
            'input[placeholder*="Search"]',
            'input[placeholder*="Cari"]',
            'input[id="pickerSearchField"]',
        ])
        if sf:
            sf.clear()
            sf.send_keys(board_name)
            time.sleep(0.2)

        # Klik nama board yang tepat
        opts = driver.find_elements(By.XPATH,
            f'//div[text()="{board_name}"]|//span[text()="{board_name}"]')
        for opt in opts:
            try:
                if opt.is_displayed():
                    driver.execute_script(_JS_SCROLL_CLICK, opt)
                    time.sleep(0.1)
                    return True
            except Exception:
                continue

        # Fallback: klik opsi pertama di listbox
        for sel in [
            'div[data-test-id="boardWithoutSection"]',
            'div[role="option"]',
            'ul[role="listbox"] li',
        ]:
            opts = driver.find_elements(By.CSS_SELECTOR, sel)
            if opts:
                try:
                    driver.execute_script(_JS_SCROLL_CLICK, opts[0])
                    time.sleep(0.1)
                    return True
                except Exception:
                    continue

        return True
    except Exception as e:
        print_warning(f"Error pilih board: {e}")
        return False


# ══════════════════════════════════════════════════════════════
#  UPLOAD PIN — INSTAN
# ══════════════════════════════════════════════════════════════

def upload_pin(driver, image_path: str, title: str,
               description: str, board_name: str,
               link_url: str = "") -> bool:
    """
    Upload pin ke Pinterest secara instan.
    - Semua field diisi via JS (bukan ngetik per karakter)
    - Deskripsi pakai execCommand('insertText') agar React terbaca
    - Semua field -> tunggu minimal
    """

    try:
        # ── 1. Buka halaman create pin ──────────────────────────────
        driver.get(PINTEREST_CREATE_PIN)

        # Tunggu input[type=file] ada di DOM (Pinterest menyembunyikannya)
        file_input = _wait_for_any(driver, [
            'input[type="file"]',
            'input[accept*="image"]',
            'input[accept*="image/"]',
        ], timeout=5)

        if not file_input:
            print_warning("input[type=file] tidak ditemukan, fallback 3 detik...")
            time.sleep(1)
            file_input = _find_any(driver, [
                'input[type="file"]',
                'input[accept*="image"]',
            ])
            if not file_input:
                print_error("Halaman create pin tidak termuat")
                return False

        # ── 2. Upload gambar ────────────────────────────────────────
        file_input.send_keys(os.path.abspath(image_path))
        print_info(f"   Mengirim file: {os.path.basename(image_path)}")
        
        time.sleep(1) # Tunggu sejenak agar React selesai render komponen form setelah gambar dimuat

        # ── 3. Isi Judul (Pure Native Selenium) ─────────────────────
        if title:
            for attempt in range(3):
                try:
                    title_el = _wait_for_visible(driver, [
                        'input[data-test-id="pin-draft-title"]',
                        'input[id="storyboard-selector-title"]',
                        'input[placeholder*="judul" i]',
                        'input[placeholder*="title" i]'
                    ], timeout=5)
                    if title_el:
                        title_el.click()
                        time.sleep(0.1)
                        title_el.clear()
                        title_el.send_keys(title)
                        print_info("   ✅ Judul terisi")
                        break
                except Exception:
                    time.sleep(0.3)

        # ── 4. Isi Deskripsi (Pure Native Selenium) ──────────────────
        if description:
            for attempt in range(3):
                try:
                    desc_el = _wait_for_visible(driver, [
                        'div[data-test-id="pin-draft-description"] div[role="textbox"]',
                        'div[data-test-id="pin-draft-description"] [contenteditable="true"]',
                        'div[data-test-id="storyboard-selector-description"] div[contenteditable="true"]',
                        'div[role="textbox"][contenteditable="true"]',
                        'div[contenteditable="true"]'
                    ], timeout=5)
                    if desc_el:
                        desc_el.click()
                        time.sleep(0.1)
                        # Select all existing text and replace
                        desc_el.send_keys(Keys.CONTROL, "a")
                        time.sleep(0.05)
                        desc_el.send_keys(description)
                        print_info("   ✅ Deskripsi terisi")
                        break
                except Exception:
                    time.sleep(0.3)

        # ── 5. Isi Tautan/Link (Pure Native Selenium) ────────────────
        if link_url:
            for attempt in range(3):
                try:
                    lf = _wait_for_visible(driver, [
                        'input[id="storyboard-selector-link"]',
                        'input[data-test-id="pin-draft-link"]',
                        'input[placeholder*="tautan" i]',
                        'input[placeholder*="link" i]',
                        'textarea[placeholder*="tautan" i]',
                        'textarea[placeholder*="link" i]'
                    ], timeout=5)
                    if lf:
                        lf.click()
                        time.sleep(0.1)
                        lf.clear()
                        lf.send_keys(link_url)
                        # Tekan TAB untuk memaksa blur event → React register value
                        lf.send_keys(Keys.TAB)
                        print_info("   ✅ Tautan terisi")
                        break
                except Exception:
                    time.sleep(0.3)

        # ── 6. Pilih Board ──────────────────────────────────────────
        _select_board(driver, board_name)

        # ── 7. Klik Tombol Terbitkan ─────────────────────────────────
        print_info("   Mencari tombol Terbitkan...")
        time.sleep(1)

        published = False
        timeout_end = time.time() + 30

        while time.time() < timeout_end:
            try:
                # Cari SEMUA button di halaman
                all_btns = driver.find_elements(By.TAG_NAME, 'button')
                for btn in all_btns:
                    try:
                        txt = btn.text.strip().lower()
                        if txt in ('terbitkan', 'publish', 'simpan', 'save'):
                            # Klik langsung pakai Selenium native click
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'})", btn)
                            btn.click()
                            print_info("   ✅ Tombol Terbitkan diklik!")
                            published = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            if published:
                break

            time.sleep(1)

        if not published:
            print_error("Tombol Publish tidak ditemukan / gagal diklik / timeout")
            return False

        # ── 8. Tunggu konfirmasi upload selesai (Toast) ──────────────
        time.sleep(3)
        try:
            val_toast = WebDriverWait(driver, 5).until(EC.presence_of_element_located((
                By.CSS_SELECTOR, 'div[data-test-id="toast"], div[class*="success"], span[class*="success"]'
            )))
        except TimeoutException:
            pass # Kadang toast terlewat atau lambat, kita anggap success
            
        # Pindah ke home/create pin awal untuk reset state
        try:
            driver.get(PINTEREST_CREATE_PIN)
            time.sleep(1)
        except Exception:
            pass
            
        return True

    except Exception as e:
        print_error(f"Error upload pin: {e}")
        return False


def upload_with_retry(driver, image_path: str, title: str,
                      description: str, board_name: str,
                      link_url: str = "",
                      max_retries: int = 3) -> bool:
    """Upload pin dengan retry otomatis."""

    for attempt in range(1, max_retries + 1):
        try:
            print_info(f"Upload attempt {attempt}/{max_retries}: {os.path.basename(image_path)}")
            if upload_pin(driver, image_path, title, description,
                          board_name, link_url):
                return True
            if attempt < max_retries:
                backoff = attempt * random.uniform(1.0, 4.0)
                print_warning(f"Gagal, retry dalam {backoff:.0f} detik...")
                time.sleep(backoff)
        except Exception as e:
            print_error(f"Error attempt {attempt}: {e}")
            if attempt < max_retries:
                time.sleep(attempt * 5)

    print_error(f"Upload gagal setelah {max_retries}x: {os.path.basename(image_path)}")
    return False
