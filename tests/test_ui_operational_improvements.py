import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

os.environ["ROTAFLOW_STORAGE_DIR"] = tempfile.mkdtemp(prefix="sannygold-ui-test-")

from app.main import (  # noqa: E402
    AUDIT_LOG_PATH,
    ATTACHMENTS_PATH,
    CLIENTS_PATH,
    CONTRACTS_PATH,
    EQUIPMENT_PATH,
    EVENTS_PATH,
    QUOTES_PATH,
    SERVICE_LOG_PATH,
    SETTINGS_PATH,
    USERS_PATH,
    VEHICLES_PATH,
    WAREHOUSE_ITEMS_PATH,
    WAREHOUSE_MOVEMENTS_PATH,
    app,
    ensure_storage_dirs,
)


BASE_DIR = Path(__file__).resolve().parents[1]
PLANNER_PATH = BASE_DIR / "scripts" / "plan_routes.py"
planner_spec = importlib.util.spec_from_file_location("plan_routes_for_tests", PLANNER_PATH)
planner = importlib.util.module_from_spec(planner_spec)
assert planner_spec and planner_spec.loader
sys.modules[planner_spec.name] = planner
planner_spec.loader.exec_module(planner)


class OperationalUiImprovementsTest(unittest.TestCase):
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
                    }
                ],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.client = app.test_client()
        self.client.post(
            "/auth/login",
            data={"email": "admin@sannygold.local", "password": "Sanny123Gold"},
            follow_redirects=True,
        )

    def test_operational_shortcuts_and_filters_are_rendered(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("central-day-panel", html)
        self.assertIn("Central do Dia", html)
        self.assertIn("global-search", html)
        self.assertIn("Busca global", html)
        self.assertIn("dashboard-pendencias", html)
        self.assertIn("Dashboard de Pendências", html)
        self.assertIn("quick-actions-bar", html)
        self.assertIn("client-search", html)
        self.assertIn("event-filter", html)
        self.assertIn("equipment-filter", html)
        self.assertIn("maintenance-panel", html)
        self.assertIn("Manutenção de equipamentos", html)
        self.assertIn("Relatórios e exportações", html)
        self.assertIn("Exportar Excel", html)
        self.assertIn("Relatório PDF", html)
        self.assertIn("data-confirm-message", html)
        self.assertIn("backup-status", html)
        self.assertIn("Backup e segurança", html)
        self.assertIn("Auditoria ativa", html)
        self.assertIn("formatCurrencyBRL", html)
        self.assertIn("customer-history", html)
        self.assertIn("quick-rental-panel", html)
        self.assertIn("Criar locação", html)
        self.assertIn("assetPhotoModal", html)
        self.assertIn("daily-command-center", html)
        self.assertIn("Agenda diária única", html)
        self.assertIn("operational-kanban", html)
        self.assertIn("Kanban operacional", html)
        self.assertIn("guided-closeout-panel", html)
        self.assertIn("Fechamento de dia guiado", html)
        self.assertIn("attachments-panel", html)
        self.assertIn("Anexos por cliente e evento", html)
        self.assertIn("equipment-history-panel", html)
        self.assertIn("Histórico por equipamento", html)
        self.assertIn("daily-closeout", html)
        self.assertIn("Próxima ação recomendada", html)
        self.assertIn("Abertura do dia", html)
        self.assertIn("Liberação operacional", html)
        self.assertIn("Fechamento do dia", html)
        self.assertIn("preventive-warning", html)
        self.assertIn("calendar-grid", html)
        self.assertIn("real-map-panel", html)
        self.assertIn("general-usability-panel", html)
        self.assertIn("Central de trabalho do dia", html)
        self.assertIn("general-improvements-panel", html)
        self.assertIn("Painel de controle e prevenção", html)
        self.assertIn("Preparar despacho", html)
        self.assertIn("Buscar por telefone, placa ou NF", html)
        self.assertIn("Pendências críticas por área", html)
        self.assertIn("Alerta de duplicidade", html)
        self.assertIn("Status padrão do processo", html)
        self.assertIn("Relatórios recomendados", html)
        self.assertIn("Eventos de hoje", html)
        self.assertIn("Rotas/paradas prontas", html)
        self.assertIn("Cobranças vencidas", html)
        self.assertIn("Pendências e alertas", html)
        self.assertIn("reports-panel", html)
        self.assertIn("Mapa geral de melhorias aplicadas", html)
        self.assertIn("Atalhos da tela inicial", html)
        self.assertIn("Novo orçamento", html)
        self.assertIn("Contrato mensal", html)
        self.assertIn("Orçamento em PDF", html)
        self.assertIn("Administrador", html)
        self.assertIn("Placa do trailer", html)
        self.assertIn("Em preparação", html)
        self.assertIn("Em andamento", html)
        self.assertIn("today-home", html)
        self.assertIn("Como operar sem se perder", html)
        self.assertIn("usage-guide-panel", html)
        self.assertIn("Manual PDF", html)
        self.assertIn("Etapas do cadastro de evento", html)
        self.assertNotIn("driver-pane", html)
        self.assertNotIn("driver-tab", html)
        self.assertNotIn("Modo motorista", html)
        self.assertNotIn("Ações de rua em poucos toques", html)
        self.assertNotIn("folha impressa por evento", html.lower())

    def test_usability_improvements_are_rendered(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for expected in (
            'id="sticky-global-search"',
            "Buscar no sistema",
            'id="quick-operation-mode"',
            "Central rápida interna",
            "Prepare rota, ordem de serviço, links de endereço e checklist para entregar impresso ou em PDF.",
            "Cards compactos",
            "Ver detalhes",
            "Atalhos recentes",
            "Tela inicial personalizada",
            "Usabilidade geral",
            "Ações sempre visíveis",
            "Cadastro simples primeiro",
            "Checklist do evento",
            "Links de endereço revisados para envio junto ao PDF.",
            "Urgente",
            "Atenção",
            "OK",
            "Pendente",
            "Limpar filtros",
            "Todos os módulos",
            '<option value="financeiro">Financeiro</option>',
            "filters-v1",
            "saveFilterState",
            "restoreFilterState",
            "highlight-after-save",
            "Mais ações",
            "Vencidas",
            "Vencem em breve",
            "Pagas",
        ):
            self.assertIn(expected, html)
        self.assertNotIn("Agrupamento por status dos eventos", html)
        self.assertNotIn("Agrupamento por status do almoxarifado", html)

    def test_executive_and_security_panels_are_rendered(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="executive-overview"', html)
        self.assertIn("Painel executivo e governança", html)
        self.assertIn("Prioridades executivas", html)
        self.assertIn("Top clientes por receita", html)
        self.assertIn("Postura de segurança", html)
        self.assertIn("Política mínima: 10+ caracteres com maiúscula, minúscula e número.", html)
        self.assertIn("Status do sistema", html)
        self.assertIn("status.json", html)
        self.assertIn("health", html)

    def test_financial_panel_is_hidden_for_operational_role(self):
        self.client.post(
            "/users",
            data={
                "nome": "Operador UI",
                "email": "operador-ui@sannygold.local",
                "password": "SenhaForte123",
                "role": "operacional",
                "status": "ativo",
            },
            follow_redirects=True,
        )
        self.client.post("/auth/logout", follow_redirects=True)
        response = self.client.post(
            "/auth/login",
            data={"email": "operador-ui@sannygold.local", "password": "SenhaForte123"},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Resultado real da operação", html)
        self.assertNotIn("Receita do mês", html)
        self.assertIn("Financeiro protegido", html)

    def test_mobile_control_center_exposes_all_core_functions(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("mobile-control-center", html)
        self.assertIn("mobile-action-grid", html)
        self.assertIn("Central de impressão e links", html)
        self.assertIn("Pacote PDF/impresso", html)
        self.assertIn("material impresso, PDF e links de endereço", html)
        for label in (
            "Resumo",
            "Eventos",
            "Clientes",
            "Frota",
            "Equipamentos",
            "Agenda",
            "Histórico",
            "Validar/Gerar",
            "Mapa real",
            "PDF",
            "Fechar dia",
            "Backup",
            "Adicionar item",
            "Alertas",
        ):
            self.assertIn(label, html)
        self.assertNotIn("Motorista", html)
        self.assertNotIn("Modo offline", html)
        self.assertNotIn("Sincronização atual", html)

    def test_daily_flow_search_and_form_helpers_are_rendered(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Próxima ação recomendada", html)
        self.assertIn("global-search-module", html)
        self.assertIn("data-module=", html)
        self.assertIn("Preenchimento rápido", html)
        self.assertIn("Menos esforço para operar", html)
        self.assertIn("Campos principais para cobrança", html)
        self.assertIn("Lançamento rápido", html)
        self.assertIn("Banheiros para eventos com controle claro da operação.", html)
        self.assertIn("Foco em banheiros", html)
        self.assertIn("Trailers com placa", html)
        self.assertIn("Banheiro Trailer Luxo", html)
        self.assertIn("Banheiro Químico", html)
        self.assertIn("Climatizador", html)
        self.assertIn("Ponto de Hidratação", html)
        self.assertIn("Cliente fixo pode ser contrato mensal", html)
        self.assertIn('id="billing_model"', html)
        self.assertIn('id="cleaning_frequency"', html)
        self.assertIn('id="service_profile"', html)
        self.assertIn("Limpeza semanal", html)

    def test_user_manual_pdf_is_available(self):
        response = self.client.get("/manual/sannygold-equipe.pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertIn(b"SannyGold - Manual rapido da equipe", response.get_data())

    def test_equipment_can_store_and_display_plate(self):
        response = self.client.post(
            "/equipment",
            data={
                "equipment_id": "TRL-001",
                "stock_equipment_type": "Trailer Luxo",
                "plate": "RIO2A45",
                "photo_url": "https://cdn.example/trailer-luxo.jpg",
                "condition": "disponivel",
                "notes": "Banheiro móvel com ar condicionado",
                "maintenance_cost": "0",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        equipment = json.loads(EQUIPMENT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        saved_equipment = next(item for item in equipment if item["equipment_id"] == "TRL-001")

        self.assertEqual(saved_equipment["plate"], "RIO2A45")
        self.assertEqual(saved_equipment["photo_url"], "https://cdn.example/trailer-luxo.jpg")
        self.assertIn("Placa RIO2A45", html)
        self.assertIn("https://cdn.example/trailer-luxo.jpg", html)
        self.assertIn("Foto de TRL-001", html)
        self.assertIn("ID, placa, banheiro, climatizador, hidratação, cliente", html)
        self.assertIn("Banheiros e equipamentos operacionais", html)
        self.assertIn("Banheiros de luxo", html)
        self.assertIn("RIO2A45", html)

    def test_vehicle_can_store_and_display_photo(self):
        response = self.client.post(
            "/vehicles",
            data={
                "vehicle_id": "VEI-FOTO",
                "vehicle_type": "Caminhão",
                "plate": "ABC1D23",
                "model": "Mercedes Sprinter",
                "photo_url": "https://cdn.example/veiculo.jpg",
                "start_lat": "-22.8753396",
                "start_lng": "-43.068074",
                "capacity": "8",
                "max_stops": "8",
                "max_minutes": "540",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        vehicles = json.loads(VEHICLES_PATH.read_text(encoding="utf-8"))
        saved_vehicle = next(item for item in vehicles if item["vehicle_id"] == "VEI-FOTO")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(saved_vehicle["photo_url"], "https://cdn.example/veiculo.jpg")
        self.assertIn("https://cdn.example/veiculo.jpg", html)
        self.assertIn("Foto de VEI-FOTO", html)

    def test_contract_quote_portal_and_cleaning_supply_flow(self):
        portal_response = self.client.post(
            "/portal/orcamento",
            data={
                "customer_name": "Cliente Portal",
                "phone": "(21) 97777-0000",
                "event_address": "Rua do Evento, 10",
                "equipment_type": "Banheiro Luxo",
                "equipment_quantity": "2",
                "billing_model": "mensal",
                "cleaning_frequency": "semanal",
            },
            follow_redirects=True,
        )
        quotes = json.loads(QUOTES_PATH.read_text(encoding="utf-8"))

        self.assertEqual(portal_response.status_code, 200)
        self.assertTrue(any(item["customer_name"] == "Cliente Portal" and item["source"] == "portal" for item in quotes))

        WAREHOUSE_ITEMS_PATH.write_text(
            json.dumps(
                [
                    {
                        "id": "ALM-001",
                        "name": "Papel toalha",
                        "category": "Higiene",
                        "unit": "pct",
                        "quantity_current": 10,
                        "stock_minimum": 2,
                        "status": "ativo",
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        self.client.post(
            "/clients",
            data={
                "client_id": "CLI-CONTRATO",
                "customer_name": "Contrato Mensal",
                "client_address": "Estrada Bento Pestana, 932 - Baldeador, Niterói - RJ",
                "client_lat": "-22.8753396",
                "client_lng": "-43.068074",
                "client_type": "fixo",
                "equipment_type": "Banheiro Luxo",
                "equipment_quantity": "1",
                "billing_model": "mensal",
                "cleaning_frequency": "semanal",
                "service_profile": "limpeza_semanal",
                "default_service_minutes": "20",
                "default_priority": "3",
                "window_start": "08:00",
                "window_end": "18:00",
                "service_value": "1500",
                "team_cost": "100",
                "equipment_cost": "50",
            },
            follow_redirects=True,
        )
        contracts = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))

        self.assertTrue(any(item["client_id"] == "CLI-CONTRATO" and item["monthly_value"] == 1500 for item in contracts))

        response = self.client.post(
            "/clients/CLI-CONTRATO/cleaning-service",
            data={"service_date": "2026-04-25", "supply_ALM-001": "2", "notes": "Limpeza semanal"},
            follow_redirects=True,
        )
        service_log = json.loads(SERVICE_LOG_PATH.read_text(encoding="utf-8"))
        warehouse_items = json.loads(WAREHOUSE_ITEMS_PATH.read_text(encoding="utf-8"))
        movements = json.loads(WAREHOUSE_MOVEMENTS_PATH.read_text(encoding="utf-8"))
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item["client_id"] == "CLI-CONTRATO" and item["service_type"] == "limpeza" for item in service_log))
        self.assertEqual(warehouse_items[0]["quantity_current"], 8.0)
        self.assertTrue(any(item["movement_type"] == "baixa limpeza" for item in movements))
        self.assertIn("Orçamentos, contratos mensais e limpezas", html)

    def test_quick_rental_creates_client_and_event(self):
        response = self.client.post(
            "/quick-rental",
            data={
                "customer_name": "Locação Rápida",
                "phone": "(21) 98888-0000",
                "title": "Evento criado pelo atalho",
                "address": "Estrada Bento Pestana, 932 - Baldeador, Niterói - RJ",
                "lat": "-22.8753396",
                "lng": "-43.068074",
                "client_type": "fixo",
                "equipment_type": "Banheiro Luxo",
                "equipment_quantity": "2",
                "billing_model": "mensal",
                "cleaning_frequency": "semanal",
                "event_date": "2026-04-25",
                "event_end_date": "2026-04-26",
                "service_value": "2500",
            },
            follow_redirects=True,
        )
        clients = json.loads(CLIENTS_PATH.read_text(encoding="utf-8"))
        events = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
        contracts = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item["customer_name"] == "Locação Rápida" for item in clients))
        quick_client = next(item for item in clients if item["customer_name"] == "Locação Rápida")
        self.assertTrue(any(quick_client["client_id"] in item["client_ids"] for item in events))
        self.assertTrue(any(item["client_id"] == quick_client["client_id"] and item["monthly_value"] == 2500 for item in contracts))

    def test_attachment_and_service_order_workflows(self):
        self.client.post(
            "/clients",
            data={
                "client_id": "CLI-OS",
                "customer_name": "Cliente OS",
                "client_address": "Estrada Bento Pestana, 932 - Baldeador, Niterói - RJ",
                "client_lat": "-22.8753396",
                "client_lng": "-43.068074",
                "client_type": "avulso",
                "equipment_type": "Banheiro Luxo",
                "equipment_quantity": "1",
                "default_service_minutes": "20",
                "default_priority": "3",
                "window_start": "08:00",
                "window_end": "18:00",
            },
            follow_redirects=True,
        )
        self.client.post(
            "/events",
            data={
                "event_id": "EVT-OS",
                "title": "Evento com OS",
                "event_date": "2026-04-25",
                "event_end_date": "2026-04-25",
                "status": "planejado",
                "event_client_ids": ["CLI-OS"],
            },
            follow_redirects=True,
        )
        attachment_response = self.client.post(
            "/attachments",
            data={
                "scope": "evento",
                "client_id": "CLI-OS",
                "event_id": "EVT-OS",
                "title": "Autorização",
                "attachment_url": "https://example.com/autorizacao.pdf",
                "notes": "Entrada liberada",
            },
            follow_redirects=True,
        )
        os_response = self.client.get("/events/EVT-OS/service-order.pdf")
        attachments = json.loads(ATTACHMENTS_PATH.read_text(encoding="utf-8"))

        self.assertIn("Anexo salvo.", attachment_response.get_data(as_text=True))
        self.assertEqual(attachments[0]["title"], "Autorização")
        self.assertEqual(os_response.status_code, 200)
        self.assertIn(b"SannyGold - Ordem de Servi", os_response.get_data())

    def test_preventive_warnings_do_not_flag_event_without_vehicle(self):
        EVENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "event_id": "EVT-SEM-VEICULO",
                        "title": "Evento Sem Veículo",
                        "event_date": "2026-04-18",
                        "event_end_date": "2026-04-18",
                        "status": "planejado",
                        "client_ids": ["CLI-001"],
                        "vehicle_ids": [],
                        "checklist": [{"label": "checklist_equipamentos", "done": True}],
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Evento incompleto: Evento Sem Veículo", html)
        self.assertNotIn("Vincule clientes e veículos antes da validação.", html)

    def test_ui_exposes_criticality_color_language(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for css_class in (
            "crit-block",
            "crit-attention",
            "crit-ready",
            "crit-info",
            "severity-block",
            "severity-attention",
            "severity-ready",
            "severity-info",
        ):
            self.assertIn(css_class, html)
        self.assertIn("Bloqueio", html)
        self.assertIn("Atenção", html)
        self.assertIn("Pronto", html)
        self.assertIn("Informativo", html)

    def test_dispatch_today_panel_is_rendered(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="dispatch-today-panel"', html)
        self.assertIn("Despacho de hoje", html)
        self.assertIn("PDF da rota", html)
        self.assertIn("Rota validada", html)
        self.assertIn("Veículo", html)
        self.assertIn("Equipamento", html)
        self.assertIn("Contato", html)

    def test_client_form_accepts_invoice_information(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="invoice_status"', html)
        self.assertIn('id="invoice_number"', html)
        self.assertIn("Nota fiscal", html)
        self.assertIn("Número da nota fiscal", html)

        post_response = self.client.post(
            "/clients",
            data={
                "client_id": "CLI-NF",
                "customer_name": "Cliente Com Nota",
                "contact_name": "Ana",
                "phone": "(21) 98888-0000",
                "cpf_cnpj": "00.000.000/0001-00",
                "email": "nota@cliente.com",
                "invoice_status": "com_nota",
                "invoice_number": "98765",
                "client_address": "Estrada Bento Pestana, 932 - Baldeador, Niterói - RJ",
                "client_lat": "-22.8753396",
                "client_lng": "-43.068074",
                "client_type": "fixo",
                "equipment_type": "Banheiro Luxo",
                "equipment_quantity": "1",
                "equipment_number": "",
                "billing_model": "mensal",
                "cleaning_frequency": "semanal",
                "service_profile": "limpeza_semanal",
                "default_service_minutes": "20",
                "default_priority": "3",
                "window_start": "08:00",
                "window_end": "18:00",
                "locked_vehicle_id": "",
                "service_value": "0",
                "team_cost": "0",
                "equipment_cost": "0",
            },
        )

        self.assertEqual(post_response.status_code, 302)
        clients = json.loads(CLIENTS_PATH.read_text(encoding="utf-8"))
        saved = next(item for item in clients if item["client_id"] == "CLI-NF")
        self.assertEqual(saved["invoice_status"], "com_nota")
        self.assertEqual(saved["invoice_number"], "98765")
        self.assertEqual(saved["billing_model"], "mensal")
        self.assertEqual(saved["cleaning_frequency"], "semanal")
        self.assertEqual(saved["service_profile"], "limpeza_semanal")

    def test_backup_download_records_timestamp(self):
        response = self.client.get("/backup/system.zip")
        self.assertEqual(response.status_code, 200)

        self.assertIn("last_backup_at", SETTINGS_PATH.read_text(encoding="utf-8"))
        audit = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
        self.assertTrue(any(item["module"] == "backup" and item["action"] == "download" for item in audit))

    def test_module_pdf_and_excel_exports_are_available(self):
        pdf_response = self.client.get("/reports/clients.pdf")
        excel_response = self.client.get("/exports/clients.xlsx")

        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.mimetype, "application/pdf")
        self.assertIn(b"SannyGold - Clientes", pdf_response.get_data())
        self.assertEqual(excel_response.status_code, 200)
        self.assertEqual(
            excel_response.mimetype,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_equipment_maintenance_flow_records_reason_and_cost(self):
        self.client.post(
            "/equipment",
            data={"equipment_id": "EQ-MAN", "stock_equipment_type": "Banheiro Luxo", "condition": "disponivel", "notes": ""},
            follow_redirects=True,
        )
        response = self.client.post(
            "/equipment/EQ-MAN/maintenance",
            data={
                "maintenance_reason": "Troca de fechadura",
                "maintenance_expected_release": "2026-04-25",
                "maintenance_cost": "120.50",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        self.assertIn("Manutenção registrada para EQ-MAN.", html)
        self.assertIn("Troca de fechadura", html)
        self.assertIn("120.5", html)

    def test_daily_closeout_download_records_timestamp(self):
        response = self.client.get("/daily-closeout.zip")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")

        self.assertIn("last_closeout_at", SETTINGS_PATH.read_text(encoding="utf-8"))

    def test_route_pdf_uses_reference_manifest_columns(self):
        output_path = Path(os.environ["ROTAFLOW_STORAGE_DIR"]) / "preview" / "route-plan.pdf"
        payload = {
            "generated_at": "2026-04-17T09:00:00",
            "operation_date": "2026-04-18",
            "event_title": "Congresso Central",
            "event_end_date": "2026-04-20",
            "total_diarias": 3,
            "summary": {"assigned_deliveries": 1, "total_deliveries": 1},
            "routes": [
                {
                    "vehicle_id": "VEI-001",
                    "vehicle_type": "Caminhao",
                    "vehicle_model": "Sprinter",
                    "vehicle_plate": "ABC1D23",
                    "distance_km": 12.5,
                    "total_minutes": 90,
                    "stops": [
                        {
                            "delivery_id": "CLI-001",
                            "customer_name": "Igreja Matriz",
                            "operation_date": "2026-04-18",
                            "event_end_date": "2026-04-20",
                            "total_diarias": 3,
                            "arrival": "09:30",
                            "window_start": "09:00",
                            "window_end": "12:00",
                            "address": "Rua Central, 10",
                            "equipment_type": "Estandarte",
                            "equipment_quantity": 2,
                            "equipment_number": "EQ-100",
                            "contact_name": "Maria Souza",
                            "phone": "(21) 99999-0000",
                            "invoice_status": "com_nota",
                            "invoice_number": "98765",
                            "operation_notes": "Montar na entrada",
                        }
                    ],
                }
            ],
            "unassigned": [],
        }

        planner.write_driver_manifest_pdf(payload, output_path)
        pdf_bytes = output_path.read_bytes()

        for expected in (
            b"N.",
            b"CLIENTE",
            b"DATA EVENTO",
            b"DATA FINAL",
            b"DIARIAS",
            b"DATA ENTREGA",
            b"DIA DA SEMANA",
            b"HORARIO",
            b"LOCAL",
            b"OBS",
            b"QUANT. ESTANDARTE",
            b"NOME CONTATO",
            b"TELEFONE",
            b"DATA RETIRADA",
            b"Igreja Matriz",
            b"Maria Souza",
            b"99999-0000",
            b"NF 98765",
        ):
            self.assertIn(expected, pdf_bytes)


if __name__ == "__main__":
    unittest.main()
