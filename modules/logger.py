"""
modules/logger.py
==================
Sistem logging CSV, error log, session state, dan CLI dashboard real-time.

Komponen:
- UploadLogger: Catat setiap upload ke upload_log.csv (detail: 13 kolom)
- SessionState: Simpan/load session_state.json secara atomic untuk resume
- write_error_log(): Catat error detail ke error_log.txt
- Rich dashboard: Progress bar, tabel status, summary
"""

import os
import csv
import json
import time
import tempfile
from datetime import datetime, timedelta

import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.layout import Layout
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn


console = Console()

# Kolom CSV yang lebih detail
LOG_COLUMNS = [
    "timestamp",        # Waktu upload
    "filename",         # Nama file foto
    "filepath",         # Path lengkap foto
    "akun",             # Email akun
    "board",            # Nama board
    "judul",            # Judul pin
    "hashtag",          # Hashtag yang digunakan
    "link_url",         # Destination link
    "status",           # success / failed
    "alasan_gagal",     # Alasan jika gagal (kosong jika sukses)
    "durasi_upload_detik",  # Durasi upload satu pin dalam detik
    "ukuran_file_kb",   # Ukuran file dalam KB
    "putaran_ke",       # Putaran ke-N (akun rotasi cycle)
]


class UploadLogger:
    """
    Mengelola file upload_log.csv untuk tracking pin yang sudah diupload.
    Menyediakan fungsi untuk cek duplikat, catat upload, dan hitung statistik.
    
    CSV columns: timestamp, filename, filepath, akun, board, judul, hashtag,
                 link_url, status, alasan_gagal, durasi_upload_detik,
                 ukuran_file_kb, putaran_ke
    """

    def __init__(self, log_path: str):
        """
        Inisialisasi UploadLogger.
        
        Args:
            log_path: Path lengkap ke file upload_log.csv
        """
        self.log_path = log_path
        self._uploaded_set: set[str] = set()  # Cache filename yang sudah sukses
        self._ensure_log_file()
        self._load_uploaded_cache()

    def _ensure_log_file(self):
        """Buat file log baru jika belum ada, dengan header kolom."""
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(LOG_COLUMNS)
        else:
            # Migrasi: cek apakah kolom lama (6 kolom) dan perlu upgrade
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                if header and len(header) < len(LOG_COLUMNS):
                    self._migrate_old_log(header)
            except Exception:
                pass

    def _load_uploaded_cache(self):
        """
        Baca CSV sekali dan cache semua filename dengan status 'success'
        ke dalam set untuk O(1) lookup.
        """
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("status") == "success":
                        self._uploaded_set.add(row.get("filename", ""))
        except (FileNotFoundError, KeyError):
            pass

    def _migrate_old_log(self, old_header: list[str]):
        """
        Migrasi file log lama (6 kolom) ke format baru (13 kolom).
        Data lama tetap dipertahankan, kolom baru diisi kosong.
        
        Args:
            old_header: Header kolom dari file log lama
        """
        try:
            rows = []
            with open(self.log_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader)  # skip old header
                for row in reader:
                    rows.append(row)
            
            # Mapping kolom lama ke baru
            # Lama: timestamp, filename, account, board, hashtags, status
            # Baru: timestamp, filename, filepath, akun, board, judul, hashtag,
            #        link_url, status, alasan_gagal, durasi_upload_detik,
            #        ukuran_file_kb, putaran_ke
            with open(self.log_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(LOG_COLUMNS)
                for row in rows:
                    new_row = [
                        row[0] if len(row) > 0 else "",   # timestamp
                        row[1] if len(row) > 1 else "",   # filename
                        "",                                 # filepath (baru)
                        row[2] if len(row) > 2 else "",   # akun (was account)
                        row[3] if len(row) > 3 else "",   # board
                        "",                                 # judul (baru)
                        row[4] if len(row) > 4 else "",   # hashtag (was hashtags)
                        "",                                 # link_url (baru)
                        row[5] if len(row) > 5 else "",   # status
                        "",                                 # alasan_gagal (baru)
                        "",                                 # durasi_upload_detik (baru)
                        "",                                 # ukuran_file_kb (baru)
                        "",                                 # putaran_ke (baru)
                    ]
                    writer.writerow(new_row)
        except Exception as e:
            print(f"[WARNING] Gagal migrasi log lama: {e}")

    def is_uploaded(self, filename: str) -> bool:
        """
        Cek apakah foto sudah pernah diupload dengan status sukses.
        Menggunakan in-memory set cache — O(1) lookup.
        
        Args:
            filename: Nama file foto (tanpa path)
        
        Returns:
            True jika file sudah ada di log dengan status 'success'
        """
        return filename in self._uploaded_set

    def log_upload(self, filename: str, filepath: str, akun: str,
                   board: str, judul: str, hashtag: str, link_url: str,
                   status: str, alasan_gagal: str = "",
                   durasi_upload_detik: float = 0.0,
                   ukuran_file_kb: float = 0.0, putaran_ke: int = 1):
        """
        Catat satu upload ke file log CSV dengan data lengkap.
        
        Args:
            filename: Nama file foto (tanpa path)
            filepath: Path lengkap ke file foto
            akun: Email akun yang digunakan
            board: Nama board tujuan
            judul: Judul pin yang diupload
            hashtag: String hashtag yang digunakan
            link_url: Destination link
            status: Status upload ('success' atau 'failed')
            alasan_gagal: Alasan jika gagal (kosong jika sukses)
            durasi_upload_detik: Durasi upload dalam detik
            ukuran_file_kb: Ukuran file dalam KB
            putaran_ke: Putaran ke-N (cycle rotasi akun)
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                timestamp, filename, filepath, akun, board, judul,
                hashtag, link_url, status, alasan_gagal,
                f"{durasi_upload_detik:.1f}", f"{ukuran_file_kb:.1f}",
                putaran_ke,
            ])

        # Update cache jika upload sukses
        if status == "success":
            self._uploaded_set.add(filename)

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
            count = len(df[(df["akun"] == email) & (df["status"] == "success")])
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
            accounts_used = df["akun"].unique().tolist()
            
            return {
                "total_success": total_success,
                "total_failed": total_failed,
                "accounts_used": accounts_used,
            }
        except (pd.errors.EmptyDataError, FileNotFoundError, KeyError):
            return {"total_success": 0, "total_failed": 0, "accounts_used": []}


# ============================================================
# SESSION STATE (session_state.json)
# ============================================================

class SessionState:
    """
    Mengelola session_state.json untuk checkpoint resume.
    
    File disimpan secara atomic (tulis ke temp → rename) agar
    tidak corrupt jika crash saat menulis.
    
    Format session_state.json:
    {
        "last_updated": "2026-03-16T09:00:00",
        "foto_index": 245,
        "akun_index": 1,
        "upload_count_per_akun": {"akun1@gmail.com": 50, ...},
        "total_sukses": 80,
        "total_gagal": 3,
        "foto_terakhir_diproses": "sunset_beach_001.jpg",
        "status_terakhir": "success",
        "akun_status": {"akun1@gmail.com": "active", ...},
        "putaran_ke": 1
    }
    """

    def __init__(self, state_path: str):
        """
        Inisialisasi SessionState.
        
        Args:
            state_path: Path lengkap ke file session_state.json
        """
        self.state_path = state_path
        self.data = {}

    def exists(self) -> bool:
        """Cek apakah file session_state.json ada."""
        return os.path.exists(self.state_path)

    def load(self) -> dict:
        """
        Baca session_state.json dan kembalikan datanya.
        
        Returns:
            Dictionary berisi state sesi terakhir, atau dict kosong jika tidak ada
        """
        if not self.exists():
            return {}
        
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                self.data = json.load(f)
            return self.data
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"[WARNING] Gagal baca session_state.json: {e}")
            return {}

    def save(self, foto_index: int, akun_index: int,
             upload_count_per_akun: dict[str, int],
             total_sukses: int, total_gagal: int,
             foto_terakhir: str, status_terakhir: str,
             akun_status: dict[str, str],
             putaran_ke: int = 1):
        """
        Simpan state sesi saat ini ke session_state.json secara ATOMIC.
        
        Proses: tulis ke temp file → rename ke session_state.json.
        Ini mencegah file corrupt jika crash di tengah penulisan.
        
        Args:
            foto_index: Index foto terakhir yang diproses (0-based)
            akun_index: Index akun yang sedang aktif
            upload_count_per_akun: Dict {email: jumlah_upload}
            total_sukses: Total foto berhasil diupload
            total_gagal: Total foto gagal
            foto_terakhir: Nama file foto terakhir yang diproses
            status_terakhir: Status terakhir ("success" atau "failed")
            akun_status: Dict {email: "active"/"limit_reached"/"banned"/"error"}
            putaran_ke: Putaran rotasi akun saat ini
        """
        self.data = {
            "last_updated": datetime.now().isoformat(timespec="seconds"),
            "foto_index": foto_index,
            "akun_index": akun_index,
            "upload_count_per_akun": upload_count_per_akun,
            "total_sukses": total_sukses,
            "total_gagal": total_gagal,
            "foto_terakhir_diproses": foto_terakhir,
            "status_terakhir": status_terakhir,
            "akun_status": akun_status,
            "putaran_ke": putaran_ke,
        }
        
        # Atomic write: temp file → rename
        state_dir = os.path.dirname(self.state_path)
        try:
            fd, tmp_path = tempfile.mkstemp(
                suffix=".tmp", prefix="session_", dir=state_dir
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            
            # Pada Windows, os.rename gagal jika file tujuan sudah ada
            # Gunakan os.replace sebagai gantinya (atomic pada Windows)
            os.replace(tmp_path, self.state_path)
        except Exception as e:
            print(f"[WARNING] Gagal simpan session_state.json: {e}")
            # Cleanup temp file jika masih ada
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass

    def delete(self):
        """Hapus file session_state.json (saat user pilih mulai dari awal)."""
        if self.exists():
            try:
                os.unlink(self.state_path)
            except Exception as e:
                print(f"[WARNING] Gagal hapus session_state.json: {e}")

    def display_summary(self):
        """
        Tampilkan ringkasan sesi terakhir di CLI menggunakan Rich.
        
        Output:
            📂 Ditemukan sesi sebelumnya:
               Terakhir diproses : sunset_beach_001.jpg
               Foto ke           : 245 dari ...
               Total sukses      : 80 pin
               Terakhir update   : 16 Maret 2026, 09:00
        """
        if not self.data:
            return
        
        last_updated_str = self.data.get("last_updated", "")
        try:
            dt = datetime.fromisoformat(last_updated_str)
            # Format Indonesia-style
            bulan = [
                "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
                "Juli", "Agustus", "September", "Oktober", "November", "Desember"
            ]
            formatted_date = f"{dt.day} {bulan[dt.month]} {dt.year}, {dt.strftime('%H:%M')}"
        except (ValueError, IndexError):
            formatted_date = last_updated_str
        
        foto_idx = self.data.get("foto_index", 0)
        total_sukses = self.data.get("total_sukses", 0)
        total_gagal = self.data.get("total_gagal", 0)
        foto_terakhir = self.data.get("foto_terakhir_diproses", "?")
        
        # Status akun summary
        akun_status = self.data.get("akun_status", {})
        active_count = sum(1 for s in akun_status.values() if s == "active")
        skip_count = sum(1 for s in akun_status.values() if s != "active")
        
        console.print()
        console.print("  [bold cyan]📂 Ditemukan sesi sebelumnya:[/bold cyan]")
        console.print(f"     Terakhir diproses : [white]{foto_terakhir}[/white]")
        console.print(f"     Foto ke           : [yellow]{foto_idx + 1}[/yellow]")
        console.print(f"     Total sukses      : [green]{total_sukses}[/green] pin")
        console.print(f"     Total gagal       : [red]{total_gagal}[/red] pin")
        console.print(f"     Akun aktif/skip   : [cyan]{active_count}[/cyan] / [yellow]{skip_count}[/yellow]")
        console.print(f"     Terakhir update   : [white]{formatted_date}[/white]")
        console.print()


# ============================================================
# ERROR LOG (error_log.txt)
# ============================================================

def write_error_log(error_log_path: str, akun: str, filename: str,
                    error_msg: str):
    """
    Catat error detail ke file error_log.txt.
    
    Format: [TIMESTAMP] [AKUN] [FILE] ERROR: <pesan error lengkap>
    
    Args:
        error_log_path: Path lengkap ke file error_log.txt
        akun: Email akun yang aktif saat error
        filename: Nama file foto yang sedang diproses saat error
        error_msg: Pesan error lengkap untuk debugging
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{akun}] [{filename}] ERROR: {error_msg}\n"
    
    try:
        with open(error_log_path, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception as e:
        print(f"[WARNING] Gagal menulis error_log.txt: {e}")


# ============================================================
# CLI DISPLAY FUNCTIONS (Rich)
# ============================================================

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


def display_summary(total_sukses: int, total_gagal: int, durasi: str,
                    akun_digunakan: list[str], total_foto: int = 0,
                    foto_sisa: int = 0, akun_diskip: list[str] = None,
                    session_saved: bool = True):
    """
    Tampilkan summary report di akhir program (versi lebih lengkap).
    
    Args:
        total_sukses: Total pin berhasil diupload
        total_gagal: Total pin gagal
        durasi: Durasi total (format string)
        akun_digunakan: List email akun yang digunakan
        total_foto: Total foto yang diproses
        foto_sisa: Jumlah foto belum diupload
        akun_diskip: List email akun yang di-skip
        session_saved: True jika session tersimpan
    """
    console.print()
    console.print("=" * 60)
    console.print(Panel.fit(
        "[bold green]📊 SUMMARY PROGRAM PINTEREST BOT[/bold green]",
        subtitle="Summary Report"
    ))

    table = Table(show_header=False, expand=True)
    table.add_column("Key", style="cyan", width=25)
    table.add_column("Value", style="white")

    table.add_row("📸 Total foto diproses", 
                  f"[bold]{total_sukses + total_gagal}[/bold] / {total_foto}" if total_foto else f"[bold]{total_sukses + total_gagal}[/bold]")
    table.add_row("✅ Total sukses upload", f"[bold green]{total_sukses}[/bold green] pin")
    table.add_row("❌ Total gagal", f"[bold red]{total_gagal}[/bold red] pin")
    table.add_row("👤 Akun digunakan", f"{len(akun_digunakan)} akun")
    
    if akun_diskip:
        table.add_row("⚠️  Akun di-skip", f"[yellow]{len(akun_diskip)}[/yellow] akun")
    
    table.add_row("⏱️  Durasi program", durasi)
    
    if foto_sisa > 0:
        table.add_row("📸 Foto belum diupload", f"[yellow]{foto_sisa}[/yellow] foto")
    
    session_icon = "✅" if session_saved else "❌"
    table.add_row("💾 Session tersimpan", session_icon)

    console.print(table)
    console.print("=" * 60)
    console.print()


def display_all_accounts_down(akun_status: dict[str, str], 
                               foto_sisa: int):
    """
    Tampilkan pesan saat semua akun tidak bisa digunakan.
    
    Args:
        akun_status: Dict {email: status} untuk semua akun
        foto_sisa: Jumlah foto yang belum diupload
    """
    console.print()
    console.print("  [bold red]🔴 Semua akun tidak dapat digunakan. Program berhenti.[/bold red]")
    
    limit_list = [e for e, s in akun_status.items() if s == "limit_reached"]
    error_list = [e for e, s in akun_status.items() if s == "error"]
    banned_list = [e for e, s in akun_status.items() if s == "banned"]
    
    if limit_list:
        console.print(f"     Akun limit   : [yellow]{', '.join(limit_list)}[/yellow]")
    if error_list:
        console.print(f"     Akun error   : [red]{', '.join(error_list)}[/red]")
    if banned_list:
        console.print(f"     Akun banned  : [bold red]{', '.join(banned_list)}[/bold red]")
    
    console.print(f"     Foto tersisa : [yellow]{foto_sisa}[/yellow] foto belum diupload")
    console.print()


_start_time = time.time()

def _elapsed() -> str:
    """Return elapsed time since program start as [HH:MM:SS]."""
    secs = int(time.time() - _start_time)
    h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def print_success(message: str):
    """Print pesan sukses berwarna hijau."""
    console.print(f"  [dim]{_elapsed()}[/dim] [bold green]✅ {message}[/bold green]")


def print_error(message: str):
    """Print pesan error berwarna merah."""
    console.print(f"  [dim]{_elapsed()}[/dim] [bold red]❌ {message}[/bold red]")


def print_warning(message: str):
    """Print pesan warning berwarna kuning."""
    console.print(f"  [dim]{_elapsed()}[/dim] [bold yellow]⚠️  {message}[/bold yellow]")


def print_info(message: str):
    """Print pesan info berwarna biru."""
    console.print(f"  [dim]{_elapsed()}[/dim] [bold blue]ℹ️  {message}[/bold blue]")
