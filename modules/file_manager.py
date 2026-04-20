"""
modules/file_manager.py
========================
Manajemen file foto: scan folder, watermark otomatis, dan optimasi gambar.
Menangani seluruh pipeline pemrosesan foto sebelum upload:
foto asli → watermark → optimasi → siap upload.
"""

import os
import glob
import functools
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter


# Format foto yang didukung
SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def scan_photos(folder: str) -> list[str]:
    """
    Scan folder foto dan kembalikan list path foto yang didukung,
    diurutkan berdasarkan tanggal modifikasi terbaru (newest first).
    
    Args:
        folder: Path ke folder yang berisi foto-foto
    
    Returns:
        List path lengkap foto-foto, diurutkan dari terbaru
    """
    if not os.path.exists(folder):
        raise FileNotFoundError(f"Folder foto tidak ditemukan: {folder}")

    photos = []
    for file in os.listdir(folder):
        # Skip subfolder watermarked dan optimized
        file_path = os.path.join(folder, file)
        if os.path.isdir(file_path):
            continue
        
        ext = os.path.splitext(file)[1].lower()
        if ext in SUPPORTED_FORMATS:
            photos.append(file_path)

    # Urutkan berdasarkan tanggal modifikasi terbaru (newest first)
    photos.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return photos


