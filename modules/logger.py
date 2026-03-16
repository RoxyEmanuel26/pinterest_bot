"""
modules/logger.py
==================
Sistem logging CSV dan CLI dashboard real-time menggunakan Rich.
Mencatat setiap pin yang diupload ke upload_log.csv dan menampilkan
progress bar, tabel status, dan statistik secara live di terminal.
"""

import os
import csv
from datetime import datetime, timedelta

import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn


console = Console()

LOG_COLUMNS = ["timestamp", "filename", "account", "board", "hashtags", "status"]


class UploadLogger:
    """
    Mengelola file upload_log.csv untuk tracking pin yang sudah diupload.
    Menyediakan fungsi untuk cek duplikat, catat upload, dan hitung statistik.
    """

    def __init__(self, log_path: str):
        """
        Inisialisasi UploadLogger.
        
        Args:
            log_path: Path lengkap ke file upload_log.csv
        """
        self.log_path = log_path
        self._ensure_log_file()

    def _ensure_log_file(self):
        """Buat file log baru jika belum ada, dengan header kolom."""
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(LOG_COLUMNS)

    def is_uploaded(self, filename: str) -> bool:
        """
        Cek apakah foto sudah pernah diupload dengan status sukses.
        
        Args:
            filename: Nama file foto (tanpa path)
        
        Returns:
            True jika file sudah ada di log dengan status 'success'
        """
        try:
            df = pd.read_csv(self.log_path, encoding="utf-8")
            if df.empty:
                return False
            success_files = df[df["status"] == "success"]["filename"].tolist()
            return filename in success_files
        except (pd.errors.EmptyDataError, FileNotFoundError, KeyError):
            return False

    def log_upload(self, filename: str, account: str, board: str,
                   hashtags: str, status: str):
        """
        Catat satu upload ke file log CSV.
        
        Args:
            filename: Nama file foto
            account: Email akun yang digunakan
            board: Nama board tujuan
            hashtags: String hashtag yang digunakan
            status: Status upload ('success' atau 'failed')
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, filename, account, board, hashtags, status])

    def get_account_upload_count(self, email: str) -> int:
        """
        Hitung jumlah upload sukses untuk akun tertentu.
        
        Args:
            email: Email akun yang ingin dihitung
        
        Returns:
            Jumlah pin yang berhasil diupload oleh akun tersebut
        """
        try:
            df = pd.read_csv(self.log_path, encoding="utf-8")
            if df.empty:
                return 0
            count = len(df[(df["account"] == email) & (df["status"] == "success")])
            return count
        except (pd.errors.EmptyDataError, FileNotFoundError, KeyError):
            return 0

    def get_total_stats(self) -> dict:
        """
        Hitung statistik total dari log.
        
        Returns:
            Dictionary berisi total_success, total_failed, accounts_used
        """
        try:
            df = pd.read_csv(self.log_path, encoding="utf-8")
            if df.empty:
                return {"total_success": 0, "total_failed": 0, "accounts_used": []}
            
            total_success = len(df[df["status"] == "success"])
            total_failed = len(df[df["status"] == "failed"])
            accounts_used = df["account"].unique().tolist()
            
            return {
                "total_success": total_success,
                "total_failed": total_failed,
                "accounts_used": accounts_used,
            }
        except (pd.errors.EmptyDataError, FileNotFoundError, KeyError):
            return {"total_success": 0, "total_failed": 0, "accounts_used": []}


def create_progress_bar() -> Progress:
    """
    Buat progress bar menggunakan Rich.
    
    Returns:
        Rich Progress instance yang siap digunakan
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def display_status_table(akun_aktif: str, chrome_profile: str,
                         upload_ke: int, max_upload: int,
                         sisa_foto: int, total_sukses: int,
                         total_gagal: int):
    """
    Tampilkan tabel status di terminal menggunakan Rich.
    
    Args:
        akun_aktif: Email akun yang sedang aktif
        chrome_profile: Path Chrome profile yang digunakan
        upload_ke: Nomor upload saat ini untuk akun aktif
        max_upload: Batas upload per akun
        sisa_foto: Jumlah foto yang tersisa  
        total_sukses: Total pin sukses keseluruhan
        total_gagal: Total pin gagal keseluruhan
    """
    table = Table(title="📊 Status Upload", show_header=True, 
                  header_style="bold magenta", expand=True)
    table.add_column("Parameter", style="cyan", width=20)
    table.add_column("Value", style="white")

    table.add_row("👤 Akun Aktif", akun_aktif)
    table.add_row("🗂️  Chrome Profile", chrome_profile)
    table.add_row("📤 Upload Akun Ini", f"[yellow]{upload_ke}[/yellow] / {max_upload}")
    table.add_row("📸 Sisa Foto", str(sisa_foto))
    table.add_row("✅ Total Sukses", f"[green]{total_sukses}[/green]")
    table.add_row("❌ Total Gagal", f"[red]{total_gagal}[/red]")

    console.print(table)


