from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

FLEET_MAINTENANCE_TEST_STORAGE = tempfile.mkdtemp(prefix="sannygold-fleet-maintenance-suite-")
os.environ["ROTAFLOW_STORAGE_DIR"] = FLEET_MAINTENANCE_TEST_STORAGE
os.environ["SANNYGOLD_SQLITE_PATH"] = str(Path(FLEET_MAINTENANCE_TEST_STORAGE) / "data" / "sannygold.db")

from app import main
from app.services.fleet_maintenance import (
    build_maintenance_plan,
    build_service_order,
    build_service_order_item,
    calculate_order_costs,
    consume_inventory,
    maintenance_plan_status,
    release_inventory,
    reserve_inventory,
    update_plan_after_service,
    validate_completion,
)
from app.services.fleet_maintenance_migration import apply_fleet_maintenance, rollback_fleet_maintenance


NOW = "2026-06-21T10:00:00"


def vehicle(**overrides):
    payload = {
        "id": "VEI-001",
        "vehicle_id": "VEI-001",
        "plate": "ABC1D23",
        "brand": "Mercedes-Benz",
        "model": "Atego",
        "current_mileage": 50000,
        "status": "disponivel",
        "deleted_at": "",
    }
    payload.update(overrides)
    return payload


def order_form(**overrides):
    payload = {
        "vehicle_id": "VEI-001",
        "maintenance_type": "corretiva",
        "priority": "normal",
        "reported_problem": "Ruído no sistema de freios",
        "opening_date": "2026-06-21",
        "entry_mileage": "50000",
        "discount": "0",
    }
    payload.update(overrides)
    return payload


