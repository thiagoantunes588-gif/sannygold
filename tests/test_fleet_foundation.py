from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.repositories.sqlite_repository import FLEET_FOUNDATION_MIGRATIONS, connect
from app.services.fleet_foundation_migration import (
    apply_fleet_foundation,
    rollback_fleet_foundation,
    validate_fleet_foundation,
)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def create_legacy_database(db_path: Path, vehicle: dict, document: dict) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE schema_migrations (
                id TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE vehicles (
                vehicle_id TEXT PRIMARY KEY,
                plate TEXT,
                vehicle_type TEXT,
                source_file TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                migrated_at TEXT NOT NULL
            );
            CREATE TABLE fleet_documents (
                document_id TEXT PRIMARY KEY,
                vehicle_id TEXT,
                document_type TEXT,
                document_number TEXT,
                issued_at TEXT,
                expires_at TEXT,
                status TEXT,
                responsible TEXT,
                source_file TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                migrated_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO vehicles
                (vehicle_id, plate, vehicle_type, source_file, payload_json, payload_hash, migrated_at)
            VALUES (?, ?, ?, 'vehicles.json', ?, 'legacy-hash', '2026-06-20T08:00:00')
            """,
            (vehicle["vehicle_id"], vehicle["plate"], vehicle["vehicle_type"], json.dumps(vehicle)),
        )
        connection.execute(
            """
            INSERT INTO fleet_documents
                (document_id, vehicle_id, document_type, document_number, issued_at, expires_at,
                 status, responsible, source_file, payload_json, payload_hash, migrated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'fleet_documents.json', ?, 'legacy-hash', '2026-06-20T08:00:00')
            """,
            (
                document["id"],
                document["vehicle_id"],
                document["document_type"],
                document["number"],
                document["issued_at"],
                document["expires_at"],
                document["status"],
                document["responsible"],
                json.dumps(document),
            ),
        )


class FleetFoundationMigrationTest(unittest.TestCase):
    @staticmethod
    def vehicle() -> dict:
        return {
            "id": "VEI-001",
            "vehicle_id": "VEI-001",
            "plate": "ABC1D23",
            "renavam": "12345678901",
            "chassis": "9BWZZZ377VT004251",
            "brand": "Mercedes-Benz",
            "model": "Atego",
            "version": "1719",
            "manufacture_year": 2022,
            "model_year": 2023,
            "vehicle_type": "Caminhao",
            "fuel_type": "Diesel",
            "current_mileage": 45200,
            "legal_owner_company": "SannyGold Locacoes Ltda.",
            "operating_company": "SannyGold Operacao",
            "cost_center": "CC-FROTA",
            "acquisition_date": "2023-02-10",
            "acquisition_value": 245000.0,
            "usual_driver_id": "",
            "status": "disponivel",
            "tracker_installed": True,
            "camera_installed": True,
            "notes": "Veiculo legado.",
            "created_at": "2026-06-19T08:00:00",
            "updated_at": "2026-06-20T08:00:00",
            "deleted_at": "",
        }

    @staticmethod
    def document() -> dict:
        return {
            "id": "DOC-FROTA-001",
            "vehicle_id": "VEI-001",
            "document_type": "crlv_e",
            "number": "CRLV-2026",
            "issued_at": "2026-01-10",
            "expires_at": "2027-01-10",
            "file_url": "/uploads/frota/ABC1D23/Documentos/crlv.pdf",
            "status": "ativo",
            "responsible": "Administrativo",
            "responsible_user_id": "USR-001",
            "notes": "Documento legado.",
            "created_at": "2026-06-19T08:00:00",
            "updated_at": "2026-06-20T08:00:00",
            "deleted_at": "",
        }

    def test_apply_creates_entities_backfills_data_and_supports_rollback(self):
        with tempfile.TemporaryDirectory(prefix="SannyGold Fleet ") as tempdir:
            root = Path(tempdir)
            data_dir = root / "dados locais"
            backups_dir = root / "backups locais"
            db_path = data_dir / "sannygold.db"
            vehicle = self.vehicle()
            document = self.document()
            write_json(data_dir / "vehicles.json", [vehicle])
            write_json(data_dir / "fleet_documents.json", [document])
            create_legacy_database(db_path, vehicle, document)
            original_db = db_path.read_bytes()

            report = apply_fleet_foundation(
                data_dir=data_dir,
                db_path=db_path,
                backups_dir=backups_dir,
                hq_lat=-22.8753396,
                hq_lng=-43.068074,
            )

            self.assertTrue(report["validation"]["ok"])
            self.assertEqual(report["validation"]["counts"]["mileage"], 1)
            self.assertEqual(report["validation"]["counts"]["audit_logs"], 1)
            snapshot_dir = Path(report["snapshot_dir"])
            self.assertTrue((snapshot_dir / "sannygold.db").exists())

            with connect(db_path) as connection:
                vehicle_row = connection.execute(
                    "SELECT * FROM vehicles WHERE vehicle_id = 'VEI-001'"
                ).fetchone()
                document_row = connection.execute(
                    "SELECT * FROM fleet_documents WHERE document_id = 'DOC-FROTA-001'"
                ).fetchone()
                migrations = {
                    row[0]
                    for row in connection.execute(
                        "SELECT id FROM schema_migrations WHERE id IN (?, ?, ?, ?)",
                        FLEET_FOUNDATION_MIGRATIONS,
                    )
                }
                self.assertEqual(vehicle_row["id"], "VEI-001")
                self.assertEqual(vehicle_row["legal_owner_company"], "SannyGold Locacoes Ltda.")
                self.assertEqual(vehicle_row["current_mileage"], 45200)
                self.assertEqual(document_row["issue_date"], "2026-01-10")
                self.assertEqual(document_row["expiration_date"], "2027-01-10")
                self.assertEqual(document_row["responsible_user_id"], "USR-001")
                self.assertEqual(migrations, set(FLEET_FOUNDATION_MIGRATIONS))
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        """
                        INSERT INTO vehicles
                            (vehicle_id, id, plate, plate_normalized, source_file, payload_json, payload_hash, migrated_at)
                        VALUES ('VEI-002', 'VEI-002', 'ABC1D23', 'ABC1D23', 'vehicles.json', '{}', 'x', '2026-06-20')
                        """
                    )
                connection.execute(
                    "UPDATE vehicles SET deleted_at = '2026-06-20T10:00:00' WHERE vehicle_id = 'VEI-001'"
                )
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM vehicles WHERE vehicle_id = 'VEI-001'").fetchone()[0],
                    1,
                )

            rollback_fleet_foundation(
                data_dir=data_dir,
                backups_dir=backups_dir,
                snapshot_dir=snapshot_dir,
            )
            self.assertEqual(db_path.read_bytes(), original_db)
            with sqlite3.connect(db_path) as connection:
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                }
            self.assertNotIn("vehicle_mileage", tables)
            self.assertNotIn("vehicle_audit_logs", tables)

    def test_dry_run_reports_duplicates_without_creating_database(self):
        with tempfile.TemporaryDirectory(prefix="SannyGold Fleet Dry Run ") as tempdir:
            root = Path(tempdir)
            data_dir = root / "data"
            db_path = data_dir / "sannygold.db"
            first = self.vehicle()
            second = {**first, "id": "VEI-002", "vehicle_id": "VEI-002", "plate": "ABC-1D23"}
            write_json(data_dir / "vehicles.json", [first, second])

            report = apply_fleet_foundation(
                data_dir=data_dir,
                db_path=db_path,
                backups_dir=root / "backups",
                hq_lat=-22.8753396,
                hq_lng=-43.068074,
                dry_run=True,
            )

            self.assertFalse(report["can_apply"])
            self.assertEqual(len(report["duplicate_identifiers"]["plate_normalized"]), 1)
            self.assertFalse(db_path.exists())

    def test_validation_detects_complete_fresh_schema(self):
        with tempfile.TemporaryDirectory(prefix="SannyGold Fleet Fresh ") as tempdir:
            root = Path(tempdir)
            data_dir = root / "data"
            write_json(data_dir / "vehicles.json", [])

            report = apply_fleet_foundation(
                data_dir=data_dir,
                db_path=data_dir / "sannygold.db",
                backups_dir=root / "backups",
                hq_lat=-22.8753396,
                hq_lng=-43.068074,
            )

            validation = validate_fleet_foundation(data_dir / "sannygold.db")
            self.assertTrue(report["validation"]["ok"])
            self.assertTrue(validation["ok"])


if __name__ == "__main__":
    unittest.main()
