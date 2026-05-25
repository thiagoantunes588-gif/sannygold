import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

os.environ["ROTAFLOW_STORAGE_DIR"] = tempfile.mkdtemp(prefix="sannygold-finance-test-")

from app.main import (  # noqa: E402
    AUDIT_LOG_PATH,
    CLIENTS_PATH,
    CONTRACTS_PATH,
    EVENTS_PATH,
    FINANCIAL_CLOSEOUTS_PATH,
    FINANCIAL_ENTRIES_PATH,
    FINANCIAL_RECEIVABLES_PATH,
    ROLE_PERMISSIONS,
    SETTINGS_PATH,
    USERS_PATH,
    app,
    ensure_storage_dirs,
    has_permission,
)


class FinancialManagementTest(unittest.TestCase):
    def setUp(self):
        ensure_storage_dirs()
        for path in (
            AUDIT_LOG_PATH,
            CLIENTS_PATH,
            CONTRACTS_PATH,
            EVENTS_PATH,
            FINANCIAL_CLOSEOUTS_PATH,
            FINANCIAL_ENTRIES_PATH,
            FINANCIAL_RECEIVABLES_PATH,
        ):
            path.write_text("[]\n", encoding="utf-8")
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
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.client.post(
            "/auth/login",
            data={"email": "admin@sannygold.local", "password": "Sanny123Gold"},
            follow_redirects=True,
        )

    def test_financial_dashboard_exposes_requested_sections(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for expected in (
            "Resumo financeiro por período",
            "DRE por evento",
            "Visão rápida",
            "Contas a receber",
            "Alertas de cobrança",
            "Fluxo de caixa",
            "Financeiro por cliente",
            "Inadimplência",
            "Fechamento financeiro mensal",
            "Anexo opcional",
            "Anexar comprovante quando disponível; etapa opcional.",
            "Previsão de caixa 30, 60 e 90 dias",
            "Contas a pagar hoje",
            "Hoje R$",
            "7 dias R$",
            "30 dias R$",
            "Impostos provisionados",
            "Provisão Lucro Presumido",
            "Conciliação bancária diária",
            "Aprovar pagamentos acima de R$ 1.000",
            "Gerar mensalidades",
            "DRE simples mensal",
            "Receita por serviço",
            "Notas fiscais",
            "Modelos de orçamento",
        ):
            self.assertIn(expected, html)
        self.assertIn('value="custom"', html)
        self.assertIn('name="financial_start"', html)
        self.assertIn('name="financial_end"', html)

    def test_financial_decision_panel_summarizes_managerial_items(self):
        today = datetime.now().date()
        CLIENTS_PATH.write_text(
            json.dumps(
                [
                    {"client_id": "CLI-ALFA", "customer_name": "Cliente Alfa", "phone": "21999990000", "address": "Rua Alfa"},
                    {"client_id": "CLI-BETA", "customer_name": "Cliente Beta", "phone": "21999990001", "address": "Rua Beta"},
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
                        "event_id": "EVT-SEM-VALOR",
                        "title": "Evento Sem Valor",
                        "event_date": today.isoformat(),
                        "client_ids": ["CLI-ALFA"],
                        "vehicle_ids": [],
                        "status": "confirmado",
                        "valor_servico": 0,
                    },
                    {
                        "event_id": "EVT-COM-VALOR",
                        "title": "Evento Com Valor",
                        "event_date": today.isoformat(),
                        "client_ids": ["CLI-BETA"],
                        "vehicle_ids": [],
                        "status": "confirmado",
                        "valor_servico": 900,
                        "valor_adicional": 100,
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
                        "id": "REC-001",
                        "client_id": "CLI-ALFA",
                        "client_name": "Cliente Alfa",
                        "event_title": "Contrato Alfa",
                        "amount": 1200,
                        "amount_received": 200,
                        "due_date": (today - timedelta(days=5)).isoformat(),
                        "received_date": "",
                        "status": "parcial",
                    },
                    {
                        "id": "REC-002",
                        "client_id": "CLI-BETA",
                        "client_name": "Cliente Beta",
                        "event_title": "Contrato Beta",
                        "amount": 800,
                        "amount_received": 0,
                        "due_date": (today + timedelta(days=4)).isoformat(),
                        "received_date": "",
                        "status": "aguardando",
                    },
                    {
                        "id": "REC-003",
                        "client_id": "CLI-BETA",
                        "client_name": "Cliente Beta",
                        "event_title": "Recebido Beta",
                        "amount": 500,
                        "amount_received": 500,
                        "due_date": today.isoformat(),
                        "received_date": today.isoformat(),
                        "status": "pago",
                    },
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for expected in (
            "Painel financeiro gerencial",
            "Total previsto no mês",
            "Total recebido no mês",
            "Total em aberto",
            "Total vencido",
            "Vencem em 7 dias",
            "Eventos/locações sem valor definido",
            "Evento Sem Valor",
            "Clientes com maior valor em aberto",
            "Cliente Alfa",
            "Clientes com atraso",
            "Recebimentos recentes",
            "Lançar recebimento",
            "Editar valor de evento",
            "Gerar relatório financeiro",
            "R$ 1.000,00",
            "R$ 500,00",
        ):
            self.assertIn(expected, html)

    def test_finance_can_update_event_value_from_decision_panel(self):
        today = datetime.now().date().isoformat()
        CLIENTS_PATH.write_text(
            json.dumps([{"client_id": "CLI-VALOR", "customer_name": "Cliente Valor", "phone": "21999990000", "address": "Rua Valor"}]),
            encoding="utf-8",
        )
        EVENTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "event_id": "EVT-VALOR",
                        "title": "Evento Valor",
                        "event_date": today,
                        "client_ids": ["CLI-VALOR"],
                        "vehicle_ids": [],
                        "status": "confirmado",
                        "valor_servico": 0,
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        response = self.client.post("/events/EVT-VALOR/financial", data={"valor_servico": "1750.50"}, follow_redirects=True)
        events = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))

        self.assertIn("Valor financeiro do evento atualizado.", response.get_data(as_text=True))
        self.assertEqual(events[0]["valor_servico"], 1750.5)

    def test_receivable_entry_and_optional_attachment_are_saved(self):
        response = self.client.post(
            "/financial/receivables",
            data={
                "client_name": "Cliente Financeiro",
                "client_phone": "(21) 99999-0000",
                "event_title": "Evento Financeiro",
                "service_type": "Banheiro Químico",
                "amount": "1500.75",
                "due_date": "2026-04-10",
                "status": "vencido",
                "payment_method": "pix",
                "invoice_status": "com_nota",
                "invoice_number": "NF-77",
                "attachment_url": "https://example.com/comprovante.pdf",
                "notes": "Cobrar responsável",
            },
            follow_redirects=True,
        )

        self.assertIn("Conta a receber salva.", response.get_data(as_text=True))
        saved = json.loads(FINANCIAL_RECEIVABLES_PATH.read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["amount"], 1500.75)
        self.assertEqual(saved[0]["attachment_url"], "https://example.com/comprovante.pdf")
        self.assertEqual(saved[0]["status"], "vencido")
        self.assertEqual(saved[0]["service_type"], "Banheiro Químico")
        self.assertEqual(saved[0]["invoice_status"], "com_nota")

    def test_receivable_can_be_deleted_with_audit(self):
        self.client.post(
            "/financial/receivables",
            data={
                "client_name": "Cliente Remover",
                "amount": "450",
                "due_date": "2026-04-10",
                "status": "aguardando",
            },
            follow_redirects=True,
        )
        receivable = json.loads(FINANCIAL_RECEIVABLES_PATH.read_text(encoding="utf-8"))[0]

        response = self.client.post(
            f"/financial/receivables/{receivable['id']}/delete",
            follow_redirects=True,
        )

        self.assertIn("Recebimento excluído.", response.get_data(as_text=True))
        self.assertEqual(json.loads(FINANCIAL_RECEIVABLES_PATH.read_text(encoding="utf-8")), [])
        audit_log = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))
        self.assertTrue(any(item.get("action") == "delete" and item.get("module") == "finance" and item.get("target_id") == receivable["id"] for item in audit_log))

    def test_cashflow_entry_is_saved_and_rendered(self):
        response = self.client.post(
            "/financial/entries",
            data={
                "entry_type": "saida",
                "category": "combustível",
                "description": "Abastecimento frota",
                "amount": "280.30",
                "entry_date": "2026-04-18",
                "attachment_url": "",
                "notes": "Posto local",
            },
            follow_redirects=True,
        )
        html = response.get_data(as_text=True)

        self.assertIn("Lançamento financeiro salvo.", html)
        self.assertIn("Abastecimento frota", html)
        saved = json.loads(FINANCIAL_ENTRIES_PATH.read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["entry_type"], "saida")
        self.assertEqual(saved[0]["amount"], 280.3)

    def test_monthly_contract_billing_payment_and_receipt(self):
        CONTRACTS_PATH.write_text(
            json.dumps(
                [
                    {
                        "id": "CTR-CLI-FIXO",
                        "client_id": "CLI-FIXO",
                        "client_name": "Cliente Fixo",
                        "equipment_type": "Banheiro Luxo",
                        "monthly_value": 1800,
                        "cleaning_frequency": "semanal",
                        "status": "ativo",
                    }
                ],
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        response = self.client.post(
            "/financial/receivables/generate-monthly",
            data={"period": "2026-04", "due_day": "12"},
            follow_redirects=True,
        )
        receivables = json.loads(FINANCIAL_RECEIVABLES_PATH.read_text(encoding="utf-8"))
        receivable_id = receivables[0]["id"]

        self.assertIn("cobrança(s) mensal(is) gerada(s)", response.get_data(as_text=True))
        self.assertEqual(receivables[0]["billing_period"], "2026-04")
        self.assertEqual(receivables[0]["due_date"], "2026-04-12")

        payment_response = self.client.post(
            f"/financial/receivables/{receivable_id}/payment",
            data={"action": "paid", "payment_method": "pix"},
            follow_redirects=True,
        )
        receipt_response = self.client.get(f"/financial/receivables/{receivable_id}/receipt.pdf")
        paid = json.loads(FINANCIAL_RECEIVABLES_PATH.read_text(encoding="utf-8"))[0]

        self.assertIn("Pagamento registrado.", payment_response.get_data(as_text=True))
        self.assertEqual(paid["status"], "pago")
        self.assertEqual(paid["amount_received"], 1800)
        self.assertEqual(receipt_response.status_code, 200)
        self.assertIn(b"SannyGold - Recibo", receipt_response.get_data())

    def test_quote_models_are_saved(self):
        response = self.client.post(
            "/settings/quote-models",
            data={
                "banheiro_luxo_daily": "900",
                "banheiro_luxo_monthly": "4500",
                "banheiro_quimico_daily": "180",
                "climatizador_daily": "350",
                "hidratacao_daily": "250",
                "limpeza_extra": "120",
            },
            follow_redirects=True,
        )
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))

        self.assertIn("Modelos de orçamento atualizados.", response.get_data(as_text=True))
        self.assertEqual(settings["quote_models"]["banheiro_luxo_monthly"], 4500)

    def test_monthly_closeout_creates_locked_snapshot_and_pdf(self):
        response = self.client.post(
            "/financial/monthly-closeouts",
            data={"period": "2026-04", "notes": "Fechamento teste"},
            follow_redirects=True,
        )
        pdf_response = self.client.get("/financial/monthly-closeouts/2026-04.pdf")

        self.assertIn("Fechamento financeiro de 2026-04 gerado.", response.get_data(as_text=True))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response.mimetype, "application/pdf")
        self.assertIn(b"SannyGold - Fechamento Financeiro 2026-04", pdf_response.get_data())
        saved = json.loads(FINANCIAL_CLOSEOUTS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["period"], "2026-04")
        self.assertTrue(saved[0]["locked"])

    def test_financial_permissions_are_granular(self):
        self.assertIn("finance.payments", ROLE_PERMISSIONS["financeiro"])
        self.assertIn("finance.close", ROLE_PERMISSIONS["financeiro"])
        self.assertIn("finance.export", ROLE_PERMISSIONS["financeiro"])
        self.assertTrue(has_permission({"role": "financeiro"}, "finance.payments"))
        self.assertFalse(has_permission({"role": "operacional"}, "finance.payments"))


if __name__ == "__main__":
    unittest.main()
