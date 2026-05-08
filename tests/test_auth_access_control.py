import os
import tempfile
import unittest
import json
from urllib.parse import urlparse

from werkzeug.security import generate_password_hash

os.environ["ROTAFLOW_STORAGE_DIR"] = tempfile.mkdtemp(prefix="sannygold-auth-test-")
os.environ["SANNYGOLD_ADMIN_EMAIL"] = "admin@sannygold.local"
os.environ["SANNYGOLD_ADMIN_PASSWORD"] = "Sanny123Gold"

from app.main import AUDIT_LOG_PATH, LOGIN_ATTEMPTS, USERS_PATH, app, ensure_storage_dirs, has_permission, invitation_url, password_reset_url  # noqa: E402


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
        LOGIN_ATTEMPTS.clear()
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
        self.assertEqual(payload["status"], "OK")
        self.assertIn("metadata", payload)
        self.assertIn("counts", payload)

        status_response = self.client.get("/status")
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.get_json()["status"], "OK")

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

    def test_login_locks_after_repeated_wrong_passwords(self):
        for _ in range(5):
            self.client.post(
                "/auth/login",
                data={"email": "admin@sannygold.local", "password": "errada"},
                follow_redirects=True,
            )

        response = self.client.post(
            "/auth/login",
            data={"email": "admin@sannygold.local", "password": "Sanny123Gold"},
            follow_redirects=True,
        )

        self.assertIn("Muitas tentativas de login", response.get_data(as_text=True))

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
        self.assertIn("Checklist de Homologação", html)
        self.assertIn("Validar endpoint /health ou /status", html)
        self.assertIn("Validar persistência após reinício/redeploy", html)
        self.assertIn("Convidar por e-mail", html)
        self.assertIn("Gerar convite", html)
        self.assertIn("Revisão semanal", html)
        self.assertIn("Padrão mínimo de cadastro", html)

        logged_out = self.client.post("/auth/logout", follow_redirects=True)
        self.assertIn("Modo visitante", logged_out.get_data(as_text=True))

    def test_permission_map_is_ready_for_module_actions(self):
        self.assertTrue(has_permission({"role": "admin"}, "settings.manage"))
        self.assertTrue(has_permission({"role": "financeiro"}, "finance.view"))
        self.assertTrue(has_permission({"role": "leitura"}, "clients.view"))
        self.assertTrue(has_permission({"role": "operacional"}, "warehouse.edit"))
        self.assertFalse(has_permission({"role": "operacional"}, "warehouse.manage"))
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

    def test_admin_invites_user_and_user_sets_own_password(self):
        self.login()

        response = self.client.post(
            "/users",
            data={
                "nome": "Operador Convite",
                "email": "convite@sannygold.local",
                "role": "operacional",
                "status": "convite_pendente",
            },
            follow_redirects=True,
        )
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        saved = next(user for user in users if user["email"] == "convite@sannygold.local")
        with app.test_request_context(base_url="http://localhost"):
            invite_path = urlparse(invitation_url(saved)).path

        self.assertIn("Convite criado para convite@sannygold.local", response.get_data(as_text=True))
        self.assertEqual(saved["status"], "convite_pendente")
        self.assertEqual(saved["senha_hash"], "")
        self.assertIn("invitation_token", saved)

        setup = self.client.get(invite_path)
        self.assertIn("Criar senha de acesso", setup.get_data(as_text=True))

        accepted = self.client.post(
            invite_path,
            data={"new_password": "SenhaEquipe2026", "confirm_password": "SenhaEquipe2026"},
            follow_redirects=True,
        )
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        activated = next(user for user in users if user["email"] == "convite@sannygold.local")

        self.assertIn("Senha criada com sucesso", accepted.get_data(as_text=True))
        self.assertEqual(activated["status"], "ativo")
        self.assertTrue(activated["senha_hash"].startswith("pbkdf2:sha256"))
        self.assertFalse(activated["must_change_password"])
        self.assertEqual(activated["invitation_token"], "")

        self.client.post("/auth/logout", follow_redirects=True)
        logged = self.login("convite@sannygold.local", "SenhaEquipe2026")
        self.assertIn("Login realizado com sucesso.", logged.get_data(as_text=True))

    def test_admin_can_generate_password_reset_link_without_knowing_password(self):
        self.login()
        self.client.post(
            "/users",
            data={
                "nome": "Operador Reset",
                "email": "reset@sannygold.local",
                "password": "SenhaForte123",
                "role": "operacional",
                "status": "ativo",
            },
            follow_redirects=True,
        )
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        created = next(user for user in users if user["email"] == "reset@sannygold.local")

        response = self.client.post(f"/users/{created['id']}/password-reset", follow_redirects=True)
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        pending_reset = next(user for user in users if user["email"] == "reset@sannygold.local")
        with app.test_request_context(base_url="http://localhost"):
            reset_path = urlparse(password_reset_url(pending_reset)).path

        self.assertIn("Link de redefinição gerado para reset@sannygold.local", response.get_data(as_text=True))
        self.assertIn("reset_token", pending_reset)

        reset = self.client.post(
            reset_path,
            data={"new_password": "SenhaNova2026", "confirm_password": "SenhaNova2026"},
            follow_redirects=True,
        )
        users = json.loads(USERS_PATH.read_text(encoding="utf-8"))
        updated = next(user for user in users if user["email"] == "reset@sannygold.local")

        self.assertIn("Senha redefinida com sucesso.", reset.get_data(as_text=True))
        self.assertEqual(updated["reset_token"], "")
        self.client.post("/auth/logout", follow_redirects=True)
        logged = self.login("reset@sannygold.local", "SenhaNova2026")
        self.assertIn("Login realizado com sucesso.", logged.get_data(as_text=True))

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
