"""
modules/models.py
==================
Dataclasses untuk type-safe configuration dan state management.
Menggantikan raw dict agar lebih aman dari typo key dan lebih mudah dibaca.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Account:
    """Representasi satu akun Pinterest."""
    email: str
    board: str
    chrome_profile_path: str = ""
    judul_template: str = ""
    deskripsi_template: str = ""
    hashtag_custom: list[str] = field(default_factory=list)
    link_url: str = ""
    password: str = ""  # Diisi dari .env saat runtime

    @classmethod
    def from_dict(cls, data: dict) -> Account:
        return cls(
            email=data["email"],
            board=data["board"],
            chrome_profile_path=data.get("chrome_profile_path", ""),
            judul_template=data.get("judul_template", ""),
            deskripsi_template=data.get("deskripsi_template", ""),
            hashtag_custom=data.get("hashtag_custom", []),
            link_url=data.get("link_url", ""),
            password=data.get("password", ""),
        )

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "board": self.board,
            "chrome_profile_path": self.chrome_profile_path,
            "judul_template": self.judul_template,
            "deskripsi_template": self.deskripsi_template,
            "hashtag_custom": self.hashtag_custom,
            "link_url": self.link_url,
            "password": self.password,
        }


@dataclass
class Config:
    """Konfigurasi global bot."""
    foto_folder: str
    accounts: list[Account]
    max_upload_per_akun: int = 50
    delay_min: int = 1
    delay_max: int = 3
    headless_mode: bool = False
    max_hashtag: int = 10
    deskripsi_mode: str = "auto"
    title_mode: str = "auto"
    judul_pool_file: str = "judul_pool.txt"
    watermark_text: str = "www.kumpulenak.web.id"
    watermark_opacity: float = 0.8
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_webhook_url: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> Config:
        accounts = [Account.from_dict(a) for a in data.get("accounts", [])]
        return cls(
            foto_folder=data["foto_folder"],
            accounts=accounts,
            max_upload_per_akun=data.get("max_upload_per_akun", 50),
            delay_min=data.get("delay_min", 1),
            delay_max=data.get("delay_max", 3),
            headless_mode=data.get("headless_mode", False),
            max_hashtag=data.get("max_hashtag", 10),
            deskripsi_mode=data.get("deskripsi_mode", "auto"),
            title_mode=data.get("title_mode", "auto"),
            judul_pool_file=data.get("judul_pool_file", "judul_pool.txt"),
            watermark_text=data.get("watermark_text", "www.kumpulenak.web.id"),
            watermark_opacity=data.get("watermark_opacity", 0.8),
            telegram_bot_token=data.get("telegram_bot_token", ""),
            telegram_chat_id=data.get("telegram_chat_id", ""),
            discord_webhook_url=data.get("discord_webhook_url", ""),
        )

    def to_dict(self) -> dict:
        """Konversi kembali ke dict (untuk kompatibilitas dengan notifier)."""
        return {
            "foto_folder": self.foto_folder,
            "max_upload_per_akun": self.max_upload_per_akun,
            "delay_min": self.delay_min,
            "delay_max": self.delay_max,
            "headless_mode": self.headless_mode,
            "max_hashtag": self.max_hashtag,
            "deskripsi_mode": self.deskripsi_mode,
            "title_mode": self.title_mode,
            "judul_pool_file": self.judul_pool_file,
            "watermark_text": self.watermark_text,
            "watermark_opacity": self.watermark_opacity,
            "telegram_bot_token": self.telegram_bot_token,
            "telegram_chat_id": self.telegram_chat_id,
            "discord_webhook_url": self.discord_webhook_url,
            "accounts": [a.to_dict() for a in self.accounts],
        }


@dataclass
class BotState:
    """State bot yang bisa di-save/restore untuk crash recovery."""
    foto_index: int = 0
    akun_index: int = 0
    upload_count_per_akun: dict[str, int] = field(default_factory=dict)
    total_sukses: int = 0
    total_gagal: int = 0
    foto_terakhir: str = ""
    status_terakhir: str = ""
    akun_status: dict[str, str] = field(default_factory=dict)
    putaran_ke: int = 1
    foto_folder: str = ""