class FleetMaintenanceDomainTest(unittest.TestCase):
    def test_creation_has_unique_sequential_number(self):
        first = build_service_order(order_form(), orders=[], vehicles=[vehicle()], user_id="USR-1", now=NOW)
        second = build_service_order(order_form(reported_problem="Troca de óleo"), orders=[first], vehicles=[vehicle()], user_id="USR-1", now=NOW)
        self.assertEqual(first["order_number"], "OS-FROTA-2026-000001")
        self.assertEqual(second["order_number"], "OS-FROTA-2026-000002")
        self.assertEqual(first["status"], "aberta")

    def test_costs_are_calculated_and_manual_override_requires_admin_justification(self):
        order = build_service_order(order_form(discount="10"), orders=[], vehicles=[vehicle()], user_id="USR-1", now=NOW)
        items = [
            {"id": "1", "service_order_id": order["id"], "item_type": "peca", "total_cost": 120, "deleted_at": ""},
            {"id": "2", "service_order_id": order["id"], "item_type": "mao_de_obra", "total_cost": 80, "deleted_at": ""},
            {"id": "3", "service_order_id": order["id"], "item_type": "taxa", "total_cost": 20, "deleted_at": ""},
        ]
        calculated = calculate_order_costs(order, items)
        self.assertEqual(calculated["parts_cost"], 120)
        self.assertEqual(calculated["labor_cost"], 80)
        self.assertEqual(calculated["additional_cost"], 20)
        self.assertEqual(calculated["total_cost"], 210)
        with self.assertRaises(PermissionError):
            calculate_order_costs(order, items, manual_total="200", override_justification="Ajuste comercial aprovado", can_override=False)
        overridden = calculate_order_costs(order, items, manual_total="200", override_justification="Ajuste comercial aprovado", can_override=True)
        self.assertEqual(overridden["total_cost"], 200)

    def test_item_rejects_negative_values_and_duplicate_warehouse_product(self):
        order = build_service_order(order_form(), orders=[], vehicles=[vehicle()], user_id="USR-1", now=NOW)
        warehouse = [{"id": "ALM-1", "name": "Pastilha", "unit": "jogo", "quantity_current": 5}]
        item = build_service_order_item({"item_type": "peca", "inventory_item_id": "ALM-1", "quantity": "1", "unit_cost": "100"}, items=[], order=order, warehouse_items=warehouse, now=NOW)
        with self.assertRaises(ValueError):
            build_service_order_item({"item_type": "peca", "inventory_item_id": "ALM-1", "quantity": "1", "unit_cost": "90"}, items=[item], order=order, warehouse_items=warehouse, now=NOW)
        with self.assertRaises(ValueError):
            build_service_order_item({"item_type": "servico", "description": "Teste", "quantity": "-1", "unit_cost": "0"}, items=[], order=order, warehouse_items=warehouse, now=NOW)

    def test_approval_reserves_without_lowering_stock_and_completion_consumes(self):
        order = build_service_order(order_form(), orders=[], vehicles=[vehicle()], user_id="USR-1", now=NOW)
        order["status"] = "aprovada"
        items = [{"id": "OSI-1", "service_order_id": order["id"], "item_type": "peca", "description": "Pastilha", "quantity": 2, "inventory_item_id": "ALM-1", "deleted_at": ""}]
        warehouse = [{"id": "ALM-1", "name": "Pastilha", "quantity_current": 5, "unit": "un"}]
        user = {"id": "USR-1", "nome": "Admin", "email": "admin@test"}
        reservations, movements = reserve_inventory(order, items, warehouse, [], [], user=user, now=NOW)
        self.assertEqual(warehouse[0]["quantity_current"], 5)
        self.assertEqual(reservations[0]["status"], "reservada")
        self.assertEqual(movements[0]["movement_type"], "reserva frota")
        reservations, warehouse_after, movements = consume_inventory(order, reservations, warehouse, movements, user=user, now=NOW)
        self.assertEqual(warehouse_after[0]["quantity_current"], 3)
        self.assertEqual(reservations[0]["status"], "consumida")
        self.assertEqual(movements[-1]["vehicle_id"], "VEI-001")
        self.assertEqual(movements[-1]["service_order_number"], order["order_number"])

    def test_negative_stock_is_blocked(self):
        order = build_service_order(order_form(), orders=[], vehicles=[vehicle()], user_id="USR-1", now=NOW)
        items = [{"id": "OSI-1", "service_order_id": order["id"], "item_type": "peca", "description": "Pneu", "quantity": 4, "inventory_item_id": "ALM-1", "deleted_at": ""}]
        warehouse = [{"id": "ALM-1", "name": "Pneu", "quantity_current": 2, "unit": "un"}]
        with self.assertRaises(ValueError):
            reserve_inventory(order, items, warehouse, [], [], user={"id": "USR-1"}, now=NOW)

    def test_cancellation_releases_reservation_without_changing_physical_stock(self):
        order = build_service_order(order_form(), orders=[], vehicles=[vehicle()], user_id="USR-1", now=NOW)
        warehouse = [{"id": "ALM-1", "name": "Filtro", "quantity_current": 3}]
        reservations = [{"id": "RES-1", "service_order_id": order["id"], "service_order_item_id": "OSI-1", "inventory_item_id": "ALM-1", "quantity": 1, "status": "reservada"}]
        released, movements = release_inventory(order, reservations, warehouse, [], user={"id": "USR-1"}, now=NOW)
        self.assertEqual(released[0]["status"], "liberada")
        self.assertEqual(warehouse[0]["quantity_current"], 3)
        self.assertEqual(movements[0]["movement_type"], "liberacao reserva frota")

    def test_completion_requires_description_and_prevents_mileage_regression(self):
        order = build_service_order(order_form(), orders=[], vehicles=[vehicle()], user_id="USR-1", now=NOW)
        with self.assertRaises(ValueError):
            validate_completion(order, services_performed="", exit_mileage="50100", current_mileage=50000, allow_mileage_correction=False, correction_justification="")
        with self.assertRaises(PermissionError):
            validate_completion(order, services_performed="Freios revisados", exit_mileage="49900", current_mileage=50000, allow_mileage_correction=False, correction_justification="")
        mileage, reason = validate_completion(order, services_performed="Freios revisados", exit_mileage="49900", current_mileage=50000, allow_mileage_correction=True, correction_justification="Odômetro anterior lançado incorretamente")
        self.assertEqual(mileage, 49900)
        self.assertTrue(reason)

    def test_plan_requires_real_interval_and_uses_first_due_criterion(self):
        with self.assertRaises(ValueError):
            build_maintenance_plan({"vehicle_id": "VEI-001", "title": "Óleo", "category": "oleo_motor"}, plans=[], vehicles=[vehicle()], now=NOW)
        plan = build_maintenance_plan({"vehicle_id": "VEI-001", "title": "Óleo", "category": "oleo_motor", "interval_mileage": "10000", "interval_days": "365", "warning_mileage": "1000", "warning_days": "30", "last_service_date": "2025-07-01", "last_service_mileage": "45000", "is_active": "1"}, plans=[], vehicles=[vehicle()], now=NOW)
        status = maintenance_plan_status(plan, current_mileage=55000, today=date(2026, 1, 1))
        self.assertEqual(status["status"], "vencido")
        self.assertEqual(status["due_by"], "quilometragem")
        updated = update_plan_after_service(plan, service_date="2026-06-21", mileage=56000, now=NOW)
        self.assertEqual(updated["next_service_mileage"], 66000)
        self.assertEqual(updated["next_service_date"], "2027-06-21")

    def test_required_permissions_are_registered_and_operational_cannot_approve(self):
        required = {
            "fleet.maintenance.view", "fleet.maintenance.create", "fleet.maintenance.edit",
            "fleet.maintenance.approve", "fleet.maintenance.execute", "fleet.maintenance.complete",
            "fleet.maintenance.cancel", "fleet.maintenance.costs.view", "fleet.maintenance.costs.manage",
            "fleet.maintenance.release_vehicle", "fleet.maintenance.plans.manage", "fleet.maintenance.inventory.manage",
        }
        source = Path(main.__file__).read_text(encoding="utf-8")
        self.assertTrue(all(permission in source for permission in required))
        self.assertIn("fleet.maintenance.execute", main.ROLE_PERMISSIONS["operacional"])
        self.assertNotIn("fleet.maintenance.approve", main.ROLE_PERMISSIONS["operacional"])
        self.assertNotIn("fleet.maintenance.costs.view", main.ROLE_PERMISSIONS["operacional"])


class FleetMaintenanceRouteTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sannygold-fleet-maintenance-route-")
        root = Path(self.temp.name)
        self.paths = {
            "DATA_DIR": root / "data", "SQLITE_DB_PATH": root / "data" / "sannygold.db",
            "VEHICLES_PATH": root / "data" / "vehicles.json", "FLEET_DOCUMENTS_PATH": root / "data" / "fleet_documents.json",
            "FLEET_SERVICE_ORDERS_PATH": root / "data" / "fleet_service_orders.json", "FLEET_SERVICE_ORDER_ITEMS_PATH": root / "data" / "fleet_service_order_items.json",
            "VEHICLE_MAINTENANCE_PLANS_PATH": root / "data" / "vehicle_maintenance_plans.json", "FLEET_MAINTENANCE_ATTACHMENTS_PATH": root / "data" / "fleet_maintenance_attachments.json",
            "FLEET_INVENTORY_RESERVATIONS_PATH": root / "data" / "fleet_inventory_reservations.json", "WAREHOUSE_ITEMS_PATH": root / "data" / "warehouse_items.json",
            "WAREHOUSE_MOVEMENTS_PATH": root / "data" / "warehouse_movements.json", "AUDIT_LOG_PATH": root / "data" / "audit_log.json",
            "USERS_PATH": root / "data" / "users.json", "SETTINGS_PATH": root / "data" / "settings.json",
        }
        self.stack = ExitStack()
        for name, path in self.paths.items():
            self.stack.enter_context(patch.object(main, name, path))
        root.joinpath("data").mkdir(parents=True)
        for key, path in self.paths.items():
            if key in {"DATA_DIR", "SQLITE_DB_PATH"}:
                continue
            payload = {} if key == "SETTINGS_PATH" else []
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.write("VEHICLES_PATH", [vehicle()])
        self.write("WAREHOUSE_ITEMS_PATH", [{"id": "ALM-1", "name": "Pastilha", "quantity_current": 4, "unit": "un", "status": "ativo"}])
        self.write("USERS_PATH", [self.user("USR-ADMIN", "admin@test", "admin"), self.user("USR-OP", "op@test", "operacional")])
        main.app.config.update(TESTING=True, STORAGE_BACKEND="json", CSRF_ENABLED=False)
        self.client = main.app.test_client()

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    @staticmethod
    def user(user_id, email, role):
        return {"id": user_id, "nome": role.title(), "email": email, "senha_hash": generate_password_hash("SenhaForte123", method="pbkdf2:sha256"), "status": "ativo", "role": role, "must_change_password": False}

    def write(self, key, payload):
        self.paths[key].write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def read(self, key):
        return json.loads(self.paths[key].read_text(encoding="utf-8"))

    def login(self, email="admin@test"):
        return self.client.post("/auth/login", data={"email": email, "password": "SenhaForte123"}, follow_redirects=True)

    def test_critical_order_blocks_vehicle_route_and_audits_action(self):
        self.login()
        response = self.client.post("/fleet/maintenance/orders", data=order_form(priority="critica"), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        order = self.read("FLEET_SERVICE_ORDERS_PATH")[0]
        self.assertEqual(order["order_number"], "OS-FROTA-2026-000001")
        self.assertEqual(self.read("VEHICLES_PATH")[0]["status"], "bloqueado")
        self.assertTrue(any(item.get("module") == "fleet_maintenance" for item in self.read("AUDIT_LOG_PATH")))
        event = {"event_id": "EVT-1", "event_date": "2026-06-22", "event_end_date": "2026-06-22", "vehicle_ids": ["VEI-001"], "client_ids": []}
        with self.assertRaisesRegex(ValueError, "bloqueado por manutenção"):
            main.validate_event_links(event, clients=[], vehicles=self.read("VEHICLES_PATH"), existing_events=[])

    def test_operational_user_can_open_but_cannot_approve(self):
        self.login("op@test")
        self.client.post("/fleet/maintenance/orders", data=order_form(), follow_redirects=True)
        order = self.read("FLEET_SERVICE_ORDERS_PATH")[0]
        denied = self.client.post(f"/fleet/maintenance/orders/{order['id']}/approve")
        self.assertEqual(denied.status_code, 302)
        self.assertTrue(any(item.get("action") == "access_denied" and item.get("target_id") == "fleet.maintenance.approve" for item in self.read("AUDIT_LOG_PATH")))

    def test_archive_is_logical_and_completed_order_cannot_be_archived(self):
        self.login()
        self.client.post("/fleet/maintenance/orders", data=order_form(), follow_redirects=True)
        order = self.read("FLEET_SERVICE_ORDERS_PATH")[0]
        self.client.post(f"/fleet/maintenance/orders/{order['id']}/archive", follow_redirects=True)
        self.assertTrue(self.read("FLEET_SERVICE_ORDERS_PATH")[0]["deleted_at"])

    def test_full_lifecycle_reserves_consumes_updates_mileage_and_releases_vehicle(self):
        self.login()
        self.client.post("/fleet/maintenance/orders", data=order_form(), follow_redirects=True)
        order = self.read("FLEET_SERVICE_ORDERS_PATH")[0]
        self.client.post(
            f"/fleet/maintenance/orders/{order['id']}/items",
            data={"item_type": "peca", "inventory_item_id": "ALM-1", "description": "Pastilha", "quantity": "2", "unit": "un", "unit_cost": "75"},
            follow_redirects=True,
        )
        self.client.post(f"/fleet/maintenance/orders/{order['id']}/approve", follow_redirects=True)
        self.assertEqual(self.read("WAREHOUSE_ITEMS_PATH")[0]["quantity_current"], 4)
        self.assertEqual(self.read("FLEET_INVENTORY_RESERVATIONS_PATH")[0]["status"], "reservada")
        self.client.post(f"/fleet/maintenance/orders/{order['id']}/execute", data={"diagnosis": "Pastilhas desgastadas"}, follow_redirects=True)
        completed = self.client.post(
            f"/fleet/maintenance/orders/{order['id']}/complete",
            data={"services_performed": "Substituição das pastilhas e teste de frenagem", "completion_date": "2026-06-22", "exit_mileage": "50120", "release_vehicle": "1"},
            follow_redirects=True,
        )
        self.assertEqual(completed.status_code, 200)
        final_order = self.read("FLEET_SERVICE_ORDERS_PATH")[0]
        self.assertEqual(final_order["status"], "concluida")
        self.assertEqual(final_order["total_cost"], 150)
        self.assertEqual(self.read("WAREHOUSE_ITEMS_PATH")[0]["quantity_current"], 2)
        self.assertEqual(self.read("FLEET_INVENTORY_RESERVATIONS_PATH")[0]["status"], "consumida")
        final_vehicle = self.read("VEHICLES_PATH")[0]
        self.assertEqual(final_vehicle["current_mileage"], 50120)
        self.assertEqual(final_vehicle["status"], "disponivel")


class FleetMaintenanceMigrationTest(unittest.TestCase):
    def test_apply_and_rollback_preserve_previous_files(self):
        with tempfile.TemporaryDirectory(prefix="sannygold-fleet-maintenance-migration-") as tempdir:
            root = Path(tempdir)
            data = root / "data"
            data.mkdir()
            original = [{"vehicle_id": "VEI-1", "plate": "ABC1D23"}]
            (data / "vehicles.json").write_text(json.dumps(original), encoding="utf-8")
            applied = apply_fleet_maintenance(data_dir=data, db_path=data / "sannygold.db", backups_dir=root / "backups")
            self.assertTrue(applied["validation"]["ok"])
            self.assertTrue((data / "fleet_service_orders.json").exists())
            rollback_fleet_maintenance(data_dir=data, backups_dir=root / "backups", snapshot_dir=Path(applied["snapshot_dir"]))
            self.assertEqual(json.loads((data / "vehicles.json").read_text(encoding="utf-8")), original)
            self.assertFalse((data / "fleet_service_orders.json").exists())
            self.assertFalse((data / "sannygold.db").exists())


if __name__ == "__main__":
    unittest.main()
