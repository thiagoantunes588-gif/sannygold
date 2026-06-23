from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

FLEET_CHECKLIST_TEST_STORAGE = tempfile.mkdtemp(prefix="sannygold-fleet-checklists-suite-")
os.environ["ROTAFLOW_STORAGE_DIR"] = FLEET_CHECKLIST_TEST_STORAGE
os.environ["SANNYGOLD_SQLITE_PATH"] = str(Path(FLEET_CHECKLIST_TEST_STORAGE) / "data" / "sannygold.db")

from app import main
from app.repositories.sqlite_repository import FLEET_CHECKLIST_MIGRATIONS, connect, initialize_database
from app.services.fleet_checklist_migration import apply_fleet_checklists, rollback_fleet_checklists, validate_fleet_checklists
from app.services.fleet_checklists import (
    build_blocks_from_failures,
    build_checklist_draft,
    build_checklist_responses,
    build_occurrences_from_failures,
    build_template_item,
    build_template_version,
    build_vehicle_assignment,
    close_vehicle_assignment,
    complete_checklist_transaction,
    driver_authorized,
    release_block_allowed,
    route_departure_status,
    validate_checklist_completion,
)
from app.services.sqlite_store import save_list_to_sqlite


NOW = "2026-06-21T10:00:00"


def vehicle(vehicle_id: str = "VEI-001", **overrides) -> dict:
    payload = {
        "id": vehicle_id, "vehicle_id": vehicle_id, "plate": "ABC1D23", "brand": "Mercedes-Benz",
        "model": "Atego", "vehicle_type": "caminhao", "current_mileage": 50000,
        "status": "disponivel", "deleted_at": "", "created_at": NOW, "updated_at": NOW,
    }
    payload.update(overrides)
    return payload


def template(**overrides) -> dict:
    payload = {
        "id": "TPL-001", "logical_id": "TPLLOG-001", "name": "Saída padrão", "description": "",
        "checklist_type": "saida", "vehicle_type": "geral", "is_active": True, "version": 1,
        "created_by": "USR-ADMIN", "created_at": NOW, "updated_at": NOW, "deleted_at": "",
    }
    payload.update(overrides)
    return payload


def template_item(item_id: str = "TPLI-001", **overrides) -> dict:
    payload = {
        "id": item_id, "template_id": "TPL-001", "category": "freios", "title": "Conferir freios",
        "description": "", "display_order": 1, "response_type": "conformidade", "selection_options": [],
        "is_required": True, "is_critical": False, "requires_photo": False,
        "requires_note_on_failure": True, "creates_occurrence_on_failure": True,
        "blocks_vehicle_on_failure": False, "created_at": NOW, "updated_at": NOW, "deleted_at": "",
    }
    payload.update(overrides)
    return payload


def checklist(**overrides) -> dict:
    payload = build_checklist_draft(
        {"vehicle_id": "VEI-001", "driver_id": "USR-DRIVER", "route_id": "EVT-001", "start_mileage": "50010"},
        template=template(), vehicle=vehicle(), checklists=[], user_id="USR-ADMIN", now=NOW,
    )
    payload.update(overrides)
    return payload