@functools.lru_cache(maxsize=64)
def _get_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Coba load font Arial, fallback ke font default Pillow jika tidak ada.
    Hasil di-cache dengan lru_cache untuk menghindari disk I/O berulang.
    
    Args:
        font_size: Ukuran font dalam pixel
    
    Returns:
        Font object yang siap digunakan
    """
    # Daftar path font yang mungkin ada
    font_paths = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, font_size)
            except (IOError, OSError):
                continue
    
    # Fallback ke font default
    try:
        return ImageFont.truetype("arial.ttf", font_size)
    except (IOError, OSError):
        return ImageFont.load_default()


def _calc_font_size_for_width(text: str, target_width: int,
                               min_size: int = 16, max_size: int = 500) -> int:
    """
    Hitung ukuran font agar lebar teks rendered ≈ target_width piksel.
    Menggunakan pendekatan iteratif (binary search).
    
    Args:
        text: Teks yang akan diukur
        target_width: Lebar target dalam piksel
        min_size: Ukuran font minimum
        max_size: Ukuran font maksimum
    
    Returns:
        Ukuran font optimal dalam piksel
    """
    low, high = min_size, max_size
    best = min_size
    
    while low <= high:
        mid = (low + high) // 2
        font = _get_font(mid)
        
        # Ukur lebar teks pada ukuran ini
        try:
            bbox = font.getbbox(text)
            tw = bbox[2] - bbox[0]
        except AttributeError:
            # Fallback Pillow lama
            tmp_img = Image.new("RGBA", (1, 1))
            tmp_draw = ImageDraw.Draw(tmp_img)
            tw, _ = tmp_draw.textsize(text, font=font)
        
        if tw <= target_width:
            best = mid
            low = mid + 1
        else:
            high = mid - 1
    
    return best


def add_watermark(src_path: str, dst_path: str, text: str = "www.roxy.my.id",
                  opacity: float = 0.8, width_ratio: float = 0.5) -> str:
    """
    Tambahkan watermark teks ke foto.
    
    Watermark diletakkan di tengah-bawah gambar. Ukuran font dihitung
    secara dinamis agar lebar teks ≈ width_ratio × lebar gambar.
    Teks putih dengan outline/shadow hitam, semi-transparan.
    
    Args:
        src_path: Path foto sumber (asli)
        dst_path: Path foto tujuan (dengan watermark)
        text: Teks watermark
        opacity: Transparansi watermark (0.0 - 1.0)
        width_ratio: Rasio lebar teks terhadap lebar gambar (0.5 = 50%)
    
    Returns:
        Path foto yang sudah di-watermark
    """
    # Buka gambar asli (dengan proper resource management)
    img = Image.open(src_path).convert("RGBA")
    try:
        width, height = img.size
        
        # Hitung ukuran font agar teks ≈ 50% lebar gambar
        target_text_width = int(width * width_ratio)
        font_size = _calc_font_size_for_width(text, target_text_width)
        font = _get_font(font_size)
        
        # Buat layer transparent untuk watermark
        watermark_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(watermark_layer)
        
        # Dapatkan ukuran teks
        padding_bottom = 20
        
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except AttributeError:
            text_width, text_height = draw.textsize(text, font=font)
        
        # Posisi: centered horizontal, dekat bawah
        x = (width - text_width) // 2
        y = height - text_height - padding_bottom
        
        # Hitung alpha dari opacity (clamp 0.0 - 1.0)
        opacity = max(0.0, min(1.0, opacity))
        alpha = int(255 * opacity)
        
        # Gambar shadow/outline hitam (offset 3px untuk ukuran besar)
        shadow_color = (0, 0, 0, alpha)
        outline_range = max(2, font_size // 30)  # outline lebih tebal untuk font besar
        for offset_x in range(-outline_range, outline_range + 1):
            for offset_y in range(-outline_range, outline_range + 1):
                if offset_x == 0 and offset_y == 0:
                    continue
                draw.text((x + offset_x, y + offset_y), text, 
                         font=font, fill=shadow_color)
        
        # Gambar teks utama putih
        text_color = (255, 255, 255, alpha)
        draw.text((x, y), text, font=font, fill=text_color)
        
        # Gabungkan watermark layer dengan gambar asli
        watermarked = Image.alpha_composite(img, watermark_layer)
        watermark_layer.close()
    finally:
        img.close()
    
    # Pastikan folder tujuan ada
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    
    # Simpan - konversi ke RGB jika format tidak mendukung RGBA
    try:
        dst_ext = os.path.splitext(dst_path)[1].lower()
        if dst_ext in (".jpg", ".jpeg"):
            watermarked = watermarked.convert("RGB")
            watermarked.save(dst_path, "JPEG", quality=95)
        elif dst_ext == ".png":
            watermarked.save(dst_path, "PNG")
        elif dst_ext == ".webp":
            watermarked.save(dst_path, "WEBP", quality=95)
        elif dst_ext == ".gif":
            watermarked = watermarked.convert("RGB")
            watermarked.save(dst_path, "JPEG", quality=95)
            dst_path = os.path.splitext(dst_path)[0] + ".jpg"
        else:
            watermarked = watermarked.convert("RGB")
            watermarked.save(dst_path, "JPEG", quality=95)
    finally:
        watermarked.close()
    
    return dst_path


def optimize_image(src_path: str, dst_path: str, 
                   max_size_mb: float = 10.0) -> str:
    """
    Optimasi ukuran gambar: resize jika terlalu besar, 
    konversi PNG/WEBP ke JPEG untuk hemat ukuran.
    
    Args:
        src_path: Path gambar sumber
        dst_path: Path gambar tujuan (optimized)
        max_size_mb: Ukuran maksimum dalam MB
    
    Returns:
        Path gambar yang sudah dioptimasi
    """
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    
    img = Image.open(src_path)
    try:
        src_ext = os.path.splitext(src_path)[1].lower()
        
        # Konversi PNG/WEBP ke JPEG untuk menghemat ukuran
        if src_ext in (".png", ".webp"):
            if img.mode in ("RGBA", "P", "LA"):
                # Buat background putih untuk gambar dengan transparansi
                background = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                img.close()
                img = background
            else:
                img = img.convert("RGB")
            
            # Ubah ekstensi tujuan ke .jpg
            dst_path = os.path.splitext(dst_path)[0] + ".jpg"
        elif img.mode == "RGBA":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img.close()
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        
        # Cek ukuran file sumber
        file_size_mb = os.path.getsize(src_path) / (1024 * 1024)
        
        if file_size_mb > max_size_mb:
            # Hitung rasio resize
            ratio = (max_size_mb / file_size_mb) ** 0.5
            new_width = int(img.width * ratio)
            new_height = int(img.height * ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Simpan dengan kompresi
        quality = 85
        img.save(dst_path, "JPEG", quality=quality, optimize=True)
        
        # Jika masih terlalu besar, kurangi quality secara bertahap
        while os.path.getsize(dst_path) > max_size_mb * 1024 * 1024 and quality > 30:
            quality -= 10
            img.save(dst_path, "JPEG", quality=quality, optimize=True)
    finally:
        img.close()
    
    return dst_path


def prepare_photo(photo_path: str, foto_folder: str, config: dict) -> str:
    """
    Pipeline lengkap pemrosesan foto sebelum upload:
    foto asli → watermark → optimasi → siap upload.
    
    Jika versi watermarked/optimized sudah ada, skip proses tersebut.
    
    Args:
        photo_path: Path lengkap ke foto asli
        foto_folder: Path folder utama foto
        config: Dictionary konfigurasi dari config.json
    
    Returns:
        Path foto final yang siap diupload
    """
    filename = os.path.basename(photo_path)
    name_without_ext = os.path.splitext(filename)[0]
    ext = os.path.splitext(filename)[1].lower()
    
    # Path subfolder
    watermarked_dir = os.path.join(foto_folder, "watermarked")
    optimized_dir = os.path.join(foto_folder, "optimized")
    os.makedirs(watermarked_dir, exist_ok=True)
    os.makedirs(optimized_dir, exist_ok=True)
    
    # Step 1: Watermark
    watermark_text = config.get("watermark_text", "www.kumpulenak.web.id")
    watermark_opacity = config.get("watermark_opacity", 0.8)
    
    # GIF → disimpan sebagai JPEG setelah watermark
    if ext == ".gif":
        wm_filename = name_without_ext + ".jpg"
    else:
        wm_filename = filename
    watermarked_path = os.path.join(watermarked_dir, wm_filename)
    
    # Cek apakah versi watermarked sudah ada
    if not os.path.exists(watermarked_path):
        watermarked_path = add_watermark(
            src_path=photo_path,
            dst_path=watermarked_path,
            text=watermark_text,
            opacity=watermark_opacity,
        )
    
    # Step 2: Optimasi
    # Tentukan nama file optimized (mungkin berubah ekstensi ke .jpg)
    if ext in (".png", ".webp", ".gif"):
        optimized_filename = name_without_ext + ".jpg"
    else:
        optimized_filename = filename
    
    optimized_path = os.path.join(optimized_dir, optimized_filename)
    
    # Cek apakah versi optimized sudah ada
    if not os.path.exists(optimized_path):
        optimized_path = optimize_image(
            src_path=watermarked_path,
            dst_path=optimized_path,
        )
    
    return optimized_path
