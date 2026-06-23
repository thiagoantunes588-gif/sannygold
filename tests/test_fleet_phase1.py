from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

FLEET_TEST_STORAGE = tempfile.mkdtemp(prefix="sannygold-fleet-test-")
os.environ["ROTAFLOW_STORAGE_DIR"] = FLEET_TEST_STORAGE
os.environ["SANNYGOLD_SQLITE_PATH"] = str(Path(FLEET_TEST_STORAGE) / "data" / "sannygold.db")

from app.main import (
    AUDIT_LOG_PATH,
    FLEET_DOCUMENTS_PATH,
    FLEET_UPLOADS_DIR,
    ROLE_PERMISSIONS,
    ROUTE_HISTORY_PATH,
    SETTINGS_PATH,
    USERS_PATH,
    VEHICLES_PATH,
    app,
    ensure_storage_dirs,
    save_vehicles_registry,
)
from app.repositories.sqlite_repository import connect
from app.services.fleet_migration import apply_fleet_phase1, rollback_fleet_phase1
from app.services.fleet import document_status_view, normalize_alert_days
from app.services.sqlite_store import save_list_to_sqlite


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class FleetPhase1Test(unittest.TestCase):
    def setUp(self):
        ensure_storage_dirs()
        app.config.update(TESTING=True, STORAGE_BACKEND="json", CSRF_ENABLED=True)
        write_json(VEHICLES_PATH, [])
        write_json(FLEET_DOCUMENTS_PATH, [])
        write_json(ROUTE_HISTORY_PATH, [])
        write_json(AUDIT_LOG_PATH, [])
        write_json(SETTINGS_PATH, {})
        write_json(
            USERS_PATH,
            [
                self.user("USR-ADMIN", "Administrador", "admin@sannygold.local", "admin"),
                self.user("USR-OP", "Operação", "operacao@sannygold.local", "operacional"),
                self.user("USR-FIN", "Financeiro", "financeiro@sannygold.local", "financeiro"),
            ],
        )
        shutil.rmtree(FLEET_UPLOADS_DIR, ignore_errors=True)
        FLEET_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.client = app.test_client()

    @staticmethod
    def user(user_id: str, name: str, email: str, role: str) -> dict:
        return {
            "id": user_id,
            "nome": name,
            "email": email,
            "senha_hash": generate_password_hash("SenhaForte123", method="pbkdf2:sha256"),
            "status": "ativo",
            "role": role,
            "must_change_password": False,
            "created_at": "2026-06-19T08:00:00",
            "updated_at": "2026-06-19T08:00:00",
        }

    def login(self, email: str = "admin@sannygold.local"):
        return self.client.post(
            "/auth/login",
            data={"email": email, "password": "SenhaForte123"},
            follow_redirects=True,
        )

    @staticmethod
    def vehicle_payload(**overrides):
        payload = {
            "vehicle_id": "VEI-001",
            "vehicle_type": "Caminhão",
            "plate": "ABC1D23",
            "renavam": "12345678901",
            "chassis": "9BWZZZ377VT004251",
            "brand": "Mercedes-Benz",
            "model": "Atego",
            "version": "1719",
            "manufacture_year": "2022",
            "model_year": "2023",
            "fuel_type": "Diesel",
            "current_mileage": "45200",
            "legal_owner": "SannyGold Locações Ltda.",
            "operating_company": "SannyGold Operação",
            "operating_unit": "Niterói",
            "cost_center": "CC-FROTA",
            "acquisition_date": "2023-02-10",
            "acquisition_value": "245000.00",
            "habitual_driver": "Motorista Teste",
            "tracker_installed": "1",
            "camera_installed": "1",
            "insurer": "Seguradora Teste",
            "insurance_policy_number": "AP-998877",
            "insurance_expiry": "2027-02-10",
            "status": "disponivel",
            "start_lat": "-22.8753396",
            "start_lng": "-43.068074",
            "capacity": "8",
            "max_stops": "8",
            "max_minutes": "540",
            "notes": "Veículo principal da operação.",
        }
        payload.update(overrides)
        return payload

    def test_vehicle_registration_rejects_duplicate_plate_renavam_and_chassis(self):
        self.login()
        first = self.client.post("/vehicles", data=self.vehicle_payload(), follow_redirects=True)
        self.assertIn("Veículo VEI-001 salvo com sucesso.", first.get_data(as_text=True))

        for field, value in (
            ("plate", "ABC-1D23"),
            ("renavam", "123.456.789-01"),
            ("chassis", "9BW ZZZ377 VT004251"),
        ):
            payload = self.vehicle_payload(
                vehicle_id=f"VEI-{field.upper()}",
                plate="DEF2E34",
                renavam="98765432100",
                chassis="8APZZZ377VT004252",
            )
            payload[field] = value
            self.client.post("/vehicles", data=payload, follow_redirects=True)

        vehicles = read_json(VEHICLES_PATH)
        self.assertEqual(len(vehicles), 1)
        self.assertEqual(vehicles[0]["plate"], "ABC1D23")
        self.assertEqual(vehicles[0]["plate_normalized"], "ABC1D23")
        self.assertEqual(vehicles[0]["legal_owner"], "SannyGold Locações Ltda.")
        self.assertEqual(vehicles[0]["operating_company"], "SannyGold Operação")
        self.assertEqual(vehicles[0]["cost_center"], "CC-FROTA")

    def test_fleet_entry_route_is_protected_and_basic_permissions_are_registered(self):
        guest_response = self.client.get("/fleet")
        self.assertEqual(guest_response.status_code, 302)
        self.assertIn("auth=required", guest_response.headers["Location"])

        self.login()
        admin_response = self.client.get("/fleet")
        self.assertEqual(admin_response.status_code, 302)
        self.assertTrue(admin_response.headers["Location"].endswith("/#fleet-pane"))
        self.assertIn("fleet.create", ROLE_PERMISSIONS["operacional"])
        self.assertIn("fleet.edit", ROLE_PERMISSIONS["operacional"])
        self.assertNotIn("fleet.delete", ROLE_PERMISSIONS["operacional"])

    def test_invalid_vehicle_with_photo_does_not_leave_orphan_file(self):
        self.login()
        self.client.post("/vehicles", data=self.vehicle_payload(), follow_redirects=True)
        duplicate = self.vehicle_payload(
            vehicle_id="VEI-002",
            renavam="98765432100",
            chassis="8APZZZ377VT004252",
        )
        duplicate["vehicle_photo_file"] = (io.BytesIO(b"test-image"), "duplicada.jpg")

        self.client.post(
            "/vehicles",
            data=duplicate,
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        self.assertEqual(len(read_json(VEHICLES_PATH)), 1)
        self.assertEqual(list(FLEET_UPLOADS_DIR.rglob("*duplicada.jpg")), [])

    def test_operational_profile_does_not_receive_sensitive_fleet_data(self):
        write_json(
            VEHICLES_PATH,
            [
                {
                    **self.vehicle_payload(),
                    "acquisition_value": 245000.0,
                    "tracker_installed": True,
                    "camera_installed": True,
                }
            ],
        )
        write_json(
            FLEET_DOCUMENTS_PATH,
            [
                {
                    "id": "DOC-FROTA-001",
                    "vehicle_id": "VEI-001",
                    "vehicle_plate": "ABC1D23",
                    "document_type": "crlv_e",
                    "document_type_label": "CRLV-e sigiloso",
                    "number": "DOC-SEGREDO-123",
                    "file_url": "/uploads/frota/ABC1D23/Documentos/crlv.pdf",
                    "status": "ativo",
                    "created_at": "2026-06-19T08:00:00",
                    "updated_at": "2026-06-19T08:00:00",
                }
            ],
        )
        html = self.login("operacao@sannygold.local").get_data(as_text=True)

        self.assertIn("ABC1D23", html)
        self.assertNotIn("12345678901", html)
        self.assertNotIn("9BWZZZ377VT004251", html)
        self.assertNotIn("AP-998877", html)
        self.assertNotIn("245000", html)
        self.assertNotIn("CRLV-e sigiloso", html)
        self.assertNotIn("DOC-SEGREDO-123", html)

    def test_operational_profile_does_not_receive_sensitive_data_through_route_search(self):
        write_json(
            VEHICLES_PATH,
            [
                {
                    **self.vehicle_payload(),
                    "acquisition_value": 245000.0,
                }
            ],
        )
        write_json(
            ROUTE_HISTORY_PATH,
            [
                {
                    "event_id": "EVT-001",
                    "event_title": "Rota sigilosa",
                    "generated_at": "2026-06-19T08:00:00",
                    "vehicle_ids": ["VEI-001"],
                    "client_ids": [],
                }
            ],
        )

        html = self.login("operacao@sannygold.local").get_data(as_text=True)

        self.assertIn("Rota sigilosa", html)
        self.assertNotIn("12345678901", html)
        self.assertNotIn("9BWZZZ377VT004251", html)
        self.assertNotIn("AP-998877", html)

    def test_operational_profile_can_block_but_cannot_release_vehicle(self):
        self.login()
        self.client.post("/vehicles", data=self.vehicle_payload(), follow_redirects=True)
        self.login("operacao@sannygold.local")

        blocked_payload = self.vehicle_payload(status="bloqueado")
        blocked_response = self.client.post("/vehicles", data=blocked_payload, follow_redirects=True)
        self.assertIn("Veículo VEI-001 salvo com sucesso.", blocked_response.get_data(as_text=True))
        self.assertEqual(read_json(VEHICLES_PATH)[0]["status"], "bloqueado")

        release_payload = self.vehicle_payload(status="disponivel")
        release_response = self.client.post("/vehicles", data=release_payload)

        self.assertEqual(release_response.status_code, 403)
        self.assertEqual(read_json(VEHICLES_PATH)[0]["status"], "bloqueado")
        self.assertTrue(
            any(
                item.get("action") == "access_denied"
                and item.get("target_id") == "fleet.vehicle.release"
                for item in read_json(AUDIT_LOG_PATH)
            )
        )

    def test_document_upload_alert_and_soft_delete_preserve_file(self):
        self.login()
        self.client.post("/vehicles", data=self.vehicle_payload(), follow_redirects=True)
        response = self.client.post(
            "/fleet/documents",
            data={
                "vehicle_id": "VEI-001",
                "document_type": "crlv_e",
                "number": "CRLV-2026",
                "issued_at": "2026-01-10",
                "expires_at": "2026-07-10",
                "responsible": "Administrativo",
                "status": "ativo",
                "notes": "Documento digital.",
                "document_file": (io.BytesIO(b"%PDF-1.4 test"), "crlv-2026.pdf"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("Documento da frota salvo com sucesso.", response.get_data(as_text=True))
        documents = read_json(FLEET_DOCUMENTS_PATH)
        self.assertEqual(len(documents), 1)
        document = documents[0]
        self.assertIn("/uploads/frota/ABC1D23/Documentos/", document["file_url"])
        stored_files = list((FLEET_UPLOADS_DIR / "ABC1D23" / "Documentos").glob("*crlv-2026.pdf"))
        self.assertEqual(len(stored_files), 1)

        self.client.post(f"/fleet/documents/{document['id']}/delete", follow_redirects=True)
        archived = read_json(FLEET_DOCUMENTS_PATH)[0]
        self.assertTrue(archived["deleted_at"])
        self.assertTrue(stored_files[0].exists())

    def test_document_alert_uses_configurable_thresholds(self):
        alert_days = normalize_alert_days("90, 60, 30, 15, 7")
        document = document_status_view(
            {
                "status": "ativo",
                "expires_at": "2026-07-09",
                "deleted_at": "",
            },
            alert_days,
            today=date(2026, 6, 19),
        )

        self.assertEqual(alert_days, [90, 60, 30, 15, 7])
        self.assertEqual(document["days_until_expiry"], 20)
        self.assertEqual(document["alert_level"], 30)
        self.assertEqual(document["effective_status"], "proximo_vencimento")

    def test_vehicle_delete_is_logical_and_removes_vehicle_from_new_routes(self):
        self.login()
        self.client.post("/vehicles", data=self.vehicle_payload(), follow_redirects=True)
        response = self.client.post("/vehicles/VEI-001/delete", follow_redirects=True)
        vehicle = read_json(VEHICLES_PATH)[0]

        self.assertIn("histórico foi preservado", response.get_data(as_text=True))
        self.assertEqual(vehicle["status"], "baixado")
        self.assertTrue(vehicle["deleted_at"])
        self.assertNotIn('<option value="VEI-001">', response.get_data(as_text=True))

    def test_migration_snapshot_can_restore_exact_previous_files(self):
        with tempfile.TemporaryDirectory(prefix="sannygold-fleet-migration-") as tempdir:
            root = Path(tempdir)
            data_dir = root / "data"
            backups_dir = root / "backups"
            data_dir.mkdir()
            original_vehicles = [{"vehicle_id": "VEI-LEGADO", "plate": "LEG1A23", "vehicle_type": "Van"}]
            original_settings = {"cost_per_km": 3.5}
            write_json(data_dir / "vehicles.json", original_vehicles)
            write_json(data_dir / "settings.json", original_settings)

            applied = apply_fleet_phase1(
                data_dir=data_dir,
                db_path=data_dir / "sannygold.db",
                backups_dir=backups_dir,
                hq_lat=-22.8753396,
                hq_lng=-43.068074,
            )
            self.assertTrue(Path(applied["snapshot_dir"]).exists())
            self.assertTrue((data_dir / "fleet_documents.json").exists())
            self.assertIn("plate_normalized", read_json(data_dir / "vehicles.json")[0])

            rollback_fleet_phase1(
                data_dir=data_dir,
                backups_dir=backups_dir,
                snapshot_dir=Path(applied["snapshot_dir"]),
            )
            self.assertEqual(read_json(data_dir / "vehicles.json"), original_vehicles)
            self.assertEqual(read_json(data_dir / "settings.json"), original_settings)
            self.assertFalse((data_dir / "fleet_documents.json").exists())
            self.assertFalse((data_dir / "sannygold.db").exists())

    def test_migration_dry_run_reports_duplicates_and_apply_preserves_files(self):
        with tempfile.TemporaryDirectory(prefix="sannygold-fleet-duplicate-migration-") as tempdir:
            root = Path(tempdir)
            data_dir = root / "data"
            backups_dir = root / "backups"
            data_dir.mkdir()
            original_vehicles = [
                {"vehicle_id": "VEI-001", "plate": "ABC1D23"},
                {"vehicle_id": "VEI-002", "plate": "ABC-1D23"},
            ]
            write_json(data_dir / "vehicles.json", original_vehicles)
            write_json(data_dir / "settings.json", {})

            dry_run = apply_fleet_phase1(
                data_dir=data_dir,
                db_path=data_dir / "sannygold.db",
                backups_dir=backups_dir,
                hq_lat=-22.8753396,
                hq_lng=-43.068074,
                dry_run=True,
            )

            self.assertFalse(dry_run["can_apply"])
            self.assertEqual(len(dry_run["duplicate_identifiers"]["plate_normalized"]), 1)
            with self.assertRaises(ValueError):
                apply_fleet_phase1(
                    data_dir=data_dir,
                    db_path=data_dir / "sannygold.db",
                    backups_dir=backups_dir,
                    hq_lat=-22.8753396,
                    hq_lng=-43.068074,
                )
            self.assertEqual(read_json(data_dir / "vehicles.json"), original_vehicles)
            self.assertFalse((data_dir / "sannygold.db").exists())
            self.assertFalse((backups_dir / "migrations").exists())

    def test_migration_failure_restores_snapshot_automatically(self):
        with tempfile.TemporaryDirectory(prefix="sannygold-fleet-failed-migration-") as tempdir:
            root = Path(tempdir)
            data_dir = root / "data"
            backups_dir = root / "backups"
            data_dir.mkdir()
            original_vehicles = [{"vehicle_id": "VEI-LEGADO", "plate": "LEG1A23"}]
            original_settings = {"cost_per_km": 3.5}
            write_json(data_dir / "vehicles.json", original_vehicles)
            write_json(data_dir / "settings.json", original_settings)

            with patch("app.services.fleet_migration.save_list_to_sqlite", return_value=False):
                with self.assertRaises(RuntimeError):
                    apply_fleet_phase1(
                        data_dir=data_dir,
                        db_path=data_dir / "sannygold.db",
                        backups_dir=backups_dir,
                        hq_lat=-22.8753396,
                        hq_lng=-43.068074,
                    )

            self.assertEqual(read_json(data_dir / "vehicles.json"), original_vehicles)
            self.assertEqual(read_json(data_dir / "settings.json"), original_settings)
            self.assertFalse((data_dir / "fleet_documents.json").exists())
            self.assertFalse((data_dir / "sannygold.db").exists())
            snapshots = list((backups_dir / "migrations").glob("*"))
            self.assertEqual(len(snapshots), 1)
            self.assertTrue((snapshots[0] / "failure-report.json").exists())

    def test_sqlite_list_write_is_atomic_when_unique_index_rejects_data(self):
        with tempfile.TemporaryDirectory(prefix="sannygold-fleet-sqlite-atomic-") as tempdir:
            root = Path(tempdir)
            source_path = root / "vehicles.json"
            db_path = root / "sannygold.db"
            original = [
                {
                    "vehicle_id": "VEI-001",
                    "plate": "ABC1D23",
                    "plate_normalized": "ABC1D23",
                    "renavam_normalized": "12345678901",
                    "chassis_normalized": "9BWZZZ377VT004251",
                    "status": "disponivel",
                    "deleted_at": "",
                }
            ]
            duplicate_batch = [
                {**original[0], "vehicle_id": "VEI-002"},
                {**original[0], "vehicle_id": "VEI-003"},
            ]

            self.assertTrue(save_list_to_sqlite(db_path, source_path, original))
            self.assertFalse(save_list_to_sqlite(db_path, source_path, duplicate_batch))

            with connect(db_path) as connection:
                rows = connection.execute(
                    "SELECT vehicle_id, payload_json FROM vehicles WHERE source_file = ? ORDER BY vehicle_id",
                    ("vehicles.json",),
                ).fetchall()
            self.assertEqual([row["vehicle_id"] for row in rows], ["VEI-001"])
            self.assertEqual(json.loads(rows[0]["payload_json"])["plate"], "ABC1D23")

    def test_sqlite_failure_does_not_update_json_mirror(self):
        original = [{"vehicle_id": "VEI-001", "plate": "ABC1D23"}]
        write_json(VEHICLES_PATH, original)
        app.config.update(STORAGE_BACKEND="sqlite", SQLITE_MIRROR_JSON=True)

        with patch("app.main.save_list_to_sqlite", return_value=False):
            with self.assertRaises(RuntimeError):
                save_vehicles_registry([{"vehicle_id": "VEI-002", "plate": "DEF2E34"}])

        self.assertEqual(read_json(VEHICLES_PATH), original)


if __name__ == "__main__":
    unittest.main()
