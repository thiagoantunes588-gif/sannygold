import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.sqlite_migration import MigrationOptions, migrate_json_to_sqlite
from app.services.sqlite_store import load_dict_from_sqlite, load_list_from_sqlite, save_dict_to_sqlite, save_list_to_sqlite


class SqliteMigrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sannygold-sqlite-migration-")
        self.root = Path(self.tmp.name)
        self.data_dir = self.root / "data"
        self.data_dir.mkdir()
        self.db_path = self.data_dir / "sannygold.db"
        self.report_path = self.data_dir / "migration-report.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write_json(self, name, payload):
        path = self.data_dir / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def test_migration_creates_sqlite_without_touching_json(self):
        clients_path = self.write_json(
            "clients.json",
            [
                {"client_id": "CLI-001", "customer_name": "Cliente Teste", "phone": "21999990000"},
                "linha inválida",
            ],
        )
        self.write_json(
            "events.json",
            [{"event_id": "EVT-001", "title": "Evento Teste", "event_date": "2026-05-22", "status": "confirmado"}],
        )
        self.write_json("settings.json", {"cost_per_km": 3.5})
        original_clients = clients_path.read_text(encoding="utf-8")

        report = migrate_json_to_sqlite(
            MigrationOptions(data_dir=self.data_dir, db_path=self.db_path, report_path=self.report_path, include_backups=False)
        )

        self.assertTrue(self.db_path.exists())
        self.assertTrue(self.report_path.exists())
        self.assertEqual(clients_path.read_text(encoding="utf-8"), original_clients)
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertGreaterEqual(report["summary"]["imported"], 3)
        self.assertGreaterEqual(report["summary"]["ignored"], 1)

        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM clients").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM json_documents WHERE entity = 'configuracoes'").fetchone()[0], 1)
            payload = connection.execute("SELECT payload_json FROM clients WHERE client_id = 'CLI-001'").fetchone()[0]
            self.assertIn("Cliente Teste", payload)

    def test_dry_run_does_not_create_database(self):
        self.write_json("clients.json", [{"client_id": "CLI-001", "customer_name": "Cliente Teste"}])

        report = migrate_json_to_sqlite(
            MigrationOptions(data_dir=self.data_dir, db_path=self.db_path, report_path=self.report_path, dry_run=True, include_backups=False)
        )

        self.assertFalse(self.db_path.exists())
        self.assertTrue(self.report_path.exists())
        self.assertEqual(report["summary"]["errors"], 0)
        self.assertGreaterEqual(report["summary"]["imported"], 1)

    def test_sqlite_store_reads_and_writes_list_and_document_payloads(self):
        clients_path = self.data_dir / "clients.json"
        settings_path = self.data_dir / "settings.json"
        clients = [{"client_id": "CLI-010", "customer_name": "Cliente SQLite", "phone": "21988887777"}]
        settings = {"cost_per_km": 4.25, "last_backup_file": "backup.zip"}

        self.assertTrue(save_list_to_sqlite(self.db_path, clients_path, clients))
        self.assertTrue(save_dict_to_sqlite(self.db_path, settings_path, settings))

        self.assertEqual(load_list_from_sqlite(self.db_path, clients_path), clients)
        self.assertEqual(load_dict_from_sqlite(self.db_path, settings_path), settings)

        updated_clients = [{"client_id": "CLI-011", "customer_name": "Cliente Novo"}]
        self.assertTrue(save_list_to_sqlite(self.db_path, clients_path, updated_clients))
        self.assertEqual(load_list_from_sqlite(self.db_path, clients_path), updated_clients)


if __name__ == "__main__":
    unittest.main()
