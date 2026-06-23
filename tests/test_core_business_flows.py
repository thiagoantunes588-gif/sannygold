from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from datetime import date, datetime
from pathlib import Path

from werkzeug.security import generate_password_hash

os.environ.setdefault("ROTAFLOW_STORAGE_DIR", tempfile.mkdtemp(prefix="sannygold-core-flow-test-"))
os.environ.setdefault("SANNYGOLD_ADMIN_EMAIL", "admin@sannygold.local")
os.environ.setdefault("SANNYGOLD_ADMIN_PASSWORD", "troque-esta-senha")

from app.main import (  # noqa: E402
    AUDIT_LOG_PATH,
    BACKUPS_DIR,
    CLIENTS_PATH,
    EQUIPMENT_PATH,
    EVENTS_PATH,
    FINANCIAL_ENTRIES_PATH,
    IMPORTANT_DATA_PATHS,
    LOGIN_ATTEMPTS,
    OPERATION_VALIDATION_PATH,
    ROUTE_JSON_PATH,
    ROUTE_PDF_PATH,
    SETTINGS_PATH,
    UPLOADS_DIR,
    USERS_PATH,
    VEHICLES_PATH,
    app,
    ensure_storage_dirs,
    run_automatic_backup_if_due,
)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class CoreBusinessFlowsTest(unittest.TestCase):
    def setUp(self):
        ensure_storage_dirs()
        app.config.update(TESTING=True, CSRF_ENABLED=True)
        LOGIN_ATTEMPTS.clear()

        for path in IMPORTANT_DATA_PATHS:
            write_json(path, [])
        write_json(SETTINGS_PATH, {})
        write_json(OPERATION_VALIDATION_PATH, {})
        write_json(
            USERS_PATH,
            [
                self.user("USR-ADMIN", "Administrador", "admin@sannygold.local", "admin"),
                self.user("USR-OP", "Operacao", "operacao@sannygold.local", "operacional"),
                self.user("USR-FIN", "Financeiro", "financeiro@sannygold.local", "financeiro"),
                self.user("USR-READ", "Leitura", "leitura@sannygold.local", "leitura"),
            ],
        )

        ROUTE_JSON_PATH.unlink(missing_ok=True)
        ROUTE_PDF_PATH.unlink(missing_ok=True)
        for backup_file in BACKUPS_DIR.glob("sannygold-data-backup-*.zip"):
            backup_file.unlink()

        self.client = app.test_client()

    @staticmethod
    def user(user_id: str, name: str, email: str, role: str) -> dict:
        return {
            "id": user_id,
            "nome": name,
            "email": email,
            "senha_hash": generate_password_hash("SenhaForte123", method="pbkdf2:sha256"),
            "status": "ativo",
            "role": role,
            "must_change_password": False,
            "created_at": "2026-05-22T08:00:00",
            "updated_at": "2026-05-22T08:00:00",
        }

    def login(self, email: str = "admin@sannygold.local", password: str = "SenhaForte123", *, follow: bool = False):
        return self.client.post(
            "/auth/login",
            data={"email": email, "password": password},
            follow_redirects=follow,
        )

    def seed_vehicle(self, vehicle_id: str = "VEI-001") -> None:
        write_json(
            VEHICLES_PATH,
            [
                {
                    "vehicle_id": vehicle_id,
                    "vehicle_type": "Van",
                    "plate": "ABC1D23",
                    "model": "Sprinter",
                    "start_lat": -22.8753396,
                    "start_lng": -43.068074,
                    "capacity": 4,
                    "max_stops": 8,
                    "max_minutes": 540,
                    "driver": "Motorista Teste",
                }
            ],
        )

    def create_equipment(self, equipment_id: str = "EQ-001") -> None:
        response = self.client.post(
            "/equipment",
            data={
                "equipment_id": equipment_id,
                "stock_equipment_type": "Banheiro Luxo",
                "status": "disponivel",
                "condition": "disponivel",
                "notes": "Equipamento falso para teste automatizado.",
            },
            follow_redirects=True,
        )
        self.assertIn(f"Equipamento {equipment_id} salvo com sucesso.", response.get_data(as_text=True))

    def client_payload(
        self,
        *,
        client_id: str = "CLI-001",
        equipment_id: str = "EQ-001",
        address: str = "Estrada Bento Pestana, 932 - Baldeador, Niteroi - RJ",
        lat: str = "-22.8753396",
        lng: str = "-43.068074",
        phone: str = "(21) 99999-1111",
    ) -> dict:
        return {
            "client_id": client_id,
            "customer_name": "Cliente Teste",
            "contact_name": "Responsavel Cliente",
            "phone": phone,
            "cpf_cnpj": "00.000.000/0001-00",
            "email": "cliente@sannygold.local",
            "invoice_status": "sem_nota",
            "client_address": address,
            "client_lat": lat,
            "client_lng": lng,
            "client_type": "avulso",
            "equipment_type": "Banheiro Luxo",
            "equipment_quantity": "1",
            "equipment_number": equipment_id,
            "billing_model": "avulso",
            "cleaning_frequency": "nao_aplica",
            "service_profile": "evento_avulso",
            "default_service_minutes": "20",
            "default_priority": "3",
            "window_start": "08:00",
            "window_end": "18:00",
            "service_value": "1500",
            "team_cost": "100",
            "equipment_cost": "50",
        }

    def create_client(self, **overrides) -> None:
        payload = self.client_payload(**overrides)
        response = self.client.post("/clients", data=payload, follow_redirects=True)
        self.assertIn("Cliente Teste", response.get_data(as_text=True))

    def seed_client_record(
        self,
        *,
        client_id: str = "CLI-001",
        equipment_id: str = "EQ-001",
        address: str = "Estrada Bento Pestana, 932 - Baldeador, Niteroi - RJ",
        lat: str | float = -22.8753396,
        lng: str | float = -43.068074,
        phone: str = "(21) 99999-1111",
    ) -> None:
        write_json(
            CLIENTS_PATH,
            [
                {
                    "client_id": client_id,
                    "customer_name": "Cliente Teste",
                    "contact_name": "Responsavel Cliente",
                    "phone": phone,
                    "cpf_cnpj": "00.000.000/0001-00",
                    "email": "cliente@sannygold.local",
                    "invoice_status": "sem_nota",
                    "address": address,
                    "lat": lat,
                    "lng": lng,
                    "client_type": "avulso",
                    "equipment_type": "Banheiro Luxo",
                    "equipment_quantity": 1,
                    "equipment_number": equipment_id,
                    "billing_model": "avulso",
                    "cleaning_frequency": "nao_aplica",
                    "service_profile": "evento_avulso",
                    "default_service_minutes": 20,
                    "default_priority": 3,
                    "window_start": "08:00",
                    "window_end": "18:00",
                    "service_value": 1500,
                    "team_cost": 100,
                    "equipment_cost": 50,
                }
            ],
        )

    def event_payload(
        self,
        *,
        event_id: str = "EVT-001",
        client_id: str = "CLI-001",
        vehicle_id: str = "VEI-001",
        responsible: str = "Operacao SannyGold",
        notes: str = "Entrada pela portaria principal. Instalar antes das 10h.",
        value: str = "1500",
    ) -> dict:
        return {
            "event_id": event_id,
            "title": "Locacao Teste",
            "event_category": "locacao",
            "event_date": "2026-05-25",
            "event_end_date": "2026-05-25",
            "status": "confirmado",
            "event_client_ids": [client_id],
            "event_vehicle_ids": [vehicle_id],
            "responsible": responsible,
            "notes": notes,
            "valor_servico": value,
        }

    def create_event(self, **overrides) -> None:
        response = self.client.post("/events", data=self.event_payload(**overrides), follow_redirects=True)
        self.assertIn("Evento Locacao Teste salvo com sucesso.", response.get_data(as_text=True))

    def seed_complete_operation(self) -> None:
        self.seed_vehicle()
        self.create_equipment()
        self.create_client()
        self.create_event()

    def audit_entries(self, *, action: str = "", module: str = "", target_id: str = "") -> list[dict]:
        entries = read_json(AUDIT_LOG_PATH)
        return [
            item for item in entries
            if (not action or item.get("action") == action)
            and (not module or item.get("module") == module)
            and (not target_id or item.get("target_id") == target_id)
        ]

    def test_01_login_de_usuario(self):
        response = self.login(follow=True)
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("admin@sannygold.local", html)
        self.assertTrue(self.audit_entries(action="login", module="auth", target_id="USR-ADMIN"))

    def test_02_criacao_de_cliente(self):
        self.login()
        self.create_equipment()
        self.create_client()

        clients = read_json(CLIENTS_PATH)
        self.assertEqual(clients[0]["client_id"], "CLI-001")
        self.assertEqual(clients[0]["customer_name"], "Cliente Teste")
        self.assertTrue(self.audit_entries(action="save", module="clients", target_id="CLI-001"))

    def test_03_criacao_de_evento_ou_locacao(self):
        self.login()
        self.seed_vehicle()
        self.create_equipment()
        self.create_client()
        self.create_event()

        events = read_json(EVENTS_PATH)
        self.assertEqual(events[0]["event_id"], "EVT-001")
        self.assertEqual(events[0]["client_ids"], ["CLI-001"])
        self.assertEqual(events[0]["vehicle_ids"], ["VEI-001"])
        self.assertTrue(self.audit_entries(action="save", module="events", target_id="EVT-001"))

    def test_04_vinculacao_de_equipamento_ao_evento(self):
        self.login()
        self.seed_complete_operation()

        client = read_json(CLIENTS_PATH)[0]
        event = read_json(EVENTS_PATH)[0]
        equipment = read_json(EQUIPMENT_PATH)[0]

        self.assertEqual(equipment["equipment_id"], "EQ-001")
        self.assertEqual(client["equipment_number"], "EQ-001")
        self.assertIn(client["client_id"], event["client_ids"])

    def test_05_validacao_de_evento_incompleto(self):
        self.login()
        self.create_equipment()
        self.seed_client_record(address="", lat="", lng="")
        write_json(VEHICLES_PATH, [])
        self.create_event(vehicle_id="", responsible="", notes="", value="0")

        response = self.client.post("/validate-operation", data={"event_id": "EVT-001"}, follow_redirects=True)
        validation = read_json(OPERATION_VALIDATION_PATH)

        self.assertIn("Validação operacional encontrou bloqueios", response.get_data(as_text=True))
        self.assertFalse(validation["is_routable"])
        self.assertTrue(validation["event_errors"] or validation["pending_items"])
        self.assertTrue(self.audit_entries(action="validate", module="operations", target_id="EVT-001"))

    def test_06_bloqueio_de_geracao_de_rota_sem_endereco(self):
        self.login()
        self.seed_vehicle()
        self.create_equipment()
        self.seed_client_record(address="", lat="", lng="")
        self.create_event()

        response = self.client.post("/generate", data={"event_id": "EVT-001"}, follow_redirects=True)
        html = response.get_data(as_text=True)

        self.assertIn("Rota bloqueada por dados incompletos", html)
        self.assertIn("Endereço incompleto", html)
        self.assertFalse(ROUTE_JSON_PATH.exists())

    def test_07_geracao_de_rota_com_dados_completos(self):
        self.login()
        self.seed_complete_operation()

        response = self.client.post("/generate", data={"event_id": "EVT-001"}, follow_redirects=True)
        route_payload = read_json(ROUTE_JSON_PATH)

        self.assertIn("Rotas geradas com sucesso.", response.get_data(as_text=True))
        self.assertTrue(ROUTE_PDF_PATH.exists())
        self.assertTrue(route_payload["routes"])
        self.assertTrue(self.audit_entries(action="generate", module="routes", target_id="EVT-001"))

    def test_08_geracao_de_ordem_de_servico_pdf_com_dados_completos(self):
        self.login()
        self.seed_complete_operation()

        response = self.client.get("/events/EVT-001/service-order.pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/pdf")
        self.assertTrue(response.get_data().startswith(b"%PDF"))
        self.assertTrue(self.audit_entries(action="generate_service_order", module="events", target_id="EVT-001"))
        response.close()

    def test_09_lancamento_financeiro_simples(self):
        self.login()

        response = self.client.post(
            "/financial/entries",
            data={
                "entry_type": "entrada",
                "category": "recebimento",
                "description": "Recebimento de teste",
                "amount": "250.75",
                "entry_date": date.today().isoformat(),
                "status": "realizado",
                "notes": "Dado falso criado pelo teste.",
            },
            follow_redirects=True,
        )
        entries = read_json(FINANCIAL_ENTRIES_PATH)

        self.assertIn("Lançamento financeiro salvo.", response.get_data(as_text=True))
        self.assertEqual(entries[0]["entry_type"], "entrada")
        self.assertEqual(entries[0]["amount"], 250.75)
        self.assertTrue(self.audit_entries(action="save", module="finance", target_id=entries[0]["id"]))

    def test_10_geracao_de_backup(self):
        self.login()
        ROUTE_PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
        ROUTE_PDF_PATH.write_bytes(b"%PDF-1.4\n% teste\n")
        uploads_assets = UPLOADS_DIR / "assets"
        uploads_assets.mkdir(parents=True, exist_ok=True)
        (uploads_assets / "anexo-teste.txt").write_text("Anexo falso para backup.\n", encoding="utf-8")

        response = self.client.post("/backup/generate", follow_redirects=True)
        backup_files = sorted(BACKUPS_DIR.glob("sannygold-data-backup-*.zip"))

        self.assertIn("Backup gerado", response.get_data(as_text=True))
        self.assertTrue(backup_files)
        with zipfile.ZipFile(backup_files[-1]) as archive:
            names = archive.namelist()
            self.assertIn("manifest.json", names)
            self.assertIn("config/backup-config.json", names)
            self.assertIn("config/runtime-config.json", names)
            self.assertIn("data/", names)
            self.assertIn("preview/", names)
            self.assertIn("uploads/", names)
            self.assertIn("data/sannygold.db", names)
            self.assertIn("data/clients.json", names)
            self.assertIn("preview/route-plan.pdf", names)
            self.assertIn("uploads/assets/anexo-teste.txt", names)
            self.assertFalse(any(name.startswith("backups/") for name in names))
            self.assertFalse(any(name.startswith("logs/") for name in names))
            self.assertFalse(any(name.endswith(".env") or "/.env" in name for name in names))
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            runtime_config = json.loads(archive.read("config/runtime-config.json").decode("utf-8"))
            self.assertEqual(manifest["app"], "SannyGold")
            self.assertEqual(manifest["backup_format"], "sannygold-data-backup-v1")
            self.assertNotIn("SANNYGOLD_SECRET_KEY", runtime_config)
            self.assertNotIn("SANNYGOLD_ADMIN_PASSWORD", runtime_config)
        self.assertTrue(self.audit_entries(action="create", module="backup"))

    def test_backup_copia_para_dropbox_quando_configurado(self):
        self.login()
        old_value = os.environ.get("DROPBOX_BACKUP_DIR")
        with tempfile.TemporaryDirectory(prefix="sannygold-dropbox-test-") as dropbox_root:
            dropbox_dir = Path(dropbox_root) / "Backups"
            dropbox_dir.mkdir(parents=True, exist_ok=True)
            os.environ["DROPBOX_BACKUP_DIR"] = str(dropbox_dir)
            try:
                response = self.client.post("/backup/generate", follow_redirects=True)
                backup_files = sorted(BACKUPS_DIR.glob("sannygold-data-backup-*.zip"))
                copied_files = sorted(dropbox_dir.glob("sannygold-data-backup-*.zip"))
                settings = read_json(SETTINGS_PATH)
            finally:
                if old_value is None:
                    os.environ.pop("DROPBOX_BACKUP_DIR", None)
                else:
                    os.environ["DROPBOX_BACKUP_DIR"] = old_value

        self.assertEqual(response.status_code, 200)
        self.assertTrue(backup_files)
        self.assertTrue(copied_files)
        self.assertEqual(copied_files[-1].name, backup_files[-1].name)
        self.assertEqual(settings.get("last_backup_copy_file"), backup_files[-1].name)
        self.assertEqual(settings.get("last_backup_copy_path"), str(copied_files[-1]))
        self.assertFalse(settings.get("last_backup_copy_warning"))
        self.assertTrue(self.audit_entries(action="copy", module="backup"))

    def test_backup_local_nao_depende_de_dropbox_inexistente(self):
        self.login()
        old_value = os.environ.get("DROPBOX_BACKUP_DIR")
        with tempfile.TemporaryDirectory(prefix="sannygold-dropbox-missing-") as dropbox_root:
            missing_dropbox = Path(dropbox_root) / "Backups"
            os.environ["DROPBOX_BACKUP_DIR"] = str(missing_dropbox)
            try:
                response = self.client.post("/backup/generate", follow_redirects=True)
                backup_files = sorted(BACKUPS_DIR.glob("sannygold-data-backup-*.zip"))
                settings = read_json(SETTINGS_PATH)
                missing_exists = missing_dropbox.exists()
            finally:
                if old_value is None:
                    os.environ.pop("DROPBOX_BACKUP_DIR", None)
                else:
                    os.environ["DROPBOX_BACKUP_DIR"] = old_value

        self.assertEqual(response.status_code, 200)
        self.assertTrue(backup_files)
        self.assertFalse(missing_exists)
        self.assertIn("Pasta Dropbox não encontrada", settings.get("last_backup_copy_warning", ""))
        self.assertIn("backup gerado", response.get_data(as_text=True).lower())
        self.assertTrue(self.audit_entries(action="copy_warning", module="backup"))

    def test_admin_consegue_testar_pasta_dropbox(self):
        self.login()
        old_value = os.environ.get("DROPBOX_BACKUP_DIR")
        with tempfile.TemporaryDirectory(prefix="sannygold-dropbox-test-ok-") as dropbox_root:
            dropbox_dir = Path(dropbox_root) / "Backups"
            dropbox_dir.mkdir(parents=True, exist_ok=True)
            os.environ["DROPBOX_BACKUP_DIR"] = str(dropbox_dir)
            try:
                response = self.client.post("/backup/dropbox/test", follow_redirects=True)
                temp_files = list(dropbox_dir.glob(".sannygold-backup-test-*.tmp"))
            finally:
                if old_value is None:
                    os.environ.pop("DROPBOX_BACKUP_DIR", None)
                else:
                    os.environ["DROPBOX_BACKUP_DIR"] = old_value

        self.assertEqual(response.status_code, 200)
        self.assertIn("Pasta Dropbox testada com sucesso", response.get_data(as_text=True))
        self.assertFalse(temp_files)

    def test_admin_consegue_testar_restauracao_sem_alterar_dados_reais(self):
        self.login()
        CLIENTS_PATH.write_text('[{"client_id": "ANTES"}]', encoding="utf-8")
        self.client.post("/backup/generate", follow_redirects=True)
        CLIENTS_PATH.write_text('[{"client_id": "DEPOIS"}]', encoding="utf-8")

        response = self.client.post("/backup/latest/test-restore", follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Teste de restauração concluído", response.get_data(as_text=True))
        self.assertIn("DEPOIS", CLIENTS_PATH.read_text(encoding="utf-8"))
        self.assertTrue(self.audit_entries(action="validate", module="backup"))

    def test_admin_configura_agendamento_de_backup(self):
        self.login()
        response = self.client.post(
            "/backup/schedule",
            data={"automatic_backup_enabled": "1", "automatic_backup_time": "21:30"},
            follow_redirects=True,
        )
        settings = read_json(SETTINGS_PATH)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(settings.get("automatic_backup_enabled"))
        self.assertEqual(settings.get("automatic_backup_time"), "21:30")
        self.assertIn("Agendamento de backup atualizado", response.get_data(as_text=True))
        self.assertTrue(self.audit_entries(action="save", module="backup", target_id="automatic_schedule"))

    def test_backup_automatico_roda_uma_vez_por_dia(self):
        self.login()
        settings = read_json(SETTINGS_PATH)
        settings["automatic_backup_enabled"] = True
        settings["automatic_backup_time"] = "08:00"
        settings["last_automatic_backup_attempt_date"] = "2026-05-25"
        write_json(SETTINGS_PATH, settings)

        first = run_automatic_backup_if_due(now=datetime(2026, 5, 26, 8, 1))
        backup_files_after_first = sorted(BACKUPS_DIR.glob("sannygold-data-backup-*.zip"))
        second = run_automatic_backup_if_due(now=datetime(2026, 5, 26, 8, 2))
        backup_files_after_second = sorted(BACKUPS_DIR.glob("sannygold-data-backup-*.zip"))
        settings = read_json(SETTINGS_PATH)

        self.assertTrue(first["ran"])
        self.assertEqual(first["status"], "sucesso")
        self.assertFalse(second["ran"])
        self.assertEqual(len(backup_files_after_first), len(backup_files_after_second))
        self.assertEqual(settings.get("last_automatic_backup_attempt_date"), "2026-05-26")
        self.assertEqual(settings.get("last_automatic_backup_status"), "sucesso")
        self.assertTrue(settings.get("last_automatic_backup_file"))
        self.assertTrue(self.audit_entries(action="automatic", module="backup"))

    def test_11_registro_de_auditoria_em_acao_critica(self):
        self.login()
        self.create_equipment()
        self.create_client()

        entries = self.audit_entries(action="save", module="clients", target_id="CLI-001")
        self.assertTrue(entries)
        self.assertEqual(entries[-1]["user_email"], "admin@sannygold.local")
        self.assertEqual(entries[-1]["action_label"], "Salvou")
        self.assertIn("ip_address", entries[-1])
        self.assertNotIn("SenhaForte123", AUDIT_LOG_PATH.read_text(encoding="utf-8"))

    def test_12_bloqueio_de_rota_admin_para_usuario_sem_permissao(self):
        self.login("operacao@sannygold.local")

        response = self.client.post("/backup/generate", follow_redirects=True)
        html = response.get_data(as_text=True)

        self.assertIn("Acesso restrito para o seu perfil", html)
        mobile_access = self.client.get("/admin/acesso-celular", follow_redirects=True)
        self.assertIn("Acesso restrito para o seu perfil", mobile_access.get_data(as_text=True))
        denied = self.audit_entries(action="access_denied", module="permissions", target_id="settings.manage")
        self.assertGreaterEqual(len(denied), 2)
        self.assertEqual(denied[-1]["user_email"], "operacao@sannygold.local")

    def test_13_duplicar_locacao_cria_novo_evento_sem_alterar_original(self):
        self.login()
        self.seed_complete_operation()
        original_events = read_json(EVENTS_PATH)
        original_events[0]["status"] = "finalizado"
        original_events[0]["last_route_generated_at"] = "2026-05-25T09:00:00"
        original_events[0]["checklist"] = [
            {"label": "checklist_equipamentos", "done": True},
            {"label": "checklist_documentos", "done": True},
            {"label": "checklist_equipe", "done": True},
            {"label": "checklist_financeiro", "done": True},
        ]
        write_json(EVENTS_PATH, original_events)

        blocked = self.client.post(
            "/events",
            data={
                "duplicated_from_event_id": "EVT-001",
                "event_id": "EVT-001",
                "title": "Locacao Teste",
                "event_category": "locacao",
                "status": "finalizado",
                "event_client_ids": ["CLI-001"],
                "event_vehicle_ids": ["VEI-001"],
                "responsible": "Operacao SannyGold",
                "notes": "Entrada pela portaria principal. Instalar antes das 10h.",
                "valor_servico": "1500",
                "last_route_generated_at": "2026-05-25T09:00:00",
                "check_checklist_equipamentos": "on",
            },
            follow_redirects=True,
        )
        self.assertIn("nova data", blocked.get_data(as_text=True))
        self.assertEqual(len(read_json(EVENTS_PATH)), 1)

        response = self.client.post(
            "/events",
            data={
                "duplicated_from_event_id": "EVT-001",
                "event_id": "EVT-001",
                "title": "Locacao Teste",
                "event_category": "locacao",
                "event_date": "2026-06-10",
                "event_end_date": "2026-06-10",
                "status": "finalizado",
                "event_client_ids": ["CLI-001"],
                "event_vehicle_ids": ["VEI-001"],
                "responsible": "Operacao SannyGold",
                "notes": "Entrada pela portaria principal. Instalar antes das 10h.",
                "valor_servico": "1500",
                "last_route_generated_at": "2026-05-25T09:00:00",
                "check_checklist_equipamentos": "on",
            },
            follow_redirects=True,
        )
        events = read_json(EVENTS_PATH)
        original = next(item for item in events if item["event_id"] == "EVT-001")
        duplicate = next(item for item in events if item["event_id"] != "EVT-001")

        self.assertIn("Locação duplicada com sucesso", response.get_data(as_text=True))
        self.assertEqual(original["status"], "finalizado")
        self.assertEqual(original["last_route_generated_at"], "2026-05-25T09:00:00")
        self.assertEqual(duplicate["event_id"], "EVT-002")
        self.assertEqual(duplicate["duplicated_from_event_id"], "EVT-001")
        self.assertEqual(duplicate["client_ids"], ["CLI-001"])
        self.assertEqual(duplicate["event_category"], "locacao")
        self.assertEqual(duplicate["responsible"], "Operacao SannyGold")
        self.assertEqual(duplicate["notes"], "Entrada pela portaria principal. Instalar antes das 10h.")
        self.assertEqual(duplicate["valor_servico"], 1500.0)
        self.assertEqual(duplicate["event_date"], "2026-06-10")
        self.assertEqual(duplicate["status"], "rascunho")
        self.assertEqual(duplicate["vehicle_ids"], [])
        self.assertEqual(duplicate["last_route_generated_at"], "")
        self.assertTrue(all(not item["done"] for item in duplicate["checklist"]))
        audit = self.audit_entries(action="duplicate", module="events", target_id="EVT-002")
        self.assertTrue(audit)
        self.assertEqual(audit[-1]["before"]["event_id"], "EVT-001")
        self.assertEqual(audit[-1]["after"]["duplicated_from_event_id"], "EVT-001")


if __name__ == "__main__":
    unittest.main()
