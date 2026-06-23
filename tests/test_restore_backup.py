from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
import zipfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
RESTORE_SCRIPT = BASE_DIR / "scripts" / "restore_backup.py"
spec = importlib.util.spec_from_file_location("restore_backup_for_tests", RESTORE_SCRIPT)
restore_module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(restore_module)


class RestoreBackupScriptTest(unittest.TestCase):
    def make_backup(self, path: Path, *, include_manifest: bool = True, include_data: bool = True) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            if include_manifest:
                archive.writestr("manifest.json", '{"app":"SannyGold","backup_format":"sannygold-data-backup-v1"}')
            if include_data:
                archive.writestr("data/clients.json", "[]")
                archive.writestr("data/sannygold.db", "sqlite")
            archive.writestr("uploads/assets/foto.txt", "upload")
            archive.writestr("preview/route-plan.pdf", "%PDF")

    def test_restore_validates_manifest_and_data_folder(self):
        with tempfile.TemporaryDirectory() as tempdir:
            missing_manifest = Path(tempdir) / "missing-manifest.zip"
            missing_data = Path(tempdir) / "missing-data.zip"
            self.make_backup(missing_manifest, include_manifest=False)
            self.make_backup(missing_data, include_data=False)

            with self.assertRaisesRegex(ValueError, "manifest.json"):
                restore_module.validate_backup_zip(missing_manifest)
            with self.assertRaisesRegex(ValueError, "pasta data"):
                restore_module.validate_backup_zip(missing_data)

    def test_restore_accepts_empty_data_directory_marker(self):
        with tempfile.TemporaryDirectory() as tempdir:
            backup = Path(tempdir) / "backup.zip"
            with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", '{"app":"SannyGold","backup_format":"sannygold-data-backup-v1"}')
                archive.writestr("data/", "")

            names = restore_module.validate_backup_zip(backup)

        self.assertIn("data/", names)

    def test_restore_rejects_unsafe_zip_paths(self):
        with tempfile.TemporaryDirectory() as tempdir:
            unsafe_backup = Path(tempdir) / "unsafe.zip"
            with zipfile.ZipFile(unsafe_backup, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", '{"app":"SannyGold","backup_format":"sannygold-data-backup-v1"}')
                archive.writestr("data/clients.json", "[]")
                archive.writestr("../outside.txt", "bad")

            with self.assertRaisesRegex(ValueError, "caminho inseguro"):
                restore_module.validate_backup_zip(unsafe_backup)

    def test_restore_rejects_zip_without_sannygold_manifest_marker(self):
        with tempfile.TemporaryDirectory() as tempdir:
            backup = Path(tempdir) / "generic.zip"
            with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", "{}")
                archive.writestr("data/clients.json", "[]")

            with self.assertRaisesRegex(ValueError, "backup SannyGold"):
                restore_module.validate_backup_zip(backup)

    def test_restore_creates_safety_backup_and_replaces_allowed_folders(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "Sistema"
            (root / "data").mkdir(parents=True)
            (root / "uploads").mkdir()
            (root / "preview").mkdir()
            (root / "backups").mkdir()
            (root / "data" / "clients.json").write_text("[{\"antigo\": true}]", encoding="utf-8")
            (root / "uploads" / "old.txt").write_text("old", encoding="utf-8")
            old_backup = root / "backups" / "sannygold-data-backup-20260101-000000-old.zip"
            old_backup.write_bytes(b"old backup")
            backup = Path(tempdir) / "Dropbox" / "SannyGold" / "Backups" / "sannygold-data-backup-20260531-100000-ok.zip"
            self.make_backup(backup)

            result = restore_module.restore_backup(backup, project_root=root, skip_running_check=True)

            self.assertTrue(old_backup.exists())
            self.assertTrue(Path(result["safety_backup"]).exists())
            self.assertEqual((root / "data" / "clients.json").read_text(encoding="utf-8"), "[]")
            self.assertEqual((root / "uploads" / "assets" / "foto.txt").read_text(encoding="utf-8"), "upload")
            self.assertTrue((root / "preview" / "route-plan.pdf").exists())
            self.assertTrue((root / "logs" / "restore.log").exists())
            self.assertIn("data", result["restored_roots"])
            self.assertIn("uploads", result["restored_roots"])
            self.assertIn("preview", result["restored_roots"])

    def test_restore_stops_when_launcher_lock_pid_is_running(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "Sistema"
            (root / "logs").mkdir(parents=True)
            (root / "logs" / "launcher.lock").write_text(f"pid={os.getpid()}\nport=5007\n", encoding="utf-8")
            backup = Path(tempdir) / "Dropbox" / "SannyGold" / "Backups" / "sannygold-data-backup-20260531-100000-ok.zip"
            self.make_backup(backup)

            self.assertTrue(restore_module.system_is_running(root))
            with self.assertRaisesRegex(RuntimeError, "sistema parece estar rodando"):
                restore_module.restore_backup(backup, project_root=root)


if __name__ == "__main__":
    unittest.main()
