import json
import os
import tempfile
import unittest

from werkzeug.security import generate_password_hash

os.environ["ROTAFLOW_STORAGE_DIR"] = tempfile.mkdtemp(prefix="sannygold-warehouse-test-")
os.environ["SANNYGOLD_ADMIN_EMAIL"] = "admin@sannygold.local"
os.environ["SANNYGOLD_ADMIN_PASSWORD"] = "Sanny123Gold"

from app.main import (  # noqa: E402
    USERS_PATH,
    WAREHOUSE_ITEMS_PATH,
    WAREHOUSE_MOVEMENTS_PATH,
    app,
    ensure_storage_dirs,
)


class WarehouseModuleTest(unittest.TestCase):
    def setUp(self):
        ensure_storage_dirs()
        USERS_PATH.write_text(
            json.dumps(
                [
                    {
                        "id": "USR-001",
                        "nome": "Administrador SannyGold",
                        "email": "admin@sannygold.local",
                        "senha_hash": generate_password_hash("Sanny123Gold", method="pbkdf2:sha256"),
                        "status": "ativo",
                        "role": "admin",
                        "must_change_password": True,
                        "created_at": "2026-04-22T08:00:00",
                        "updated_at": "2026-04-22T08:00:00",
                    },
                    {
                        "id": "USR-002",
                        "nome": "Operador SannyGold",
                        "email": "operador@sannygold.local",
                        "senha_hash": generate_password_hash("Operador1234", method="pbkdf2:sha256"),
                        "status": "ativo",
                        "role": "operacional",
                        "must_change_password": False,
                        "created_at": "2026-04-22T08:00:00",
                        "updated_at": "2026-04-22T08:00:00",
                    }
                ],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        WAREHOUSE_ITEMS_PATH.write_text("[]\n", encoding="utf-8")
        WAREHOUSE_MOVEMENTS_PATH.write_text("[]\n", encoding="utf-8")
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def login(self, email="admin@sannygold.local", password="Sanny123Gold"):
        return self.client.post(
            "/auth/login",
            data={"email": email, "password": password},
            follow_redirects=True,
        )

    def create_item(self):
        return self.client.post(
            "/warehouse/items",
            data={
                "name": "Papel toalha",
                "category": "Higiene",
                "description": "Pacote para reposicao interna",
                "unit": "pct",
                "quantity_current": "3",
                "stock_minimum": "5",
                "storage_location": "Prateleira A",
                "purchase_link": "https://fornecedor.example/papel-toalha",
                "purchase_location": "Distribuidora Central",
                "photo_url": "https://cdn.example/papel-toalha.jpg",
                "notes": "Uso interno",
                "status": "ativo",
            },
        )

    def test_guest_cannot_create_warehouse_item(self):
        response = self.client.post("/warehouse/items", data={"name": "Sabonete"})

        self.assertEqual(response.status_code, 302)
        self.assertIn("/?auth=required", response.headers["Location"])

    def test_admin_can_create_item_and_dashboard_shows_warehouse_module(self):
        self.login()
        response = self.create_item()
        html = self.client.get("/").get_data(as_text=True)
        items = json.loads(WAREHOUSE_ITEMS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Papel toalha")
        self.assertEqual(items[0]["quantity_current"], 3.0)
        self.assertEqual(items[0]["stock_minimum"], 5.0)
        self.assertEqual(items[0]["purchase_link"], "https://fornecedor.example/papel-toalha")
        self.assertEqual(items[0]["purchase_location"], "Distribuidora Central")
        self.assertEqual(items[0]["photo_url"], "https://cdn.example/papel-toalha.jpg")
        self.assertIn("Almoxarifado", html)
        self.assertIn('id="warehouse-pane"', html)
        self.assertIn('id="warehouseItemModal"', html)
        self.assertIn("Adicionar item", html)
        self.assertIn("Exportar PDF", html)
        self.assertIn("Estoque baixo PDF", html)
        self.assertIn("Lista completa do almoxarifado", html)
        self.assertIn("warehouse-search", html)
        self.assertIn("Comprar online", html)
        self.assertIn("Distribuidora Central", html)
        self.assertIn("https://cdn.example/papel-toalha.jpg", html)
        self.assertIn("Registrar entrada", html)
        self.assertIn("Registrar saída", html)
        self.assertIn("Ajustar quantidade", html)
        self.assertIn("1 item(ns) baixo(s)", html)

    def test_create_panels_start_closed_and_new_buttons_are_available(self):
        self.login()
        html = self.client.get("/").get_data(as_text=True)

        self.assertIn('id="event-create-panel" hidden', html)
        self.assertIn('id="manual-client-form" hidden', html)
        self.assertIn('id="vehicle-create-panel" hidden', html)
        self.assertIn('id="equipment-create-panel" hidden', html)
        self.assertIn('id="warehouseItemModal"', html)
        for label in ("Novo evento", "Novo cliente", "Novo veículo", "Novo equipamento", "Adicionar item"):
            self.assertIn(label, html)

    def test_admin_can_export_complete_warehouse_pdf(self):
        self.login()
        self.create_item()

        response = self.client.get("/warehouse/items.pdf")
        pdf_bytes = response.get_data()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertIn(b"SannyGold - Almoxarifado", pdf_bytes)
        self.assertIn(b"Papel toalha", pdf_bytes)
        self.assertIn(b"Distribuidora Central", pdf_bytes)
        self.assertIn(b"https://fornecedor.example/papel-toalha", pdf_bytes)

    def test_can_export_low_stock_warehouse_pdf(self):
        self.login()
        self.create_item()

        response = self.client.get("/warehouse/low-stock.pdf")
        pdf_bytes = response.get_data()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertIn(b"SannyGold - Estoque baixo", pdf_bytes)
        self.assertIn(b"Papel toalha", pdf_bytes)
        self.assertIn(b"repor antes", pdf_bytes)

    def test_movements_update_balance_and_register_history_with_user(self):
        self.login()
        self.create_item()
        item_id = json.loads(WAREHOUSE_ITEMS_PATH.read_text(encoding="utf-8"))[0]["id"]

        self.client.post(
            f"/warehouse/items/{item_id}/movement",
            data={"movement_type": "entrada", "quantity": "7", "observation": "Compra semanal"},
        )
        self.client.post(
            f"/warehouse/items/{item_id}/movement",
            data={"movement_type": "saida", "quantity": "4", "observation": "Uso na sede"},
        )
        self.client.post(
            f"/warehouse/items/{item_id}/movement",
            data={"movement_type": "ajuste manual", "final_quantity": "12", "observation": "Contagem física"},
        )

        items = json.loads(WAREHOUSE_ITEMS_PATH.read_text(encoding="utf-8"))
        movements = json.loads(WAREHOUSE_MOVEMENTS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(items[0]["quantity_current"], 12.0)
        self.assertEqual([item["movement_type"] for item in movements], ["entrada", "saida", "ajuste manual"])
        self.assertEqual(movements[0]["previous_balance"], 3.0)
        self.assertEqual(movements[0]["final_balance"], 10.0)
        self.assertEqual(movements[1]["previous_balance"], 10.0)
        self.assertEqual(movements[1]["final_balance"], 6.0)
        self.assertEqual(movements[2]["quantity_changed"], 6.0)
        self.assertEqual(movements[2]["final_balance"], 12.0)
        self.assertEqual(movements[2]["user_email"], "admin@sannygold.local")

    def test_writeoff_cannot_make_negative_without_explicit_confirmation(self):
        self.login()
        self.create_item()
        item_id = json.loads(WAREHOUSE_ITEMS_PATH.read_text(encoding="utf-8"))[0]["id"]

        response = self.client.post(
            f"/warehouse/items/{item_id}/movement",
            data={"movement_type": "baixa", "quantity": "99", "observation": "Erro operacional"},
            follow_redirects=True,
        )
        items = json.loads(WAREHOUSE_ITEMS_PATH.read_text(encoding="utf-8"))
        movements = json.loads(WAREHOUSE_MOVEMENTS_PATH.read_text(encoding="utf-8"))

        self.assertIn("não pode ficar negativa", response.get_data(as_text=True))
        self.assertEqual(items[0]["quantity_current"], 3.0)
        self.assertEqual(movements, [])

    def test_operator_can_move_stock_but_cannot_manage_item_or_manual_adjust(self):
        self.login()
        self.create_item()
        item_id = json.loads(WAREHOUSE_ITEMS_PATH.read_text(encoding="utf-8"))[0]["id"]
        self.client.post("/auth/logout")
        self.login("operador@sannygold.local", "Operador1234")

        create_response = self.client.post(
            "/warehouse/items",
            data={"name": "Material bloqueado", "category": "Teste", "quantity_current": "1", "stock_minimum": "1"},
            follow_redirects=True,
        )
        entry_response = self.client.post(
            f"/warehouse/items/{item_id}/movement",
            data={"movement_type": "entrada", "quantity": "2", "observation": "Reposicao operacional"},
            follow_redirects=True,
        )
        adjustment_response = self.client.post(
            f"/warehouse/items/{item_id}/movement",
            data={"movement_type": "ajuste manual", "final_quantity": "99", "observation": "Contagem"},
            follow_redirects=True,
        )
        items = json.loads(WAREHOUSE_ITEMS_PATH.read_text(encoding="utf-8"))
        movements = json.loads(WAREHOUSE_MOVEMENTS_PATH.read_text(encoding="utf-8"))

        self.assertIn("Acesso restrito", create_response.get_data(as_text=True))
        self.assertIn("Movimentação registrada", entry_response.get_data(as_text=True))
        self.assertIn("permitido apenas para administrador", adjustment_response.get_data(as_text=True))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["quantity_current"], 5.0)
        self.assertEqual([item["movement_type"] for item in movements], ["entrada"])


if __name__ == "__main__":
    unittest.main()