class FleetChecklistDomainTest(unittest.TestCase):
    def test_template_creation_and_versioning_preserve_original(self):
        first, previous = build_template_version({"name": "Saída", "checklist_type": "saida", "vehicle_type": "caminhao"}, templates=[], user_id="USR-1", now=NOW)
        self.assertIsNone(previous)
        second, archived = build_template_version({"template_id": first["id"], "name": "Saída revisada"}, templates=[first], user_id="USR-1", now=NOW)
        self.assertEqual(second["logical_id"], first["logical_id"])
        self.assertEqual(second["version"], 2)
        self.assertFalse(archived["is_active"])
        self.assertEqual(first["version"], 1)

    def test_template_item_is_configurable(self):
        item = build_template_item(
            {"category": "pneus", "title": "Estado dos pneus", "response_type": "selecao", "selection_options": "Bom|Regular|Ruim", "is_required": "1", "requires_photo": "1"},
            template_id="TPL-001", items=[], now=NOW,
        )
        self.assertEqual(item["selection_options"], ["Bom", "Regular", "Ruim"])
        self.assertTrue(item["requires_photo"])

    def test_draft_responses_and_required_item(self):
        draft = checklist()
        item = template_item()
        responses = build_checklist_responses({}, checklist=draft, template_items=[item], existing=[], now=NOW)
        self.assertEqual(responses[0]["item_title_snapshot"], item["title"])
        with self.assertRaisesRegex(ValueError, "Item obrigatório"):
            validate_checklist_completion(draft, responses, [item], [], signature_name="Motorista")

    def test_photo_and_failure_note_are_required_when_configured(self):
        draft = checklist()
        item = template_item(requires_photo=True)
        responses = build_checklist_responses({f"response_{item['id']}": "nao_conforme"}, checklist=draft, template_items=[item], existing=[], now=NOW)
        with self.assertRaisesRegex(ValueError, "Foto obrigatória"):
            validate_checklist_completion(draft, responses, [item], [], signature_name="Motorista")
        evidence = [{"checklist_id": draft["id"], "template_item_id": item["id"], "deleted_at": ""}]
        with self.assertRaisesRegex(ValueError, "Observação obrigatória"):
            validate_checklist_completion(draft, responses, [item], evidence, signature_name="Motorista")

    def test_noncritical_and_critical_failures_create_occurrence_and_block(self):
        draft = checklist()
        noncritical = template_item()
        response = build_checklist_responses({f"response_{noncritical['id']}": "atencao", f"note_{noncritical['id']}": "Ruído leve observado"}, checklist=draft, template_items=[noncritical], existing=[], now=NOW)
        result = validate_checklist_completion(draft, response, [noncritical], [], signature_name="Motorista")
        self.assertEqual(result["status"], "concluido_com_ressalvas")
        occurrences = build_occurrences_from_failures(draft, result["failures"], [], user_id="USR-1", now=NOW)
        self.assertEqual(len(occurrences), 1)
        critical = template_item(is_critical=True, requires_photo=False)
        critical_response = build_checklist_responses({f"response_{critical['id']}": "nao_conforme", f"note_{critical['id']}": "Freio sem resposta adequada"}, checklist=draft, template_items=[critical], existing=[], now=NOW)
        critical_result = validate_checklist_completion(draft, critical_response, [critical], [], signature_name="Motorista")
        critical_occurrences = build_occurrences_from_failures(draft, critical_result["failures"], [], user_id="USR-1", now=NOW)
        blocks = build_blocks_from_failures(draft, critical_result["critical_failures"], critical_occurrences, [], user_id="USR-1", now=NOW)
        self.assertEqual(critical_result["status"], "reprovado")
        self.assertEqual(blocks[0]["status"], "ativo")
        self.assertEqual(blocks[0]["severity"], "critica")

    def test_route_is_blocked_and_matching_delivery_is_allowed(self):
        draft = checklist(id="CHK-001", status="concluido", completed_at=NOW)
        blocked = route_departure_status(vehicle_id="VEI-001", route_id="EVT-001", operation_id="", checklists=[draft], blocks=[{"id": "BLK-1", "vehicle_id": "VEI-001", "status": "ativo", "severity": "critica", "reason": "Freios", "deleted_at": ""}], assignments=[], required=True)
        self.assertFalse(blocked["allowed"])
        assignment = build_vehicle_assignment(draft, [], user_id="USR-1", now=NOW)
        ready = route_departure_status(vehicle_id="VEI-001", route_id="EVT-001", operation_id="", checklists=[draft], blocks=[], assignments=[assignment], required=True)
        self.assertTrue(ready["allowed"])

    def test_release_requires_no_other_critical_impediment(self):
        block = {"id": "BLK-1", "vehicle_id": "VEI-001", "status": "ativo"}
        allowed, reasons = release_block_allowed(block=block, blocks=[block, {"id": "BLK-2", "vehicle_id": "VEI-001", "status": "ativo", "deleted_at": ""}], occurrences=[], service_orders=[], documents=[])
        self.assertFalse(allowed)
        self.assertIn("outro bloqueio", reasons[0])
        allowed, reasons = release_block_allowed(block=block, blocks=[block], occurrences=[{"vehicle_id": "VEI-001", "severity": "critica", "status": "aberta", "deleted_at": ""}], service_orders=[], documents=[])
        self.assertFalse(allowed)
        self.assertTrue(reasons)
        allowed, reasons = release_block_allowed(block=block, blocks=[block], occurrences=[{"vehicle_id": "VEI-001", "severity": "critica", "status": "resolvida", "deleted_at": ""}], service_orders=[], documents=[])
        self.assertTrue(allowed)
        self.assertEqual(reasons, [])

    def test_delivery_return_and_existing_delivery_guard(self):
        departure = checklist(id="CHK-S", start_mileage=50010)
        assignment = build_vehicle_assignment(departure, [], user_id="USR-1", now=NOW)
        with self.assertRaisesRegex(ValueError, "entrega aberta"):
            build_vehicle_assignment(departure, [assignment], user_id="USR-1", now=NOW)
        returned = close_vehicle_assignment(checklist(id="CHK-R", checklist_type="retorno", start_mileage=None, end_mileage=50100), [assignment], user_id="USR-2", now="2026-06-21T18:00:00")
        self.assertEqual(returned["status"], "devolvido")
        self.assertEqual(returned["end_mileage"], 50100)

    def test_driver_authorization_is_limited_by_vehicle_or_type(self):
        authorizations = [{"user_id": "USR-D", "status": "ativo", "authorized_vehicle_ids": ["VEI-001"], "authorized_vehicle_types": [], "deleted_at": ""}]
        self.assertTrue(driver_authorized("USR-D", vehicle(), authorizations))
        self.assertFalse(driver_authorized("USR-D", vehicle("VEI-002"), authorizations))

    def test_mileage_transaction_updates_and_rejects_regression(self):
        with tempfile.TemporaryDirectory(prefix="fleet-checklist-transaction-") as tempdir:
            root = Path(tempdir)
            data = root / "data"
            db = data / "sannygold.db"
            vehicles_path = data / "vehicles.json"
            templates_path = data / "fleet_checklist_templates.json"
            vehicles_path.parent.mkdir(parents=True)
            vehicles_path.write_text("[]\n", encoding="utf-8")
            templates_path.write_text("[]\n", encoding="utf-8")
            initialize_database(db)
            save_list_to_sqlite(db, vehicles_path, [vehicle(current_mileage=50000)])
            save_list_to_sqlite(db, templates_path, [template()])
            draft = checklist(id="CHK-TX", status="concluido", completed_at=NOW, start_mileage=50020)
            result = complete_checklist_transaction(db_path=db, checklist=draft, responses=[], vehicle=vehicle(), mileage=50020, mileage_source="checklist de saída", user_id="USR-1", correction_allowed=False, correction_justification="")
            self.assertEqual(result["vehicle"]["current_mileage"], 50020)
            with self.assertRaisesRegex(PermissionError, "não pode regredir"):
                complete_checklist_transaction(db_path=db, checklist={**draft, "id": "CHK-TX-2"}, responses=[], vehicle=result["vehicle"], mileage=49999, mileage_source="checklist de retorno", user_id="USR-1", correction_allowed=False, correction_justification="")
            with connect(db) as connection:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM vehicle_mileage").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM vehicle_audit_logs").fetchone()[0], 1)


