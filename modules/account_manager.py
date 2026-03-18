"""
modules/account_manager.py
===========================
Mengelola rotasi akun, status tracking, dan skip logic.
Mengekstrak logika akun dari main.py ke class terpisah.
"""

from __future__ import annotations

from modules.models import Account
from modules.notifier import send_all_notifications
from modules.logger import print_warning, print_info


class AccountManager:
    """
    Mengelola rotasi multi-akun Pinterest.

    Tracking status per akun (active, limit_reached, banned, error),
    pencarian akun aktif berikutnya, skip logic, dan reset putaran.
    """

    def __init__(self, accounts: list[Account], config_dict: dict):
        """
        Args:
            accounts: List akun Pinterest
            config_dict: Config dict untuk notifikasi (kompatibilitas notifier)
        """
        self.accounts = accounts
        self.config_dict = config_dict
        self.status: dict[str, str] = {acc.email: "active" for acc in accounts}
        self.consecutive_fails: dict[str, int] = {acc.email: 0 for acc in accounts}
        self.session_upload_count: dict[str, int] = {acc.email: 0 for acc in accounts}

    def find_next_active(self, start_idx: int = 0) -> int:
        """
        Cari index akun aktif berikutnya mulai dari start_idx.

        Returns:
            Index akun aktif, atau -1 jika tidak ada
        """
        for idx in range(start_idx, len(self.accounts)):
            email = self.accounts[idx].email
            if self.status.get(email, "active") == "active":
                return idx
        return -1

    def all_inactive(self) -> bool:
        """Cek apakah semua akun non-active."""
        return all(s != "active" for s in self.status.values())

    def has_limit_only(self) -> bool:
        """Cek apakah semua akun non-active hanya karena limit_reached."""
        inactive = [s for s in self.status.values() if s != "active"]
        if not inactive:
            return False
        return all(s == "limit_reached" for s in inactive)

    def skip(self, email: str, reason: str, foto_gagal: str = "") -> int:
        """
        Tandai akun sebagai skip dan cari akun berikutnya.

        Args:
            email: Email akun yang di-skip
            reason: Alasan skip (limit_reached, banned, error)
            foto_gagal: Nama file foto terakhir yang gagal

        Returns:
            Index akun aktif berikutnya, atau -1 jika tidak ada
        """
        self.status[email] = reason

        # Safe lookup — tidak crash jika email tidak ditemukan
        current_idx = -1
        for i, acc in enumerate(self.accounts):
            if acc.email == email:
                current_idx = i
                break

        search_start = current_idx + 1 if current_idx != -1 else 0
        next_idx = self.find_next_active(search_start)
        if next_idx == -1:
            next_idx = self.find_next_active(0)

        next_email = self.accounts[next_idx].email if next_idx != -1 else "tidak ada"

        print_warning(f"Akun {email} di-skip [alasan: {reason}]")
        if next_idx != -1:
            print_info(f"   Lanjut ke akun berikutnya: {next_email}")

        send_all_notifications(self.config_dict, "skip",
            akun_skip=email,
            alasan=reason,
            akun_baru=next_email,
            foto_gagal=foto_gagal,
        )
        return next_idx

    def reset_limits(self):
        """Reset semua akun limit_reached → active untuk putaran baru."""
        for email, status in self.status.items():
            if status == "limit_reached":
                self.status[email] = "active"
                self.session_upload_count[email] = 0

    def record_success(self, email: str):
        """Catat upload sukses untuk akun."""
        self.session_upload_count[email] = self.session_upload_count.get(email, 0) + 1
        self.consecutive_fails[email] = 0

    def record_failure(self, email: str):
        """Catat upload gagal untuk akun."""
        self.consecutive_fails[email] = self.consecutive_fails.get(email, 0) + 1

    def has_too_many_fails(self, email: str, threshold: int = 3) -> bool:
        """Cek apakah akun sudah gagal berturut-turut melebihi threshold."""
        return self.consecutive_fails.get(email, 0) >= threshold

    def get_upload_count(self, email: str) -> int:
        """Dapatkan jumlah upload di sesi ini untuk akun tertentu."""
        return self.session_upload_count.get(email, 0)

    def restore_status(self, saved_status: dict[str, str]):
        """Restore status akun dari session state."""
        for email, status in saved_status.items():
            if email in self.status:
                # Reset limit_reached → active (sesi baru, counter baru)
                if status == "limit_reached":
                    self.status[email] = "active"
                else:
                    self.status[email] = status
