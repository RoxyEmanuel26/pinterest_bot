"""
modules/browser.py
===================
Inisialisasi Chrome WebDriver dengan fitur anti-deteksi bot.
Menggunakan undetected-chromedriver dengan Chrome Profile per akun,
rotasi User-Agent, dan stealth mode untuk menghindari deteksi.
"""

import os
import time
import random

import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options


# Daftar User-Agent modern yang valid untuk rotasi
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


def create_driver(chrome_profile_path: str, headless: bool = False) -> uc.Chrome:
    """
    Buat instance Chrome WebDriver dengan configurasi anti-deteksi.
    
    Menggunakan undetected-chromedriver untuk bypass deteksi bot,
    Chrome Profile terpisah per akun, dan User-Agent acak.
    
    Args:
        chrome_profile_path: Path ke folder Chrome Profile untuk akun ini
        headless: Jalankan Chrome tanpa tampilan jika True
    
    Returns:
        Instance Chrome WebDriver yang siap digunakan
    """
    # Pastikan folder profile ada
    os.makedirs(chrome_profile_path, exist_ok=True)
    
    # Pilih User-Agent secara acak
    user_agent = random.choice(USER_AGENTS)
    
    # Konfigurasi Chrome options
    options = uc.ChromeOptions()
    
    # Chrome Profile untuk menyimpan sesi login
    options.add_argument(f"--user-data-dir={chrome_profile_path}")
    
    # User-Agent acak
    options.add_argument(f"--user-agent={user_agent}")
    
    # Anti-deteksi flags
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-first-run")
    options.add_argument("--no-service-autorun")
    options.add_argument("--password-store=basic")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--lang=id-ID")
    
    # Window size yang realistis
    options.add_argument("--window-size=1366,768")
    
    # Headless mode jika diminta
    if headless:
        options.add_argument("--headless=new")
    
    # Buat driver dengan undetected-chromedriver
    try:
        driver = uc.Chrome(options=options, version_main=145, use_subprocess=True)
    except Exception as e:
        print(f"[ERROR] Gagal membuat Chrome driver: {e}")
        print("[INFO] Pastikan Google Chrome terinstal dan versinya kompatibel.")
        raise
    
    # Set implicit wait
    driver.implicitly_wait(10)
    
    # Set page load timeout
    driver.set_page_load_timeout(60)
    
    # Inject JavaScript tambahan untuk stealth
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                // Hapus properti webdriver
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Override plugins agar tidak kosong
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                
                // Override languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['id-ID', 'id', 'en-US', 'en']
                });
                
                // Hapus chrome automation indicators
                window.chrome = {
                    runtime: {}
                };
            """
        })
    except Exception:
        # CDP commands mungkin tidak didukung di semua versi
        pass
    
    return driver


def close_driver(driver) -> None:
    """
    Tutup Chrome WebDriver dengan aman.
    
    Args:
        driver: Instance Chrome WebDriver yang akan ditutup
    """
    try:
        if driver:
            driver.quit()
    except Exception as e:
        print(f"[WARNING] Error saat menutup driver: {e}")


def random_delay(min_seconds: float, max_seconds: float) -> None:
    """
    Jeda acak antara aksi untuk simulasi perilaku manusia.
    
    Args:
        min_seconds: Minimum waktu jeda (detik)
        max_seconds: Maximum waktu jeda (detik)
    """
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)


def human_type(element, text: str, min_delay: float = 0.05, 
               max_delay: float = 0.15) -> None:
    """
    Ketik teks karakter demi karakter dengan kecepatan manusia.
    
    Mensimulasikan kecepatan mengetik manusia dengan jeda acak 
    antara setiap karakter (50-150ms default).
    
    Args:
        element: Selenium WebElement tempat mengetik
        text: Teks yang akan diketik
        min_delay: Minimum delay per karakter (detik)
        max_delay: Maximum delay per karakter (detik)
    """
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(min_delay, max_delay))


def short_delay(min_s: float = 1.0, max_s: float = 3.0) -> None:
    """
    Jeda pendek untuk transisi antar langkah.
    
    Args:
        min_s: Minimum waktu jeda (detik)
        max_s: Maximum waktu jeda (detik)
    """
    time.sleep(random.uniform(min_s, max_s))
