from __future__ import annotations

import os
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from app.services.backup import BackupConfig, create_data_backup, diagnose_dropbox_backup


def noop(*args, **kwargs) -> None:
    return None


def clean_text(value=None, fallback: str = "") -> str:
    return str(value or fallback).strip()


def format_datetime_br(value: str | None) -> str:
    return value or ""


class DropboxDiagnosticTest(unittest.TestCase):
    def make_config(
        self,
        root: Path,
        *,
        dropbox_dir: Path | None,
        data_dir: Path | None = None,
        sqlite_path: Path | None = None,
        include_directories: tuple[tuple[Path, str], ...] | None = None,
        external_retention_limit: int | None = None,
    ) -> BackupConfig:
        data_dir = data_dir or root / "data"
        sqlite_path = sqlite_path or data_dir / "sannygold.db"
        return BackupConfig(
            backups_dir=root / "backups",
            data_dir=data_dir,
            storage_root=root,
            important_data_paths=(sqlite_path, data_dir / "clients.json"),
            include_directories=include_directories or ((root / "preview", "preview"), (root / "uploads", "uploads")),
            retention_limit=30,
            backup_copy_dir=dropbox_dir,
            load_settings=lambda: {},
            save_settings=noop,
            now_iso=lambda: datetime.now().isoformat(timespec="seconds"),
            record_audit=noop,
            clean_text=clean_text,
            format_datetime_br=format_datetime_br,
            external_retention_limit=external_retention_limit,
        )

    def write_backup(self, directory: Path, name: str, content: bytes = b"backup") -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_bytes(content)
        return path

    def test_dropbox_not_configured(self):
        with tempfile.TemporaryDirectory() as tempdir:
            config = self.make_config(Path(tempdir), dropbox_dir=None)

            diagnostic = diagnose_dropbox_backup(config)

        self.assertFalse(diagnostic["configured"])
        self.assertEqual(diagnostic["status_label"], "Dropbox não configurado")

    def test_dropbox_missing_folder(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "Sistema"
            config = self.make_config(root, dropbox_dir=Path(tempdir) / "Dropbox" / "SannyGold" / "Backups")

            diagnostic = diagnose_dropbox_backup(config)

        self.assertEqual(diagnostic["status_label"], "Dropbox configurado, mas pasta não encontrada")
        self.assertIn("Dropbox não encontrado", diagnostic["warning"])

    def test_dropbox_without_zip_is_ready_but_empty(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            dropbox_dir = root / "Dropbox" / "SannyGold" / "Backups"
            dropbox_dir.mkdir(parents=True)
            config = self.make_config(root / "Sistema", dropbox_dir=dropbox_dir)

            diagnostic = diagnose_dropbox_backup(config)

        self.assertTrue(diagnostic["exists"])
        self.assertTrue(diagnostic["writable"])
        self.assertFalse(diagnostic["has_zip"])
        self.assertEqual(diagnostic["status_label"], "Dropbox configurado, mas sem backup ainda")

    def test_dropbox_ok_with_latest_local_and_copy_details(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "Sistema"
            dropbox_dir = Path(tempdir) / "Dropbox" / "SannyGold" / "Backups"
            local = self.write_backup(root / "backups", "sannygold-data-backup-20260531-100000-local.zip", b"local")
            copy = self.write_backup(dropbox_dir, "sannygold-data-backup-20260531-100000-local.zip", b"dropbox")
            os.utime(local, (1_700_000_000, 1_700_000_000))
            os.utime(copy, (1_700_000_120, 1_700_000_120))
            config = self.make_config(root, dropbox_dir=dropbox_dir)

            diagnostic = diagnose_dropbox_backup(config)

        self.assertEqual(diagnostic["status_label"], "Dropbox OK")
        self.assertEqual(diagnostic["latest_local_filename"], local.name)
        self.assertEqual(diagnostic["latest_copy_filename"], copy.name)
        self.assertEqual(diagnostic["latest_copy_size_bytes"], len(b"dropbox"))
        self.assertEqual(diagnostic["time_difference_seconds"], 120)

    def test_dropbox_without_write_permission(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "Sistema"
            dropbox_dir = Path(tempdir) / "Dropbox" / "SannyGold" / "Backups"
            dropbox_dir.mkdir(parents=True)
            old_mode = dropbox_dir.stat().st_mode
            try:
                dropbox_dir.chmod(0o500)
                config = self.make_config(root, dropbox_dir=dropbox_dir)

                diagnostic = diagnose_dropbox_backup(config)
            finally:
                dropbox_dir.chmod(old_mode)

        self.assertEqual(diagnostic["status_label"], "Sem permissão para gravar no Dropbox")

    def test_alerts_when_database_is_inside_dropbox(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "Sistema"
            dropbox_root = Path(tempdir) / "Dropbox"
            dropbox_dir = dropbox_root / "SannyGold" / "Backups"
            dropbox_dir.mkdir(parents=True)
            data_dir = dropbox_root / "SannyGold" / "data"
            sqlite_path = data_dir / "sannygold.db"
            config = self.make_config(root, dropbox_dir=dropbox_dir, data_dir=data_dir, sqlite_path=sqlite_path)

            diagnostic = diagnose_dropbox_backup(config)

        self.assertEqual(diagnostic["status_label"], "Risco: banco ativo parece estar dentro do Dropbox")
        self.assertIn("sannygold.db", diagnostic["status_detail"])

    def test_alerts_when_uploads_is_inside_dropbox(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "Sistema"
            dropbox_root = Path(tempdir) / "Dropbox"
            dropbox_dir = dropbox_root / "SannyGold" / "Backups"
            dropbox_dir.mkdir(parents=True)
            uploads_dir = dropbox_root / "SannyGold" / "uploads"
            config = self.make_config(
                root,
                dropbox_dir=dropbox_dir,
                include_directories=((root / "preview", "preview"), (uploads_dir, "uploads")),
            )

            diagnostic = diagnose_dropbox_backup(config)

        self.assertEqual(diagnostic["status_label"], "Risco: banco ativo parece estar dentro do Dropbox")
        self.assertIn("uploads/", diagnostic["status_detail"])

    def test_external_retention_limit_prunes_dropbox_copies_independently(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "Sistema"
            dropbox_dir = Path(tempdir) / "Dropbox" / "SannyGold" / "Backups"
            data_dir = root / "data"
            data_dir.mkdir(parents=True)
            dropbox_dir.mkdir(parents=True)
            (data_dir / "clients.json").write_text("[]", encoding="utf-8")
            config = self.make_config(root, dropbox_dir=dropbox_dir, external_retention_limit=2)

            for _ in range(4):
                create_data_backup(config, trigger="test", audit_action=None, copy_external=True)
                time.sleep(0.01)

            copied = sorted(dropbox_dir.glob("sannygold-data-backup-*.zip"))

        self.assertEqual(len(copied), 2)


if __name__ == "__main__":
    unittest.main()