def display_initial_info(total_foto: int, total_akun: int,
                         accounts: list[dict], estimasi_menit: float):
    """
    Tampilkan informasi awal sebelum mulai upload.
    
    Args:
        total_foto: Total foto yang akan diupload
        total_akun: Jumlah akun yang tersedia
        accounts: List dict akun dari config
        estimasi_menit: Estimasi waktu total dalam menit
    """
    console.print()
    console.print(Panel.fit(
        "[bold cyan]🎯 Pinterest Auto-Upload Bot[/bold cyan]",
        subtitle="by roxy.my.id"
    ))
    console.print()

    table = Table(title="📋 Informasi Upload", show_header=True,
                  header_style="bold green", expand=True)
    table.add_column("No", style="cyan", width=5)
    table.add_column("Email", style="white")
    table.add_column("Board", style="yellow")
    table.add_column("Chrome Profile", style="dim")

    for i, acc in enumerate(accounts, 1):
        table.add_row(str(i), acc["email"], acc["board"], acc.get("chrome_profile_path", "default"))

    console.print(table)
    console.print()
    console.print(f"  📸 Total foto yang akan diupload: [bold green]{total_foto}[/bold green]")
    console.print(f"  👤 Total akun tersedia: [bold cyan]{total_akun}[/bold cyan]")
    console.print(f"  ⏱️  Estimasi waktu: [bold yellow]{estimasi_menit:.1f} menit[/bold yellow]")
    console.print()


def display_summary(total_sukses: int, total_gagal: int,
                    durasi: str, akun_digunakan: list[str]):
    """
    Tampilkan summary report di akhir program.
    
    Args:
        total_sukses: Total pin berhasil diupload
        total_gagal: Total pin gagal
        durasi: Durasi total (format string)
        akun_digunakan: List email akun yang digunakan
    """
    console.print()
    console.print("=" * 60)
    console.print(Panel.fit(
        "[bold green]✅ UPLOAD SELESAI[/bold green]",
        subtitle="Summary Report"
    ))

    table = Table(show_header=False, expand=True)
    table.add_column("Key", style="cyan", width=20)
    table.add_column("Value", style="white")

    table.add_row("✅ Total Sukses", f"[bold green]{total_sukses}[/bold green]")
    table.add_row("❌ Total Gagal", f"[bold red]{total_gagal}[/bold red]")
    table.add_row("⏱️  Durasi", durasi)
    table.add_row("👤 Akun Digunakan", ", ".join(akun_digunakan) if akun_digunakan else "-")

    console.print(table)
    console.print("=" * 60)
    console.print()


def print_success(message: str):
    """Print pesan sukses berwarna hijau."""
    console.print(f"  [bold green]✅ {message}[/bold green]")


def print_error(message: str):
    """Print pesan error berwarna merah."""
    console.print(f"  [bold red]❌ {message}[/bold red]")


def print_warning(message: str):
    """Print pesan warning berwarna kuning."""
    console.print(f"  [bold yellow]⚠️  {message}[/bold yellow]")


def print_info(message: str):
    """Print pesan info berwarna biru."""
    console.print(f"  [bold blue]ℹ️  {message}[/bold blue]")
