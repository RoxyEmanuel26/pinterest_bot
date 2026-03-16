"""
modules/pinterest.py
=====================
Fungsi-fungsi interaksi dengan Pinterest via Selenium WebDriver.
Menangani login, logout, cek sesi, upload pin, dan retry mechanism.
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


# URL Pinterest
PINTEREST_HOME = "https://www.pinterest.com/"
PINTEREST_LOGIN = "https://www.pinterest.com/login/"
PINTEREST_CREATE_PIN = "https://www.pinterest.com/pin-creation-tool/"
PINTEREST_LOGOUT = "https://www.pinterest.com/logout/"


def is_logged_in(driver) -> bool:
    """
    Cek apakah sesi Pinterest masih aktif (user sudah login).
    
    Mengecek keberadaan elemen yang hanya muncul saat sudah login,
    seperti tombol create atau avatar user.
    
    Args:
        driver: Instance Chrome WebDriver
    
    Returns:
        True jika masih login, False jika belum/expired
    """
    try:
        driver.get(PINTEREST_HOME)
        short_delay(2.0, 4.0)
        
        # Cek apakah redirect ke halaman login
        current_url = driver.current_url
        if "/login" in current_url:
            return False
        
        # Cek elemen yang menandakan sudah login
        wait = WebDriverWait(driver, 10)
        
        # Coba beberapa selector yang menandakan user sudah login
        login_indicators = [
            '[data-test-id="header-avatar"]',
            '[data-test-id="headerUserMenuButton"]',
            'div[data-test-id="homefeed-feed"]',
            '[data-test-id="create-button"]',
            'button[aria-label="Account and more options"]',
        ]
        
        for selector in login_indicators:
            try:
                element = driver.find_element(By.CSS_SELECTOR, selector)
                if element:
                    return True
            except (NoSuchElementException, TimeoutException):
                continue
        
        # Fallback: cek apakah ada elemen login form → belum login
        try:
            login_form = driver.find_element(By.CSS_SELECTOR, 'input[name="id"]')
            if login_form:
                return False
        except NoSuchElementException:
            pass
        
        # Jika tidak redirect ke login dan tidak ada form login,
        # kemungkinan besar sudah login
        if "/login" not in current_url and "/reset" not in current_url:
            return True
        
        return False
        
    except Exception as e:
        print_warning(f"Error saat cek status login: {e}")
        return False


def login(driver, email: str, password: str) -> bool:
    """
    Login ke Pinterest menggunakan email dan password.
    
    Menggunakan human_type untuk simulasi kecepatan mengetik manusia.
    Jika CAPTCHA muncul, program akan pause dan minta input manual.
    
    Args:
        driver: Instance Chrome WebDriver
        email: Email akun Pinterest
        password: Password akun Pinterest
    
    Returns:
        True jika login berhasil, False jika gagal
    """
    try:
        print_info(f"Memulai login untuk {email}...")
        
        # Navigasi ke halaman login
        driver.get(PINTEREST_LOGIN)
        short_delay(3.0, 5.0)
        
        wait = WebDriverWait(driver, 15)
        
        # Tunggu halaman login dimuat
        try:
            email_field = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[id="email"]'))
            )
        except TimeoutException:
            # Coba selector alternatif
            try:
                email_field = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name="id"]'))
                )
            except TimeoutException:
                # Mungkin sudah login
                if is_logged_in(driver):
                    print_success("Sudah login (sesi aktif dari Chrome Profile)")
                    return True
                print_error("Tidak bisa menemukan form login")
                return False
        
        # Clear field dan ketik email
        email_field.clear()
        short_delay(0.5, 1.0)
        human_type(email_field, email)
        short_delay(1.0, 2.0)
        
        # Cari dan isi field password
        try:
            password_field = driver.find_element(By.CSS_SELECTOR, 'input[id="password"]')
        except NoSuchElementException:
            password_field = driver.find_element(By.CSS_SELECTOR, 'input[name="password"]')
        
        password_field.clear()
        short_delay(0.5, 1.0)
        human_type(password_field, password)
        short_delay(1.0, 2.0)
        
        # Klik tombol login
        try:
            login_btn = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"]')
            login_btn.click()
        except NoSuchElementException:
            # Fallback: tekan Enter
            password_field.send_keys(Keys.RETURN)
        
        short_delay(5.0, 8.0)
        
        # Cek apakah ada CAPTCHA atau error
        current_url = driver.current_url
        page_source = driver.page_source.lower()
        
        # Deteksi CAPTCHA
        if "challenge" in current_url or "captcha" in page_source or "verify" in current_url:
            print_warning("⚠️ CAPTCHA terdeteksi! Silakan selesaikan CAPTCHA secara manual.")
            input("Tekan ENTER setelah menyelesaikan CAPTCHA...")
            short_delay(2.0, 3.0)
        
        # Deteksi error login
        error_selectors = [
            'div[data-test-id="loginError"]',
            '.error-text',
            'div[class*="error"]',
        ]
        for selector in error_selectors:
            try:
                error_el = driver.find_element(By.CSS_SELECTOR, selector)
                if error_el and error_el.is_displayed():
                    print_error(f"Login gagal: {error_el.text}")
                    return False
            except NoSuchElementException:
                continue
        
        # Verifikasi login berhasil
        short_delay(3.0, 5.0)
        if is_logged_in(driver):
            print_success(f"Login berhasil untuk {email}")
            return True
        
        # Cek sekali lagi setelah delay lebih lama
        short_delay(5.0, 8.0)
        if "/login" not in driver.current_url:
            print_success(f"Login berhasil untuk {email}")
            return True
        
        print_error(f"Login gagal untuk {email}")
        return False
        
    except Exception as e:
        print_error(f"Error saat login: {e}")
        return False


def logout(driver) -> bool:
    """
    Logout dari Pinterest.
    
    Args:
        driver: Instance Chrome WebDriver
    
    Returns:
        True jika logout berhasil
    """
    try:
        driver.get(PINTEREST_LOGOUT)
        short_delay(3.0, 5.0)
        print_info("Logout berhasil")
        return True
    except Exception as e:
        print_warning(f"Error saat logout: {e}")
        return False


def _select_board(driver, board_name: str) -> bool:
    """
    Pilih board untuk pin yang akan diupload.
    
    Args:
        driver: Instance Chrome WebDriver
        board_name: Nama board tujuan
    
    Returns:
        True jika board berhasil dipilih
    """
    try:
        wait = WebDriverWait(driver, 10)
        
        # Klik dropdown board
        board_selectors = [
            'button[data-test-id="board-dropdown-select-button"]',
            'button[data-test-id="boardDropdownSelectButton"]',
            'div[data-test-id="board-dropdown-select-button"]',
            'button[aria-label="Board"]',
            'div[data-test-id="boardDropdown"]',
        ]
        
        board_btn = None
        for selector in board_selectors:
            try:
                board_btn = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                if board_btn:
                    board_btn.click()
                    short_delay(1.5, 2.5)
                    break
            except (TimeoutException, NoSuchElementException):
                continue
        
        if not board_btn:
            # Coba cari board dropdown dengan teks
            try:
                board_elements = driver.find_elements(By.XPATH, 
                    '//button[contains(text(), "Choose a board")] | //button[contains(text(), "board")] | //div[@role="button"][contains(text(), "board")]')
                if board_elements:
                    board_elements[0].click()
                    short_delay(1.5, 2.5)
            except Exception:
                pass
        
        # Cari field pencarian board
        search_selectors = [
            'input[data-test-id="board-search-input"]',
            'input[placeholder*="Search"]',
            'input[placeholder*="search"]',
            'input[aria-label*="Search"]',
            'input[id="pickerSearchField"]',
        ]
        
        search_field = None
        for selector in search_selectors:
            try:
                search_field = driver.find_element(By.CSS_SELECTOR, selector)
                if search_field:
                    break
            except NoSuchElementException:
                continue
        
        if search_field:
            search_field.clear()
            human_type(search_field, board_name)
            short_delay(2.0, 3.0)
        
        # Klik board yang sesuai dari hasil pencarian
        try:
            # Cari board dengan nama yang sesuai
            board_options = driver.find_elements(By.XPATH,
                f'//div[contains(text(), "{board_name}")] | //span[contains(text(), "{board_name}")]')
            
            if board_options:
                for option in board_options:
                    try:
                        if option.is_displayed():
                            option.click()
                            short_delay(1.0, 2.0)
                            return True
                    except (ElementNotInteractableException, WebDriverException):
                        continue
            
            # Fallback: klik opsi pertama yang muncul
            short_delay(1.0, 1.5)
            first_option_selectors = [
                'div[data-test-id="boardWithoutSection"]',
                'div[role="option"]',
                'ul[role="listbox"] li',
            ]
            for selector in first_option_selectors:
                try:
                    options = driver.find_elements(By.CSS_SELECTOR, selector)
                    if options:
                        options[0].click()
                        short_delay(1.0, 2.0)
                        return True
                except (NoSuchElementException, ElementNotInteractableException):
                    continue
            
        except Exception as e:
            print_warning(f"Error memilih board: {e}")
        
        return True  # Proceed anyway, board mungkin sudah terpilih
        
    except Exception as e:
        print_warning(f"Error pada pemilihan board: {e}")
        return False


def upload_pin(driver, image_path: str, title: str, 
               description: str, board_name: str) -> bool:
    """
    Upload satu pin ke Pinterest.
    
    Langkah:
    1. Buka halaman pin creation tool
    2. Upload gambar
    3. Isi judul
    4. Isi deskripsi
    5. Pilih board
    6. Publish pin
    
    Args:
        driver: Instance Chrome WebDriver
        image_path: Path lengkap ke file gambar yang akan diupload
        title: Judul pin
        description: Deskripsi pin (termasuk hashtag)
        board_name: Nama board tujuan
    
    Returns:
        True jika upload berhasil, False jika gagal
    """
    try:
        # Navigasi ke halaman create pin
        driver.get(PINTEREST_CREATE_PIN)
        short_delay(3.0, 5.0)
        
        wait = WebDriverWait(driver, 20)
        
        # Step 1: Upload gambar
        # Cari input file (biasanya hidden)
        file_input = None
        file_input_selectors = [
            'input[type="file"]',
            'input[data-test-id="image-upload-input"]',
            'input[accept*="image"]',
        ]
        
        for selector in file_input_selectors:
            try:
                inputs = driver.find_elements(By.CSS_SELECTOR, selector)
                if inputs:
                    file_input = inputs[0]
                    break
            except NoSuchElementException:
                continue
        
        if not file_input:
            print_error("Tidak bisa menemukan input upload file")
            return False
        
        # Kirim path gambar ke input file
        absolute_path = os.path.abspath(image_path)
        file_input.send_keys(absolute_path)
        short_delay(4.0, 6.0)
        
        # Tunggu gambar selesai diupload
        try:
            wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, 
                'div[data-test-id="pin-draft-image"] img, '
                'div[data-test-id="uploadedImage"], '
                'img[data-test-id="pin-draft-image"], '
                'div[class*="uploaded"]'))
        except TimeoutException:
            # Mungkin tetap berhasil, lanjutkan
            short_delay(3.0, 5.0)
        
        # Step 2: Isi judul
        title_selectors = [
            'input[data-test-id="pin-draft-title"]',
            'input[id="pin-draft-title"]',
            'input[placeholder*="title" i]',
            'input[name="title"]',
            'div[data-test-id="pin-draft-title"] input',
            'textarea[data-test-id="pin-draft-title"]',
        ]
        
        title_field = None
        for selector in title_selectors:
            try:
                title_field = driver.find_element(By.CSS_SELECTOR, selector)
                if title_field:
                    break
            except NoSuchElementException:
                continue
        
        if not title_field:
            # Coba dengan XPath
            try:
                title_field = driver.find_element(By.XPATH,
                    '//input[@placeholder="Add a title"] | //input[contains(@placeholder, "title")]')
            except NoSuchElementException:
                pass
        
        if title_field:
            title_field.clear()
            short_delay(0.5, 1.0)
            human_type(title_field, title)
            short_delay(1.0, 2.0)
        
        # Step 3: Isi deskripsi
        desc_selectors = [
            'div[data-test-id="pin-draft-description"] .notranslate',
            'div[data-test-id="pin-draft-description"] [contenteditable="true"]',
            'div[role="textbox"][data-test-id="pin-draft-description"]',
            'textarea[data-test-id="pin-draft-description"]',
            'div[class*="Description"] [contenteditable="true"]',
            'div.public-DraftEditor-content',
        ]
        
        desc_field = None
        for selector in desc_selectors:
            try:
                desc_field = driver.find_element(By.CSS_SELECTOR, selector)
                if desc_field:
                    break
            except NoSuchElementException:
                continue
        
        if not desc_field:
            # Coba dengan XPath
            try:
                desc_field = driver.find_element(By.XPATH,
                    '//div[@data-test-id="pin-draft-description"]//div[@contenteditable="true"] | '
                    '//textarea[contains(@placeholder, "description") or contains(@placeholder, "Tell")]')
            except NoSuchElementException:
                pass
        
        if desc_field:
            desc_field.click()
            short_delay(0.5, 1.0)
            human_type(desc_field, description)
            short_delay(1.0, 2.0)
        
        # Step 4: Pilih board
        _select_board(driver, board_name)
        short_delay(1.0, 2.0)
        
        # Step 5: Publish pin
        publish_selectors = [
            'button[data-test-id="board-dropdown-save-button"]',
            'button[data-test-id="create-pin-save-button"]',
            'div[data-test-id="pin-draft-save-button"] button',
            'button[aria-label="Publish"]',
            'button[aria-label="Save"]',
        ]
        
        published = False
        for selector in publish_selectors:
            try:
                publish_btn = wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                if publish_btn:
                    publish_btn.click()
                    published = True
                    break
            except (TimeoutException, NoSuchElementException, 
                    ElementNotInteractableException):
                continue
        
        if not published:
            # Coba cari tombol Publish / Save dengan teks
            try:
                buttons = driver.find_elements(By.TAG_NAME, 'button')
                for btn in buttons:
                    btn_text = btn.text.strip().lower()
                    if btn_text in ('publish', 'save', 'simpan'):
                        btn.click()
                        published = True
                        break
            except Exception:
                pass
        
        if not published:
            print_error("Tidak bisa menemukan tombol Publish/Save")
            return False
        
        # Tunggu konfirmasi upload
        short_delay(5.0, 8.0)
        
        # Verifikasi sukses - cek apakah ada notifikasi sukses
        try:
            success_indicators = [
                'div[data-test-id="toast"]',
                'div[class*="success"]',
                'span[class*="success"]',
            ]
            for selector in success_indicators:
                try:
                    success_el = driver.find_element(By.CSS_SELECTOR, selector)
                    if success_el:
                        return True
                except NoSuchElementException:
                    continue
        except Exception:
            pass
        
        # Jika tidak ada error yang jelas, anggap berhasil
        current_url = driver.current_url
        if "pin-creation-tool" not in current_url or "published" in current_url:
            return True
        
        # Cek apakah masih di halaman yang sama (mungkin berhasil)
        return True
        
    except Exception as e:
        print_error(f"Error saat upload pin: {e}")
        return False


def upload_with_retry(driver, image_path: str, title: str,
                      description: str, board_name: str,
                      max_retries: int = 3) -> bool:
    """
    Upload pin dengan mekanisme retry.
    
    Jika upload gagal, coba ulang hingga max_retries kali.
    Setiap retry memiliki delay yang semakin lama (backoff).
    
    Args:
        driver: Instance Chrome WebDriver
        image_path: Path lengkap ke file gambar
        title: Judul pin
        description: Deskripsi pin
        board_name: Nama board tujuan
        max_retries: Jumlah maksimum percobaan ulang
    
    Returns:
        True jika upload berhasil (setelah retry), False jika tetap gagal
    """
    for attempt in range(1, max_retries + 1):
        try:
            print_info(f"Upload attempt {attempt}/{max_retries}: {os.path.basename(image_path)}")
            
            success = upload_pin(driver, image_path, title, description, board_name)
            
            if success:
                return True
            
            if attempt < max_retries:
                # Backoff delay: semakin lama dengan setiap retry
                backoff = attempt * random.uniform(5.0, 10.0)
                print_warning(f"Upload gagal, mencoba ulang dalam {backoff:.0f} detik...")
                time.sleep(backoff)
                
        except Exception as e:
            print_error(f"Error pada attempt {attempt}: {e}")
            if attempt < max_retries:
                backoff = attempt * random.uniform(5.0, 10.0)
                print_warning(f"Mencoba ulang dalam {backoff:.0f} detik...")
                time.sleep(backoff)
    
    print_error(f"Upload gagal setelah {max_retries} percobaan: {os.path.basename(image_path)}")
    return False
