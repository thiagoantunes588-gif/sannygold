import json
import os
import tempfile
import unittest
from datetime import datetime

from werkzeug.security import generate_password_hash

os.environ["ROTAFLOW_STORAGE_DIR"] = tempfile.mkdtemp(prefix="sannygold-warehouse-test-")
os.environ["SANNYGOLD_ADMIN_EMAIL"] = "admin@sannygold.local"
os.environ["SANNYGOLD_ADMIN_PASSWORD"] = "troque-esta-senha"

from app.main import (  # noqa: E402
    CLIENTS_PATH,
    EQUIPMENT_PATH,
    EVENTS_PATH,
    USERS_PATH,
    WAREHOUSE_ITEMS_PATH,
    WAREHOUSE_MOVEMENTS_PATH,
    app,
    build_warehouse_dashboard,
    ensure_storage_dirs,
    filter_warehouse_items_for_pdf,
    validate_event_links,
)
from app.services.warehouse_pdf import (  # noqa: E402
    build_warehouse_pdf_bytes,
    format_quantity,
    item_detail_markup,
    link_markup,
    sorted_warehouse_items,
    warehouse_pdf_filename,
    warehouse_stock_info,
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
                        "senha_hash": generate_password_hash("troque-esta-senha", method="pbkdf2:sha256"),
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
        CLIENTS_PATH.write_text("[]\n", encoding="utf-8")
        EVENTS_PATH.write_text("[]\n", encoding="utf-8")
        EQUIPMENT_PATH.write_text("[]\n", encoding="utf-8")
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def login(self, email="admin@sannygold.local", password="troque-esta-senha"):
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
                "item_kind": "consumivel",
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
        self.assertEqual(items[0]["item_kind"], "consumivel")
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
        self.assertIn("Registrar perda", html)
        self.assertIn("Registrar retorno", html)
        self.assertIn("Ajustar quantidade", html)
        self.assertIn("Material consumível", html)
        self.assertIn("Acessório operacional", html)
        self.assertIn("1 baixo(s)", html)

    def test_equipment_statuses_are_official_and_legacy_status_is_normalized(self):
        self.login()

        response = self.client.post(
            "/equipment",
            data={
                "equipment_id": "EQ-001",
                "stock_equipment_type": "Banheiro Luxo",
                "asset_class": "locavel",
                "condition": "em_rota",
                "notes": "Trailer principal",
            },
        )
        html = self.client.get("/").get_data(as_text=True)
        items = json.loads(EQUIPMENT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(items[0]["status"], "em_operacao")
        self.assertEqual(items[0]["condition"], "em_operacao")
        self.assertEqual(items[0]["asset_class"], "locavel")
        self.assertIn("Equipamento locável", html)
        self.assertIn("Em operação", html)
        self.assertIn("Aguardando limpeza", html)
        self.assertIn("Baixado", html)

    def test_overlapping_event_blocks_same_equipment(self):
        clients = [
            {
                "client_id": "CLI-EQ",
                "customer_name": "Cliente Evento",
                "equipment_number": "EQ-CONFLITO",
                "address": "Rua A",
                "lat": -22.8,
                "lng": -43.0,
            }
        ]
        existing_events = [
            {
                "event_id": "EVT-1",
                "title": "Evento 1",
                "event_date": "2026-06-10",
                "event_end_date": "2026-06-12",
                "status": "confirmado",
                "client_ids": ["CLI-EQ"],
                "vehicle_ids": [],
            }
        ]
        new_event = {
            "event_id": "EVT-2",
            "title": "Evento 2",
            "event_date": "2026-06-11",
            "event_end_date": "2026-06-11",
            "status": "confirmado",
            "client_ids": ["CLI-EQ"],
            "vehicle_ids": [],
        }

        with self.assertRaisesRegex(ValueError, "já está comprometido"):
            validate_event_links(new_event, clients=clients, vehicles=[], existing_events=existing_events)

    def test_equipment_maintenance_adds_history(self):
        self.login()
        self.client.post(
            "/equipment",
            data={"equipment_id": "EQ-MAN", "stock_equipment_type": "Banheiro Luxo", "condition": "disponivel"},
        )

        response = self.client.post(
            "/equipment/EQ-MAN/maintenance",
            data={
                "maintenance_reason": "Troca de bomba",
                "maintenance_expected_release": "2026-06-20",
                "maintenance_cost": "180.50",
            },
            follow_redirects=True,
        )
        items = json.loads(EQUIPMENT_PATH.read_text(encoding="utf-8"))

        self.assertIn("Manutenção registrada para EQ-MAN.", response.get_data(as_text=True))
        self.assertEqual(items[0]["status"], "manutencao")
        self.assertEqual(items[0]["maintenance_history"][0]["reason"], "Troca de bomba")
        self.assertEqual(items[0]["maintenance_history"][0]["cost"], 180.5)

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

    def test_warehouse_modal_is_protected_from_fixed_ui_layers(self):
        self.login()
        html = self.client.get("/").get_data(as_text=True)

        self.assertIn("function relocateNestedBootstrapModals()", html)
        self.assertIn('document.querySelectorAll(".tab-pane .modal")', html)
        self.assertIn("body.modal-open .help-assistant-button", html)
        self.assertIn("body.modal-open .bottom-action-bar", html)
        self.assertIn("body.work-mode .modal-content .form-label", html)
        self.assertIn("color: var(--aqua-deep) !important", html)
        self.assertIn('id="warehouse-export-pdf"', html)
        self.assertIn("function syncWarehousePdfExportHref()", html)

    def test_admin_can_export_complete_warehouse_pdf(self):
        self.login()
        self.create_item()

        response = self.client.get("/warehouse/items.pdf")
        pdf_bytes = response.get_data()
        disposition = response.headers.get("Content-Disposition", "")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"/FontFile2", pdf_bytes)
        self.assertIn("sannygold-almoxarifado-", disposition)
        self.assertIn(".pdf", disposition)
        self.assertIn(b"/URI", pdf_bytes)
        self.assertIn(b"https://fornecedor.example/papel-toalha", pdf_bytes)

    def test_can_export_low_stock_warehouse_pdf(self):
        self.login()
        self.create_item()

        response = self.client.get("/warehouse/low-stock.pdf")
        pdf_bytes = response.get_data()
        disposition = response.headers.get("Content-Disposition", "")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"/FontFile2", pdf_bytes)
        self.assertIn("sannygold-estoque-baixo-", disposition)
        self.assertIn(".pdf", disposition)

    def test_warehouse_pdf_formatting_preserves_accents_and_hides_empty_fields(self):
        self.assertEqual(format_quantity(5, "un"), "5 un")
        self.assertEqual(format_quantity("5,5", "L"), "5,5 L")
        self.assertEqual(warehouse_pdf_filename(datetime(2026, 6, 17, 18, 35)), "sannygold-almoxarifado-2026-06-17_18-35.pdf")

        details = item_detail_markup(
            {
                "id": "MAT-001",
                "description": "sala de epi",
                "notes": "Observações: tomada Fêmea, Acessório no Mínimo",
                "purchase_location": "n/d",
                "purchase_link": "",
                "photo_url": "n/d",
                "brand": None,
                "model": "--",
            }
        )
        rendered = "\n".join(details)

        for expected in ("Observações", "Fêmea", "Acessório", "Mínimo", "Sala de EPI"):
            self.assertIn(expected, rendered)
        for hidden in ("Onde comprar", "Link:", "Foto:", "n/d", "--"):
            self.assertNotIn(hidden, rendered)

    def test_warehouse_pdf_stock_statuses_and_priority_order_are_centralized(self):
        items = [
            {"name": "Álcool", "quantity_current": 9, "stock_minimum": 5, "status": "ativo"},
            {"name": "Cone inativo", "quantity_current": 0, "stock_minimum": 5, "status": "inativo"},
            {"name": "Filtro baixo", "quantity_current": 2, "stock_minimum": 5, "status": "ativo"},
            {"name": "Bateria zerada", "quantity_current": 0, "stock_minimum": 5, "status": "ativo"},
        ]

        self.assertEqual(warehouse_stock_info(items[0]).status, "normal")
        self.assertEqual(warehouse_stock_info(items[0]).label, "NORMAL")
        self.assertEqual(warehouse_stock_info(items[1]).status, "inativo")
        self.assertEqual(warehouse_stock_info(items[1]).label, "INATIVO")
        self.assertEqual(warehouse_stock_info(items[2]).status, "baixo")
        self.assertEqual(warehouse_stock_info(items[2]).label, "BAIXO")
        self.assertEqual(warehouse_stock_info(items[2]).reorder_label, "Repor 3")
        self.assertEqual(warehouse_stock_info(items[3]).status, "zerado")
        self.assertEqual(warehouse_stock_info(items[3]).label, "ZERADO")

        self.assertEqual(
            [item["name"] for item in sorted_warehouse_items(items)],
            ["Bateria zerada", "Filtro baixo", "Álcool", "Cone inativo"],
        )

    def test_warehouse_pdf_generation_handles_empty_many_items_and_clickable_links(self):
        empty_pdf = build_warehouse_pdf_bytes([], generated_at=datetime(2026, 6, 17, 18, 35))
        self.assertTrue(empty_pdf.startswith(b"%PDF"))
        self.assertIn(b"/FontFile2", empty_pdf)

        many_items = []
        for index in range(30):
            many_items.append(
                {
                    "id": f"MAT-{index:03d}",
                    "name": f"Material Fêmea {index:02d}",
                    "category": "Acessório operacional",
                    "description": "Aplicação com Observações e Mínimo bem definidos",
                    "unit": "un",
                    "quantity_current": index % 7,
                    "stock_minimum": 3,
                    "storage_location": "Sala de EPI",
                    "purchase_link": f"https://fornecedor.example/item-{index:02d}",
                    "status": "ativo",
                    "item_kind": "acessorio_operacional",
                }
            )

        pdf_bytes = build_warehouse_pdf_bytes(many_items, generated_at=datetime(2026, 6, 17, 18, 35))

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"/FontFile2", pdf_bytes)
        self.assertIn(b"/URI", pdf_bytes)
        self.assertIn(b"https://fornecedor.example/item-00", pdf_bytes)
        self.assertIn('href="https://fornecedor.example/item-00"', link_markup("https://fornecedor.example/item-00"))

    def test_warehouse_pdf_export_respects_screen_filters(self):
        self.login()
        self.create_item()
        items = json.loads(WAREHOUSE_ITEMS_PATH.read_text(encoding="utf-8"))
        items.append(
            {
                "id": "ALM-002",
                "name": "Cabo de energia",
                "category": "Elétrica",
                "description": "Acessório operacional",
                "unit": "un",
                "quantity_current": 12,
                "stock_minimum": 2,
                "storage_location": "Sala de EPI",
                "status": "ativo",
                "item_kind": "acessorio_operacional",
            }
        )
        WAREHOUSE_ITEMS_PATH.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        dashboard_items = build_warehouse_dashboard()["items"]
        filtered = filter_warehouse_items_for_pdf(
            dashboard_items,
            {"q": "papel", "category": "Higiene", "item_kind": "consumivel", "stock_status": "baixo"},
        )
        normal_items = filter_warehouse_items_for_pdf(dashboard_items, {"stock_status": "normal"})
        response = self.client.get("/warehouse/items.pdf?q=papel&category=Higiene&item_kind=consumivel&stock_status=baixo")

        self.assertEqual([item["name"] for item in filtered], ["Papel toalha"])
        self.assertEqual([item["name"] for item in normal_items], ["Cabo de energia"])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_data().startswith(b"%PDF"))

    def test_movements_update_balance_and_register_history_with_user(self):
        self.login()
        self.create_item()
        item_id = json.loads(WAREHOUSE_ITEMS_PATH.read_text(encoding="utf-8"))[0]["id"]

        self.client.post(
            f"/warehouse/items/{item_id}/movement",
            data={"movement_type": "entrada", "quantity": "7", "observation": "Compra semanal"},
        )
        CLIENTS_PATH.write_text(
            json.dumps([{"client_id": "CLI-001", "customer_name": "Cliente Evento", "phone": "11999990000", "address": "Rua A"}]),
            encoding="utf-8",
        )
        EVENTS_PATH.write_text(
            json.dumps([{"event_id": "EVT-001", "title": "Evento Teste", "event_date": "2026-05-12", "client_ids": ["CLI-001"], "vehicle_ids": []}]),
            encoding="utf-8",
        )
        self.client.post(
            f"/warehouse/items/{item_id}/movement",
            data={
                "movement_type": "saida",
                "quantity": "4",
                "observation": "Uso no evento",
                "event_id": "EVT-001",
                "client_id": "CLI-001",
            },
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
        self.assertEqual(movements[1]["event_id"], "EVT-001")
        self.assertEqual(movements[1]["event_title"], "Evento Teste")
        self.assertEqual(movements[1]["client_id"], "CLI-001")
        self.assertEqual(movements[1]["client_name"], "Cliente Evento")
        self.assertEqual(movements[2]["quantity_changed"], 6.0)
        self.assertEqual(movements[2]["final_balance"], 12.0)
        self.assertEqual(movements[2]["user_email"], "admin@sannygold.local")

    def test_loss_and_return_movements_update_stock_and_low_alert(self):
        self.login()
        self.create_item()
        item_id = json.loads(WAREHOUSE_ITEMS_PATH.read_text(encoding="utf-8"))[0]["id"]

        self.client.post(
            f"/warehouse/items/{item_id}/movement",
            data={"movement_type": "perda", "quantity": "2", "observation": "Material avariado"},
        )
        self.client.post(
            f"/warehouse/items/{item_id}/movement",
            data={"movement_type": "retorno", "quantity": "1", "observation": "Retorno de evento"},
        )
        items = json.loads(WAREHOUSE_ITEMS_PATH.read_text(encoding="utf-8"))
        movements = json.loads(WAREHOUSE_MOVEMENTS_PATH.read_text(encoding="utf-8"))
        dashboard = build_warehouse_dashboard()

        self.assertEqual(items[0]["quantity_current"], 2.0)
        self.assertEqual([item["movement_type"] for item in movements], ["perda", "retorno"])
        self.assertEqual(dashboard["counts"]["low"], 1)

    def test_inventory_status_report_exports_equipment_and_low_materials(self):
        self.login()
        EQUIPMENT_PATH.write_text(
            json.dumps(
                [
                    {"equipment_id": "EQ-DISP", "equipment_type": "Banheiro Químico", "status": "disponivel", "condition": "disponivel"},
                    {"equipment_id": "EQ-USO", "equipment_type": "Trailer", "status": "em_operacao", "condition": "em_operacao"},
                    {"equipment_id": "EQ-MAN", "equipment_type": "Climatizador", "status": "manutencao", "condition": "manutencao", "maintenance_reason": "Filtro"},
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        self.create_item()

        pdf_response = self.client.get("/reports/inventory_status.pdf")
        excel_response = self.client.get("/exports/inventory_status.xlsx")

        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.mimetype, "application/pdf")
        self.assertIn(b"EQ-DISP", pdf_response.get_data())
        self.assertIn(b"Materiais abaixo", pdf_response.get_data())
        self.assertEqual(excel_response.status_code, 200)
        self.assertEqual(
            excel_response.mimetype,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

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
