import os
import tempfile
import unittest
import json

from werkzeug.security import generate_password_hash

os.environ["ROTAFLOW_STORAGE_DIR"] = tempfile.mkdtemp(prefix="sannygold-auth-test-")
os.environ["SANNYGOLD_ADMIN_EMAIL"] = "admin@sannygold.local"
os.environ["SANNYGOLD_ADMIN_PASSWORD"] = "Sanny123Gold"

from app.main import AUDIT_LOG_PATH, USERS_PATH, app, ensure_storage_dirs, has_permission  # noqa: E402


class AuthAccessControlTest(unittest.TestCase):
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
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def login(self, email="admin@sannygold.local", password="Sanny123Gold"):
        return self.client.post(
            "/auth/login",
            data={"email": email, "password": password},
            follow_redirects=True,
        )

    def test_public_dashboard_is_visible_but_hides_sensitive_modules(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Modo visitante", html)
        self.assertIn("settings-menu-button", html)
        self.assertIn("Entrar na conta", html)
        self.assertIn("public-dashboard", html)
        self.assertNotIn('id="clients-pane"', html)
        self.assertNotIn('id="fleet-pane"', html)
        self.assertNotIn("Valor do serviço", html)
        self.assertNotIn("Backup</a>", html)

    def test_protected_endpoint_rejects_guest_direct_access(self):
        response = self.client.post("/clients", data={"customer_name": "Cliente oculto"})

        self.assertEqual(response.status_code, 302)
        self.assertIn("/?auth=required", response.headers["Location"])

    def test_health_endpoint_is_public_and_reports_ok(self):
        response = self.client.get("/health")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("metadata", payload)
        self.assertIn("counts", payload)

    def test_login_reports_user_not_found_and_wrong_password(self):
        missing = self.client.post(
            "/auth/login",
            data={"email": "ninguem@sannygold.local", "password": "senha"},
            follow_redirects=True,
        )
        wrong = self.client.post(
            "/auth/login",
            data={"email": "admin@sannygold.local", "password": "errada"},
            follow_redirects=True,
        )

        self.assertIn("Usuário não encontrado.", missing.get_data(as_text=True))
        self.assertIn("Senha incorreta.", wrong.get_data(as_text=True))

    def test_admin_login_unlocks_internal_modules_and_logout_returns_guest(self):
        logged = self.login()
        html = logged.get_data(as_text=True)

        self.assertEqual(logged.status_code, 200)
        self.assertIn("admin@sannygold.local", html)
        self.assertIn("Troca de senha pendente", html)
        self.assertIn('id="clients-pane"', html)
        self.assertIn("Permissões", html)
        self.assertIn("settings.manage", html)
        self.assertIn("Matriz de permissões por função", html)
        self.assertIn("Painel de acessos da equipe", html)
        self.assertIn("Novo acesso", html)
        self.assertIn("Revisão semanal", html)
        self.assertIn("Padrão mínimo de cadastro", html)

        logged_out = self.client.post("/auth/logout", follow_redirects=True)
        self.assertIn("Modo visitante", logged_out.get_data(as_text=True))

    def test_permission_map_is_ready_for_module_actions(self):
        self.assertTrue(has_permission({"role": "admin"}, "settings.manage"))
        self.assertTrue(has_permission({"role": "financeiro"}, "finance.view"))
        self.assertTrue(has_permission({"role": "leitura"}, "clients.view"))
        self.assertFalse(has_permission({"role": "guest"}, "clients.view"))
        self.assertFalse(has_permission({"role": "operacional"}, "finance.view"))

    def test_admin_can_create_user_without_plain_text_password(self):
        self.login()

        response = self.client.post(
            "/users",
            data={
                "nome": "Operador Teste",
                "email": "operador@sannygold.local",
                "password": "SenhaForte123",
                "role": "operacional",
                "status": "ativo",
            },
            follow_redirects=True,
        )
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        saved = next(user for user in users if user["email"] == "operador@sannygold.local")
        audit = json.loads(AUDIT_LOG_PATH.read_text(encoding="utf-8"))

        self.assertIn("Usuário operador@sannygold.local salvo com sucesso.", response.get_data(as_text=True))
        self.assertEqual(saved["role"], "operacional")
        self.assertNotEqual(saved["senha_hash"], "SenhaForte123")
        self.assertTrue(saved["senha_hash"].startswith("pbkdf2:sha256"))
        self.assertTrue(saved["must_change_password"])
        self.assertTrue(any(item["module"] == "users" and item["action"] == "save" for item in audit))

    def test_admin_can_edit_and_deactivate_existing_user(self):
        self.login()
        self.client.post(
            "/users",
            data={
                "nome": "Operador Editavel",
                "email": "editavel@sannygold.local",
                "password": "SenhaForte123",
                "role": "operacional",
                "status": "ativo",
            },
            follow_redirects=True,
        )
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        created = next(user for user in users if user["email"] == "editavel@sannygold.local")

        response = self.client.post(
            "/users",
            data={
                "user_id": created["id"],
                "nome": "Operador Financeiro",
                "email": "editavel@sannygold.local",
                "role": "financeiro",
                "status": "inativo",
            },
            follow_redirects=True,
        )
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        saved = next(user for user in users if user["email"] == "editavel@sannygold.local")

        self.assertIn("Usuário editavel@sannygold.local salvo com sucesso.", response.get_data(as_text=True))
        self.assertEqual(saved["nome"], "Operador Financeiro")
        self.assertEqual(saved["role"], "financeiro")
        self.assertEqual(saved["status"], "inativo")
        self.assertTrue(saved["senha_hash"].startswith("pbkdf2:sha256"))

    def test_user_creation_rejects_weak_password(self):
        self.login()

        response = self.client.post(
            "/users",
            data={
                "nome": "Operador Fraco",
                "email": "fraco@sannygold.local",
                "password": "abc123",
                "role": "operacional",
                "status": "ativo",
            },
            follow_redirects=True,
        )

        self.assertIn("A senha precisa ter pelo menos 10 caracteres.", response.get_data(as_text=True))

    def test_password_change_clears_first_access_flag(self):
        self.login()

        response = self.client.post(
            "/account/password",
            data={"current_password": "Sanny123Gold", "new_password": "NovaSenha2026"},
            follow_redirects=True,
        )
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        admin = next(user for user in users if user["email"] == "admin@sannygold.local")

        self.assertIn("Senha atualizada com sucesso.", response.get_data(as_text=True))
        self.assertFalse(admin["must_change_password"])


if __name__ == "__main__":
    unittest.main()
