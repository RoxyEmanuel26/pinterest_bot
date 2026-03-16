"""
modules/hashtag.py
==================
Auto-generate judul, deskripsi, dan hashtag dari nama file foto.
Mengekstrak kata kunci dari nama file, memfilter stopwords,
dan memformat menjadi hashtag yang siap digunakan.
"""

import os
import re


# Daftar kata umum yang difilter dari hashtag
STOPWORDS = {
    "the", "and", "or", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can",
    "a", "an", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "as", "into", "through", "during", "before",
    "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there",
    "when", "where", "why", "how", "all", "each", "every", "both",
    "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "because", "but", "if", "while", "about", "up", "down",
    # Kata terkait foto yang tidak relevan sebagai hashtag
    "img", "image", "photo", "pic", "picture", "foto", "gambar",
    "screenshot", "screen", "capture", "snap", "shot", "copy",
    "file", "untitled", "dsc", "dcim", "raw", "edit", "final",
    "version", "ver", "new", "old", "original", "ori",
}


def generate_title(filename: str) -> str:
    """
    Generate judul pin dari nama file foto.
    
    Menghapus ekstensi file, mengganti underscore dan dash dengan spasi,
    lalu mengubah ke title case.
    
    Args:
        filename: Nama file foto (contoh: "sunset_beach_bali_2024.jpg")
    
    Returns:
        Judul yang sudah diformat (contoh: "Sunset Beach Bali 2024")
    """
    # Hapus ekstensi file
    name_without_ext = os.path.splitext(filename)[0]
    
    # Ganti underscore, dash, dan titik dengan spasi
    cleaned = re.sub(r'[_\-\.]+', ' ', name_without_ext)
    
    # Hapus karakter non-alfanumerik selain spasi
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', cleaned)
    
    # Hapus spasi berlebih
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # Title case
    return cleaned.title()


def generate_hashtags(filename: str, max_count: int = 10) -> list[str]:
    """
    Ekstrak kata kunci dari nama file dan ubah menjadi hashtag.
    
    Memfilter stopwords dan kata pendek (kurang dari 3 karakter).
    
    Args:
        filename: Nama file foto (contoh: "sunset_beach_bali_golden_hour.jpg")
        max_count: Jumlah maksimum hashtag yang dihasilkan
    
    Returns:
        List hashtag (contoh: ["#sunset", "#beach", "#bali", "#golden", "#hour"])
    """
    # Hapus ekstensi file
    name_without_ext = os.path.splitext(filename)[0]
    
    # Ganti underscore, dash, dan titik dengan spasi
    cleaned = re.sub(r'[_\-\.]+', ' ', name_without_ext)
    
    # Hapus karakter non-alfanumerik selain spasi
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', cleaned)
    
    # Split menjadi kata-kata
    words = cleaned.lower().split()
    
    # Filter: hapus stopwords dan kata pendek (<3 karakter)
    hashtags = []
    seen = set()
    for word in words:
        if (
            len(word) >= 3
            and word not in STOPWORDS
            and word not in seen
        ):
            hashtags.append(f"#{word}")
            seen.add(word)
    
    # Batasi jumlah hashtag
    return hashtags[:max_count]


def build_description(template: str, hashtags: list[str]) -> str:
    """
    Gabungkan template deskripsi dengan hashtag.
    
    Args:
        template: Template deskripsi dari config (contoh: "Follow untuk konten!")
        hashtags: List hashtag (contoh: ["#sunset", "#beach"])
    
    Returns:
        Deskripsi lengkap (contoh: "Follow untuk konten! #sunset #beach")
    """
    hashtag_str = " ".join(hashtags)
    
    if template and hashtag_str:
        return f"{template} {hashtag_str}"
    elif template:
        return template
    elif hashtag_str:
        return hashtag_str
    else:
        return ""


def gabungkan_hashtag(hashtag_auto: list[str], hashtag_custom: list[str],
                      max_total: int = 10) -> list[str]:
    """
    Gabungkan hashtag dari auto-generate (nama file) dengan hashtag custom dari config.
    
    Hashtag custom diletakkan di depan, lalu ditambahkan hashtag auto.
    Duplikat dihapus (case-insensitive) dan total dibatasi max_total.
    
    Args:
        hashtag_auto: List hashtag dari auto-generate nama file
                      (contoh: ["#sunset", "#beach", "#bali"])
        hashtag_custom: List hashtag custom dari config.json
                        (contoh: ["#aesthetic", "#viral", "#fyp"])
        max_total: Jumlah maksimum hashtag gabungan
    
    Returns:
        List hashtag gabungan tanpa duplikat, dibatasi max_total
        (contoh: ["#aesthetic", "#viral", "#fyp", "#sunset", "#beach", "#bali"])
    """
    combined = []
    seen = set()
    
    # Tambahkan hashtag custom terlebih dahulu (prioritas)
    for tag in hashtag_custom:
        # Pastikan format #hashtag
        tag_clean = tag.strip()
        if not tag_clean.startswith("#"):
            tag_clean = f"#{tag_clean}"
        
        tag_lower = tag_clean.lower()
        if tag_lower not in seen:
            combined.append(tag_clean)
            seen.add(tag_lower)
    
    # Tambahkan hashtag auto-generate
    for tag in hashtag_auto:
        tag_lower = tag.lower()
        if tag_lower not in seen:
            combined.append(tag)
            seen.add(tag_lower)
    
    return combined[:max_total]


if __name__ == "__main__":
    # Test module
    test_file = "sunset_beach_bali_golden_hour.jpg"
    print(f"File    : {test_file}")
    print(f"Judul   : {generate_title(test_file)}")
    
    tags_auto = generate_hashtags(test_file, max_count=10)
    print(f"Auto Hashtag : {tags_auto}")
    
    custom = ["#aesthetic", "#viral", "#fyp"]
    tags_gabungan = gabungkan_hashtag(tags_auto, custom, max_total=10)
    print(f"Gabungan     : {tags_gabungan}")
    
    desc = build_description("Follow untuk konten lebih lanjut!", tags_gabungan)
    print(f"Deskripsi    : {desc}")
