import importlib.util
import json
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

os.environ["ROTAFLOW_STORAGE_DIR"] = tempfile.mkdtemp(prefix="sannygold-ui-test-")

from app.main import (  # noqa: E402
    AUDIT_LOG_PATH,
    ATTACHMENTS_PATH,
    BACKUPS_DIR,
    CLIENTS_PATH,
    CONTRACTS_PATH,
    EQUIPMENT_PATH,
    EVENTS_PATH,
    FINANCIAL_RECEIVABLES_PATH,
    QUOTES_PATH,
    ROUTE_HISTORY_PATH,
    SERVICE_LOG_PATH,
    SERVICE_ORDERS_PATH,
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
        SERVICE_ORDERS_PATH.write_text("[]\n", encoding="utf-8")
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
                    }
                ],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.client.post(
            "/auth/login",
            data={"email": "admin@sannygold.local", "password": "troque-esta-senha"},
            follow_redirects=True,
        )

    def test_operational_shortcuts_and_filters_are_rendered(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("central-day-panel", html)
        self.assertIn("Central do Dia", html)
        self.assertIn("Pendências críticas de hoje", html)
        self.assertIn("Ações rápidas", html)
        self.assertIn("Eventos/serviços de hoje", html)
        self.assertIn("Próximos 7 dias", html)
        self.assertIn("Rotas pendentes de geração", html)
        self.assertIn("Ordens de serviço pendentes", html)
        self.assertIn("Clientes sem endereço completo", html)
        self.assertIn("Eventos sem valor financeiro", html)
        self.assertIn("Contas a receber vencidas", html)
        self.assertIn("Alertas preventivos", html)
        self.assertIn("Equipamentos reservados, em operação ou aguardando limpeza", html)
        self.assertIn("Equipamentos em manutenção", html)
        self.assertIn("Veículos/motoristas do dia", html)
        self.assertIn("Cadastrar cliente", html)
        self.assertIn("Cadastrar evento", html)
        self.assertIn("Gerar ordem de serviço", html)
        self.assertIn("Registrar recebimento", html)
        self.assertIn("Movimentar estoque", html)
        self.assertIn("Gerar backup", html)
        self.assertIn("global-search", html)
        self.assertIn("Busca global", html)
        self.assertIn("status, data", html)
        self.assertIn("js-set-filter", html)
        self.assertIn('data-select-target="global-search-module"', html)
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
        self.assertIn("data-confirm-title", html)
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
        self.assertIn("role-focus-panel", html)

    def test_daily_center_exposes_preventive_alerts_and_management_reports(self):
        paths = [
            CLIENTS_PATH,
            EVENTS_PATH,
            VEHICLES_PATH,
            EQUIPMENT_PATH,
            FINANCIAL_RECEIVABLES_PATH,
            ROUTE_HISTORY_PATH,
            AUDIT_LOG_PATH,
            WAREHOUSE_ITEMS_PATH,
            WAREHOUSE_MOVEMENTS_PATH,
        ]
        previous_contents = {
            path: path.read_text(encoding="utf-8") if path.exists() else None
            for path in paths
        }
        today = date.today()
        yesterday = today - timedelta(days=1)
        try:
            CLIENTS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "client_id": "CLI-SEM-ENDERECO",
                            "customer_name": "Cliente Sem Endereço",
                            "phone": "(21) 90000-0001",
                            "address": "",
                            "lat": "",
                            "lng": "",
                            "equipment_type": "Banheiro Químico",
                            "equipment_quantity": 3,
                            "equipment_number": "EQ-CONFLITO",
                        },
                        {
                            "client_id": "CLI-OK",
                            "customer_name": "Cliente OK",
                            "phone": "(21) 90000-0002",
                            "address": "Rua Central, 100",
                            "lat": -22.9,
                            "lng": -43.1,
                            "equipment_type": "Banheiro Químico",
                            "equipment_quantity": 1,
                            "equipment_number": "EQ-CONFLITO",
                        },
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            EVENTS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "event_id": "EVT-HOJE",
                            "title": "Evento Hoje",
                            "event_date": today.isoformat(),
                            "event_end_date": today.isoformat(),
                            "status": "confirmado",
                            "client_ids": ["CLI-SEM-ENDERECO"],
                            "vehicle_ids": ["VEI-BLOQUEADO"],
                            "valor_servico": 0,
                        },
                        {
                            "event_id": "EVT-CONFLITO",
                            "title": "Evento Conflito",
                            "event_date": today.isoformat(),
                            "event_end_date": today.isoformat(),
                            "status": "confirmado",
                            "client_ids": ["CLI-OK"],
                            "vehicle_ids": ["VEI-BLOQUEADO"],
                            "valor_servico": 1500,
                        },
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            VEHICLES_PATH.write_text(
                json.dumps(
                    [
                        {
                            "vehicle_id": "VEI-BLOQUEADO",
                            "vehicle_type": "Caminhão",
                            "plate": "SGD3A21",
                            "driver": "João",
                            "capacity": 1,
                            "status": "indisponivel",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            EQUIPMENT_PATH.write_text(
                json.dumps(
                    [
                        {"equipment_id": "EQ-CONFLITO", "equipment_type": "Banheiro Químico", "status": "disponivel"},
                        {"equipment_id": "EQ-MAN", "equipment_type": "Banheiro Luxo", "status": "manutencao", "maintenance_reason": "troca de bomba"},
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            FINANCIAL_RECEIVABLES_PATH.write_text(
                json.dumps(
                    [
                        {
                            "id": "REC-VENCIDO",
                            "client_id": "CLI-OK",
                            "client_name": "Cliente OK",
                            "event_id": "EVT-ANTIGO",
                            "amount": 500,
                            "amount_received": 0,
                            "due_date": yesterday.isoformat(),
                            "status": "vencido",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            WAREHOUSE_ITEMS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "id": "MAT-001",
                            "name": "Sabonete",
                            "category": "Limpeza",
                            "quantity_current": 0,
                            "stock_minimum": 2,
                            "unit": "un",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            WAREHOUSE_MOVEMENTS_PATH.write_text("[]\n", encoding="utf-8")
            ROUTE_HISTORY_PATH.write_text("[]\n", encoding="utf-8")
            AUDIT_LOG_PATH.write_text("[]\n", encoding="utf-8")

            response = self.client.get("/")
            html = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            for expected in (
                "Cliente sem endereço",
                "Equipamento já reservado em outro evento",
                "Veículo indisponível",
                "Evento sem banheiro suficiente",
                "Evento sem cobrança cadastrada",
                "Recebimento atrasado",
                "Estoque abaixo do mínimo",
                "Eventos sem valor financeiro",
                "Contas a receber vencidas",
                "Relatório diário de operação",
                "Relatório semanal de eventos",
                "Relatório de equipamentos",
                "Relatório financeiro básico",
                "Relatório de estoque",
                "Relatório de pendências",
            ):
                self.assertIn(expected, html)
        finally:
            for path, content in previous_contents.items():
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(content, encoding="utf-8")

    def test_local_first_assets_and_status_are_rendered(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        index_template = (BASE_DIR / "app" / "templates" / "index.html").read_text(encoding="utf-8")
        password_template = (BASE_DIR / "app" / "templates" / "password_setup.html").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertTrue((BASE_DIR / "app" / "static" / "vendor" / "bootstrap" / "bootstrap.min.css").exists())
        self.assertTrue((BASE_DIR / "app" / "static" / "vendor" / "bootstrap" / "bootstrap.bundle.min.js").exists())
        self.assertTrue((BASE_DIR / "app" / "static" / "vendor" / "qrcode" / "qrcode.min.js").exists())
        self.assertIn("/static/vendor/bootstrap/bootstrap.min.css", html)
        self.assertIn("/static/vendor/bootstrap/bootstrap.bundle.min.js", html)
        self.assertIn("/static/vendor/qrcode/qrcode.min.js", html)
        self.assertIn("/static/manifest.webmanifest", html)
        self.assertIn("/service-worker.js", html)
        self.assertIn("Sistema local ativo", html)
        self.assertIn("Banco ativo", html)
        self.assertIn("Internet: verificando", html)
        self.assertIn("Internet disponível", html)
        self.assertIn("Internet indisponível", html)
        self.assertIn("Último backup", html)
        self.assertIn("Acesso pelo celular no Wi-Fi", html)
        self.assertIn("Acesso pelo Celular", html)
        self.assertIn("wifi-access-qr", html)
        self.assertIn("/admin/acesso-celular", html)
        self.assertIn("@media (max-width: 767.98px)", html)
        self.assertIn(".finance-status-row", html)
        self.assertIn("#wifi-access-panel .wifi-qr-box", html)
        self.assertIn("mobile-stack-table", html)
        self.assertIn('data-label="Usuário"', html)
        self.assertIn('data-label="Cliente"', index_template)
        self.assertIn("Mapa embutido externo não carrega automaticamente", html)
        self.assertNotIn("cdn.jsdelivr.net", html)
        self.assertNotIn("maps.googleapis.com/maps/api/js", html)
        self.assertNotIn("<iframe src=\"https://", html)
        self.assertNotIn("cdn.jsdelivr.net", password_template)
        self.assertIn("@media (max-width: 520px)", password_template)
        self.assertIn("min-height: 46px", password_template)

        service_worker = self.client.get("/service-worker.js")
        self.assertEqual(service_worker.status_code, 200)
        self.assertEqual(service_worker.headers.get("Service-Worker-Allowed"), "/")
        service_worker.close()
        self.assertIn("Prioridade da sua função", html)
        self.assertIn("guided-operation-flow", html)
        self.assertIn("Roteiro rápido da operação", html)
        self.assertIn("sem etapa de confirmação de saída ou retorno", html)
        self.assertIn("attention-now-panel", html)
        self.assertIn("O que precisa de atenção agora", html)
        self.assertIn("operational-kanban", html)
        self.assertIn("Kanban operacional", html)
        self.assertIn("guided-closeout-panel", html)
        self.assertIn("Fechamento administrativo do dia", html)
        self.assertIn("daily-management-checklist", html)
        self.assertIn("Checklist diário da gestão", html)
        self.assertIn("report-hub-grid", html)
        self.assertIn("Abrir origem", html)
        self.assertIn("Estoque baixo", html)
        self.assertIn("attachments-panel", html)
        self.assertIn("Anexos por cliente e evento", html)
        self.assertIn("equipment-history-panel", html)
        self.assertIn("Histórico por equipamento", html)
        self.assertIn("daily-closeout", html)
        self.assertIn("Próxima ação recomendada", html)
        self.assertIn("Abertura do dia", html)
        self.assertIn("Liberação operacional", html)
        self.assertIn("Fechamento do dia", html)
        self.assertIn("Backup e conferência", html)
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
        self.assertIn("Escopo aplicado agora", html)
        self.assertIn("Item 5 fora", html)
        self.assertIn("Agenda operacional reforçada", html)
        self.assertIn("Preparo para publicação", html)
        self.assertIn("Relatório semanal PDF", html)
        self.assertIn("Baixar PDF semanal", html)
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
        self.assertIn("Programado", html)
        self.assertIn("Em andamento", html)
        self.assertIn("today-home", html)
        self.assertIn("Como operar sem se perder", html)
        self.assertIn(".sg-card", html)
        self.assertIn(".sg-table", html)
        self.assertIn(".sg-btn-primary", html)
        self.assertIn(".sg-btn-secondary", html)
        self.assertIn(".sg-btn-danger", html)
        self.assertIn(".sg-alert-critical", html)
        self.assertIn(".sg-alert-attention", html)
        self.assertIn(".sg-alert-success", html)
        self.assertIn(".sg-status-event", html)
        self.assertIn(".sg-status-finance", html)
        self.assertIn(".sg-status-equipment", html)
        self.assertIn(".route-badge.badge-danger", html)
        self.assertIn(".finance-status-tile .route-badge", html)
        self.assertIn(".equipment-list-item .route-badge", html)
        self.assertIn("usage-guide-panel", html)
        self.assertIn("team-enable-guide", html)
        self.assertIn("Guia prático de uso por função", html)
        self.assertIn("Padrão de nomes no sistema", html)
        self.assertIn("Cadastro mínimo sem retrabalho", html)
        self.assertIn("criticalConfirmModal", html)
        self.assertIn("Confirmar ação crítica", html)
        self.assertIn("Item afetado", html)
        self.assertIn("Consequência", html)
        self.assertNotIn("window.confirm", html)
        self.assertIn("Pacote para PDF, impresso e links", html)
        self.assertIn("Regras para evitar confusão", html)
        self.assertIn("smart-system-panel", html)
        self.assertIn("Inteligência operacional da SannyGold", html)
        self.assertIn("Próximos passos automáticos", html)
        self.assertIn("Validação inteligente antes da rota", html)
        self.assertIn("Histórico inteligente do cliente", html)
        self.assertIn("Busca esperta e duplicidades", html)
        self.assertIn("Recomendações financeiras", html)
        self.assertIn("Previsão de demanda", html)
        self.assertIn("Relatórios automáticos recomendados", html)
        self.assertIn("Checklists dinâmicos por tipo de operação", html)
        self.assertIn("Assistente Operacional", html)
        self.assertIn("help-assistant-button", html)
        self.assertIn("quick-help-panel", html)
        self.assertIn("Ajuda Rápida", html)
        self.assertIn("Como criar cliente", html)
        self.assertIn("Como criar locação rápida", html)
        self.assertIn("Como gerar rota", html)
        self.assertIn("Como gerar ordem de serviço", html)
        self.assertIn("Como lançar recebimento", html)
        self.assertIn("Como corrigir pendências", html)
        self.assertIn("Como consultar agenda", html)
        self.assertIn("Como saber o que fazer hoje", html)
        self.assertIn("O que fazer quando aparecer erro", html)
        self.assertIn("Quem chamar em caso de dúvida interna", html)
        self.assertIn("evento em Niterói/RJ", html)
        self.assertIn("banheiro químico", html)
        self.assertIn("trailer de luxo", html)
        self.assertIn("climatizador", html)
        self.assertIn("ponto de hidratação", html)
        self.assertIn('href="#quick-help-hoje"', html)
        self.assertIn('href="#quick-help-locacao-rapida"', html)
        self.assertIn('href="#quick-help-financeiro"', html)
        self.assertIn('href="#quick-help-rota"', html)
        self.assertNotIn("Manual PDF", html)
        self.assertIn("Etapas do cadastro de evento", html)
        self.assertIn("smart-usage-panel", html)
        self.assertIn("Central inteligente de uso diário", html)
        self.assertIn("daily-attention-mode", html)
        self.assertIn("Modo atenção do dia", html)
        self.assertIn("Comando da próxima ação", html)
        self.assertIn("Qualidade dos cadastros", html)
        self.assertIn("Roteiro de revisão rápida", html)
        self.assertIn("Atalhos da função e semana", html)
        self.assertIn("Banheiros/equipamentos", html)
        self.assertIn("PDF/impresso", html)
        self.assertIn("Resumo automático do dia", html)
        self.assertIn("Mostrar só o que precisa de ação", html)
        self.assertIn("Pontuação de risco por evento", html)
        self.assertIn("Prioridade automática das pendências", html)
        self.assertIn("Favoritos por usuário", html)
        self.assertIn("Ranking de clientes que exigem atenção", html)
        self.assertIn("Previsão de estoque por uso", html)
        self.assertIn("Alertas por prazo", html)
        self.assertIn("Relatório semanal automático", html)
        self.assertIn("Detecção de inconsistência", html)
        self.assertIn("Histórico de alterações visível", html)
        self.assertIn("Fechar o dia guiado", html)
        self.assertIn("Modo revisão antes de imprimir/PDF", html)
        self.assertIn("Templates rápidos e campos guiados por etapa", html)
        self.assertIn("Completar o que falta", html)
        self.assertIn("Busca com comandos", html)
        self.assertIn("Assistente de cadastro por etapas", html)
        self.assertIn("Resumo antes de salvar", html)
        self.assertIn("Progresso do evento", html)
        self.assertIn("Linha do tempo do cliente", html)
        self.assertNotIn("driver-pane", html)
        self.assertNotIn("driver-tab", html)
        self.assertNotIn("Modo motorista", html)
        self.assertNotIn("Ações de rua em poucos toques", html)
        self.assertNotIn("folha impressa por evento", html.lower())
        self.assertNotIn("equipamento ideal", html.lower())

    def test_admin_mobile_access_page_renders_qr_guidance_and_local_assets(self):
        response = self.client.get("/admin/acesso-celular")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Acesso pelo Celular", html)
        self.assertIn("Endereço local do sistema", html)
        self.assertIn("mobile-access-qr", html)
        self.assertIn("local-mobile-url", html)
        self.assertIn("mesmo Wi-Fi", html)
        self.assertIn("O computador servidor precisa ficar ligado", html)
        self.assertIn("Login continua obrigatório", html)
        self.assertIn("Não abra portas automaticamente no roteador", html)
        self.assertIn("não publica o sistema na internet", html)
        self.assertIn("Acesso externo seguro com Tailscale", html)
        self.assertIn("Tailscale opcional não configurado", html)
        self.assertIn("SANNYGOLD_TAILSCALE_URL", html)
        self.assertIn("Computador e celular precisam estar na mesma conta/rede Tailscale", html)
        self.assertIn("overflow-wrap: anywhere", html)
        self.assertIn("@media (max-width: 720px)", html)
        self.assertIn("max-width: min(188px, 100%)", html)
        self.assertIn("/static/vendor/bootstrap/bootstrap.min.css", html)
        self.assertIn("/static/vendor/bootstrap/bootstrap.bundle.min.js", html)
        self.assertIn("/static/vendor/qrcode/qrcode.min.js", html)
        self.assertNotIn("cdn.jsdelivr.net", html)

    def test_admin_mobile_access_page_shows_configured_tailscale_url(self):
        old_url = os.environ.get("SANNYGOLD_TAILSCALE_URL")
        old_ip = os.environ.get("SANNYGOLD_TAILSCALE_IP")
        os.environ["SANNYGOLD_TAILSCALE_URL"] = "http://100.101.102.103:5007/"
        os.environ.pop("SANNYGOLD_TAILSCALE_IP", None)
        try:
            response = self.client.get("/admin/acesso-celular")
        finally:
            if old_url is None:
                os.environ.pop("SANNYGOLD_TAILSCALE_URL", None)
            else:
                os.environ["SANNYGOLD_TAILSCALE_URL"] = old_url
            if old_ip is None:
                os.environ.pop("SANNYGOLD_TAILSCALE_IP", None)
            else:
                os.environ["SANNYGOLD_TAILSCALE_IP"] = old_ip

        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Tailscale configurado", html)
        self.assertIn("http://100.101.102.103:5007/", html)
        self.assertIn("Não compartilhe este endereço", html)

    def test_training_panel_is_visual_only_and_does_not_write_data(self):
        CLIENTS_PATH.write_text(
            json.dumps([{"client_id": "CLI-REAL", "customer_name": "Cliente Real"}], ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        EVENTS_PATH.write_text(
            json.dumps([{"event_id": "EVT-REAL", "title": "Evento Real"}], ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        clients_before = CLIENTS_PATH.read_text(encoding="utf-8")
        events_before = EVENTS_PATH.read_text(encoding="utf-8")

        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(CLIENTS_PATH.read_text(encoding="utf-8"), clients_before)
        self.assertEqual(EVENTS_PATH.read_text(encoding="utf-8"), events_before)
        self.assertIn('id="training-panel"', html)
        self.assertIn("Treinamento", html)
        self.assertIn("Simulação guiada do fluxo principal", html)
        self.assertIn("Simulação visual", html)
        self.assertIn("Dados fictícios", html)
        self.assertIn("Sem gravação real", html)
        self.assertIn("não salva dados reais", html)
        self.assertIn("não grava na pasta data/", html)
        self.assertIn("não gera rota, OS, PDF ou cobrança real", html)
        for label in (
            "Cadastrar cliente fictício",
            "Criar locação fictícia",
            "Adicionar serviço",
            "Gerar rota simulada",
            "Gerar OS simulada",
            "Lançar recebimento simulado",
        ):
            self.assertIn(label, html)
        for sample in (
            "Cliente Treinamento SannyGold",
            "Evento Treinamento - Niterói/RJ",
            "2 banheiro químico + 1 ponto de hidratação",
            "Rota simulada: Base SannyGold -> Niterói/RJ",
            "OS-SIM-001",
            "R$ 1.200,00",
        ):
            self.assertIn(sample, html)
        self.assertIn('href="#training-panel"', html)
        self.assertIn('data-tab-target="history-tab"', html)
        self.assertIn("training-step-card", html)
        self.assertIn("data-training-step", html)
        self.assertIn("training-next-step", html)
        self.assertIn("initTrainingSimulation", html)
        training_start = html.index('id="training-panel"')
        training_end = html.index("Histórico diário de saídas", training_start)
        training_html = html[training_start:training_end].lower()
        self.assertNotIn('method="post"', training_html)
        self.assertNotIn("action=", training_html)

    def seed_intelligent_pending_data(self):
        today = date.today()
        yesterday = today - timedelta(days=1)
        CLIENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "client_id": "CLI-PEND",
                        "customer_name": "Cliente Pendência",
                        "phone": "",
                        "cpf_cnpj": "",
                        "address": "",
                        "lat": None,
                        "lng": None,
                        "client_type": "fixo",
                        "billing_model": "mensal",
                        "invoice_status": "com_nota",
                        "equipment_type": "",
                        "equipment_quantity": 0,
                        "created_at": today.isoformat(),
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        EVENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "event_id": "EVT-PEND",
                        "title": "Evento com Pendência",
                        "event_date": today.isoformat(),
                        "event_end_date": today.isoformat(),
                        "status": "confirmado",
                        "client_ids": ["CLI-PEND"],
                        "vehicle_ids": [],
                        "valor_servico": 0,
                        "created_at": today.isoformat(),
                    },
                    {
                        "event_id": "EVT-FIN",
                        "title": "Locação Sem Financeiro",
                        "event_date": yesterday.isoformat(),
                        "event_end_date": yesterday.isoformat(),
                        "status": "finalizado",
                        "client_ids": ["CLI-PEND"],
                        "vehicle_ids": [],
                        "valor_servico": 1500,
                        "responsible": "Equipe interna",
                    },
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        VEHICLES_PATH.write_text(
            json.dumps(
                [
                    {
                        "vehicle_id": "VEI-PEND",
                        "vehicle_type": "",
                        "plate": "",
                        "capacity": "",
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        EQUIPMENT_PATH.write_text(
            json.dumps(
                [
                    {
                        "equipment_id": "EQ-SEM-STATUS",
                        "equipment_type": "Banheiro Químico",
                        "status": "",
                    },
                    {
                        "equipment_id": "EQ-MAN",
                        "equipment_type": "Trailer de Luxo",
                        "status": "manutencao",
                        "maintenance_reason": "Revisar bomba",
                        "maintenance_expected_release": today.isoformat(),
                    },
                    {
                        "equipment_id": "EQ-RET",
                        "equipment_type": "Banheiro PNE",
                        "status": "retirada_pendente",
                    },
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        FINANCIAL_RECEIVABLES_PATH.write_text(
            json.dumps(
                [
                    {
                        "id": "REC-PEND",
                        "client_id": "CLI-PEND",
                        "client_name": "Cliente Pendência",
                        "event_id": "EVT-PEND",
                        "amount": 900,
                        "amount_received": 0,
                        "due_date": yesterday.isoformat(),
                        "status": "vencido",
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    def test_intelligent_pending_panel_groups_and_filters_items(self):
        self.seed_intelligent_pending_data()

        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="intelligent-pending-panel"', html)
        self.assertIn("Pendências Inteligentes", html)
        self.assertIn('id="intelligent-pending-category-filter"', html)
        self.assertIn('id="intelligent-pending-severity-filter"', html)
        self.assertIn('data-category="operational"', html)
        self.assertIn('data-category="financial"', html)
        self.assertIn('data-category="registration"', html)
        self.assertIn('data-category="maintenance"', html)
        for label in (
            "Evento sem endereço",
            "Evento sem responsável",
            "Evento sem equipamento",
            "Evento sem quantidade",
            "Rota sem veículo",
            "Ordem de serviço não gerada",
            "Evento sem valor",
            "Recebimento vencido",
            "Cliente com cobrança em aberto",
            "Locação realizada sem lançamento financeiro",
            "Cliente sem telefone",
            "Cliente sem CNPJ/CPF quando necessário",
            "Cliente sem endereço",
            "Equipamento sem status",
            "Equipamento em manutenção",
            "Equipamento com retorno pendente",
            "Veículo sem informação básica",
        ):
            self.assertIn(label, html)

    def test_intelligent_pending_panel_respects_user_profile(self):
        self.seed_intelligent_pending_data()
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        users.extend(
            [
                {
                    "id": "USR-OP-PEND",
                    "nome": "Operação Pendências",
                    "email": "operacao-pendencias@sannygold.local",
                    "senha_hash": generate_password_hash("SenhaForte123", method="pbkdf2:sha256"),
                    "status": "ativo",
                    "role": "operacional",
                    "must_change_password": False,
                },
                {
                    "id": "USR-FIN-PEND",
                    "nome": "Financeiro Pendências",
                    "email": "financeiro-pendencias@sannygold.local",
                    "senha_hash": generate_password_hash("SenhaForte123", method="pbkdf2:sha256"),
                    "status": "ativo",
                    "role": "financeiro",
                    "must_change_password": False,
                },
            ]
        )
        USERS_PATH.write_text(json.dumps(users, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        self.client.post("/auth/logout", follow_redirects=True)
        operational_response = self.client.post(
            "/auth/login",
            data={"email": "operacao-pendencias@sannygold.local", "password": "SenhaForte123"},
            follow_redirects=True,
        )
        operational_html = operational_response.get_data(as_text=True)
        self.assertIn("Pendências operacionais", operational_html)
        self.assertIn("Pendências de cadastro", operational_html)
        self.assertIn("Pendências de manutenção", operational_html)
        self.assertNotIn('data-category="financial"', operational_html)
        self.assertNotIn("Recebimento vencido", operational_html)

        self.client.post("/auth/logout", follow_redirects=True)
        financial_response = self.client.post(
            "/auth/login",
            data={"email": "financeiro-pendencias@sannygold.local", "password": "SenhaForte123"},
            follow_redirects=True,
        )
        financial_html = financial_response.get_data(as_text=True)
        self.assertIn("Pendências financeiras", financial_html)
        self.assertIn("Recebimento vencido", financial_html)
        self.assertNotIn('data-category="operational"', financial_html)

    def seed_smart_client_summary_data(self):
        today = date.today()
        yesterday = today - timedelta(days=20)
        tomorrow = today + timedelta(days=3)
        CLIENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "client_id": "CLI-SMART",
                        "customer_name": "Cliente Resumo",
                        "contact_name": "Mariana",
                        "phone": "(21) 98888-0000",
                        "cpf_cnpj": "12.345.678/0001-90",
                        "email": "resumo@sannygold.local",
                        "address": "Rua das Operações, 100 - Niterói",
                        "lat": -22.88,
                        "lng": -43.09,
                        "client_type": "fixo",
                        "equipment_type": "Banheiro Químico",
                        "equipment_quantity": 3,
                        "equipment_number": "EQ-SMART",
                        "billing_model": "mensal",
                        "cleaning_frequency": "semanal",
                        "service_profile": "evento_avulso",
                        "window_start": "09:00",
                        "window_end": "17:00",
                        "service_value": 1200,
                        "invoice_status": "com_nota",
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        EVENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "event_id": "EVT-SMART-OLD",
                        "title": "Locação anterior",
                        "event_category": "evento_corporativo",
                        "event_date": yesterday.isoformat(),
                        "event_end_date": yesterday.isoformat(),
                        "status": "finalizado",
                        "client_ids": ["CLI-SMART"],
                        "vehicle_ids": [],
                        "responsible": "Operação",
                        "notes": "Entrada pela portaria de carga com restrição de acesso.",
                        "valor_servico": 1200,
                    },
                    {
                        "event_id": "EVT-SMART-NEXT",
                        "title": "Próxima locação",
                        "event_category": "evento_corporativo",
                        "event_date": tomorrow.isoformat(),
                        "event_end_date": tomorrow.isoformat(),
                        "status": "confirmado",
                        "client_ids": ["CLI-SMART"],
                        "vehicle_ids": [],
                        "responsible": "Operação",
                        "notes": "Confirmar acesso pela portaria.",
                        "valor_servico": 1800,
                    },
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        FINANCIAL_RECEIVABLES_PATH.write_text(
            json.dumps(
                [
                    {
                        "id": "REC-SMART-1",
                        "client_id": "CLI-SMART",
                        "client_name": "Cliente Resumo",
                        "event_id": "EVT-SMART-OLD",
                        "amount": 1200,
                        "amount_received": 400,
                        "due_date": (today - timedelta(days=5)).isoformat(),
                        "status": "vencido",
                    },
                    {
                        "id": "REC-SMART-2",
                        "client_id": "CLI-SMART",
                        "client_name": "Cliente Resumo",
                        "event_id": "EVT-SMART-NEXT",
                        "amount": 1800,
                        "amount_received": 0,
                        "due_date": (today + timedelta(days=10)).isoformat(),
                        "status": "aguardando",
                    },
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        CONTRACTS_PATH.write_text("[]\n", encoding="utf-8")
        SERVICE_LOG_PATH.write_text("[]\n", encoding="utf-8")
        QUOTES_PATH.write_text("[]\n", encoding="utf-8")
        ROUTE_HISTORY_PATH.write_text("[]\n", encoding="utf-8")

    def test_smart_client_summary_shows_history_preferences_alerts_and_actions(self):
        self.seed_smart_client_summary_data()

        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Resumo Inteligente do Cliente", html)
        self.assertIn("Cliente Resumo", html)
        self.assertIn("Cliente com atraso", html)
        self.assertIn("Dados principais", html)
        self.assertIn("Telefone/WhatsApp", html)
        self.assertIn("resumo@sannygold.local", html)
        self.assertIn("Histórico", html)
        self.assertIn("Total de locações/eventos", html)
        self.assertIn("Última locação", html)
        self.assertIn("Próxima locação", html)
        self.assertIn("Ticket médio", html)
        self.assertIn("Valor total faturado", html)
        self.assertIn("Valor em aberto", html)
        self.assertIn("Atrasos anteriores", html)
        self.assertIn("Preferências operacionais", html)
        self.assertIn("evento corporativo", html)
        self.assertIn("Banheiro Químico", html)
        self.assertIn("Entrada pela portaria de carga com restrição de acesso.", html)
        self.assertIn("Cliente com pagamento vencido", html)
        self.assertIn("Cliente com evento próximo", html)
        self.assertIn("Criar nova locação", html)
        self.assertIn("Lançar recebimento", html)
        self.assertIn("Gerar relatório do cliente", html)
        self.assertIn("/clients/CLI-SMART/report.pdf", html)
        self.assertIn("Enviar cobrança", html)
        self.assertIn("js-start-client-rental", html)

        pdf_response = self.client.get("/clients/CLI-SMART/report.pdf")
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.mimetype, "application/pdf")
        self.assertIn(b"SannyGold - Cliente Cliente Resumo", pdf_response.get_data())
        pdf_response.close()

    def test_next_recommended_actions_guide_clients_events_and_finance(self):
        today = date.today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=3)
        old_day = today - timedelta(days=220)
        paths = [
            CLIENTS_PATH,
            EVENTS_PATH,
            VEHICLES_PATH,
            FINANCIAL_RECEIVABLES_PATH,
            AUDIT_LOG_PATH,
            CONTRACTS_PATH,
            SERVICE_LOG_PATH,
            QUOTES_PATH,
            ROUTE_HISTORY_PATH,
        ]
        previous_contents = {
            path: path.read_text(encoding="utf-8") if path.exists() else None
            for path in paths
        }
        try:
            CLIENTS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "client_id": "CLI-REC-INCOMPLETE",
                            "customer_name": "Cliente Recomendação",
                            "phone": "",
                            "address": "",
                            "client_type": "avulso",
                            "equipment_type": "",
                            "equipment_quantity": 0,
                            "service_value": 0,
                        },
                        {
                            "client_id": "CLI-REC-READY",
                            "customer_name": "Cliente Operação Pronta",
                            "phone": "(21) 99999-3333",
                            "address": "Rua Pronta, 100 - Niterói/RJ",
                            "lat": -22.88,
                            "lng": -43.09,
                            "client_type": "avulso",
                            "equipment_type": "Banheiro Químico",
                            "equipment_quantity": 2,
                            "equipment_number": "EQ-REC",
                            "service_value": 1400,
                        },
                        {
                            "client_id": "CLI-REC-INACTIVE",
                            "customer_name": "Cliente Inativo",
                            "phone": "(21) 98888-4444",
                            "address": "Rua Antiga, 50 - Niterói/RJ",
                            "lat": -22.87,
                            "lng": -43.08,
                            "client_type": "avulso",
                            "equipment_type": "Climatizador",
                            "equipment_quantity": 1,
                            "service_value": 600,
                        },
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            EVENTS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "event_id": "EVT-REC-INCOMPLETE",
                            "title": "Locação Incompleta",
                            "event_date": today.isoformat(),
                            "event_end_date": today.isoformat(),
                            "status": "confirmado",
                            "client_ids": ["CLI-REC-INCOMPLETE"],
                            "vehicle_ids": [],
                            "valor_servico": 0,
                        },
                        {
                            "event_id": "EVT-REC-OS",
                            "title": "Locação com rota pronta",
                            "event_date": tomorrow.isoformat(),
                            "event_end_date": tomorrow.isoformat(),
                            "status": "confirmado",
                            "client_ids": ["CLI-REC-READY"],
                            "vehicle_ids": ["VEI-REC"],
                            "responsible": "Operação",
                            "notes": "Acesso pela portaria lateral.",
                            "valor_servico": 1400,
                            "last_route_generated_at": f"{today.isoformat()}T08:00:00",
                        },
                        {
                            "event_id": "EVT-REC-DONE",
                            "title": "Locação Concluída Sem Pagamento",
                            "event_date": yesterday.isoformat(),
                            "event_end_date": yesterday.isoformat(),
                            "status": "concluido",
                            "client_ids": ["CLI-REC-READY"],
                            "vehicle_ids": ["VEI-REC"],
                            "responsible": "Operação",
                            "notes": "Concluída para cobrança.",
                            "valor_servico": 1500,
                        },
                        {
                            "event_id": "EVT-REC-PAID",
                            "title": "Locação Paga",
                            "event_date": yesterday.isoformat(),
                            "event_end_date": yesterday.isoformat(),
                            "status": "pago",
                            "client_ids": ["CLI-REC-READY"],
                            "vehicle_ids": ["VEI-REC"],
                            "responsible": "Operação",
                            "notes": "Pagamento já registrado.",
                            "valor_servico": 900,
                        },
                        {
                            "event_id": "EVT-REC-OLD",
                            "title": "Locação Antiga",
                            "event_date": old_day.isoformat(),
                            "event_end_date": old_day.isoformat(),
                            "status": "finalizado",
                            "client_ids": ["CLI-REC-INACTIVE"],
                            "vehicle_ids": [],
                            "responsible": "Operação",
                            "valor_servico": 600,
                        },
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            VEHICLES_PATH.write_text(
                json.dumps(
                    [
                        {
                            "vehicle_id": "VEI-REC",
                            "vehicle_type": "Caminhão",
                            "plate": "REC1A23",
                            "driver": "Motorista Recomendação",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            FINANCIAL_RECEIVABLES_PATH.write_text(
                json.dumps(
                    [
                        {
                            "id": "REC-OVERDUE-ACTION",
                            "client_id": "CLI-REC-INCOMPLETE",
                            "client_name": "Cliente Recomendação",
                            "event_id": "EVT-REC-INCOMPLETE",
                            "amount": 900,
                            "amount_received": 0,
                            "due_date": yesterday.isoformat(),
                            "status": "vencido",
                        },
                        {
                            "id": "REC-DUE-SOON-ACTION",
                            "client_id": "CLI-REC-READY",
                            "client_name": "Cliente Operação Pronta",
                            "event_id": "EVT-REC-OS",
                            "amount": 1400,
                            "amount_received": 0,
                            "due_date": tomorrow.isoformat(),
                            "status": "aguardando",
                        },
                        {
                            "id": "REC-PAID-ACTION",
                            "client_id": "CLI-REC-READY",
                            "client_name": "Cliente Operação Pronta",
                            "event_id": "EVT-REC-PAID",
                            "amount": 900,
                            "amount_received": 900,
                            "due_date": yesterday.isoformat(),
                            "status": "pago",
                        },
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            AUDIT_LOG_PATH.write_text("[]\n", encoding="utf-8")
            CONTRACTS_PATH.write_text("[]\n", encoding="utf-8")
            SERVICE_LOG_PATH.write_text("[]\n", encoding="utf-8")
            QUOTES_PATH.write_text("[]\n", encoding="utf-8")
            ROUTE_HISTORY_PATH.write_text("[]\n", encoding="utf-8")

            response = self.client.get("/")
            html = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            self.assertIn("Próxima ação recomendada", html)
            for expected in (
                "Completar endereço",
                "Adicionar equipamento",
                "Gerar rota",
                "Gerar ordem de serviço",
                "Lançar recebimento",
                "Arquivar ou finalizar",
                "Adicionar telefone",
                "Ver cobrança",
                "Abrir próxima locação",
                "Criar nova abordagem",
                "Ver cobranças vencidas",
                "Corrigir valores",
                "Conferir próximos vencimentos",
            ):
                self.assertIn(expected, html)
        finally:
            for path, content in previous_contents.items():
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(content, encoding="utf-8")

    def test_smart_client_summary_hides_financial_values_for_operational_profile(self):
        self.seed_smart_client_summary_data()
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        users.append(
            {
                "id": "USR-OP-SMART",
                "nome": "Operação Cliente",
                "email": "operacao-cliente@sannygold.local",
                "senha_hash": generate_password_hash("SenhaForte123", method="pbkdf2:sha256"),
                "status": "ativo",
                "role": "operacional",
                "must_change_password": False,
            }
        )
        USERS_PATH.write_text(json.dumps(users, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        self.client.post("/auth/logout", follow_redirects=True)
        response = self.client.post(
            "/auth/login",
            data={"email": "operacao-cliente@sannygold.local", "password": "SenhaForte123"},
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Resumo Inteligente do Cliente", html)
        self.assertIn("Financeiro protegido para perfis com permissão.", html)
        summary_start = html.index("Resumo Inteligente do Cliente")
        summary_html = html[summary_start : summary_start + 7000]
        self.assertNotIn("Valor em aberto", summary_html)
        self.assertNotIn("R$ 800,00", summary_html)
        self.assertNotIn("Enviar cobrança", summary_html)

    def test_weekly_report_pdf_is_available(self):
        response = self.client.get("/reports/weekly.pdf")
        pdf_bytes = response.get_data()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertIn(b"SannyGold - Relat", pdf_bytes)
        self.assertIn(b"Agenda da semana", pdf_bytes)

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
            "Produto principal da operação.",
            "Use um acesso por pessoa",
            "Não liberar rota com bloqueio vermelho",
            "CPF/CNPJ",
            "placa",
            "NF",
            "observações",
            "Evento avulso",
            "Contrato mensal",
            "Limpeza recorrente",
            "Despacho com PDF",
            "action-only-filter",
            "applyActionOnlyFilter",
            "smart-template-button",
            "Modelo de cobrança sugerido",
            "js-complete-missing",
            "js-command-search",
            "event-progress-step",
            "field-needs-attention",
            "checklist-motion-label",
            "updateQuickReview",
            "updateEventReview",
            "applyCommandSearch",
            "motion-ready",
            "surfaceEnter",
            "toastSlideIn",
            "section-loading",
            "page-is-loading",
            "filter-just-matched",
            "initSubmitFeedback",
            "initKanbanMotion",
            "showMotionToast",
            "draggable=\"true\"",
            "kanban-card",
            "kanban-dropzone",
            "prefers-reduced-motion",
            "next-action-floating",
            "O que faço agora?",
            "Cadastro guiado em 5 passos",
            "Avisos antes de salvar",
            "Pacote pronto para PDF/impresso",
            "event-save-warning-panel",
            "client-save-warning-panel",
            "equipment-save-warning-panel",
            "warehouse-save-warning-panel",
            "renderSaveWarnings",
            "initGuidedFormValidation",
            "js-search-example",
            "Cliente fixo mensal",
            "Banheiro químico",
            "Material extra",
            "Ordem de serviço",
            "Como alimentar o assistente",
        ):
            self.assertIn(expected, html)
        self.assertNotIn("Agrupamento por status dos eventos", html)
        self.assertNotIn("Agrupamento por status do almoxarifado", html)

    def test_form_fill_help_is_rendered_for_core_forms(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for expected in (
            "Ajuda de Preenchimento",
            "field-fill-help",
            "Informe rua, número, bairro, cidade e ponto de referência.",
            "Esse endereço será usado para gerar rota e ordem de serviço.",
            "Informe o valor combinado com o cliente. Esse valor entra na previsão financeira.",
            "Use para informar acesso difícil, horário de chegada, contato no local ou exigência especial.",
            "Antes de gerar a ordem de serviço ou PDF",
            "Escolha o evento antes de gerar a rota para usar os clientes, endereços e veículos certos.",
            "Defina o vencimento para aparecer em atrasos e próximos 7 dias.",
            "Sem telefone, operação e cobrança ficam sem contato rápido.",
            "Obrigatório",
            "Opcional",
            "Rota/PDF",
            "Financeiro",
        ):
            self.assertIn(expected, html)

    def test_duplicate_event_controls_are_rendered(self):
        paths = [CLIENTS_PATH, EVENTS_PATH, VEHICLES_PATH]
        previous_contents = {
            path: path.read_text(encoding="utf-8") if path.exists() else None
            for path in paths
        }
        try:
            CLIENTS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "client_id": "CLI-DUP",
                            "customer_name": "Cliente Recorrente",
                            "phone": "(21) 99999-0000",
                            "address": "Rua do Evento, 100 - Centro",
                            "equipment_type": "Banheiro Químico",
                            "equipment_quantity": "2",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            EVENTS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "event_id": "EVT-DUP",
                            "title": "Locação recorrente",
                            "event_category": "locacao",
                            "event_date": "2026-05-20",
                            "event_end_date": "2026-05-20",
                            "status": "finalizado",
                            "client_ids": ["CLI-DUP"],
                            "vehicle_ids": ["VEI-DUP"],
                            "responsible": "Operação",
                            "notes": "Acesso pela lateral.",
                            "valor_servico": 900,
                            "last_route_generated_at": "2026-05-20T09:00:00",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            VEHICLES_PATH.write_text(
                json.dumps(
                    [
                        {
                            "vehicle_id": "VEI-DUP",
                            "vehicle_type": "Caminhão",
                            "plate": "DUP1A23",
                            "driver": "Motorista",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            response = self.client.get("/")
            html = response.get_data(as_text=True)

            self.assertIn("Duplicar locação", html)
            self.assertIn("duplicate-event-button", html)
            self.assertIn("duplicated_from_event_id", html)
            self.assertIn("Revise data, endereço, quantidade e valor antes de salvar.", html)
            self.assertIn("Salvar nova locação duplicada", html)
            self.assertIn("não são copiados", html)
        finally:
            for path, content in previous_contents.items():
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(content, encoding="utf-8")

    def test_event_statuses_are_standardized_and_show_next_step(self):
        paths = [CLIENTS_PATH, EVENTS_PATH, VEHICLES_PATH, AUDIT_LOG_PATH]
        previous_contents = {
            path: path.read_text(encoding="utf-8") if path.exists() else None
            for path in paths
        }
        try:
            CLIENTS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "client_id": "CLI-STATUS",
                            "customer_name": "Cliente Status",
                            "phone": "(21) 98888-7777",
                            "address": "Rua Status, 100 - Centro, Niterói - RJ",
                            "lat": -22.9,
                            "lng": -43.1,
                            "equipment_type": "Banheiro Químico",
                            "equipment_quantity": "2",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            EVENTS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "event_id": "EVT-OLD",
                            "title": "Pedido antigo",
                            "event_date": "2026-05-26",
                            "event_end_date": "2026-05-26",
                            "status": "orcamento",
                            "client_ids": ["CLI-STATUS"],
                            "vehicle_ids": [],
                            "responsible": "Operação",
                            "valor_servico": 500,
                            "checklist": [],
                        },
                        {
                            "event_id": "EVT-MISS",
                            "title": "Evento sem dados",
                            "event_date": "2026-05-27",
                            "event_end_date": "2026-05-27",
                            "status": "confirmado",
                            "client_ids": [],
                            "vehicle_ids": [],
                            "responsible": "",
                            "checklist": [],
                        },
                        {
                            "event_id": "EVT-ROUTE",
                            "title": "Evento com rota pendente",
                            "event_date": "2026-05-28",
                            "event_end_date": "2026-05-28",
                            "status": "confirmado",
                            "client_ids": ["CLI-STATUS"],
                            "vehicle_ids": ["VEI-STATUS"],
                            "responsible": "Operação",
                            "valor_servico": 800,
                            "checklist": [],
                        },
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            VEHICLES_PATH.write_text(
                json.dumps(
                    [
                        {
                            "vehicle_id": "VEI-STATUS",
                            "vehicle_type": "Caminhão",
                            "plate": "STD1A23",
                            "driver": "Motorista Status",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            AUDIT_LOG_PATH.write_text("[]\n", encoding="utf-8")

            response = self.client.get("/")
            html = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            for label in (
                "Rascunho",
                "Confirmado",
                "Pendente de dados",
                "Rota pendente",
                "OS pendente",
                "Programado",
                "Em andamento",
                "Concluído",
                "Aguardando pagamento",
                "Pago",
                "Cancelado",
            ):
                self.assertIn(label, html)
            self.assertIn("Pedido antigo", html)
            self.assertIn("status Rascunho", html)
            self.assertIn("Evento sem dados", html)
            self.assertIn("Complete cliente, endereço, serviço e quantidade.", html)
            self.assertIn("Evento com rota pendente", html)
            self.assertIn("Gerar rota", html)
            self.assertIn("Próximo passo:", html)
        finally:
            for path, content in previous_contents.items():
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(content, encoding="utf-8")

    def test_operational_visual_agenda_groups_events_and_filters(self):
        paths = [CLIENTS_PATH, EVENTS_PATH, VEHICLES_PATH, AUDIT_LOG_PATH]
        previous_contents = {
            path: path.read_text(encoding="utf-8") if path.exists() else None
            for path in paths
        }
        today = date.today()
        try:
            CLIENTS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "client_id": "CLI-AGENDA",
                            "customer_name": "Cliente Agenda",
                            "phone": "(21) 99999-2026",
                            "address": "Rua da Praia, 100, Centro, Niterói - RJ",
                            "equipment_type": "Banheiro Químico",
                            "equipment_quantity": "3",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            EVENTS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "event_id": "EVT-AGENDA",
                            "title": "Locação da agenda",
                            "event_category": "locacao",
                            "event_date": today.isoformat(),
                            "event_end_date": today.isoformat(),
                            "status": "confirmado",
                            "client_ids": ["CLI-AGENDA"],
                            "vehicle_ids": ["VEI-AGENDA"],
                            "responsible": "Operação Agenda",
                            "notes": "Entregar antes das 8h.",
                            "valor_servico": 1800,
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            VEHICLES_PATH.write_text(
                json.dumps(
                    [
                        {
                            "vehicle_id": "VEI-AGENDA",
                            "vehicle_type": "Caminhão",
                            "plate": "AGE1D24",
                            "driver": "Motorista Agenda",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            response = self.client.get("/")
            html = response.get_data(as_text=True)

            self.assertIn("Agenda operacional visual", html)
            self.assertIn("Locações por hoje, semana, mês e próximos dias", html)
            for label in ("Hoje", "Semana", "Mês", "Próximos 7 dias", "Próximos 30 dias"):
                self.assertIn(label, html)
            for filter_id in (
                "operational-agenda-search",
                "operational-agenda-status-filter",
                "operational-agenda-service-filter",
                "operational-agenda-responsible-filter",
                "operational-agenda-client-filter",
                "operational-agenda-region-filter",
                "operational-agenda-pending-filter",
            ):
                self.assertIn(filter_id, html)
            self.assertIn("Cliente Agenda", html)
            self.assertIn("Banheiro Químico", html)
            self.assertIn("Operação Agenda", html)
            self.assertIn("Centro / Niterói", html)
            self.assertIn("rota ainda não gerada", html)
            self.assertIn("ordem de serviço não gerada", html)
            self.assertIn("Abrir detalhes", html)
            self.assertIn('data-filter-target=".operational-agenda-item"', html)
            self.assertIn('data-pending="com_pendencia"', html)
        finally:
            for path, content in previous_contents.items():
                if content is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(content, encoding="utf-8")

    def test_global_search_groups_main_operational_records(self):
        paths = [
            CLIENTS_PATH,
            EVENTS_PATH,
            VEHICLES_PATH,
            EQUIPMENT_PATH,
            FINANCIAL_RECEIVABLES_PATH,
            ROUTE_HISTORY_PATH,
            AUDIT_LOG_PATH,
            WAREHOUSE_ITEMS_PATH,
            WAREHOUSE_MOVEMENTS_PATH,
            ATTACHMENTS_PATH,
        ]
        previous_contents = {
            path: path.read_text(encoding="utf-8") if path.exists() else None
            for path in paths
        }
        today = date.today()
        try:
            CLIENTS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "client_id": "CLI-SEARCH",
                            "customer_name": "Igreja São Pedro",
                            "contact_name": "Marina Souza",
                            "phone": "(21) 98888-1234",
                            "cpf_cnpj": "12.345.678/0001-90",
                            "email": "contato@saopedro.local",
                            "address": "Rua das Flores, 123",
                            "equipment_type": "Banheiro Químico",
                            "client_type": "avulso",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            EVENTS_PATH.write_text(
                json.dumps(
                    [
                        {
                            "event_id": "EVT-SEARCH",
                            "title": "Casamento Jardim",
                            "event_category": "locacao",
                            "event_date": today.isoformat(),
                            "event_end_date": today.isoformat(),
                            "status": "confirmado",
                            "client_ids": ["CLI-SEARCH"],
                            "vehicle_ids": ["VEI-SEARCH"],
                            "responsible": "Carlos Motorista",
                            "notes": "Entrega na Rua das Flores, 123 pela portaria lateral.",
                            "valor_servico": 1500,
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            VEHICLES_PATH.write_text(
                json.dumps(
                    [
                        {
                            "vehicle_id": "VEI-SEARCH",
                            "vehicle_type": "Caminhão",
                            "plate": "ABC1D23",
                            "driver": "Carlos Motorista",
                            "model": "Delivery",
                            "status": "disponível",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            EQUIPMENT_PATH.write_text(
                json.dumps(
                    [
                        {
                            "equipment_id": "EQ-SEARCH",
                            "equipment_type": "Banheiro PNE",
                            "plate": "PNE-44",
                            "status": "reservado",
                            "linked_client_name": "Igreja São Pedro",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            FINANCIAL_RECEIVABLES_PATH.write_text(
                json.dumps(
                    [
                        {
                            "id": "REC-SEARCH",
                            "client_id": "CLI-SEARCH",
                            "client_name": "Igreja São Pedro",
                            "client_phone": "(21) 98888-1234",
                            "event_id": "EVT-SEARCH",
                            "event_title": "Casamento Jardim",
                            "service_type": "Banheiro Químico",
                            "invoice_number": "NF-SEARCH",
                            "payment_method": "PIX",
                            "amount": 1500,
                            "amount_received": 0,
                            "due_date": today.isoformat(),
                            "status": "em_aberto",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            ROUTE_HISTORY_PATH.write_text(
                json.dumps(
                    [
                        {
                            "generated_at": f"{today.isoformat()}T08:00:00",
                            "event_id": "EVT-SEARCH",
                            "event_title": "Casamento Jardim",
                            "event_date": today.isoformat(),
                            "client_ids": ["CLI-SEARCH"],
                            "vehicle_ids": ["VEI-SEARCH"],
                            "financial_summary": {
                                "status": "estimado",
                                "profit_total": 800,
                                "revenue_total": 1500,
                                "operational_total": 700,
                                "margin_pct": 53,
                            },
                            "financial_events": [
                                {
                                    "client_id": "CLI-SEARCH",
                                    "client_name": "Igreja São Pedro",
                                    "address": "Rua das Flores, 123",
                                    "service_type": "Banheiro Químico",
                                }
                            ],
                            "equipment_in_route": [
                                {
                                    "equipment_id": "EQ-SEARCH",
                                    "equipment_type": "Banheiro PNE",
                                    "vehicle_id": "VEI-SEARCH",
                                    "client_name": "Igreja São Pedro",
                                }
                            ],
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            AUDIT_LOG_PATH.write_text(
                json.dumps(
                    [
                        {
                            "created_at": f"{today.isoformat()}T09:00:00",
                            "user": "Administrador SannyGold",
                            "action": "generate_service_order",
                            "module": "events",
                            "target_id": "EVT-SEARCH",
                            "detail": "Ordem de serviço/PDF gerada.",
                        }
                    ],
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            WAREHOUSE_ITEMS_PATH.write_text("[]\n", encoding="utf-8")
            WAREHOUSE_MOVEMENTS_PATH.write_text("[]\n", encoding="utf-8")
            ATTACHMENTS_PATH.write_text("[]\n", encoding="utf-8")

            response = self.client.get("/")
            html = response.get_data(as_text=True)

            self.assertEqual(response.status_code, 200)
            for expected in (
                "Clientes",
                "Eventos/Locações",
                "Equipamentos",
                "Rotas/Ordens de Serviço",
                "Financeiro",
                "Igreja São Pedro",
                "988881234",
                "12345678000190",
                "Casamento Jardim",
                "Rua das Flores, 123",
                "Banheiro PNE",
                "ABC1D23",
                "Carlos Motorista",
                "Rota • Casamento Jardim",
                "OS • Casamento Jardim",
                "REC-SEARCH",
                'data-module="clientes"',
                'data-module="eventos"',
                'data-module="equipamentos"',
                'data-module="rotas_os"',
                'data-module="financeiro"',
                "Abrir",
            ):
                self.assertIn(expected, html)
        finally:
            for path, content in previous_contents.items():
                if content is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.write_text(content, encoding="utf-8")

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
        self.assertNotIn("Painel financeiro gerencial", html)
        self.assertNotIn("Receita do mês", html)
        self.assertIn("Financeiro protegido", html)
        self.assertIn("Movimentar estoque", html)
        self.assertIn("Almoxarifado", html)

    def test_mobile_control_center_exposes_all_core_functions(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("mobile-control-center", html)
        self.assertIn("mobile-action-grid", html)
        self.assertIn("Central de impressão e links", html)
        self.assertIn("Pacote PDF/impresso", html)
        self.assertIn("material impresso, PDF e links de endereço", html)
        self.assertIn("mobile-quick-observation", html)
        self.assertIn("Lançar observação rápida", html)
        self.assertIn("Salvar observação", html)
        self.assertIn("@media (max-width: 420px)", html)
        self.assertIn(".operational-agenda-main .btn", html)
        self.assertIn(".event-list-item > .d-flex", html)
        self.assertIn(".equipment-list-item", html)
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
        self.assertIn("Motorista habitual", html)
        self.assertNotIn("Modo offline", html)
        self.assertNotIn("Sincronização atual", html)

    def test_simplified_navigation_and_modes_are_rendered(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("work-mode compact-density compact-hide-archived smart-forms-enabled simple-mode", html)
        self.assertIn('id="primary-simple-shell"', html)
        self.assertIn('id="primary-simple-nav"', html)
        self.assertIn('data-navigation-limit="9"', html)
        self.assertEqual(html.count('class="primary-nav-link'), 9)
        for label in (
            "Central do Dia",
            "Clientes",
            "Eventos",
            "Equipamentos",
            "Frota",
            "Financeiro",
            "Estoque",
            "Relatórios",
            "Administração",
        ):
            self.assertIn(label, html)
        self.assertIn('id="simple-mode-toggle"', html)
        self.assertIn('id="advanced-mode-toggle"', html)
        self.assertIn("sannygold-ui-mode-v1", html)
        self.assertIn("syncUiModePreference", html)
        self.assertIn("setUiModePreference", html)
        self.assertIn('id="simple-actions-panel"', html)
        self.assertIn('id="advanced-actions-panel"', html)
        for label in ("Cadastrar cliente", "Cadastrar evento", "Gerar rota", "Gerar OS", "Registrar recebimento", "Movimentar estoque"):
            self.assertIn(label, html)
        for label in ("Auditoria", "Backup", "Configurações", "Diagnósticos", "Acesso pelo Celular", "Homologação", "Usuários"):
            self.assertIn(label, html)
        self.assertIn('class="quick-actions-bar advanced-only"', html)
        self.assertIn('class="compact-system-panel advanced-only', html)
        self.assertIn('class="nav nav-tabs ops-tabs-nav advanced-only', html)
        self.assertIn("simple-mode .advanced-only", html)
        self.assertIn("advanced-mode .simple-only", html)

    def test_quick_observation_is_saved_to_audit_log(self):
        response = self.client.post(
            "/observations/quick",
            data={
                "area": "Rota",
                "reference": "EVT-CELULAR",
                "note": "Acesso pela portaria lateral em Niterói/RJ.",
            },
            follow_redirects=True,
        )
        audit = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
        entries = [item for item in audit if item.get("action") == "quick_observation" and item.get("module") == "observations"]

        self.assertEqual(response.status_code, 200)
        self.assertTrue(entries)
        self.assertIn("EVT-CELULAR", entries[0]["detail"])
        self.assertEqual(entries[0]["after"]["note"], "Acesso pela portaria lateral em Niterói/RJ.")
        self.assertIn("Observação rápida registrada", response.get_data(as_text=True))

    def test_compact_system_usage_features_are_rendered(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("work-mode compact-density", html)
        self.assertIn('id="compact-system-panel"', html)
        self.assertIn("Uso rápido do sistema", html)
        self.assertIn("menu por áreas", html.lower())
        self.assertIn("Modo ultra compacto por função", html)
        self.assertIn('id="ultra-compact-toggle"', html)
        self.assertIn("js-ultra-compact-toggle", html)
        self.assertIn("ultra-compact-mode", html)
        self.assertIn("syncUltraCompactPreference", html)
        self.assertIn('id="compact-area-menu"', html)
        self.assertIn("Menu principal", html)
        self.assertIn('id="current-navigation-label"', html)
        for label in ("Hoje", "Operação", "Financeiro", "Gestão", "Ajuda"):
            self.assertIn(label, html)
        for label in ("Central do Dia", "Pendências", "Agenda dos próximos 7 dias", "Locação Rápida", "Eventos/Locações", "Ordens de Serviço", "Painel Financeiro", "Backups", "Treinamento", "Dúvidas frequentes"):
            self.assertIn(label, html)
        for label in ("Banheiros", "Clientes", "Estoque", "Relatórios", "Acessos"):
            self.assertIn(label, html)
        self.assertIn("Busca única", html)
        self.assertIn("cliente, evento, banheiro/equipamento, placa, cobrança, orçamento, material e NF", html)
        self.assertIn('id="quick-command-center"', html)
        self.assertIn("Comando rápido", html)
        self.assertIn('id="quick-command-input"', html)
        self.assertIn("js-quick-command", html)
        self.assertIn("executeQuickCommand", html)
        self.assertIn("updateQuickCommandResults", html)
        self.assertIn('id="role-screen-panel"', html)
        self.assertIn("Tela por função", html)
        self.assertIn('id="batch-action-panel"', html)
        self.assertIn("Ações em lote", html)
        self.assertIn("js-batch-select", html)
        self.assertIn("performBatchAction", html)
        self.assertIn('id="dense-list-toggle"', html)
        self.assertIn('id="archive-visibility-toggle"', html)
        self.assertIn('id="smart-form-toggle"', html)
        self.assertIn("dense-list-mode", html)
        self.assertIn("compact-hide-archived", html)
        self.assertIn("smart-forms-enabled", html)
        self.assertIn("Campos essenciais primeiro", html)
        self.assertIn("Mais opções", html)
        self.assertIn("PDF/impresso", html)
        self.assertIn('id="day-focus-panel"', html)
        self.assertIn("Modo foco do dia", html)
        self.assertIn("Só o que precisa de ação agora", html)
        self.assertIn('id="priority-menu-panel"', html)
        self.assertIn("Menu por prioridade", html)
        self.assertIn("Primeiro resolver", html)
        self.assertIn('id="quick-edit-drawer"', html)
        self.assertIn("Edição rápida lateral", html)
        self.assertIn("Editar banheiro/equipamento", html)
        self.assertIn("Novo orçamento", html)
        self.assertIn("Painel rápido", html)
        self.assertIn('id="quick-edit-drawer-toggle"', html)
        self.assertIn('id="compact-strong-toggle"', html)
        self.assertIn('id="copy-density-toggle"', html)
        self.assertIn('id="compact-collapse-toggle"', html)
        self.assertIn("compact-strong-mode", html)
        self.assertIn("copy-minimal-mode", html)
        self.assertIn("compact-collapsed-panels", html)
        self.assertIn("day-focus-active", html)
        self.assertIn("quickDrawerSlideIn", html)
        self.assertIn("rowUpdatePulse", html)
        self.assertIn("dayFocusGlow", html)
        self.assertIn("js-quick-drawer-action", html)
        self.assertIn("updateStickySearchCount", html)
        self.assertIn("setQuickDrawerOpen", html)
        self.assertIn('id="compact-list-filters"', html)
        self.assertIn("js-compact-filter", html)
        self.assertIn('id="compact-list-toggle"', html)
        self.assertIn('id="compact-density-toggle"', html)
        self.assertIn("Detalhes avançados do cliente", html)
        self.assertIn("Mais campos de cobrança e rota", html)
        self.assertIn("Mais campos do evento", html)
        self.assertIn('id="equipment-family-filter"', html)
        self.assertIn('data-filter-attribute="family"', html)

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

    def test_user_manual_pdf_was_replaced_by_assistant(self):
        response = self.client.get("/manual/sannygold-equipe.pdf")
        dashboard = self.client.get("/")
        html = dashboard.get_data(as_text=True)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Assistente Operacional", html)
        self.assertIn("Abrir assistente", html)
        self.assertNotIn("Manual PDF", html)

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
        CLIENTS_PATH.write_text("[]\n", encoding="utf-8")
        EVENTS_PATH.write_text("[]\n", encoding="utf-8")
        CONTRACTS_PATH.write_text("[]\n", encoding="utf-8")
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
                "service_type": "banheiro_quimico",
                "equipment_type": "Banheiro Químico",
                "equipment_quantity": "2",
                "billing_model": "mensal",
                "cleaning_frequency": "semanal",
                "event_date": "2026-04-25",
                "event_end_date": "2026-04-26",
                "service_value": "2500",
                "responsible": "Operação SannyGold",
                "notes": "Entrada pela portaria principal.",
                "review_confirmed": "true",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        clients = json.loads(CLIENTS_PATH.read_text(encoding="utf-8"))
        events = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
        contracts = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("quick-rental-summary-panel", html)
        self.assertIn("Gerar ordem de serviço", html)
        self.assertIn("Gerar rota", html)
        self.assertIn("Lançar cobrança", html)
        self.assertIn("Voltar para Central do Dia", html)
        self.assertTrue(any(item["customer_name"] == "Locação Rápida" for item in clients))
        quick_client = next(item for item in clients if item["customer_name"] == "Locação Rápida")
        self.assertTrue(any(quick_client["client_id"] in item["client_ids"] for item in events))
        self.assertTrue(any(item["client_id"] == quick_client["client_id"] and item["monthly_value"] == 2500 for item in contracts))

    def test_quick_rental_blocks_missing_required_fields(self):
        CLIENTS_PATH.write_text("[]\n", encoding="utf-8")
        EVENTS_PATH.write_text("[]\n", encoding="utf-8")

        response = self.client.post(
            "/quick-rental",
            data={
                "customer_name": "Locação Incompleta",
                "service_type": "banheiro_quimico",
                "equipment_quantity": "1",
                "service_value": "1000",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)
        clients = json.loads(CLIENTS_PATH.read_text(encoding="utf-8"))
        events = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("Preencha os campos obrigatórios da locação rápida", html)
        self.assertIn("telefone/WhatsApp", html)
        self.assertIn("data do evento/serviço", html)
        self.assertIn("endereço completo", html)
        self.assertIn("responsável interno", html)
        self.assertIn("observações operacionais", html)
        self.assertEqual(clients, [])
        self.assertEqual(events, [])

    def test_quick_rental_reuses_existing_client_data(self):
        CLIENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "client_id": "CLI-RAPIDA",
                        "customer_name": "Cliente Já Cadastrado",
                        "contact_name": "Marta",
                        "phone": "(21) 97777-0000",
                        "address": "Estrada Bento Pestana, 932 - Baldeador, Niterói - RJ",
                        "lat": -22.8753396,
                        "lng": -43.068074,
                        "client_type": "avulso",
                        "equipment_type": "Trailer Especial",
                        "equipment_quantity": 1,
                        "equipment_number": "",
                        "billing_model": "avulso",
                        "cleaning_frequency": "nao_aplica",
                        "service_profile": "evento_avulso",
                        "default_service_minutes": 20,
                        "default_priority": 3,
                        "window_start": "08:00",
                        "window_end": "18:00",
                        "locked_vehicle_id": "",
                        "service_value": 1800,
                        "team_cost": 0,
                        "equipment_cost": 0,
                        "invoice_status": "sem_nota",
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        EVENTS_PATH.write_text("[]\n", encoding="utf-8")

        response = self.client.post(
            "/quick-rental",
            data={
                "client_id": "CLI-RAPIDA",
                "event_date": "2026-04-27",
                "service_type": "trailer_luxo",
                "equipment_quantity": "1",
                "service_value": "1800",
                "responsible": "Thiago",
                "notes": "Cliente reaproveitado pelo fluxo rápido.",
                "review_confirmed": "true",
            },
            follow_redirects=True,
        )
        clients = json.loads(CLIENTS_PATH.read_text(encoding="utf-8"))
        events = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0]["client_id"], "CLI-RAPIDA")
        self.assertEqual(clients[0]["phone"], "(21) 97777-0000")
        self.assertTrue(any(item["client_ids"] == ["CLI-RAPIDA"] for item in events))

    def test_attachment_and_service_order_workflows(self):
        SERVICE_ORDERS_PATH.write_text("[]\n", encoding="utf-8")
        self.client.post(
            "/clients",
            data={
                "client_id": "CLI-OS",
                "customer_name": "Cliente OS",
                "phone": "(21) 99999-1111",
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
                "responsible": "Operação SannyGold",
                "notes": "Entrada pela portaria principal.",
                "valor_servico": "1200",
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
        mobile_response = self.client.get("/events/EVT-OS/service-order")
        attachments = json.loads(ATTACHMENTS_PATH.read_text(encoding="utf-8"))
        service_orders = json.loads(SERVICE_ORDERS_PATH.read_text(encoding="utf-8"))

        self.assertIn("Anexo salvo.", attachment_response.get_data(as_text=True))
        self.assertEqual(attachments[0]["title"], "Autorização")
        self.assertEqual(os_response.status_code, 200)
        self.assertIn(b"SannyGold - Ordem de Servi", os_response.get_data())
        self.assertEqual(mobile_response.status_code, 200)
        self.assertIn("OS Mobile OS-EVT-OS", mobile_response.get_data(as_text=True))
        self.assertIn("Copiar resumo para WhatsApp", mobile_response.get_data(as_text=True))
        self.assertIn("Histórico de alterações", mobile_response.get_data(as_text=True))
        self.assertEqual(service_orders[0]["event_id"], "EVT-OS")
        self.assertEqual(service_orders[0]["status"], "liberada")
        self.assertIn("Checklist de saída", os_response.get_data().decode("latin-1", errors="ignore"))
        self.assertIn("saida_base", service_orders[0]["confirmations"])

    def test_complete_service_order_flow_tracks_status_confirmations_and_history(self):
        SERVICE_ORDERS_PATH.write_text("[]\n", encoding="utf-8")
        CLIENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "client_id": "CLI-OS-FULL",
                        "customer_name": "Cliente OS Completa",
                        "phone": "(21) 98888-0000",
                        "email": "cliente@example.com",
                        "address": "Estrada Bento Pestana, 932 - Baldeador, Niterói - RJ",
                        "lat": "-22.8753396",
                        "lng": "-43.068074",
                        "equipment_type": "Banheiro Luxo",
                        "equipment_quantity": 2,
                        "equipment_number": "EQ-OS-001",
                        "window_start": "08:00",
                        "window_end": "12:00",
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        VEHICLES_PATH.write_text(
            json.dumps(
                [
                    {
                        "vehicle_id": "VEI-OS-001",
                        "vehicle_type": "Van",
                        "plate": "ABC1D23",
                        "driver": "Equipe OS",
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        EQUIPMENT_PATH.write_text(
            json.dumps(
                [
                    {
                        "equipment_id": "EQ-OS-001",
                        "equipment_type": "Banheiro Luxo",
                        "plate": "EQP-123",
                        "status": "reservado",
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        EVENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "event_id": "EVT-OS-FULL",
                        "title": "Evento OS Completa",
                        "event_date": "2026-06-10",
                        "event_end_date": "2026-06-10",
                        "status": "confirmado",
                        "client_ids": ["CLI-OS-FULL"],
                        "vehicle_ids": ["VEI-OS-001"],
                        "responsible": "Responsável OS",
                        "notes": "Montagem perto da entrada principal.",
                        "valor_servico": 2500,
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        pdf_response = self.client.get("/events/EVT-OS-FULL/service-order.pdf")
        home_response = self.client.get("/")
        for step in ("saida_base", "chegada_local", "instalacao_concluida", "retirada_concluida", "retorno_base"):
            confirm_response = self.client.post(
                "/events/EVT-OS-FULL/service-order/confirm",
                data={"step": step},
                follow_redirects=True,
            )
            self.assertEqual(confirm_response.status_code, 200)
        cancel_response = self.client.post(
            "/events/EVT-OS-FULL/service-order/status",
            data={"status": "cancelada"},
            follow_redirects=True,
        )
        orders = json.loads(SERVICE_ORDERS_PATH.read_text(encoding="utf-8"))
        order = next(item for item in orders if item["event_id"] == "EVT-OS-FULL")
        pdf_text = pdf_response.get_data().decode("latin-1", errors="ignore")
        html = home_response.get_data(as_text=True)

        self.assertEqual(pdf_response.status_code, 200)
        self.assertIn("Checklist de saída", pdf_text)
        self.assertIn("Checklist de retorno", pdf_text)
        self.assertIn("Histórico de alterações da OS", pdf_text)
        self.assertIn("Link do mapa", pdf_text)
        self.assertIn("OS mobile", html)
        self.assertIn("Copiar resumo para WhatsApp", html)
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(order["status"], "cancelada")
        self.assertTrue(all(order["confirmations"][step]["confirmed_at"] for step in ("saida_base", "chegada_local", "instalacao_concluida", "retirada_concluida", "retorno_base")))
        self.assertGreaterEqual(len(order["history"]), 7)

    def test_generation_blocks_route_with_incomplete_client_data(self):
        CLIENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "client_id": "CLI-BLOCK",
                        "customer_name": "Cliente Sem Endereço",
                        "phone": "",
                        "address": "",
                        "lat": None,
                        "lng": None,
                        "client_type": "avulso",
                        "equipment_type": "Banheiro Luxo",
                        "equipment_quantity": 1,
                        "equipment_number": "",
                        "default_service_minutes": 20,
                        "default_priority": 3,
                        "window_start": "08:00",
                        "window_end": "18:00",
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        VEHICLES_PATH.write_text(
            json.dumps(
                [
                    {
                        "vehicle_id": "VEI-BLOCK",
                        "vehicle_type": "Van",
                        "plate": "ABC1D23",
                        "model": "Sprinter",
                        "capacity": 4,
                        "max_stops": 8,
                        "max_minutes": 540,
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        EVENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "event_id": "EVT-BLOCK",
                        "title": "Evento Bloqueado",
                        "event_date": "2026-05-25",
                        "event_end_date": "2026-05-25",
                        "status": "confirmado",
                        "client_ids": ["CLI-BLOCK"],
                        "vehicle_ids": ["VEI-BLOCK"],
                        "responsible": "Operação",
                        "notes": "Separar equipamento.",
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        response = self.client.post("/generate", data={"event_id": "EVT-BLOCK"}, follow_redirects=True)
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Rota bloqueada por dados incompletos", html)
        self.assertIn("Cliente sem telefone", html)
        self.assertIn("Endereço incompleto", html)
        self.assertIn("Cliente não possui equipamento vinculado.", html)
        self.assertIn("Editar cliente", html)

    def test_generation_allows_complete_route_after_required_checklist(self):
        CLIENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "client_id": "CLI-OK",
                        "customer_name": "Cliente Completo",
                        "phone": "(21) 99999-2222",
                        "address": "Estrada Bento Pestana, 932 - Baldeador, Niterói - RJ",
                        "lat": -22.8753396,
                        "lng": -43.068074,
                        "client_type": "avulso",
                        "equipment_type": "Banheiro Luxo",
                        "equipment_quantity": 1,
                        "equipment_number": "EQ-OK",
                        "default_service_minutes": 20,
                        "default_priority": 3,
                        "window_start": "08:00",
                        "window_end": "18:00",
                        "service_value": 1500,
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        VEHICLES_PATH.write_text(
            json.dumps(
                [
                    {
                        "vehicle_id": "VEI-OK",
                        "vehicle_type": "Van",
                        "plate": "XYZ9A87",
                        "model": "Sprinter",
                        "capacity": 4,
                        "max_stops": 8,
                        "max_minutes": 540,
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        EQUIPMENT_PATH.write_text(
            json.dumps(
                [
                    {
                        "equipment_id": "EQ-OK",
                        "equipment_type": "Banheiro Luxo",
                        "status": "disponivel",
                        "condition": "disponivel",
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        EVENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "event_id": "EVT-OK",
                        "title": "Evento Completo",
                        "event_date": "2026-05-25",
                        "event_end_date": "2026-05-25",
                        "status": "confirmado",
                        "client_ids": ["CLI-OK"],
                        "vehicle_ids": ["VEI-OK"],
                        "responsible": "Operação",
                        "notes": "Acesso pela portaria principal.",
                        "valor_servico": 1500,
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        response = self.client.post("/generate", data={"event_id": "EVT-OK"}, follow_redirects=True)
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Rotas geradas com sucesso.", html)
        self.assertIn("EVT-OK", html)

    def test_service_order_blocks_when_client_or_service_is_missing(self):
        EVENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "event_id": "EVT-OS-BLOCK",
                        "title": "OS Sem Cliente",
                        "event_date": "2026-05-25",
                        "event_end_date": "2026-05-25",
                        "status": "confirmado",
                        "client_ids": [],
                        "vehicle_ids": [],
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        response = self.client.get("/events/EVT-OS-BLOCK/service-order.pdf", follow_redirects=True)
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Ordem de serviço bloqueada por dados incompletos", html)
        self.assertIn("Cliente não vinculado", html)
        self.assertIn("Observação operacional ausente", html)
        self.assertIn("Responsável interno ausente", html)

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
        self.assertEqual(response.mimetype, "application/zip")

        backup_files = sorted(BACKUPS_DIR.glob("sannygold-data-backup-*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
        self.assertTrue(backup_files)
        latest_backup = backup_files[0]
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        self.assertIn("last_backup_at", settings)
        self.assertEqual(settings["last_backup_file"], latest_backup.name)
        with zipfile.ZipFile(latest_backup) as archive:
            names = set(archive.namelist())
            self.assertIn("manifest.json", names)
            self.assertIn("data/clients.json", names)
            self.assertIn("data/audit_log.json", names)
            self.assertFalse(any(name.startswith("backups/") for name in names))
            self.assertFalse(any("__pycache__" in name for name in names))
            self.assertFalse(any(name.endswith(".env") or "/.env" in name for name in names))
        audit = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
        self.assertTrue(any(item["module"] == "backup" and item["action"] == "download" for item in audit))
        response.close()

    def test_admin_backup_panel_generates_and_downloads_latest_backup(self):
        page_response = self.client.get("/")
        page_html = page_response.get_data(as_text=True)

        self.assertIn("admin-backup-panel", page_html)
        self.assertIn("Backup local dos dados", page_html)
        self.assertIn("Gerar backup agora", page_html)
        self.assertIn("Baixar último backup", page_html)
        self.assertIn("Status do backup", page_html)
        self.assertIn("Tamanho", page_html)
        self.assertIn("Cópia Dropbox", page_html)
        self.assertIn("Testar pasta Dropbox", page_html)
        self.assertIn("Testar restauração", page_html)
        self.assertIn("Configure DROPBOX_BACKUP_DIR", page_html)
        self.assertIn("Retenção Dropbox", page_html)
        self.assertIn("Backup automático", page_html)
        self.assertIn("Salvar agendamento", page_html)
        self.assertIn("Próxima execução", page_html)

        response = self.client.post("/backup/generate", follow_redirects=True)
        html = response.get_data(as_text=True)
        backup_files = sorted(BACKUPS_DIR.glob("sannygold-data-backup-*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Backup gerado", html)
        self.assertTrue(backup_files)

        download_response = self.client.get("/backup/latest.zip")
        self.assertEqual(download_response.status_code, 200)
        self.assertEqual(download_response.mimetype, "application/zip")
        self.assertIn(backup_files[0].name, download_response.headers.get("Content-Disposition", ""))
        audit = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
        self.assertTrue(any(item["module"] == "backup" and item["action"] == "create" for item in audit))
        download_response.close()

    def test_admin_audit_panel_filters_critical_actions(self):
        base_client = {
            "client_id": "CLI-AUDIT",
            "customer_name": "Cliente Auditoria",
            "contact_name": "Marcos",
            "phone": "(21) 99999-1000",
            "cpf_cnpj": "00.000.000/0001-00",
            "email": "auditoria@sannygold.com",
            "invoice_status": "sem_nota",
            "client_address": "Estrada Bento Pestana, 932 - Baldeador, Niterói - RJ",
            "client_lat": "-22.8753396",
            "client_lng": "-43.068074",
            "client_type": "avulso",
            "equipment_type": "Banheiro Luxo",
            "equipment_quantity": "1",
            "equipment_number": "",
            "billing_model": "avulso",
            "cleaning_frequency": "nao_aplica",
            "service_profile": "evento_avulso",
            "default_service_minutes": "20",
            "default_priority": "3",
            "window_start": "08:00",
            "window_end": "18:00",
            "locked_vehicle_id": "",
            "service_value": "1200",
            "team_cost": "100",
            "equipment_cost": "50",
        }
        self.client.post("/clients", data=base_client, environ_base={"REMOTE_ADDR": "10.10.0.5"})
        edited_client = {**base_client, "phone": "(21) 99999-2000"}
        self.client.post("/clients", data=edited_client, environ_base={"REMOTE_ADDR": "10.10.0.5"})

        response = self.client.get("/?audit_action=save&audit_module=clients&audit_user=admin@sannygold.local")
        html = response.get_data(as_text=True)
        audit = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
        client_entries = [item for item in audit if item.get("module") == "clients" and item.get("target_id") == "CLI-AUDIT"]

        self.assertEqual(response.status_code, 200)
        self.assertIn("admin-audit-panel", html)
        self.assertIn("Auditoria operacional", html)
        self.assertIn("Cliente Auditoria", html)
        self.assertIn("Salvou", html)
        self.assertIn("Clientes", html)
        self.assertIn("10.10.0.5", html)
        self.assertIn("Ver antes/depois", html)
        self.assertTrue(any(item.get("ip_address") == "10.10.0.5" for item in client_entries))
        self.assertTrue(any(item.get("changes") for item in client_entries))

    def test_backup_retention_keeps_latest_thirty_files(self):
        for path in BACKUPS_DIR.glob("sannygold-data-backup-*.zip"):
            path.unlink()

        for _ in range(32):
            response = self.client.post("/backup/generate")
            self.assertEqual(response.status_code, 302)

        backup_files = list(BACKUPS_DIR.glob("sannygold-data-backup-*.zip"))
        self.assertEqual(len(backup_files), 30)

    def test_module_pdf_and_excel_exports_are_available(self):
        expected_pdf_titles = {
            "clients": b"SannyGold - Clientes",
            "daily": b"SannyGold - Relat",
            "weekly_events": b"SannyGold - Relat",
            "equipment": b"SannyGold - Equipamentos",
            "financial": b"SannyGold - Financeiro",
            "warehouse": None,
            "pending": b"SannyGold - Relat",
        }
        for module, expected_title in expected_pdf_titles.items():
            with self.subTest(module=module):
                pdf_response = self.client.get(f"/reports/{module}.pdf")
                excel_response = self.client.get(f"/exports/{module}.xlsx")
                pdf_bytes = pdf_response.get_data()

                self.assertEqual(pdf_response.status_code, 200)
                self.assertEqual(pdf_response.mimetype, "application/pdf")
                if module == "warehouse":
                    self.assertTrue(pdf_bytes.startswith(b"%PDF"))
                    self.assertIn(b"/FontFile2", pdf_bytes)
                    self.assertIn("sannygold-almoxarifado-", pdf_response.headers.get("Content-Disposition", ""))
                else:
                    self.assertIn(expected_title, pdf_bytes)
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