class FleetChecklistMigrationTest(unittest.TestCase):
    def test_apply_validate_and_rollback(self):
        with tempfile.TemporaryDirectory(prefix="fleet-checklist-migration-") as tempdir:
            root = Path(tempdir)
            data = root / "data"
            data.mkdir()
            (data / "vehicles.json").write_text(json.dumps([vehicle()]), encoding="utf-8")
            (data / "users.json").write_text("[]", encoding="utf-8")
            (data / "settings.json").write_text("{}", encoding="utf-8")
            applied = apply_fleet_checklists(data_dir=data, db_path=data / "sannygold.db", backups_dir=root / "backups")
            self.assertTrue(applied["validation"]["ok"])
            self.assertEqual(applied["validation"]["missing_migrations"], [])
            with connect(data / "sannygold.db") as connection:
                applied_ids = {row[0] for row in connection.execute("SELECT id FROM schema_migrations")}
            self.assertTrue(set(FLEET_CHECKLIST_MIGRATIONS).issubset(applied_ids))
            self.assertGreaterEqual(len(json.loads((data / "fleet_checklist_templates.json").read_text(encoding="utf-8"))), 2)
            self.assertTrue(validate_fleet_checklists(data / "sannygold.db")["ok"])
            rollback_fleet_checklists(data_dir=data, backups_dir=root / "backups", snapshot_dir=Path(applied["snapshot_dir"]))
            self.assertFalse((data / "fleet_checklists.json").exists())


class FleetChecklistRouteTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fleet-checklist-routes-")
        root = Path(self.temp.name)
        data = root / "data"
        data.mkdir(parents=True)
        names = {
            "DATA_DIR": data, "SQLITE_DB_PATH": data / "sannygold.db", "VEHICLES_PATH": data / "vehicles.json",
            "FLEET_DOCUMENTS_PATH": data / "fleet_documents.json", "FLEET_SERVICE_ORDERS_PATH": data / "fleet_service_orders.json",
            "FLEET_CHECKLIST_TEMPLATES_PATH": data / "fleet_checklist_templates.json", "FLEET_CHECKLIST_TEMPLATE_ITEMS_PATH": data / "fleet_checklist_template_items.json",
            "FLEET_CHECKLISTS_PATH": data / "fleet_checklists.json", "FLEET_CHECKLIST_RESPONSES_PATH": data / "fleet_checklist_responses.json",
            "FLEET_CHECKLIST_EVIDENCE_PATH": data / "fleet_checklist_evidence.json", "FLEET_OCCURRENCES_PATH": data / "fleet_occurrences.json",
            "VEHICLE_OPERATIONAL_BLOCKS_PATH": data / "vehicle_operational_blocks.json", "FLEET_VEHICLE_ASSIGNMENTS_PATH": data / "fleet_vehicle_assignments.json",
            "FLEET_DRIVER_AUTHORIZATIONS_PATH": data / "fleet_driver_authorizations.json", "USERS_PATH": data / "users.json",
            "SETTINGS_PATH": data / "settings.json", "EVENTS_PATH": data / "events.json", "AUDIT_LOG_PATH": data / "audit_log.json",
            "FLEET_UPLOADS_DIR": root / "uploads" / "Frota" / "Veiculos",
        }
        self.paths = names
        self.stack = ExitStack()
        for name, path in names.items():
            self.stack.enter_context(patch.object(main, name, path))
        for name, path in names.items():
            if name in {"DATA_DIR", "SQLITE_DB_PATH", "FLEET_UPLOADS_DIR"}:
                continue
            payload = {} if name == "SETTINGS_PATH" else []
            path.write_text(json.dumps(payload), encoding="utf-8")
        self.write("VEHICLES_PATH", [vehicle()])
        self.write("FLEET_CHECKLIST_TEMPLATES_PATH", [template()])
        self.write("FLEET_CHECKLIST_TEMPLATE_ITEMS_PATH", [template_item()])
        self.write("USERS_PATH", [self.user("USR-ADMIN", "admin@test", "admin"), self.user("USR-DRIVER", "driver@test", "leitura")])
        self.write("FLEET_DRIVER_AUTHORIZATIONS_PATH", [{"id": "DRV-1", "user_id": "USR-DRIVER", "status": "ativo", "authorized_vehicle_ids": ["VEI-001"], "authorized_vehicle_types": [], "deleted_at": ""}])
        main.app.config.update(TESTING=True, STORAGE_BACKEND="json", CSRF_ENABLED=False)
        self.client = main.app.test_client()

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    @staticmethod
    def user(user_id: str, email: str, role: str) -> dict:
        return {"id": user_id, "nome": role.title(), "email": email, "senha_hash": generate_password_hash("SenhaForte123", method="pbkdf2:sha256"), "status": "ativo", "role": role, "must_change_password": False}

    def write(self, name: str, payload) -> None:
        self.paths[name].write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def read(self, name: str):
        return json.loads(self.paths[name].read_text(encoding="utf-8"))

    def login(self, email: str = "admin@test"):
        return self.client.post("/auth/login", data={"email": email, "password": "SenhaForte123"})

    def test_mobile_page_and_draft_save(self):
        self.login()
        page = self.client.get("/fleet/checklists")
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn("Checklists e operação", html)
        self.assertIn("Iniciar checklist", html)
        draft = checklist(id="CHK-ROUTE")
        self.write("FLEET_CHECKLISTS_PATH", [draft])
        detail = self.client.get(f"/fleet/checklists?checklist={draft['id']}")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("Conferir freios", detail.get_data(as_text=True))
        saved = self.client.post(f"/fleet/checklists/{draft['id']}/draft", data={f"response_TPLI-001": "conforme", "start_mileage": "50020"}, headers={"Accept": "application/json"})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.read("FLEET_CHECKLISTS_PATH")[0]["status"], "em_preenchimento")

    def test_driver_can_create_authorized_occurrence_but_not_release(self):
        block = {"id": "BLK-1", "vehicle_id": "VEI-001", "status": "ativo", "severity": "alta", "reason": "Avaria", "created_at": NOW, "updated_at": NOW, "deleted_at": ""}
        self.write("VEHICLE_OPERATIONAL_BLOCKS_PATH", [block])
        self.login("driver@test")
        response = self.client.post("/fleet/occurrences", data={"vehicle_id": "VEI-001", "occurrence_type": "avaria", "severity": "media", "title": "Avaria lateral", "description": "Risco observado na lateral direita"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.read("FLEET_OCCURRENCES_PATH")), 1)
        denied = self.client.post("/fleet/operational-blocks/BLK-1/release", data={"resolution_confirmed": "1", "release_reason": "Avaria corrigida e inspecionada"})
        self.assertEqual(denied.status_code, 302)
        self.assertEqual(self.read("VEHICLE_OPERATIONAL_BLOCKS_PATH")[0]["status"], "ativo")

    def test_driver_cannot_act_for_or_view_another_driver(self):
        own = checklist(id="CHK-OWN", driver_id="USR-DRIVER")
        other = checklist(id="CHK-OTHER", driver_id="USR-ADMIN")
        self.write("FLEET_CHECKLISTS_PATH", [own, other])
        self.login("driver@test")
        page = self.client.get("/fleet/checklists")
        html = page.get_data(as_text=True)
        self.assertIn("CHK-OWN", html)
        self.assertNotIn("CHK-OTHER", html)
        response = self.client.post("/fleet/checklists", data={"vehicle_id": "VEI-001", "template_id": "TPL-001", "driver_id": "USR-ADMIN"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(self.read("FLEET_CHECKLISTS_PATH")), 2)

    def test_archive_item_is_logical_and_audited(self):
        self.login()
        response = self.client.post("/fleet/checklists/templates/TPL-001/items/TPLI-001/archive")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.read("FLEET_CHECKLIST_TEMPLATE_ITEMS_PATH")[0]["deleted_at"])
        self.assertTrue(any(item.get("module") == "fleet_checklist_templates" for item in self.read("AUDIT_LOG_PATH")))


if __name__ == "__main__":
    unittest.main()
