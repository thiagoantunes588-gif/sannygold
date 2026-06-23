import json
import os
import tempfile
import unittest

from werkzeug.security import generate_password_hash

os.environ.setdefault("ROTAFLOW_STORAGE_DIR", tempfile.mkdtemp(prefix="sannygold-help-test-"))

from app.help_assistant import DEFAULT_HELP_KNOWLEDGE_BASE  # noqa: E402
from app.main import (  # noqa: E402
    HELP_KNOWLEDGE_BASE_PATH,
    HELP_METRICS_PATH,
    HELP_SUPPORT_TICKETS_PATH,
    HELP_UNANSWERED_PATH,
    USERS_PATH,
    app,
    ensure_storage_dirs,
)


class HelpAssistantTest(unittest.TestCase):
    def setUp(self):
        ensure_storage_dirs()
        app.config.update(TESTING=True)
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
                        "must_change_password": False,
                        "created_at": "2026-05-14T08:00:00",
                        "updated_at": "2026-05-14T08:00:00",
                    }
                ],
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        HELP_KNOWLEDGE_BASE_PATH.write_text(json.dumps(DEFAULT_HELP_KNOWLEDGE_BASE, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        HELP_UNANSWERED_PATH.write_text("[]\n", encoding="utf-8")
        HELP_SUPPORT_TICKETS_PATH.write_text("[]\n", encoding="utf-8")
        HELP_METRICS_PATH.write_text(
            json.dumps(
                {
                    "question_counts": {},
                    "useful_counts": {},
                    "not_useful_counts": {},
                    "support_clicks": 0,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        self.client = app.test_client()
        self.client.post(
            "/auth/login",
            data={"email": "admin@sannygold.local", "password": "troque-esta-senha"},
            follow_redirects=True,
        )

    def test_assistant_button_panel_and_admin_sections_render(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("help-assistant-button", html)
        self.assertIn("HelpAssistantButton", html)
        self.assertIn("help-assistant-panel", html)
        self.assertIn("HelpAssistantPanel", html)
        self.assertIn("Olá, sou o Assistente Operacional. Posso te ajudar a usar o sistema.", html)
        self.assertIn("Cadastrar evento", html)
        self.assertIn("Registrar material extra enviado", html)
        self.assertIn("Falar com suporte humano", html)
        self.assertIn("help-admin-panel", html)
        self.assertIn("UnansweredQuestionsAdmin", html)
        self.assertIn("support-tickets-admin-panel", html)
        self.assertIn("useHelpAssistant", html)
        self.assertIn("Me mostre onde fica", html)
        self.assertIn("Abrir tela", html)
        self.assertIn("Ainda estou com dúvida", html)
        self.assertIn("Chamar suporte", html)
        self.assertIn("help-assistant-state", html)
        self.assertIn("help-steps", html)
        self.assertIn("help-assistant-context", html)
        self.assertIn("Ajuda desta tela", html)
        self.assertIn("js-context-help", html)
        self.assertIn('data-help-context="events"', html)
        self.assertIn("syncHelpContextButtons", html)

    def test_help_routes_open_quick_help_and_assistant(self):
        quick_help = self.client.get("/ajuda", follow_redirects=False)
        assistant = self.client.get("/assistente", follow_redirects=False)

        self.assertEqual(quick_help.status_code, 302)
        self.assertIn("#quick-help-panel", quick_help.headers["Location"])
        self.assertEqual(assistant.status_code, 302)
        self.assertIn("#help-assistant-button", assistant.headers["Location"])

    def test_initial_knowledge_base_has_common_operational_questions(self):
        categories = {entry["categoria"] for entry in DEFAULT_HELP_KNOWLEDGE_BASE}

        self.assertGreaterEqual(len(DEFAULT_HELP_KNOWLEDGE_BASE), 20)
        self.assertIn("Eventos", categories)
        self.assertIn("Clientes", categories)
        self.assertIn("Equipamentos", categories)
        self.assertIn("Banheiros de luxo", categories)
        self.assertIn("Banheiros químicos", categories)
        self.assertIn("Rotas", categories)
        self.assertIn("Ajuda Rápida", categories)
        self.assertTrue(all(entry.get("passos") for entry in DEFAULT_HELP_KNOWLEDGE_BASE))
        quick_help_titles = {entry["titulo"] for entry in DEFAULT_HELP_KNOWLEDGE_BASE if entry["categoria"] == "Ajuda Rápida"}
        self.assertIn("Como criar locação rápida", quick_help_titles)
        self.assertIn("Como lançar recebimento", quick_help_titles)
        self.assertTrue(all(entry.get("exemplo") for entry in DEFAULT_HELP_KNOWLEDGE_BASE if entry["categoria"] == "Ajuda Rápida"))

    def test_search_returns_controlled_answer_by_keyword(self):
        response = self.client.get("/assistant/search?q=material%20extra")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["found"])
        self.assertEqual(payload["entry"]["id"], "registrar-material-extra")
        self.assertEqual(payload["entry"]["resposta"], "Material extra enviado deve sair pelo Almoxarifado.")
        self.assertIn("Abra Almoxarifado.", payload["entry"]["passos"])

        metrics = json.loads(HELP_METRICS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(metrics["question_counts"]["registrar-material-extra"], 1)

    def test_search_does_not_invent_answer_when_base_has_no_match(self):
        response = self.client.get("/assistant/search?q=pergunta%20sem%20base%20xyzabc")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["found"])
        self.assertEqual(
            payload["message"],
            "Não encontrei uma resposta segura para essa dúvida. Posso registrar isso para o suporte analisar.",
        )

    def test_unanswered_question_is_saved(self):
        response = self.client.post(
            "/assistant/unanswered",
            data={"text": "Não achei onde conferir material retornado", "screen": "/#warehouse-pane"},
        )
        payload = response.get_json()
        saved = json.loads(HELP_UNANSWERED_PATH.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["status"], "nova")
        self.assertEqual(saved[0]["user_email"], "admin@sannygold.local")
        self.assertIn("material retornado", saved[0]["text"])

    def test_support_ticket_and_support_click_are_saved(self):
        click_response = self.client.post("/assistant/support-click", data={"screen": "/"})
        ticket_response = self.client.post(
            "/assistant/support",
            data={"message": "Estou travado na ordem de serviço.", "priority": "alta", "screen": "/#events-pane"},
        )
        saved = json.loads(HELP_SUPPORT_TICKETS_PATH.read_text(encoding="utf-8"))
        metrics = json.loads(HELP_METRICS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(click_response.status_code, 200)
        self.assertEqual(ticket_response.status_code, 200)
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["status"], "novo")
        self.assertEqual(saved[0]["priority"], "alta")
        self.assertEqual(metrics["support_clicks"], 1)

    def test_feedback_tracks_useful_and_not_useful_counts(self):
        useful = self.client.post("/assistant/feedback", data={"answer_id": "cadastrar-evento", "useful": "true"})
        not_useful = self.client.post("/assistant/feedback", data={"answer_id": "cadastrar-evento", "useful": "false"})
        metrics = json.loads(HELP_METRICS_PATH.read_text(encoding="utf-8"))

        self.assertEqual(useful.status_code, 200)
        self.assertEqual(not_useful.status_code, 200)
        self.assertEqual(metrics["useful_counts"]["cadastrar-evento"], 1)
        self.assertEqual(metrics["not_useful_counts"]["cadastrar-evento"], 1)


if __name__ == "__main__":
    unittest.main()
