from __future__ import annotations

from collections import Counter
import csv
import hmac
import importlib.util
import io
import json
import os
import secrets
import sys
import tempfile
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from xml.etree import ElementTree as ET

from flask import Flask, flash, has_request_context, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for
from itsdangerous import BadSignature, URLSafeSerializer
from werkzeug.datastructures import MultiDict
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from app.executive import build_executive_dashboard
from app.help_assistant import (
    DEFAULT_HELP_KNOWLEDGE_BASE,
    DEFAULT_HELP_KNOWLEDGE_BASE_VERSION,
    QUICK_HELP_GUIDE_IDS,
    search_help_knowledge_base,
    summarize_help_metrics,
)
from app.routes.backup import register_backup_routes
from app.routes.finance import register_finance_routes
from app.security import (
    DEFAULT_SECRET_KEY,
    build_security_posture,
    is_production_environment,
    password_change_required,
    password_policy_issues,
    validate_secret_key_value,
)
from app.services.backup import (
    BackupConfig,
    backup_file_created_at as backup_service_file_created_at,
    build_backup_status as backup_service_status,
    create_data_backup as backup_service_create,
    list_backup_files as backup_service_list_files,
    prune_old_backups as backup_service_prune_old,
    restore_data_backup as backup_service_restore,
    write_data_backup_archive as backup_service_write_archive,
)


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BASE_DIR / "scripts" / "plan_routes.py"
DEFAULT_STORAGE_ROOT = Path("/tmp/rotaflow") if os.environ.get("VERCEL") else BASE_DIR
STORAGE_ROOT = Path(os.environ.get("ROTAFLOW_STORAGE_DIR", str(DEFAULT_STORAGE_ROOT)))
DATA_DIR = STORAGE_ROOT / "data"
BACKUPS_DIR = STORAGE_ROOT / "backups"
CLIENTS_PATH = DATA_DIR / "clients.json"
VEHICLES_PATH = DATA_DIR / "vehicles.json"
EQUIPMENT_PATH = DATA_DIR / "equipment.json"
CONTRACTS_PATH = DATA_DIR / "contracts.json"
QUOTES_PATH = DATA_DIR / "quotes.json"
SERVICE_LOG_PATH = DATA_DIR / "service_log.json"
ATTACHMENTS_PATH = DATA_DIR / "attachments.json"
ROUTE_HISTORY_PATH = DATA_DIR / "route_history.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
EVENTS_PATH = DATA_DIR / "events.json"
USERS_PATH = DATA_DIR / "users.json"
WAREHOUSE_ITEMS_PATH = DATA_DIR / "warehouse_items.json"
WAREHOUSE_MOVEMENTS_PATH = DATA_DIR / "warehouse_movements.json"
AUDIT_LOG_PATH = DATA_DIR / "audit_log.json"
FINANCIAL_RECEIVABLES_PATH = DATA_DIR / "financial_receivables.json"
FINANCIAL_ENTRIES_PATH = DATA_DIR / "financial_entries.json"
FINANCIAL_CLOSEOUTS_PATH = DATA_DIR / "financial_closeouts.json"
FIELD_CONFIRMATIONS_PATH = DATA_DIR / "field_confirmations.json"
OPERATION_VALIDATION_PATH = DATA_DIR / "operation_validation.json"
FORECAST_AUDIT_PATH = DATA_DIR / "forecast_audit.json"
HELP_KNOWLEDGE_BASE_PATH = DATA_DIR / "help_knowledge_base.json"
HELP_UNANSWERED_PATH = DATA_DIR / "help_unanswered_questions.json"
HELP_SUPPORT_TICKETS_PATH = DATA_DIR / "help_support_tickets.json"
HELP_METRICS_PATH = DATA_DIR / "help_metrics.json"
BACKUP_RETENTION_LIMIT = 30
IMPORTANT_DATA_PATHS = (
    CLIENTS_PATH,
    VEHICLES_PATH,
    EQUIPMENT_PATH,
    CONTRACTS_PATH,
    QUOTES_PATH,
    SERVICE_LOG_PATH,
    ATTACHMENTS_PATH,
    ROUTE_HISTORY_PATH,
    SETTINGS_PATH,
    EVENTS_PATH,
    USERS_PATH,
    WAREHOUSE_ITEMS_PATH,
    WAREHOUSE_MOVEMENTS_PATH,
    AUDIT_LOG_PATH,
    FINANCIAL_RECEIVABLES_PATH,
    FINANCIAL_ENTRIES_PATH,
    FINANCIAL_CLOSEOUTS_PATH,
    FIELD_CONFIRMATIONS_PATH,
    OPERATION_VALIDATION_PATH,
    FORECAST_AUDIT_PATH,
    HELP_KNOWLEDGE_BASE_PATH,
    HELP_UNANSWERED_PATH,
    HELP_SUPPORT_TICKETS_PATH,
    HELP_METRICS_PATH,
)
UPLOADS_DIR = STORAGE_ROOT / "uploads"
PREVIEW_DIR = STORAGE_ROOT / "preview"
ROUTE_JSON_PATH = PREVIEW_DIR / "route-plan-mobile.json"
ROUTE_PDF_PATH = PREVIEW_DIR / "route-plan.pdf"
APP_VERSION = os.environ.get("SANNYGOLD_APP_VERSION", "v1.0.0")
DEPLOY_TARGET = "vercel" if os.environ.get("VERCEL") else ("render" if os.environ.get("RENDER") else "local")
APP_ENV = os.environ.get("SANNYGOLD_ENV") or os.environ.get("FLASK_ENV") or ("production" if DEPLOY_TARGET in {"render", "vercel"} else "local")
IS_PRODUCTION = is_production_environment(DEPLOY_TARGET, APP_ENV)
FLASK_DEBUG_ENABLED = os.environ.get("FLASK_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
INVITATION_EXPIRATION_HOURS = 48
PASSWORD_RESET_EXPIRATION_HOURS = 2
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15
CSRF_SESSION_KEY = "_csrf_token"
CSRF_FIELD_NAME = "_csrf_token"
CSRF_HEADER_NAMES = ("X-CSRFToken", "X-CSRF-Token")
UPLOAD_MAX_BYTES = 10 * 1024 * 1024
IMAGE_UPLOAD_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ROUTE_UPLOAD_EXTENSIONS = {".csv"}
EXCEL_UPLOAD_EXTENSIONS = {".xlsx"}
HQ_ADDRESS = "Estrada Bento Pestana, 932 - Baldeador, Niterói - RJ"
HQ_LAT = -22.8753396
HQ_LNG = -43.068074
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
EQUIPMENT_STATUS_OPTIONS = {
    "disponivel",
    "reservado",
    "carregado",
    "em_rota",
    "instalado",
    "retirada_pendente",
    "retornado",
    "manutencao",
    "indisponivel",
}
EQUIPMENT_TYPE_SUGGESTIONS = [
    "Banheiro Trailer Luxo",
    "Banheiro Luxo",
    "Banheiro Químico",
    "Cabine PCD",
    "Climatizador",
    "Ponto de Hidratação",
    "Lavabo",
    "Container",
]
QUICK_RENTAL_SERVICE_OPTIONS = [
    {"value": "banheiro_quimico", "label": "Banheiro químico", "equipment_type": "Banheiro Químico"},
    {"value": "banheiro_pne", "label": "Banheiro PNE", "equipment_type": "Banheiro PNE"},
    {"value": "trailer_luxo", "label": "Trailer de luxo", "equipment_type": "Banheiro Trailer Luxo"},
    {"value": "climatizador", "label": "Climatizador", "equipment_type": "Climatizador"},
    {"value": "ponto_hidratacao", "label": "Ponto de hidratação", "equipment_type": "Ponto de Hidratação"},
    {"value": "outro", "label": "Outro serviço", "equipment_type": ""},
]
QUICK_RENTAL_SERVICE_BY_VALUE = {item["value"]: item for item in QUICK_RENTAL_SERVICE_OPTIONS}
BLOCKED_EQUIPMENT_STATUSES = {"manutencao", "indisponivel"}
COMMITTED_EQUIPMENT_STATUSES = {"reservado", "carregado", "em_rota", "instalado", "retirada_pendente"}
PENDING_REASON_LABELS = {
    "sem_equipamento_disponivel": "Sem equipamento disponível",
    "equipamento_em_conflito": "Equipamento em conflito",
    "sem_veiculo_disponivel": "Sem veículo disponível",
    "veiculo_em_conflito": "Veículo em conflito",
    "janela_inviavel": "Janela inviável",
    "capacidade_excedida": "Capacidade excedida",
    "tempo_excedido": "Tempo excedido",
    "evento_inapto": "Evento inapto",
    "endereco_incompleto": "Endereço incompleto",
    "cliente_sem_telefone": "Cliente sem telefone",
    "cliente_nao_vinculado": "Cliente não vinculado",
    "data_servico_incompleta": "Data ou horário incompleto",
    "sem_responsavel": "Responsável não informado",
    "sem_observacao_operacional": "Observação operacional vazia",
    "valor_nao_informado": "Valor não informado",
}
RECURRENCE_STATUS_OPTIONS = {"ativo", "pausado", "encerrado"}
RECURRENCE_FREQUENCIES = {"semanal", "quinzenal", "mensal", "personalizada"}
CLIENT_BILLING_MODELS = {"mensal", "avulso", "orcamento"}
CLIENT_CLEANING_FREQUENCIES = {"semanal", "quinzenal", "mensal", "sob_demanda", "nao_aplica"}
CLIENT_SERVICE_PROFILES = {"limpeza_semanal", "instalacao", "retirada", "evento_avulso", "apoio"}
EVENT_STATUS_FLOW = [
    {"key": "rascunho", "label": "Rascunho", "description": "Cadastro iniciado, ainda sem confirmação operacional."},
    {"key": "confirmado", "label": "Confirmado", "description": "Cliente aprovou a locação e a operação deve preparar os dados."},
    {"key": "pendente_dados", "label": "Pendente de dados", "description": "Faltam dados essenciais para rota, OS/PDF ou cobrança."},
    {"key": "rota_pendente", "label": "Rota pendente", "description": "Dados principais existem, mas a rota ainda precisa ser gerada."},
    {"key": "os_pendente", "label": "OS pendente", "description": "Rota ou dados prontos, mas a ordem de serviço ainda precisa ser gerada."},
    {"key": "programado", "label": "Programado", "description": "Rota, OS e dados conferidos para execução."},
    {"key": "em_andamento", "label": "Em andamento", "description": "Entrega, instalação, permanência ou atendimento em execução."},
    {"key": "concluido", "label": "Concluído", "description": "Operação finalizada e pronta para fechamento financeiro."},
    {"key": "aguardando_pagamento", "label": "Aguardando pagamento", "description": "Serviço concluído ou faturado, ainda sem baixa financeira."},
    {"key": "pago", "label": "Pago", "description": "Fechamento recebido e registrado."},
    {"key": "cancelado", "label": "Cancelado", "description": "Evento cancelado ou sem continuidade."},
]
EVENT_STATUS_LABELS = {item["key"]: item["label"] for item in EVENT_STATUS_FLOW}
EVENT_STATUS_DESCRIPTIONS = {item["key"]: item["description"] for item in EVENT_STATUS_FLOW}
EVENT_STATUS_OPTIONS = set(EVENT_STATUS_LABELS)
EVENT_STATUS_ALIASES = {
    "novo": "rascunho",
    "orcamento": "rascunho",
    "orcamentacao": "rascunho",
    "proposta": "rascunho",
    "planejado": "programado",
    "em_preparacao": "programado",
    "em_execucao": "em_andamento",
    "em rota": "em_andamento",
    "em_rota": "em_andamento",
    "finalizado": "concluido",
    "finalizada": "concluido",
    "concluida": "concluido",
    "aguardando": "aguardando_pagamento",
    "pendente_pagamento": "aguardando_pagamento",
}
EVENT_STATUS_BADGE_CLASSES = {
    "rascunho": "badge-fixed",
    "confirmado": "badge-fixed",
    "pendente_dados": "badge-danger",
    "rota_pendente": "badge-avulso",
    "os_pendente": "badge-avulso",
    "programado": "badge-success",
    "em_andamento": "badge-avulso",
    "concluido": "badge-success",
    "aguardando_pagamento": "badge-danger",
    "pago": "badge-success",
    "cancelado": "badge-danger",
}
EVENT_STATUS_NEXT_STEPS = {
    "rascunho": {
        "message": "Revise os dados principais e confirme a locação quando o cliente aprovar.",
        "action": "Completar cadastro",
        "target_tab": "events-tab",
        "target_href": "#event-create-panel",
    },
    "confirmado": {
        "message": "Confira cliente, endereço, serviço, quantidade e responsável antes de gerar rota ou OS.",
        "action": "Revisar dados",
        "target_tab": "events-tab",
        "target_href": "#events-pane",
    },
    "pendente_dados": {
        "message": "Complete cliente, endereço, serviço e quantidade.",
        "action": "Corrigir dados",
        "target_tab": "events-tab",
        "target_href": "#events-pane",
    },
    "rota_pendente": {
        "message": "Gere a rota para orientar entrega, retirada ou atendimento.",
        "action": "Gerar rota",
        "target_tab": "operations-tab",
        "target_href": "#operations-pane",
    },
    "os_pendente": {
        "message": "Gere a ordem de serviço antes de liberar a operação.",
        "action": "Gerar OS",
        "target_tab": "events-tab",
        "target_href": "#events-pane",
    },
    "programado": {
        "message": "Acompanhe a execução no dia do evento e atualize para em andamento quando a equipe iniciar.",
        "action": "Acompanhar agenda",
        "target_tab": "agenda-tab",
        "target_href": "#agenda-operacional-panel",
    },
    "em_andamento": {
        "message": "Acompanhe a execução, confira checklist e finalize quando a operação terminar.",
        "action": "Revisar checklist",
        "target_tab": "events-tab",
        "target_href": "#events-pane",
    },
    "concluido": {
        "message": "Confira se há recebimento em aberto e lance a baixa quando necessário.",
        "action": "Ver financeiro",
        "target_tab": "summary-tab",
        "target_href": "#receivables-panel",
    },
    "aguardando_pagamento": {
        "message": "Lance recebimento ou acompanhe a cobrança até quitar.",
        "action": "Lançar recebimento",
        "target_tab": "summary-tab",
        "target_href": "#receivables-panel",
    },
    "pago": {
        "message": "Locação quitada. Mantenha o histórico para consulta.",
        "action": "Ver histórico",
        "target_tab": "events-tab",
        "target_href": "#events-pane",
    },
    "cancelado": {
        "message": "Locação cancelada. Não gere rota, OS ou cobrança sem reativar o cadastro.",
        "action": "Revisar cadastro",
        "target_tab": "events-tab",
        "target_href": "#events-pane",
    },
}
ACTIVE_EVENT_STATUSES = {
    "rascunho",
    "confirmado",
    "pendente_dados",
    "rota_pendente",
    "os_pendente",
    "programado",
    "em_andamento",
    "aguardando_pagamento",
}

app = Flask(__name__)
SECRET_KEY_VALUE = os.environ.get("SANNYGOLD_SECRET_KEY", "").strip()
SECRET_KEY_CONFIGURED = bool(SECRET_KEY_VALUE)
SECRET_KEY_ISSUES = validate_secret_key_value(SECRET_KEY_VALUE, production=IS_PRODUCTION)
if IS_PRODUCTION and SECRET_KEY_ISSUES:
    raise RuntimeError("Configuração insegura: " + " ".join(SECRET_KEY_ISSUES))
if IS_PRODUCTION and FLASK_DEBUG_ENABLED:
    raise RuntimeError("Configuração insegura: FLASK_DEBUG não pode ficar ativo em produção.")
app.config["SECRET_KEY"] = SECRET_KEY_VALUE or secrets.token_urlsafe(32)
app.config["MAX_CONTENT_LENGTH"] = UPLOAD_MAX_BYTES
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = IS_PRODUCTION or os.environ.get("SANNYGOLD_SESSION_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}
app.config["CSRF_ENABLED"] = os.environ.get("SANNYGOLD_CSRF_DISABLED", "").strip().lower() not in {"1", "true", "yes", "on"}


ROLES = {"guest", "admin", "operacional", "financeiro", "leitura"}
ROLE_PERMISSIONS = {
    "guest": {"public.view"},
    "leitura": {
        "public.view",
        "dashboard.view",
        "clients.view",
        "events.view",
        "fleet.view",
        "inventory.view",
        "routes.view",
        "warehouse.view",
    },
    "operacional": {
        "public.view",
        "dashboard.view",
        "clients.view",
        "clients.edit",
        "events.view",
        "events.create",
        "events.edit",
        "events.close",
        "events.service_order",
        "fleet.view",
        "fleet.edit",
        "inventory.view",
        "inventory.edit",
        "routes.view",
        "routes.generate",
        "operations.validate",
        "warehouse.view",
        "warehouse.edit",
    },
    "financeiro": {
        "public.view",
        "dashboard.view",
        "clients.view",
        "events.view",
        "fleet.view",
        "inventory.view",
        "routes.view",
        "finance.view",
        "finance.edit",
        "finance.payments",
        "finance.close",
        "finance.export",
        "warehouse.view",
    },
    "admin": {"*"},
}
AUDIT_ACTION_LABELS = {
    "access_denied": "Acesso bloqueado",
    "accept_invitation": "Convite aceito",
    "automatic": "Backup automático",
    "bulk_import": "Importação em lote",
    "cancel_invitation": "Convite cancelado",
    "change_password": "Senha alterada",
    "cleaning": "Limpeza registrada",
    "close": "Fechamento gerado",
    "create": "Criou",
    "create_password_reset": "Redefinição criada",
    "delete": "Excluiu",
    "duplicate": "Duplicou",
    "download": "Baixou arquivo",
    "excel_import": "Importou Excel",
    "field_confirmation": "Confirmação operacional",
    "generate": "Gerou",
    "generate_pdf": "Gerou PDF",
    "generate_recurrence": "Gerou recorrência",
    "generate_service_order": "Gerou ordem de serviço",
    "login": "Login",
    "logout": "Logout",
    "maintenance": "Manutenção",
    "movement": "Movimentação",
    "payment": "Pagamento",
    "quick_observation": "Observação rápida",
    "quick_rental": "Locação rápida",
    "recurrence_status": "Recorrência alterada",
    "release": "Equipamento liberado",
    "reissue_invitation": "Convite reenviado",
    "request_password_reset": "Redefinição solicitada",
    "reset_password": "Senha redefinida",
    "return": "Retorno registrado",
    "save": "Salvou",
    "status": "Status alterado",
    "support_ticket": "Chamado criado",
    "unanswered": "Dúvida registrada",
    "update": "Atualizou",
    "validate": "Validou",
}
AUDIT_MODULE_LABELS = {
    "attachments": "Anexos",
    "auth": "Acessos",
    "backup": "Backup",
    "clients": "Clientes",
    "closeout": "Fechamento",
    "equipment": "Equipamentos",
    "events": "Eventos/locações",
    "exports": "Exportações",
    "finance": "Financeiro",
    "fleet": "Veículos",
    "help_assistant": "Assistente",
    "help_knowledge": "Ajuda",
    "help_support": "Suporte",
    "help_unanswered": "Dúvidas",
    "operations": "Operação",
    "observations": "Observações",
    "permissions": "Permissões",
    "quotes": "Orçamentos",
    "reports": "Relatórios/PDFs",
    "routes": "Rotas",
    "users": "Usuários",
    "warehouse": "Almoxarifado",
}
AUDIT_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "csrf",
    "invitation_token",
    "password",
    "reset_token",
    "secret",
    "senha",
    "senha_hash",
    "token",
}
LOGIN_ATTEMPTS: dict[str, dict] = {}


def ensure_storage_dirs() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    for path in (
        CLIENTS_PATH,
        VEHICLES_PATH,
        EQUIPMENT_PATH,
        CONTRACTS_PATH,
        QUOTES_PATH,
        SERVICE_LOG_PATH,
        ATTACHMENTS_PATH,
        ROUTE_HISTORY_PATH,
        EVENTS_PATH,
        FIELD_CONFIRMATIONS_PATH,
        WAREHOUSE_ITEMS_PATH,
        WAREHOUSE_MOVEMENTS_PATH,
        AUDIT_LOG_PATH,
        FINANCIAL_RECEIVABLES_PATH,
        FINANCIAL_ENTRIES_PATH,
        FINANCIAL_CLOSEOUTS_PATH,
        HELP_UNANSWERED_PATH,
        HELP_SUPPORT_TICKETS_PATH,
    ):
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")
    ensure_users_file()
    if not SETTINGS_PATH.exists():
        SETTINGS_PATH.write_text(json.dumps({"cost_per_km": 0.0}, indent=2) + "\n", encoding="utf-8")
    if not OPERATION_VALIDATION_PATH.exists():
        OPERATION_VALIDATION_PATH.write_text(json.dumps({}, indent=2) + "\n", encoding="utf-8")
    if not FORECAST_AUDIT_PATH.exists():
        FORECAST_AUDIT_PATH.write_text(json.dumps({}, indent=2) + "\n", encoding="utf-8")
    if not HELP_KNOWLEDGE_BASE_PATH.exists():
        HELP_KNOWLEDGE_BASE_PATH.write_text(json.dumps(DEFAULT_HELP_KNOWLEDGE_BASE, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not HELP_METRICS_PATH.exists():
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


def ensure_users_file() -> None:
    if USERS_PATH.exists():
        return
    now = datetime.now().isoformat(timespec="seconds")
    default_email = clean_text(os.environ.get("SANNYGOLD_ADMIN_EMAIL"), "contato@sannygold.com").lower()
    default_password = os.environ.get("SANNYGOLD_ADMIN_PASSWORD", "Sanny123Gold")
    users = [
        {
            "id": "USR-001",
            "nome": os.environ.get("SANNYGOLD_ADMIN_NAME", "Administrador SannyGold"),
            "email": default_email,
            "senha_hash": generate_password_hash(default_password, method="pbkdf2:sha256"),
            "status": "ativo",
            "role": "admin",
            "must_change_password": True,
            "created_at": now,
            "updated_at": now,
        }
    ]
    USERS_PATH.write_text(json.dumps(users, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_planner_module():
    spec = importlib.util.spec_from_file_location("plan_routes", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load planner module from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


PLANNER = load_planner_module()


def clean_text(value: str | None, fallback: str = "") -> str:
    return (value or fallback).strip()


def csrf_token() -> str:
    token = clean_text(session.get(CSRF_SESSION_KEY))
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def request_csrf_token() -> str:
    for header_name in CSRF_HEADER_NAMES:
        token = clean_text(request.headers.get(header_name))
        if token:
            return token
    return clean_text(request.form.get(CSRF_FIELD_NAME))


def csrf_is_valid() -> bool:
    expected = clean_text(session.get(CSRF_SESSION_KEY))
    received = request_csrf_token()
    return bool(expected and received and hmac.compare_digest(expected, received))


def normalize_status_key(value: str | None, fallback: str = "") -> str:
    normalized = unicodedata.normalize("NFD", clean_text(value, fallback).lower())
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    for token in (" ", "-", "/", ".", "(", ")", ":"):
        without_marks = without_marks.replace(token, "_")
    while "__" in without_marks:
        without_marks = without_marks.replace("__", "_")
    return without_marks.strip("_")


def normalize_event_status(value: str | None, fallback: str = "rascunho") -> str:
    status = normalize_status_key(value, fallback)
    status = EVENT_STATUS_ALIASES.get(status, status)
    normalized_fallback = EVENT_STATUS_ALIASES.get(normalize_status_key(fallback, "rascunho"), "rascunho")
    return status if status in EVENT_STATUS_OPTIONS else normalized_fallback


def event_status_label(value: str | None) -> str:
    status = normalize_event_status(value)
    return EVENT_STATUS_LABELS.get(status, status.replace("_", " ").title())


def load_json_list(path: Path) -> list[dict]:
    ensure_storage_dirs()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_json_list(path: Path, items: list[dict]) -> None:
    ensure_storage_dirs()
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json_dict(path: Path) -> dict:
    ensure_storage_dirs()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_json_dict(path: Path, payload: dict) -> None:
    ensure_storage_dirs()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sort_by_label(items: list[dict], *fields: str) -> list[dict]:
    return sorted(items, key=lambda item: tuple(str(item.get(field) or "").lower() for field in fields))


def next_numeric_id(items: list[dict], prefix: str, field: str) -> str:
    used_numbers = []
    for item in items:
        raw = str(item.get(field) or "")
        digits = "".join(ch for ch in raw if ch.isdigit())
        if digits:
            used_numbers.append(int(digits))
    return f"{prefix}-{(max(used_numbers, default=0) + 1):03d}"


def load_route_data() -> dict | None:
    ensure_storage_dirs()
    if not ROUTE_JSON_PATH.exists():
        return None
    try:
        return json.loads(ROUTE_JSON_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def hhmm_to_minutes(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 2:
        return 0
    return int(parts[0]) * 60 + int(parts[1])


def load_clients() -> list[dict]:
    return load_json_list(CLIENTS_PATH)


def save_clients(clients: list[dict]) -> None:
    save_json_list(CLIENTS_PATH, sort_by_label(clients, "customer_name", "client_id"))


def load_vehicles_registry() -> list[dict]:
    return load_json_list(VEHICLES_PATH)


def save_vehicles_registry(vehicles: list[dict]) -> None:
    save_json_list(VEHICLES_PATH, sort_by_label(vehicles, "vehicle_id", "plate"))


def load_equipment_registry() -> list[dict]:
    return load_json_list(EQUIPMENT_PATH)


def save_equipment_registry(equipment_items: list[dict]) -> None:
    save_json_list(EQUIPMENT_PATH, sort_by_label(equipment_items, "equipment_type", "equipment_id"))


def load_contracts() -> list[dict]:
    return load_json_list(CONTRACTS_PATH)


def save_contracts(items: list[dict]) -> None:
    save_json_list(CONTRACTS_PATH, sort_by_label(items, "client_name", "id"))


def load_quotes() -> list[dict]:
    return load_json_list(QUOTES_PATH)


def save_quotes(items: list[dict]) -> None:
    ordered = sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    save_json_list(QUOTES_PATH, ordered)


def load_service_log() -> list[dict]:
    return load_json_list(SERVICE_LOG_PATH)


def save_service_log(items: list[dict]) -> None:
    ordered = sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    save_json_list(SERVICE_LOG_PATH, ordered[:1000])


def load_attachments() -> list[dict]:
    return load_json_list(ATTACHMENTS_PATH)


def save_attachments(items: list[dict]) -> None:
    ordered = sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    save_json_list(ATTACHMENTS_PATH, ordered[:1000])


def uploaded_asset_url(field_name: str) -> str:
    uploaded = request.files.get(field_name)
    if uploaded is None or uploaded.filename is None or not uploaded.filename.strip():
        return ""
    safe_name, extension = validate_uploaded_file(
        uploaded,
        field_label="imagem",
        allowed_extensions=IMAGE_UPLOAD_EXTENSIONS,
        allowed_label="JPG, PNG, WEBP ou GIF",
    )
    safe_name = safe_name or f"foto{extension}"
    destination_dir = UPLOADS_DIR / "assets"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}-{safe_name}"
    uploaded.save(destination)
    return url_for("uploaded_asset", filename=destination.name)


def uploaded_asset_path_from_url(value: str | None) -> Path | None:
    parsed = urllib.parse.urlparse(clean_text(value))
    url_path = parsed.path or clean_text(value)
    prefix = "/uploads/assets/"
    if not url_path.startswith(prefix):
        return None
    filename = Path(url_path).name
    if not filename:
        return None
    target = (UPLOADS_DIR / "assets" / filename).resolve()
    assets_dir = (UPLOADS_DIR / "assets").resolve()
    return target if target.parent == assets_dir else None


def parse_decimal(value, fallback: float = 0.0) -> float:
    text = str(value if value is not None else fallback).strip().replace(",", ".")
    try:
        return round(float(text), 2)
    except (TypeError, ValueError):
        return fallback


def load_warehouse_items() -> list[dict]:
    return load_json_list(WAREHOUSE_ITEMS_PATH)


def save_warehouse_items(items: list[dict]) -> None:
    save_json_list(WAREHOUSE_ITEMS_PATH, sort_by_label(items, "category", "name", "id"))


def load_warehouse_movements() -> list[dict]:
    return load_json_list(WAREHOUSE_MOVEMENTS_PATH)


def save_warehouse_movements(movements: list[dict]) -> None:
    ordered = sorted(movements, key=lambda item: str(item.get("created_at") or ""))
    save_json_list(WAREHOUSE_MOVEMENTS_PATH, ordered[-1000:])


def load_audit_log() -> list[dict]:
    return load_json_list(AUDIT_LOG_PATH)


def save_audit_log(items: list[dict]) -> None:
    ordered = sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    save_json_list(AUDIT_LOG_PATH, ordered[:1000])


def load_financial_receivables() -> list[dict]:
    return load_json_list(FINANCIAL_RECEIVABLES_PATH)


def save_financial_receivables(items: list[dict]) -> None:
    ordered = sorted(items, key=lambda item: (str(item.get("due_date") or ""), str(item.get("client_name") or "")))
    save_json_list(FINANCIAL_RECEIVABLES_PATH, ordered)


def load_financial_entries() -> list[dict]:
    return load_json_list(FINANCIAL_ENTRIES_PATH)


def save_financial_entries(items: list[dict]) -> None:
    ordered = sorted(items, key=lambda item: str(item.get("entry_date") or ""), reverse=True)
    save_json_list(FINANCIAL_ENTRIES_PATH, ordered)


def load_financial_closeouts() -> list[dict]:
    return load_json_list(FINANCIAL_CLOSEOUTS_PATH)


def save_financial_closeouts(items: list[dict]) -> None:
    ordered = sorted(items, key=lambda item: str(item.get("period") or ""), reverse=True)
    save_json_list(FINANCIAL_CLOSEOUTS_PATH, ordered)


def create_financial_receivable_record(form, existing_items: list[dict] | None = None) -> dict:
    items = existing_items if existing_items is not None else load_financial_receivables()
    item_id = clean_text(form.get("receivable_id")) or next_numeric_id(items, "REC", "id")
    current = next((item for item in items if clean_text(item.get("id")) == item_id), {})
    amount = parse_decimal(form.get("amount"))
    if amount <= 0:
        raise ValueError("Informe um valor a receber maior que zero. Sem valor, a cobrança não entra no controle financeiro.")
    status = clean_text(form.get("status"), "aguardando").lower()
    if status not in {"aguardando", "parcial", "pago", "vencido"}:
        raise ValueError("Status de recebimento inválido. Escolha aguardando, parcial, pago ou vencido.")
    now = now_iso()
    return {
        "id": item_id,
        "client_id": clean_text(form.get("client_id")),
        "client_name": clean_text(form.get("client_name")) or "Cliente não informado",
        "client_phone": clean_text(form.get("client_phone") or form.get("phone")),
        "event_id": clean_text(form.get("event_id")),
        "event_title": clean_text(form.get("event_title")),
        "service_type": clean_text(form.get("service_type"), "Banheiro Luxo") or "Banheiro Luxo",
        "amount": amount,
        "amount_received": parse_decimal(form.get("amount_received")),
        "due_date": clean_text(form.get("due_date")),
        "received_date": clean_text(form.get("received_date")),
        "status": status,
        "payment_method": clean_text(form.get("payment_method")),
        "invoice_status": clean_text(form.get("invoice_status"), "sem_nota") or "sem_nota",
        "invoice_number": clean_text(form.get("invoice_number")),
        "last_contact": clean_text(form.get("last_contact")),
        "collection_status": clean_text(form.get("collection_status")),
        "attachment_url": clean_text(form.get("attachment_url")),
        "attachment_note": clean_text(form.get("attachment_note")),
        "notes": clean_text(form.get("notes")),
        "created_at": clean_text(current.get("created_at")) or now,
        "updated_at": now,
    }


def create_financial_entry_record(form, existing_items: list[dict] | None = None) -> dict:
    items = existing_items if existing_items is not None else load_financial_entries()
    item_id = clean_text(form.get("entry_id")) or next_numeric_id(items, "LAN", "id")
    current = next((item for item in items if clean_text(item.get("id")) == item_id), {})
    entry_type = clean_text(form.get("entry_type"), "saida").lower()
    if entry_type not in {"entrada", "saida"}:
        raise ValueError("Tipo de lançamento financeiro inválido. Escolha entrada ou saída antes de salvar.")
    amount = parse_decimal(form.get("amount"))
    if amount <= 0:
        raise ValueError("Informe um valor de lançamento maior que zero. Lançamento sem valor não altera o financeiro.")
    now = now_iso()
    return {
        "id": item_id,
        "entry_type": entry_type,
        "category": clean_text(form.get("category"), "outros") or "outros",
        "description": clean_text(form.get("description")) or "Lançamento financeiro",
        "amount": amount,
        "entry_date": clean_text(form.get("entry_date")) or datetime.now().date().isoformat(),
        "status": clean_text(form.get("status"), "realizado") or "realizado",
        "client_id": clean_text(form.get("client_id")),
        "event_id": clean_text(form.get("event_id")),
        "attachment_url": clean_text(form.get("attachment_url")),
        "attachment_note": clean_text(form.get("attachment_note")),
        "notes": clean_text(form.get("notes")),
        "created_at": clean_text(current.get("created_at")) or now,
        "updated_at": now,
    }


def create_quote_record(form, existing_items: list[dict] | None = None, *, source: str = "interno") -> dict:
    items = existing_items if existing_items is not None else load_quotes()
    quote_id = clean_text(form.get("quote_id")) or next_numeric_id(items, "ORC", "id")
    customer_name = clean_text(form.get("customer_name"))
    phone = clean_text(form.get("phone"))
    event_address = clean_text(form.get("event_address") or form.get("address"))
    equipment_type = clean_text(form.get("equipment_type"), "Banheiro Luxo") or "Banheiro Luxo"
    quantity = int(clean_text(form.get("equipment_quantity"), "1") or 1)
    billing_model = clean_text(form.get("billing_model"), "orcamento") or "orcamento"
    cleaning_frequency = clean_text(form.get("cleaning_frequency"), "semanal") or "semanal"
    monthly_value = parse_decimal(form.get("monthly_value"))
    event_value = parse_decimal(form.get("event_value"))
    if not customer_name or not phone:
        raise ValueError("Informe nome e telefone para o orçamento. Sem contato, a equipe não consegue retornar ao cliente.")
    if quantity <= 0:
        raise ValueError("Quantidade do orçamento deve ser maior que zero. Informe quantos itens ou serviços serão cotados.")
    now = now_iso()
    current = next((item for item in items if clean_text(item.get("id")) == quote_id), {})
    return {
        "id": quote_id,
        "customer_name": customer_name,
        "contact_name": clean_text(form.get("contact_name")),
        "phone": phone,
        "email": clean_text(form.get("email")),
        "event_address": event_address,
        "event_date": clean_text(form.get("event_date")),
        "event_end_date": clean_text(form.get("event_end_date")),
        "equipment_type": equipment_type,
        "equipment_quantity": quantity,
        "billing_model": billing_model if billing_model in CLIENT_BILLING_MODELS else "orcamento",
        "cleaning_frequency": cleaning_frequency if cleaning_frequency in CLIENT_CLEANING_FREQUENCIES else "semanal",
        "monthly_value": monthly_value,
        "event_value": event_value,
        "status": clean_text(form.get("status"), "novo") or "novo",
        "notes": clean_text(form.get("notes")),
        "source": source,
        "created_at": clean_text(current.get("created_at")) or now,
        "updated_at": now,
    }


def quick_rental_service_from_form(form) -> tuple[str, str, str]:
    service_type = clean_text(form.get("service_type"))
    option = QUICK_RENTAL_SERVICE_BY_VALUE.get(service_type)
    if option:
        equipment_type = clean_text(form.get("equipment_type")) or clean_text(option.get("equipment_type"))
        label = clean_text(option.get("label"))
    else:
        equipment_type = clean_text(form.get("equipment_type"))
        label = equipment_type
        service_type = service_type or "outro"
    if service_type == "outro":
        equipment_type = clean_text(form.get("other_service")) or equipment_type
        label = equipment_type or "Outro serviço"
    return service_type, equipment_type, label


def validate_quick_rental_required_fields(
    *,
    customer_name: str,
    phone: str,
    event_date: str,
    address: str,
    equipment_type: str,
    quantity: int,
    service_value: float,
    responsible: str,
    notes: str,
) -> list[str]:
    missing = []
    if not customer_name:
        missing.append("cliente")
    if not phone:
        missing.append("telefone/WhatsApp")
    if not event_date:
        missing.append("data do evento/serviço")
    if not address:
        missing.append("endereço completo")
    if not equipment_type:
        missing.append("tipo de serviço")
    if quantity <= 0:
        missing.append("quantidade")
    if service_value <= 0:
        missing.append("valor previsto")
    if not responsible:
        missing.append("responsável interno")
    if not notes:
        missing.append("observações operacionais")
    return missing


def record_text(record: dict | None, key: str) -> str:
    if not record:
        return ""
    value = record.get(key)
    if value is None:
        return ""
    return clean_text(str(value))


MESSAGE_CONTEXTS = {
    "general": {
        "title": "Erro: ação não concluída",
        "intro": "Não foi possível concluir a ação porque alguma informação está ausente ou inconsistente. O sistema bloqueou a operação para evitar cadastro incorreto ou perda de dados.",
        "next": "Revise os dados informados e tente novamente. Se a mensagem aparecer de novo, acione um administrador com o que você estava tentando fazer.",
        "target_href": "#central-day-panel",
        "target_tab": "summary-tab",
        "action": "Voltar para a Central do Dia",
    },
    "access": {
        "title": "Acesso restrito para o seu perfil",
        "intro": "Esta função não está liberada para o seu perfil. O sistema bloqueou a ação para proteger cadastros, financeiro ou configurações sensíveis.",
        "next": "Entre com uma conta autorizada ou peça ao administrador para ajustar seu perfil de acesso.",
        "target_href": "#access-management-panel",
        "target_tab": "access-tab",
        "action": "Ver acessos",
    },
    "login": {
        "title": "Não foi possível entrar",
        "intro": "O login não foi concluído porque o e-mail, a senha ou o status do usuário precisam ser corrigidos antes do acesso.",
        "next": "Confira e-mail e senha. Se o convite estiver pendente, peça um novo link ao administrador.",
        "target_href": "#login-panel",
        "target_tab": "summary-tab",
        "action": "Tentar novamente",
    },
    "client": {
        "title": "Cliente não foi salvo",
        "intro": "Não foi possível salvar o cliente porque faltam dados obrigatórios ou existe conflito com outro cadastro.",
        "next": "Complete nome, telefone, endereço completo, coordenadas e informações do serviço antes de salvar novamente.",
        "target_href": "#manual-client-form",
        "target_tab": "clients-tab",
        "action": "Corrigir cliente",
    },
    "event": {
        "title": "Evento/locação não foi salvo",
        "intro": "Não foi possível salvar o evento porque faltam dados necessários para operação, financeiro ou geração de documentos.",
        "next": "Revise nome, data, cliente vinculado, responsável, observações, equipamentos, veículos e valores quando aplicável.",
        "target_href": "#event-create-panel",
        "target_tab": "events-tab",
        "action": "Corrigir evento",
    },
    "quick_rental": {
        "title": "Locação rápida não foi salva",
        "intro": "Não foi possível salvar a locação rápida porque há campos obrigatórios sem preenchimento. A locação não é criada enquanto esses dados estiverem incompletos.",
        "next": "Complete cliente, telefone, data, endereço, serviço, quantidade, valor, responsável e observações. Depois confira o resumo e salve novamente.",
        "target_href": "#quick-rental-panel",
        "target_tab": "summary-tab",
        "action": "Corrigir locação",
    },
    "route": {
        "title": "Rota não foi gerada",
        "intro": "Não foi possível gerar a rota porque a operação ainda tem dados incompletos. Gerar rota assim poderia enviar equipe, veículo ou equipamento para informação errada.",
        "next": "Revise cliente, telefone, endereço, data, serviço, quantidade, veículo e responsável antes de gerar novamente.",
        "target_href": "#gerador",
        "target_tab": "operations-tab",
        "action": "Corrigir rota",
    },
    "service_order": {
        "title": "Ordem de serviço/PDF não foi gerado",
        "intro": "Não foi possível gerar o documento porque faltam dados que a equipe precisa receber com segurança.",
        "next": "Revise cliente, local, data, horário, serviço, quantidade, observações, responsável e valor quando o documento também servir para controle financeiro.",
        "target_href": "#events-pane",
        "target_tab": "events-tab",
        "action": "Revisar evento",
    },
    "finance": {
        "title": "Financeiro não foi atualizado",
        "intro": "Não foi possível concluir o lançamento financeiro porque valor, status, período ou cobrança precisam ser corrigidos.",
        "next": "Confira cliente, vencimento, valor, status de pagamento e período antes de salvar novamente.",
        "target_href": "#receivables-panel",
        "target_tab": "summary-tab",
        "action": "Corrigir financeiro",
    },
    "upload": {
        "title": "Arquivo não foi enviado",
        "intro": "Não foi possível aceitar o arquivo porque ele está ausente, muito grande, com nome inválido ou em formato não permitido.",
        "next": "Envie o arquivo correto no formato indicado na tela e tente novamente.",
        "target_href": "#attachments-panel",
        "target_tab": "clients-tab",
        "action": "Revisar arquivo",
    },
    "backup": {
        "title": "Backup não foi concluído",
        "intro": "Não foi possível concluir o backup agora. O sistema protegeu os dados atuais e não apagou os arquivos originais.",
        "next": "Tente gerar o backup novamente. Se continuar falhando, verifique a pasta de backups e permissões do servidor.",
        "target_href": "#admin-backup-panel",
        "target_tab": "access-tab",
        "action": "Abrir backups",
    },
    "warehouse": {
        "title": "Almoxarifado não foi atualizado",
        "intro": "Não foi possível atualizar o almoxarifado porque algum item, quantidade ou movimentação está inconsistente.",
        "next": "Revise o material, o tipo de movimentação e o saldo antes de salvar novamente.",
        "target_href": "#warehouse-pane",
        "target_tab": "warehouse-tab",
        "action": "Corrigir almoxarifado",
    },
    "fleet": {
        "title": "Frota ou equipamento não foi salvo",
        "intro": "Não foi possível salvar porque faltam dados ou existe conflito de uso com outro cliente/evento.",
        "next": "Revise veículo, equipamento, vínculo, status e disponibilidade antes de salvar novamente.",
        "target_href": "#fleet-pane",
        "target_tab": "fleet-tab",
        "action": "Corrigir frota",
    },
}


FRIENDLY_ERROR_PATTERNS = (
    ("preencha id, nome, endereco, latitude e longitude do cliente", "Não foi possível salvar o cliente porque falta nome, endereço completo ou coordenada. Sem isso, o sistema não consegue colocar o cliente na rota.", "Complete o endereço e use a busca de coordenadas antes de salvar."),
    ("servico, prioridade e quantidade devem ser maiores que zero", "Não foi possível salvar porque serviço, prioridade ou quantidade estão zerados. Esses campos são necessários para calcular rota, equipe e equipamento.", "Informe valores maiores que zero e salve novamente."),
    ("janela do evento deve ter hora inicial menor", "Não foi possível salvar porque a janela de atendimento termina antes de começar. Isso impede o planejamento correto da rota.", "Ajuste a hora inicial e final para o período real de atendimento."),
    ("ja esta vinculado ao cliente", "Não foi possível usar esse equipamento porque ele já está vinculado a outro cliente. Reutilizar o mesmo item pode causar conflito operacional.", "Escolha outro equipamento ou libere o vínculo atual antes de continuar."),
    ("nao pode ser reservado", "Não foi possível reservar o equipamento porque o status atual bloqueia o uso operacional.", "Marque o equipamento como disponível ou escolha outro item."),
    ("informe nome e data inicial do evento", "Não foi possível salvar o evento porque faltam nome e data. Sem esses dados, a equipe não sabe qual operação executar nem quando.", "Preencha o nome da locação/evento e a data do serviço."),
    ("informe a nova data da locacao duplicada", "Não foi possível duplicar a locação porque a nova data não foi informada. A data antiga não é copiada automaticamente para evitar erro na agenda.", "Informe a nova data, revise endereço, quantidade e valor, e salve a nova locação."),
    ("informe datas validas para o evento", "Não foi possível salvar o evento porque a data informada não é válida. Datas inválidas impedem agenda, rota e documentos.", "Corrija a data do evento e tente salvar novamente."),
    ("data final do evento nao pode ser anterior", "Não foi possível salvar o evento porque a data final vem antes da data inicial. Isso deixaria a agenda inconsistente.", "Ajuste a data final para ser igual ou posterior à data inicial."),
    ("nenhum cliente vinculado ao evento", "Não foi possível gerar a rota porque o evento não tem cliente vinculado. Sem cliente, não há endereço, telefone nem serviço para a equipe.", "Vincule pelo menos um cliente ao evento antes de gerar a rota."),
    ("cadastre pelo menos um endereco", "Não foi possível gerar a rota porque não há endereço cadastrado ou arquivo de entregas. A rota precisa de paradas válidas.", "Cadastre clientes com endereço completo ou envie o CSV de entregas."),
    ("cadastre pelo menos um veiculo", "Não foi possível gerar a rota porque não há veículo disponível. Sem veículo, a operação não pode ser distribuída.", "Cadastre ou vincule um veículo antes de gerar a rota."),
    ("nenhum veiculo vinculado ao evento", "Não foi possível gerar a rota porque o evento não tem veículo vinculado. Isso impede definir quem executa a operação.", "Vincule um veículo ao evento ou gere com a frota cadastrada."),
    ("envie o arquivo de", "Não foi possível continuar porque o arquivo obrigatório não foi enviado.", "Selecione o arquivo indicado e envie novamente."),
    ("nome do arquivo enviado e invalido", "Não foi possível aceitar o arquivo porque o nome não é seguro para gravação.", "Renomeie o arquivo sem símbolos especiais e tente enviar de novo."),
    ("formato de arquivo nao permitido", "Não foi possível aceitar o arquivo porque o formato não é permitido para essa ação.", "Envie o arquivo no formato indicado na tela."),
    ("arquivo muito grande", "Não foi possível enviar o arquivo porque ele ultrapassa o tamanho máximo aceito.", "Reduza o arquivo ou envie uma versão menor."),
    ("informe um valor a receber maior que zero", "Não foi possível salvar a cobrança porque o valor está zerado. Uma conta a receber precisa ter valor para entrar no financeiro.", "Informe o valor previsto da cobrança e salve novamente."),
    ("status de recebimento invalido", "Não foi possível salvar a cobrança porque o status escolhido não é aceito.", "Escolha um status da lista e salve novamente."),
    ("tipo de lancamento financeiro invalido", "Não foi possível salvar o lançamento porque o tipo financeiro não é aceito.", "Escolha entrada ou saída e tente novamente."),
    ("informe um valor de lancamento maior que zero", "Não foi possível salvar o lançamento porque o valor está zerado.", "Informe um valor maior que zero antes de salvar."),
    ("conta a receber nao encontrada", "Não foi possível atualizar a cobrança porque ela não foi encontrada na base atual.", "Atualize a tela e selecione uma cobrança existente."),
    ("informe nome e telefone para o orcamento", "Não foi possível salvar o orçamento porque faltam nome e telefone do cliente. Sem contato, a equipe não consegue retornar.", "Preencha nome e telefone antes de salvar o orçamento."),
    ("quantidade do orcamento deve ser maior que zero", "Não foi possível salvar o orçamento porque a quantidade está zerada.", "Informe a quantidade de banheiros, trailers, climatizadores ou pontos de hidratação."),
    ("preencha os campos obrigatorios da locacao rapida", "Não foi possível salvar a locação rápida porque faltam campos obrigatórios. A locação não é criada para evitar evento incompleto.", "Complete os campos listados na mensagem e confirme o resumo novamente."),
    ("cliente nao encontrado", "Não foi possível concluir porque o cliente selecionado não foi encontrado na base atual.", "Atualize a tela ou selecione um cliente existente."),
    ("evento nao encontrado", "Não foi possível concluir porque o evento selecionado não foi encontrado na base atual.", "Atualize a tela e selecione um evento existente."),
    ("usuario nao encontrado", "Usuário não encontrado. Não foi possível concluir porque o usuário selecionado não existe na base atual.", "Atualize o painel de acessos e selecione um usuário existente."),
    ("role invalida", "Não foi possível salvar o usuário porque o perfil escolhido não existe.", "Escolha Admin, Operacional, Financeiro ou Leitura."),
    ("ja existe usuario com este email", "Não foi possível criar o usuário porque esse e-mail já está cadastrado.", "Edite o usuário existente ou use outro e-mail."),
    ("estoque insuficiente", "Não foi possível registrar a movimentação porque o saldo ficaria negativo. Isso evita divergência no almoxarifado.", "Confira o estoque atual ou confirme uma entrada antes da saída."),
    ("google maps nao conseguiu geocodificar", "Não foi possível encontrar coordenadas para esse endereço. Sem coordenadas, a rota pode ficar incorreta.", "Revise rua, número, bairro e cidade antes de buscar novamente."),
    ("endereco nao encontrado para geocodificacao", "Não foi possível encontrar o endereço informado.", "Confira se o endereço está completo com número, bairro e cidade."),
    ("mes no formato aaaa-mm", "Não foi possível processar o período financeiro porque o mês está em formato inválido.", "Informe o período como AAAA-MM, por exemplo 2026-05."),
)


TECHNICAL_ERROR_MARKERS = (
    "attributeerror",
    "keyerror",
    "typeerror",
    "traceback",
    "object has no attribute",
    "none",
    "undefined",
    "jsondecodeerror",
    "permission denied",
    "errno",
    "no such file",
)


def normalize_for_message_match(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", clean_text(value))
    without_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return without_marks.lower()


def user_message_item(title: str, detail: str, *, target_href: str, target_tab: str, action: str) -> dict:
    return {
        "title": clean_text(title),
        "detail": clean_text(detail),
        "target_href": clean_text(target_href),
        "target_tab": clean_text(target_tab),
        "action": clean_text(action),
    }


def user_message_payload(title: str, intro: str, *, item_title: str = "Próximo passo", item_detail: str = "", target_href: str = "#central-day-panel", target_tab: str = "summary-tab", action: str = "Abrir painel") -> dict:
    items = []
    if item_detail:
        items.append(user_message_item(item_title, item_detail, target_href=target_href, target_tab=target_tab, action=action))
    return {
        "title": clean_text(title),
        "intro": clean_text(intro),
        "items": items,
    }


def friendly_error_parts(exc, context: str = "general") -> tuple[str, str, str, dict]:
    context_data = MESSAGE_CONTEXTS.get(context, MESSAGE_CONTEXTS["general"])
    raw = clean_text(str(exc))
    normalized = normalize_for_message_match(raw)
    for pattern, intro, next_step in FRIENDLY_ERROR_PATTERNS:
        if pattern in normalized:
            if "preencha os campos obrigatorios da locacao rapida" in pattern and ":" in raw:
                missing = raw.split(":", 1)[1].strip().rstrip(".")
                intro = f"Não foi possível salvar a locação rápida porque faltam: {missing}. A locação não é criada para evitar evento incompleto."
                next_step = f"Preencha os campos obrigatórios da locação rápida: {missing}. Depois confira o resumo e salve novamente."
            return clean_text(context_data["title"]), intro, next_step, context_data
    if raw and not any(marker in normalized for marker in TECHNICAL_ERROR_MARKERS):
        return (
            clean_text(context_data["title"]),
            f"{context_data['intro']} Detalhe: {raw}",
            clean_text(context_data["next"]),
            context_data,
        )
    return clean_text(context_data["title"]), clean_text(context_data["intro"]), clean_text(context_data["next"]), context_data


def friendly_error_payload(exc, context: str = "general") -> dict:
    title, intro, next_step, context_data = friendly_error_parts(exc, context)
    return user_message_payload(
        title,
        intro,
        item_detail=next_step,
        target_href=context_data["target_href"],
        target_tab=context_data["target_tab"],
        action=context_data["action"],
    )


def friendly_error_text(exc, context: str = "general") -> str:
    title, intro, next_step, _context_data = friendly_error_parts(exc, context)
    return f"{title}. {intro} Próximo passo: {next_step}"


def flash_action_error(exc, context: str = "general") -> None:
    flash(friendly_error_payload(exc, context), "danger")


def flash_action_warning(title: str, intro: str, *, next_step: str, target_href: str = "#central-day-panel", target_tab: str = "summary-tab", action: str = "Abrir painel") -> None:
    flash(user_message_payload(title, intro, item_detail=next_step, target_href=target_href, target_tab=target_tab, action=action), "warning")


def flash_action_success(title: str, intro: str, *, next_step: str = "", target_href: str = "#central-day-panel", target_tab: str = "summary-tab", action: str = "Abrir painel") -> None:
    flash(user_message_payload(title, intro, item_detail=next_step, target_href=target_href, target_tab=target_tab, action=action), "success")


def upsert_contract_from_client(client: dict) -> None:
    if clean_text(client.get("client_type")) != "fixo" or clean_text(client.get("billing_model")) != "mensal":
        return
    contracts = load_contracts()
    existing = next((item for item in contracts if clean_text(item.get("client_id")) == clean_text(client.get("client_id"))), {})
    now = now_iso()
    contract = {
        "id": clean_text(existing.get("id")) or f"CTR-{clean_text(client.get('client_id')) or uuid4().hex[:6]}",
        "client_id": clean_text(client.get("client_id")),
        "client_name": clean_text(client.get("customer_name")),
        "equipment_id": clean_text(client.get("equipment_number")),
        "equipment_type": clean_text(client.get("equipment_type")),
        "equipment_quantity": int(client.get("equipment_quantity") or 1),
        "monthly_value": parse_decimal(client.get("service_value")),
        "cleaning_frequency": clean_text(client.get("cleaning_frequency"), "semanal") or "semanal",
        "service_profile": clean_text(client.get("service_profile"), "limpeza_semanal") or "limpeza_semanal",
        "status": clean_text(existing.get("status"), "ativo") or "ativo",
        "start_date": clean_text(existing.get("start_date")) or datetime.now().date().isoformat(),
        "next_billing_date": clean_text(existing.get("next_billing_date")),
        "notes": clean_text(existing.get("notes")),
        "created_at": clean_text(existing.get("created_at")) or now,
        "updated_at": now,
    }
    save_contracts(upsert_item(contracts, contract, "id"))


def generate_monthly_contract_receivables(period: str, due_day: int = 10) -> list[dict]:
    try:
        year, month = [int(part) for part in period.split("-", 1)]
        due_day = min(max(int(due_day), 1), 28)
        due_date = datetime(year, month, due_day).date().isoformat()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Informe o mês no formato AAAA-MM.") from exc
    contracts = [
        item for item in load_contracts()
        if clean_text(item.get("status"), "ativo") == "ativo" and parse_decimal(item.get("monthly_value")) > 0
    ]
    receivables = load_financial_receivables()
    created: list[dict] = []
    for contract in contracts:
        contract_id = clean_text(contract.get("id"))
        already_exists = any(
            clean_text(item.get("contract_id")) == contract_id and clean_text(item.get("billing_period")) == period
            for item in receivables
        )
        if already_exists:
            continue
        record = {
            "id": next_numeric_id(receivables, "REC", "id"),
            "client_id": clean_text(contract.get("client_id")),
            "client_name": clean_text(contract.get("client_name")),
            "client_phone": "",
            "event_id": "",
            "event_title": f"Mensalidade {period}",
            "service_type": clean_text(contract.get("equipment_type"), "Banheiro Luxo") or "Banheiro Luxo",
            "amount": parse_decimal(contract.get("monthly_value")),
            "amount_received": 0.0,
            "due_date": due_date,
            "received_date": "",
            "status": "aguardando",
            "payment_method": "",
            "invoice_status": "sem_nota",
            "invoice_number": "",
            "last_contact": "",
            "collection_status": "mensalidade_gerada",
            "attachment_url": "",
            "attachment_note": "",
            "notes": f"Contrato mensal {contract_id} com limpeza {contract.get('cleaning_frequency') or 'semanal'}.",
            "contract_id": contract_id,
            "billing_period": period,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        receivables.append(record)
        created.append(record)
    save_financial_receivables(receivables)
    return created


def build_receipt_pdf(receivable: dict) -> bytes:
    lines = [
        f"Recibo: {receivable.get('id')}",
        f"Cliente: {receivable.get('client_name')}",
        f"Referência: {receivable.get('event_title') or receivable.get('service_type') or 'Cobrança'}",
        f"Valor: {format_currency_br(receivable.get('amount'))}",
        f"Recebido: {format_currency_br(receivable.get('amount_received'))}",
        f"Forma de pagamento: {receivable.get('payment_method') or 'n/d'}",
        f"Data de recebimento: {format_date_br(receivable.get('received_date'))}",
        f"Nota fiscal: {receivable.get('invoice_number') or receivable.get('invoice_status') or 'n/d'}",
        f"Observações: {receivable.get('notes') or 'n/d'}",
    ]
    return build_simple_text_pdf(f"SannyGold - Recibo {receivable.get('id')}", lines)


def cleaning_frequency_days(value: str | None) -> int:
    return {
        "semanal": 7,
        "quinzenal": 14,
        "mensal": 30,
        "sob_demanda": 0,
        "nao_aplica": 0,
    }.get(clean_text(value), 0)


def build_cleaning_agenda(clients: list[dict], service_log: list[dict], *, days_ahead: int = 28) -> list[dict]:
    today = datetime.now().date()
    logged = {
        (clean_text(item.get("client_id")), clean_text(item.get("service_date")))
        for item in service_log
        if clean_text(item.get("service_type")) == "limpeza"
    }
    agenda = []
    for client in clients:
        if clean_text(client.get("client_type")) != "fixo":
            continue
        step = cleaning_frequency_days(client.get("cleaning_frequency"))
        if step <= 0:
            continue
        current = today
        for _ in range(max(1, days_ahead // step)):
            date_text = current.isoformat()
            agenda.append(
                {
                    "client_id": clean_text(client.get("client_id")),
                    "client_name": clean_text(client.get("customer_name")),
                    "address": clean_text(client.get("address")),
                    "equipment_id": clean_text(client.get("equipment_number")),
                    "equipment_type": clean_text(client.get("equipment_type")),
                    "cleaning_frequency": clean_text(client.get("cleaning_frequency")),
                    "service_date": date_text,
                    "status": "executada" if (clean_text(client.get("client_id")), date_text) in logged else "prevista",
                }
            )
            current = current + timedelta(days=step)
    return sorted(agenda, key=lambda item: (item["service_date"], item["client_name"]))[:60]


def build_contract_financial_dashboard(contracts: list[dict], service_log: list[dict]) -> dict:
    active = [item for item in contracts if clean_text(item.get("status"), "ativo") == "ativo"]
    monthly_revenue = round2(sum(parse_decimal(item.get("monthly_value")) for item in active))
    cleanings_by_client: dict[str, int] = {}
    for item in service_log:
        if clean_text(item.get("service_type")) == "limpeza":
            client_id = clean_text(item.get("client_id"))
            cleanings_by_client[client_id] = cleanings_by_client.get(client_id, 0) + 1
    rows = []
    for contract in active:
        client_id = clean_text(contract.get("client_id"))
        cleanings = cleanings_by_client.get(client_id, 0)
        monthly_value = parse_decimal(contract.get("monthly_value"))
        rows.append(
            {
                **contract,
                "cleanings_done": cleanings,
                "revenue_per_cleaning": round2(monthly_value / cleanings) if cleanings else monthly_value,
            }
        )
    return {
        "active_count": len(active),
        "monthly_revenue": monthly_revenue,
        "cleanings_done": sum(cleanings_by_client.values()),
        "rows": rows[:12],
    }


def build_maintenance_preventive_dashboard(equipment_items: list[dict], service_log: list[dict]) -> dict:
    cleanings_by_equipment: dict[str, int] = {}
    for item in service_log:
        equipment_id = clean_text(item.get("equipment_id"))
        if equipment_id and clean_text(item.get("service_type")) == "limpeza":
            cleanings_by_equipment[equipment_id] = cleanings_by_equipment.get(equipment_id, 0) + 1
    alerts = []
    for equipment in equipment_items:
        equipment_id = clean_text(equipment.get("equipment_id"))
        cleanings = cleanings_by_equipment.get(equipment_id, 0)
        if cleanings >= 12 and clean_text(equipment.get("status")) not in BLOCKED_EQUIPMENT_STATUSES:
            alerts.append(
                {
                    "equipment_id": equipment_id,
                    "equipment_type": clean_text(equipment.get("equipment_type")),
                    "cleanings": cleanings,
                    "level": "warning" if cleanings < 20 else "danger",
                    "message": "Revisão preventiva recomendada" if cleanings < 20 else "Revisão preventiva urgente",
                }
            )
    return {"alerts": alerts[:12], "total_alerts": len(alerts)}


def audit_label(labels: dict[str, str], value: str | None, fallback: str = "Geral") -> str:
    text = clean_text(value)
    if not text:
        return fallback
    return labels.get(text, text.replace("_", " ").replace("-", " ").title())


def audit_request_metadata() -> dict:
    if not has_request_context():
        return {}
    forwarded_for = clean_text(request.headers.get("X-Forwarded-For")).split(",")[0].strip()
    user_agent = clean_text(request.headers.get("User-Agent"))
    return {
        "ip_address": forwarded_for or clean_text(request.remote_addr),
        "request_method": clean_text(request.method),
        "request_path": clean_text(request.path),
        "user_agent": user_agent[:180],
    }


def sanitize_audit_payload(value, *, depth: int = 0):
    if depth > 4:
        return "[resumo omitido]"
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            key_text = clean_text(key)
            lowered = key_text.lower()
            if any(secret in lowered for secret in AUDIT_SENSITIVE_KEYS):
                sanitized[key_text] = "[protegido]"
            else:
                sanitized[key_text] = sanitize_audit_payload(item, depth=depth + 1)
        return sanitized
    if isinstance(value, list):
        sanitized_items = [sanitize_audit_payload(item, depth=depth + 1) for item in value[:20]]
        if len(value) > 20:
            sanitized_items.append(f"... {len(value) - 20} item(ns) omitido(s)")
        return sanitized_items
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        text = clean_text(value) if isinstance(value, str) else value
        if isinstance(text, str) and len(text) > 500:
            return f"{text[:500]}..."
        return text
    return clean_text(str(value))


def audit_value_label(value) -> str:
    if value is None or value == "":
        return "vazio"
    if isinstance(value, (dict, list)):
        return "dados estruturados"
    text = clean_text(str(value))
    return text[:120] + ("..." if len(text) > 120 else "")


def audit_change_preview(before, after) -> list[dict]:
    if not isinstance(before, dict) or not isinstance(after, dict):
        return []
    ignored = {"created_at", "updated_at", "last_route_generated_at"}
    changes = []
    for key in sorted(set(before) | set(after)):
        if key in ignored:
            continue
        previous = before.get(key)
        current = after.get(key)
        if previous != current:
            changes.append(
                {
                    "field": key.replace("_", " "),
                    "before": audit_value_label(previous),
                    "after": audit_value_label(current),
                }
            )
    return changes[:8]


def record_audit(action: str, module: str, target_id: str = "", detail: str = "", before=None, after=None) -> None:
    try:
        user = current_user() if has_request_context() else public_user()
        items = load_audit_log()
        entry = {
            "id": next_numeric_id(items, "AUD", "id"),
            "created_at": now_iso(),
            "action": clean_text(action),
            "action_label": audit_label(AUDIT_ACTION_LABELS, action, "Ação"),
            "module": clean_text(module),
            "module_label": audit_label(AUDIT_MODULE_LABELS, module, "Geral"),
            "target_id": clean_text(target_id),
            "detail": clean_text(detail),
            "user_id": clean_text(user.get("id")),
            "user_name": clean_text(user.get("nome")),
            "user_email": clean_text(user.get("email")),
            "user_role": clean_text(user.get("role")),
            **audit_request_metadata(),
        }
        if before is not None:
            entry["before"] = sanitize_audit_payload(before)
        if after is not None:
            entry["after"] = sanitize_audit_payload(after)
        if "before" in entry and "after" in entry:
            entry["changes"] = audit_change_preview(entry.get("before"), entry.get("after"))
        items.append(entry)
        save_audit_log(items)
    except Exception as exc:  # noqa: BLE001
        print(f"[audit] falha ao registrar auditoria: {exc}", file=sys.stderr)


def warehouse_stock_status(item: dict) -> str:
    quantity = parse_decimal(item.get("quantity_current"))
    minimum = parse_decimal(item.get("stock_minimum"))
    if quantity <= 0:
        return "zerado"
    if quantity <= minimum:
        return "baixo"
    return "normal"


def warehouse_status_label(status: str) -> str:
    return {"normal": "normal", "baixo": "baixo", "zerado": "zerado"}.get(status, "normal")


def create_warehouse_item_record(form, existing_items: list[dict] | None = None) -> dict:
    items = existing_items if existing_items is not None else load_warehouse_items()
    item_id = clean_text(form.get("item_id") or form.get("id")) or next_numeric_id(items, "ALM", "id")
    name = clean_text(form.get("name"))
    category = clean_text(form.get("category"), "Geral") or "Geral"
    unit = clean_text(form.get("unit"), "un") or "un"
    quantity_current = parse_decimal(form.get("quantity_current"))
    stock_minimum = parse_decimal(form.get("stock_minimum"))
    if not name:
        raise ValueError("Informe o nome do material.")
    if quantity_current < 0:
        raise ValueError("A quantidade atual não pode ser negativa no cadastro.")
    if stock_minimum < 0:
        raise ValueError("O estoque mínimo não pode ser negativo.")

    current = next((item for item in items if item.get("id") == item_id), {})
    now = now_iso()
    return {
        "id": item_id,
        "name": name,
        "category": category,
        "description": clean_text(form.get("description")),
        "unit": unit,
        "quantity_current": quantity_current,
        "stock_minimum": stock_minimum,
        "storage_location": clean_text(form.get("storage_location")),
        "purchase_link": clean_text(form.get("purchase_link")),
        "purchase_location": clean_text(form.get("purchase_location")),
        "photo_url": uploaded_asset_url("vehicle_photo_file") or clean_text(form.get("photo_url")),
        "notes": clean_text(form.get("notes")),
        "status": clean_text(form.get("status"), "ativo") if clean_text(form.get("status"), "ativo") in {"ativo", "inativo"} else "ativo",
        "sector": clean_text(form.get("sector")),
        "deposit": clean_text(form.get("deposit")),
        "created_at": clean_text(current.get("created_at")) or now,
        "updated_at": now,
    }


def apply_warehouse_movement(item_id: str, form, user: dict) -> dict:
    items = load_warehouse_items()
    target = next((item for item in items if clean_text(item.get("id")) == item_id), None)
    if not target:
        raise ValueError("Material não encontrado no almoxarifado.")

    movement_type = clean_text(form.get("movement_type")).lower()
    movement_aliases = {
        "reposição": "entrada",
        "reposicao": "entrada",
        "entrada": "entrada",
        "baixa": "saida",
        "saída": "saida",
        "saida": "saida",
        "ajuste manual": "ajuste manual",
    }
    movement_type = movement_aliases.get(movement_type, movement_type)
    previous_balance = parse_decimal(target.get("quantity_current"))
    final_balance = previous_balance
    quantity_changed = 0.0
    if movement_type == "entrada":
        quantity_changed = parse_decimal(form.get("quantity"))
        if quantity_changed <= 0:
            raise ValueError("Informe uma quantidade de entrada maior que zero.")
        final_balance = round(previous_balance + quantity_changed, 2)
    elif movement_type == "saida":
        quantity_changed = parse_decimal(form.get("quantity"))
        if quantity_changed <= 0:
            raise ValueError("Informe uma quantidade de saída maior que zero.")
        final_balance = round(previous_balance - quantity_changed, 2)
        if final_balance < 0 and clean_text(form.get("allow_negative")) != "true":
            raise ValueError("A quantidade não pode ficar negativa sem confirmação explícita.")
    elif movement_type == "ajuste manual":
        if not has_permission(user, "warehouse.manage"):
            raise ValueError("Ajuste manual de quantidade é permitido apenas para administrador.")
        final_balance = parse_decimal(form.get("final_quantity"))
        if final_balance < 0 and clean_text(form.get("allow_negative")) != "true":
            raise ValueError("A quantidade não pode ficar negativa sem confirmação explícita.")
        quantity_changed = round(final_balance - previous_balance, 2)
    else:
        raise ValueError("Tipo de movimentação inválido.")

    now = now_iso()
    target["quantity_current"] = final_balance
    target["updated_at"] = now
    save_warehouse_items(items)

    event_id = clean_text(form.get("event_id"))
    client_id = clean_text(form.get("client_id"))
    event = next((item for item in load_events() if clean_text(item.get("event_id")) == event_id), {}) if event_id else {}
    client = next((item for item in load_clients() if clean_text(item.get("client_id")) == client_id), {}) if client_id else {}
    movements = load_warehouse_movements()
    movement = {
        "id": next_numeric_id(movements, "MOV", "id"),
        "item_id": item_id,
        "item_name": clean_text(target.get("name")),
        "movement_type": movement_type,
        "quantity_changed": quantity_changed,
        "previous_balance": previous_balance,
        "final_balance": final_balance,
        "observation": clean_text(form.get("observation")),
        "event_id": event_id,
        "event_title": clean_text(event.get("title")),
        "client_id": client_id,
        "client_name": clean_text(client.get("customer_name")),
        "user_id": clean_text(user.get("id")),
        "user_name": clean_text(user.get("nome")),
        "user_email": clean_text(user.get("email")),
        "created_at": now,
    }
    movements.append(movement)
    save_warehouse_movements(movements)
    return movement


def build_warehouse_dashboard() -> dict:
    movements = load_warehouse_movements()
    by_item: dict[str, list[dict]] = {}
    for movement in reversed(movements):
        by_item.setdefault(clean_text(movement.get("item_id")), []).append(movement)

    items = []
    for item in load_warehouse_items():
        stock_status = warehouse_stock_status(item)
        items.append(
            {
                **item,
                "stock_status": stock_status,
                "stock_status_label": warehouse_status_label(stock_status),
                "recent_movements": by_item.get(clean_text(item.get("id")), [])[:5],
            }
        )
    categories = sorted({clean_text(item.get("category")) for item in items if clean_text(item.get("category"))})
    return {
        "items": items,
        "categories": categories,
        "movements": movements[-30:],
        "counts": {
            "total": len(items),
            "active": sum(1 for item in items if item.get("status") == "ativo"),
            "low": sum(1 for item in items if item.get("stock_status") == "baixo"),
            "zero": sum(1 for item in items if item.get("stock_status") == "zerado"),
        },
    }


def pdf_escape(value) -> str:
    return str(value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_simple_text_pdf(title: str, lines: list[str]) -> bytes:
    page_width = 595
    page_height = 842
    margin_x = 42
    start_y = 790
    line_height = 14
    max_chars = 104
    lines_per_page = 50
    wrapped_lines: list[str] = []
    for line in lines:
      text = str(line or "")
      if not text:
          wrapped_lines.append("")
          continue
      while len(text) > max_chars:
          split_at = text.rfind(" ", 0, max_chars)
          if split_at < 40:
              split_at = max_chars
          wrapped_lines.append(text[:split_at].rstrip())
          text = text[split_at:].strip()
      wrapped_lines.append(text)

    pages = [wrapped_lines[index : index + lines_per_page] for index in range(0, len(wrapped_lines), lines_per_page)] or [[]]
    objects: list[bytes] = []
    page_ids: list[int] = []
    for page_index, page_lines in enumerate(pages, start=1):
        commands = [
            "BT",
            "/F1 16 Tf",
            f"{margin_x} {start_y} Td",
            f"({pdf_escape(title)}) Tj",
            "0 -24 Td",
            "/F1 9 Tf",
            f"(Página {page_index} de {len(pages)}) Tj",
            "0 -20 Td",
            "/F1 10 Tf",
        ]
        for line in page_lines:
            commands.append(f"({pdf_escape(line)}) Tj")
            commands.append(f"0 -{line_height} Td")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        content_object_id = len(objects) + 1
        objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")
        page_object_id = len(objects) + 1
        page_ids.append(page_object_id)
        objects.append(
            (
                f"<< /Type /Page /Parent 0 0 R /MediaBox [0 0 {page_width} {page_height}] "
                f"/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >> >> "
                f"/Contents {content_object_id} 0 R >>"
            ).encode("ascii")
        )

    pages_object_id = len(objects) + 1
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii"))
    catalog_object_id = len(objects) + 1
    objects.append(f"<< /Type /Catalog /Pages {pages_object_id} 0 R >>".encode("ascii"))
    objects = [
        obj.replace(b"/Parent 0 0 R", f"/Parent {pages_object_id} 0 R".encode("ascii"))
        for obj in objects
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_id} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_object_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def build_warehouse_pdf() -> bytes:
    dashboard = build_warehouse_dashboard()
    counts = dashboard["counts"]
    lines = [
        f"Gerado em {format_datetime_br(now_iso())}",
        f"Total: {counts['total']} | Ativos: {counts['active']} | Baixo: {counts['low']} | Zerado: {counts['zero']}",
        "",
        "Lista completa de materiais do almoxarifado",
        "",
    ]
    for index, item in enumerate(dashboard["items"], start=1):
        lines.extend(
            [
                f"{index}. {item.get('name')} | {item.get('category')} | {item.get('stock_status_label')} | {item.get('status')}",
                f"   Quantidade: {item.get('quantity_current')} {item.get('unit')} | Mínimo: {item.get('stock_minimum')} {item.get('unit')}",
                f"   Local: {item.get('storage_location') or 'n/d'} | Onde comprar: {item.get('purchase_location') or 'n/d'}",
                f"   Link: {item.get('purchase_link') or 'n/d'}",
                f"   Foto: {item.get('photo_url') or 'n/d'}",
                f"   Observações: {item.get('notes') or item.get('description') or 'n/d'}",
                "",
            ]
        )
    if not dashboard["items"]:
        lines.append("Nenhum material cadastrado.")
    return build_simple_text_pdf("SannyGold - Almoxarifado", lines)


def build_low_stock_warehouse_pdf() -> bytes:
    dashboard = build_warehouse_dashboard()
    alert_items = [item for item in dashboard["items"] if item.get("stock_status") in {"baixo", "zerado"}]
    lines = [
        f"Gerado em {format_datetime_br(now_iso())}",
        f"Materiais em alerta: {len(alert_items)}",
        "",
        "Relatório de estoque baixo e zerado",
        "",
    ]
    for index, item in enumerate(alert_items, start=1):
        lines.extend(
            [
                f"{index}. {item.get('name')} | {item.get('category')} | {item.get('stock_status_label')}",
                f"   Saldo atual: {item.get('quantity_current')} {item.get('unit')} | mínimo: {item.get('stock_minimum')} {item.get('unit')}",
                f"   Local: {item.get('storage_location') or 'n/d'}",
                f"   Comprar: {item.get('purchase_link') or item.get('purchase_location') or 'n/d'}",
                f"   Próxima ação: {'comprar imediatamente' if item.get('stock_status') == 'zerado' else 'repor antes da próxima operação'}",
                "",
            ]
        )
    if not alert_items:
        lines.append("Nenhum material com estoque baixo ou zerado no momento.")
    return build_simple_text_pdf("SannyGold - Estoque baixo", lines)


def module_export_data(module: str) -> tuple[str, list[str], list[list[str]], str]:
    module = clean_text(module).lower()
    if module == "clients":
        headers = ["ID", "Cliente", "Contato", "Telefone", "Email", "Endereco", "Equipamento", "Valor"]
        rows = [
            [
                item.get("client_id", ""),
                item.get("customer_name", ""),
                item.get("contact_name", ""),
                item.get("phone", ""),
                item.get("email", ""),
                item.get("address", ""),
                item.get("equipment_number", ""),
                item.get("service_value", ""),
            ]
            for item in load_clients()
        ]
        return "Clientes", headers, rows, "clients.view"
    if module == "equipment":
        headers = ["ID", "Tipo", "Status", "Condicao", "Manutencao", "Previsao", "Custo", "Observacoes"]
        rows = [
            [
                item.get("equipment_id", ""),
                item.get("equipment_type", ""),
                item.get("status", ""),
                item.get("condition", ""),
                item.get("maintenance_reason", ""),
                item.get("maintenance_expected_release", ""),
                item.get("maintenance_cost", ""),
                item.get("notes", ""),
            ]
            for item in load_equipment_registry()
        ]
        return "Equipamentos", headers, rows, "inventory.view"
    if module in {"vehicles", "fleet"}:
        headers = ["ID", "Tipo", "Placa", "Modelo", "Capacidade", "Max Paradas", "Max Minutos", "Base"]
        rows = [
            [
                item.get("vehicle_id", ""),
                item.get("vehicle_type", ""),
                item.get("plate", ""),
                item.get("model", ""),
                item.get("capacity", ""),
                item.get("max_stops", ""),
                item.get("max_minutes", ""),
                f"{item.get('start_lat', '')}, {item.get('start_lng', '')}",
            ]
            for item in load_vehicles_registry()
        ]
        return "Frota", headers, rows, "fleet.view"
    if module == "warehouse":
        headers = ["ID", "Material", "Categoria", "Qtd", "Unidade", "Minimo", "Status", "Local", "Comprar"]
        rows = [
            [
                item.get("id", ""),
                item.get("name", ""),
                item.get("category", ""),
                item.get("quantity_current", ""),
                item.get("unit", ""),
                item.get("stock_minimum", ""),
                warehouse_stock_status(item),
                item.get("storage_location", ""),
                item.get("purchase_link") or item.get("purchase_location", ""),
            ]
            for item in load_warehouse_items()
        ]
        return "Almoxarifado", headers, rows, "warehouse.view"
    if module == "events":
        headers = ["ID", "Evento", "Inicio", "Fim", "Status", "Clientes", "Veiculos", "Recorrencia"]
        rows = [
            [
                item.get("event_id", ""),
                item.get("title", ""),
                item.get("event_date", ""),
                item.get("event_end_date", ""),
                item.get("status", ""),
                ", ".join(item.get("client_ids") or []),
                ", ".join(item.get("vehicle_ids") or []),
                item.get("recurrence_frequency", ""),
            ]
            for item in load_events()
        ]
        return "Eventos", headers, rows, "events.view"
    if module == "financial":
        headers = ["Gerado em", "Evento", "Receita", "Custo", "Lucro", "Margem"]
        rows = [
            [
                item.get("generated_at", ""),
                item.get("event_title") or item.get("event_id") or "Operação geral",
                (item.get("financial_summary") or {}).get("revenue_total", ""),
                (item.get("financial_summary") or {}).get("operational_total", ""),
                (item.get("financial_summary") or {}).get("profit_total", ""),
                (item.get("financial_summary") or {}).get("margin_pct", ""),
            ]
            for item in load_route_history()
        ]
        return "Financeiro", headers, rows, "finance.export"
    raise ValueError("Relatório não encontrado.")


def build_module_pdf(module: str) -> tuple[str, bytes, str]:
    title, headers, rows, permission = module_export_data(module)
    lines = [" | ".join(headers), ""]
    for row in rows:
        lines.append(" | ".join(str(value or "") for value in row))
    if not rows:
        lines.append("Nenhum registro encontrado.")
    return title, build_simple_text_pdf(f"SannyGold - {title}", lines), permission


def build_module_xlsx(module: str) -> tuple[str, bytes, str]:
    title, headers, rows, permission = module_export_data(module)
    return title, build_simple_xlsx_bytes(headers, rows, sheet_name=title[:31]), permission


def load_route_history() -> list[dict]:
    return load_json_list(ROUTE_HISTORY_PATH)


def save_route_history(history_items: list[dict]) -> None:
    ordered = sorted(history_items, key=lambda item: str(item.get("generated_at") or ""), reverse=True)
    save_json_list(ROUTE_HISTORY_PATH, ordered[:100])


def load_events() -> list[dict]:
    return load_json_list(EVENTS_PATH)


def save_events(events: list[dict]) -> None:
    save_json_list(EVENTS_PATH, sort_by_label(events, "event_date", "event_id", "title"))


def load_field_confirmations() -> list[dict]:
    return load_json_list(FIELD_CONFIRMATIONS_PATH)


def save_field_confirmations(items: list[dict]) -> None:
    ordered = sorted(
        items,
        key=lambda item: (
            str(item.get("route_generated_at") or ""),
            str(item.get("client_id") or ""),
            str(item.get("equipment_id") or ""),
        ),
        reverse=True,
    )
    save_json_list(FIELD_CONFIRMATIONS_PATH, ordered[:500])


def load_operation_validation() -> dict:
    return load_json_dict(OPERATION_VALIDATION_PATH)


def save_operation_validation(payload: dict) -> None:
    save_json_dict(OPERATION_VALIDATION_PATH, payload)


def load_forecast_audit() -> dict:
    return load_json_dict(FORECAST_AUDIT_PATH)


def save_forecast_audit(payload: dict) -> None:
    save_json_dict(FORECAST_AUDIT_PATH, payload)


def default_help_metrics() -> dict:
    return {
        "question_counts": {},
        "useful_counts": {},
        "not_useful_counts": {},
        "support_clicks": 0,
    }


def merge_default_help_knowledge_base(items: list[dict]) -> tuple[list[dict], bool]:
    defaults_by_id = {clean_text(entry.get("id")): entry for entry in DEFAULT_HELP_KNOWLEDGE_BASE}
    merged_by_id: dict[str, dict] = {}
    changed = False
    for item in items:
        item_id = clean_text(item.get("id"))
        if not item_id:
            changed = True
            continue
        default_entry = defaults_by_id.get(item_id)
        seed_version = int(item.get("seedVersion") or 0)
        if default_entry and seed_version < DEFAULT_HELP_KNOWLEDGE_BASE_VERSION:
            merged_by_id[item_id] = dict(default_entry)
            changed = True
        else:
            merged_by_id[item_id] = item
    for item_id, default_entry in defaults_by_id.items():
        if item_id not in merged_by_id:
            merged_by_id[item_id] = dict(default_entry)
            changed = True
    return list(merged_by_id.values()), changed


def load_help_knowledge_base() -> list[dict]:
    items = load_json_list(HELP_KNOWLEDGE_BASE_PATH)
    if not items:
        items = [dict(item) for item in DEFAULT_HELP_KNOWLEDGE_BASE]
        save_json_list(HELP_KNOWLEDGE_BASE_PATH, items)
        return items
    merged_items, changed = merge_default_help_knowledge_base(items)
    if changed:
        save_help_knowledge_base(merged_items)
    return merged_items


def save_help_knowledge_base(items: list[dict]) -> None:
    ordered = sort_by_label(items, "categoria", "titulo", "id")
    save_json_list(HELP_KNOWLEDGE_BASE_PATH, ordered)


def load_help_unanswered_questions() -> list[dict]:
    return load_json_list(HELP_UNANSWERED_PATH)


def save_help_unanswered_questions(items: list[dict]) -> None:
    ordered = sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    save_json_list(HELP_UNANSWERED_PATH, ordered[:1000])


def load_help_support_tickets() -> list[dict]:
    return load_json_list(HELP_SUPPORT_TICKETS_PATH)


def save_help_support_tickets(items: list[dict]) -> None:
    ordered = sorted(items, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    save_json_list(HELP_SUPPORT_TICKETS_PATH, ordered[:1000])


def load_help_metrics() -> dict:
    metrics = default_help_metrics()
    stored = load_json_dict(HELP_METRICS_PATH)
    for key in ("question_counts", "useful_counts", "not_useful_counts"):
        if isinstance(stored.get(key), dict):
            metrics[key] = stored[key]
    metrics["support_clicks"] = int(stored.get("support_clicks") or 0)
    return metrics


def save_help_metrics(metrics: dict) -> None:
    baseline = default_help_metrics()
    baseline.update(metrics)
    for key in ("question_counts", "useful_counts", "not_useful_counts"):
        if not isinstance(baseline.get(key), dict):
            baseline[key] = {}
    baseline["support_clicks"] = int(baseline.get("support_clicks") or 0)
    save_json_dict(HELP_METRICS_PATH, baseline)


QUICK_HELP_ANCHORS = {
    "ajuda-criar-cliente": "quick-help-cliente",
    "ajuda-locacao-rapida": "quick-help-locacao-rapida",
    "ajuda-gerar-rota": "quick-help-rota",
    "ajuda-gerar-ordem-servico": "quick-help-os",
    "ajuda-lancar-recebimento": "quick-help-financeiro",
    "ajuda-corrigir-pendencias": "quick-help-pendencias",
    "ajuda-consultar-agenda": "quick-help-agenda",
    "ajuda-saber-hoje": "quick-help-hoje",
    "ajuda-quando-aparecer-erro": "quick-help-erros",
    "ajuda-duvida-interna": "quick-help-suporte",
}


def public_help_entry(entry: dict) -> dict:
    return {
        "id": clean_text(entry.get("id")),
        "titulo": clean_text(entry.get("titulo")),
        "categoria": clean_text(entry.get("categoria")),
        "pergunta": clean_text(entry.get("pergunta")),
        "resposta": clean_text(entry.get("resposta")),
        "exemplo": clean_text(entry.get("exemplo") or entry.get("example")),
        "passos": [clean_text(step) for step in entry.get("passos") or [] if clean_text(step)],
        "palavrasChave": [clean_text(word) for word in entry.get("palavrasChave") or [] if clean_text(word)],
        "rotaRelacionada": clean_text(entry.get("rotaRelacionada")),
        "targetHref": clean_text(entry.get("targetHref") or entry.get("rotaRelacionada")),
        "targetTab": clean_text(entry.get("targetTab")),
        "criticidade": clean_text(entry.get("criticidade"), "baixo") or "baixo",
    }


def build_quick_help_guides(entries: list[dict]) -> list[dict]:
    by_id = {clean_text(entry.get("id")): dict(entry) for entry in entries}
    guides = []
    for index, entry_id in enumerate(QUICK_HELP_GUIDE_IDS, start=1):
        entry = by_id.get(entry_id)
        if not entry:
            continue
        entry["number"] = index
        entry["anchor_id"] = QUICK_HELP_ANCHORS.get(entry_id, f"quick-help-{entry_id}")
        guides.append(entry)
    return guides


def help_request_payload() -> dict:
    if request.is_json:
        payload = request.get_json(silent=True)
        return payload if isinstance(payload, dict) else {}
    return request.form.to_dict(flat=True)


def help_current_screen(payload: dict | None = None) -> str:
    payload = payload or {}
    return clean_text(payload.get("screen") or request.args.get("screen") or request.headers.get("Referer"))[:500]


def help_user_snapshot(user: dict | None = None) -> dict:
    user = user or current_user()
    return {
        "user_id": clean_text(user.get("id")),
        "user_name": clean_text(user.get("nome")),
        "user_email": clean_text(user.get("email")),
        "user_role": clean_text(user.get("role")),
    }


def increment_help_counter(metrics: dict, group: str, key: str, amount: int = 1) -> None:
    if group not in metrics or not isinstance(metrics.get(group), dict):
        metrics[group] = {}
    metrics[group][key] = int(metrics[group].get(key) or 0) + amount


def help_initial_options(entries: list[dict]) -> list[dict]:
    preferred_order = [entry["id"] for entry in DEFAULT_HELP_KNOWLEDGE_BASE if entry.get("opcaoInicial")]
    by_id = {clean_text(entry.get("id")): entry for entry in entries if entry.get("opcaoInicial", True)}
    ordered = [by_id[item_id] for item_id in preferred_order if item_id in by_id]
    remaining = [entry for entry in entries if clean_text(entry.get("id")) not in preferred_order and entry.get("opcaoInicial", False)]
    return [public_help_entry(entry) for entry in ordered + sort_by_label(remaining, "titulo")][:12]


def help_context_options(entries: list[dict]) -> list[dict]:
    context_groups = [
        ("summary", "Resumo", ["ajuda-saber-hoje", "ajuda-corrigir-pendencias", "ajuda-quando-aparecer-erro", "ver-pendencias", "buscar-no-sistema", "fechar-dia"]),
        ("events", "Eventos", ["cadastrar-evento", "criar-ordem-servico", "evento-sem-endereco", "corrigir-status-evento"]),
        ("clients", "Clientes", ["cadastrar-cliente", "cliente-duplicado", "cliente-sem-telefone", "registrar-limpeza-cliente"]),
        ("fleet", "Banheiros e frota", ["check-in-equipamento", "check-out-equipamento", "banheiro-luxo-cadastrar", "banheiro-quimico-cadastrar", "equipamento-em-manutencao"]),
        ("warehouse", "Almoxarifado", ["registrar-material-extra", "conferir-material-retornado", "estoque-baixo", "registrar-entrada-material", "registrar-saida-material"]),
        ("operations", "Rotas e PDF", ["ajuda-gerar-rota", "ajuda-gerar-ordem-servico", "gerar-rota", "validar-operacao", "baixar-pdf-operacional"]),
        ("finance", "Financeiro", ["ajuda-lancar-recebimento"]),
        ("agenda", "Agenda", ["ajuda-consultar-agenda"]),
        ("support", "Suporte", ["ajuda-duvida-interna", "falar-suporte-humano"]),
    ]
    by_id = {clean_text(entry.get("id")): entry for entry in entries}
    options = []
    for context, context_label, entry_ids in context_groups:
        for entry_id in entry_ids:
            entry = by_id.get(entry_id)
            if not entry:
                continue
            option = public_help_entry(entry)
            option["context"] = context
            option["contextLabel"] = context_label
            options.append(option)
    return options


def build_help_assistant_context(user: dict) -> dict:
    knowledge_base = [public_help_entry(entry) for entry in load_help_knowledge_base()]
    unanswered = load_help_unanswered_questions()
    tickets = load_help_support_tickets()
    metrics = summarize_help_metrics(load_help_metrics(), knowledge_base, unanswered, tickets)
    can_manage = has_permission(user, "settings.manage")
    return {
        "initial_options": help_initial_options(knowledge_base),
        "context_options": help_context_options(knowledge_base),
        "quick_guides": build_quick_help_guides(knowledge_base),
        "knowledge_base": knowledge_base if can_manage else [],
        "unanswered_questions": unanswered[:40] if can_manage else [],
        "support_tickets": tickets[:40] if can_manage else [],
        "metrics": metrics,
        "can_manage": can_manage,
        "fallback_message": "Não encontrei uma resposta segura para essa dúvida. Posso registrar isso para o suporte analisar.",
    }


def create_help_knowledge_record(form) -> dict:
    entry_id = clean_text(form.get("entry_id") or form.get("id")).lower()
    title = clean_text(form.get("titulo") or form.get("title"))
    category = clean_text(form.get("categoria") or form.get("category"), "Operacional") or "Operacional"
    question = clean_text(form.get("pergunta") or form.get("question"))
    answer = clean_text(form.get("resposta") or form.get("answer"))
    example = clean_text(form.get("exemplo") or form.get("example"))
    steps_text = clean_text(form.get("passos") or form.get("steps"))
    keywords_text = clean_text(form.get("palavrasChave") or form.get("keywords"))
    if not title or not question or not answer:
        raise ValueError("Informe título, pergunta e resposta da base de conhecimento.")
    if not entry_id:
        base = "".join(ch if ch.isalnum() else "-" for ch in title.lower())
        entry_id = "-".join(part for part in base.split("-") if part)[:60]
    if not entry_id:
        raise ValueError("Informe um ID válido para a pergunta.")
    criticality = clean_text(form.get("criticidade"), "baixo").lower()
    if criticality not in {"baixo", "medio", "médio", "alto"}:
        raise ValueError("Criticidade deve ser baixo, médio ou alto.")
    if criticality == "médio":
        criticality = "medio"
    keywords = [clean_text(word) for word in keywords_text.split(",") if clean_text(word)]
    return {
        "id": entry_id,
        "titulo": title,
        "categoria": category,
        "pergunta": question,
        "resposta": answer,
        "exemplo": example,
        "passos": [clean_text(step).lstrip("0123456789.:-) ") for step in steps_text.splitlines() if clean_text(step)],
        "palavrasChave": keywords,
        "rotaRelacionada": clean_text(form.get("rotaRelacionada") or form.get("route") or "/"),
        "targetHref": clean_text(form.get("targetHref") or form.get("target_href") or form.get("rotaRelacionada") or "/"),
        "targetTab": clean_text(form.get("targetTab") or form.get("target_tab")),
        "criticidade": criticality,
        "opcaoInicial": clean_text(form.get("opcaoInicial") or form.get("initial_option")) in {"1", "true", "on", "sim"},
    }


def load_users() -> list[dict]:
    return load_json_list(USERS_PATH)


def save_users(users: list[dict]) -> None:
    save_json_list(USERS_PATH, sort_by_label(users, "nome", "email"))


def access_token_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(app.config["SECRET_KEY"], salt="sannygold-access")


def iso_expired(value: str | None) -> bool:
    text = clean_text(value)
    if not text:
        return True
    try:
        return datetime.now() > datetime.fromisoformat(text)
    except ValueError:
        return True


def issue_user_invitation(user: dict) -> None:
    now = now_iso()
    user["status"] = "convite_pendente"
    user["senha_hash"] = ""
    user["must_change_password"] = False
    user["invitation_token"] = secrets.token_urlsafe(32)
    user["invitation_created_at"] = now
    user["invitation_expires_at"] = (datetime.now() + timedelta(hours=INVITATION_EXPIRATION_HOURS)).isoformat(timespec="seconds")
    user["invitation_accepted_at"] = ""
    user["updated_at"] = now


def clear_user_invitation(user: dict) -> None:
    for key in ("invitation_token", "invitation_created_at", "invitation_expires_at"):
        user[key] = ""


def issue_password_reset(user: dict) -> None:
    now = now_iso()
    user["reset_token"] = secrets.token_urlsafe(32)
    user["reset_requested_at"] = now
    user["reset_expires_at"] = (datetime.now() + timedelta(hours=PASSWORD_RESET_EXPIRATION_HOURS)).isoformat(timespec="seconds")
    user["updated_at"] = now


def clear_password_reset(user: dict) -> None:
    for key in ("reset_token", "reset_requested_at", "reset_expires_at"):
        user[key] = ""


def build_access_token(user: dict, purpose: str, nonce_field: str) -> str:
    nonce = clean_text(user.get(nonce_field))
    if not nonce:
        return ""
    return access_token_serializer().dumps(
        {
            "purpose": purpose,
            "user_id": clean_text(user.get("id")),
            "nonce": nonce,
        }
    )


def invitation_url(user: dict) -> str:
    token = build_access_token(user, "invite", "invitation_token")
    return url_for("accept_invitation", token=token, _external=True) if token else ""


def password_reset_url(user: dict) -> str:
    token = build_access_token(user, "password_reset", "reset_token")
    return url_for("reset_password", token=token, _external=True) if token else ""


def mailto_url(email: str, subject: str, body: str) -> str:
    return f"mailto:{urllib.parse.quote(clean_text(email))}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"


def resolve_access_token(token: str, purpose: str, nonce_field: str, expiry_field: str) -> tuple[list[dict], dict | None, str]:
    try:
        payload = access_token_serializer().loads(token)
    except BadSignature:
        return [], None, "Link inválido. Peça um novo link ao administrador."
    if clean_text(payload.get("purpose")) != purpose:
        return [], None, "Link inválido para esta ação."
    users = load_users()
    user = next((item for item in users if clean_text(item.get("id")) == clean_text(payload.get("user_id"))), None)
    if not user or clean_text(user.get(nonce_field)) != clean_text(payload.get("nonce")):
        return users, None, "Link já usado, cancelado ou substituído por outro."
    if iso_expired(user.get(expiry_field)):
        return users, None, "Link expirado. Peça um novo link ao administrador."
    return users, user, ""


def serialize_access_user(user: dict) -> dict:
    payload = sanitize_user(user)
    invitation_active = (
        clean_text(user.get("status")) == "convite_pendente"
        and clean_text(user.get("invitation_token"))
        and not iso_expired(user.get("invitation_expires_at"))
    )
    reset_active = clean_text(user.get("reset_token")) and not iso_expired(user.get("reset_expires_at"))
    invite_link = invitation_url(user) if invitation_active else ""
    reset_link = password_reset_url(user) if reset_active else ""
    payload.update(
        {
            "invitation_created_at": clean_text(user.get("invitation_created_at")),
            "invitation_expires_at": clean_text(user.get("invitation_expires_at")),
            "invitation_expires_label": format_datetime_br(user.get("invitation_expires_at")),
            "invitation_active": invitation_active,
            "invitation_url": invite_link,
            "invitation_mailto": mailto_url(
                payload["email"],
                "Convite para acessar o sistema SannyGold",
                f"Olá {payload['nome'] or payload['email']},\n\nUse este link para criar sua senha e acessar o sistema SannyGold:\n{invite_link}\n\nO link expira em {format_datetime_br(user.get('invitation_expires_at'))}.",
            )
            if invite_link
            else "",
            "reset_requested_at": clean_text(user.get("reset_requested_at")),
            "reset_expires_at": clean_text(user.get("reset_expires_at")),
            "reset_expires_label": format_datetime_br(user.get("reset_expires_at")),
            "reset_active": reset_active,
            "reset_url": reset_link,
            "reset_mailto": mailto_url(
                payload["email"],
                "Redefinição de senha - SannyGold",
                f"Olá {payload['nome'] or payload['email']},\n\nUse este link para criar uma nova senha no sistema SannyGold:\n{reset_link}\n\nO link expira em {format_datetime_br(user.get('reset_expires_at'))}.",
            )
            if reset_link
            else "",
        }
    )
    return payload


def create_user_record(form, existing_users: list[dict]) -> dict:
    user_id = clean_text(form.get("user_id")) or next_numeric_id(existing_users, "USR", "id")
    current = next((user for user in existing_users if clean_text(user.get("id")) == user_id), {})
    nome = clean_text(form.get("nome"))
    email = clean_text(form.get("email")).lower()
    role = clean_text(form.get("role"), "leitura") or "leitura"
    password = form.get("password", "")
    status = clean_text(form.get("status"), "ativo" if password else "convite_pendente") or "convite_pendente"
    if not nome:
        raise ValueError("Informe o nome do usuário. Sem nome, o administrador não consegue identificar o acesso.")
    if not email:
        raise ValueError("Informe o e-mail do usuário. O e-mail é usado para login, convite e redefinição de senha.")
    if role not in ROLES or role == "guest":
        raise ValueError("Perfil inválido para usuário interno. Escolha Admin, Operacional, Financeiro ou Leitura.")
    if status not in {"ativo", "inativo", "convite_pendente"}:
        raise ValueError("Status inválido. Escolha ativo, inativo ou convite pendente.")
    issues = password_policy_issues(password, [nome, email]) if password else []
    if issues:
        raise ValueError(issues[0])
    duplicate = next((user for user in existing_users if clean_text(user.get("email")).lower() == email and clean_text(user.get("id")) != user_id), None)
    if duplicate:
        raise ValueError("Já existe usuário com este e-mail. Edite o acesso existente ou use outro endereço.")
    now = now_iso()
    record = {
        "id": user_id,
        "nome": nome,
        "email": email,
        "senha_hash": generate_password_hash(password, method="pbkdf2:sha256") if password else clean_text(current.get("senha_hash")),
        "status": status,
        "role": role,
        "must_change_password": bool(password) if password else bool(current.get("must_change_password")),
        "created_at": clean_text(current.get("created_at")) or now,
        "updated_at": now,
    }
    for key in (
        "invitation_token",
        "invitation_created_at",
        "invitation_expires_at",
        "invitation_accepted_at",
        "reset_token",
        "reset_requested_at",
        "reset_expires_at",
    ):
        record[key] = clean_text(current.get(key))
    if password:
        clear_user_invitation(record)
        clear_password_reset(record)
    elif status == "convite_pendente":
        if not clean_text(record.get("invitation_token")) or iso_expired(record.get("invitation_expires_at")):
            issue_user_invitation(record)
        record["senha_hash"] = ""
        record["must_change_password"] = False
    elif status == "ativo" and not record["senha_hash"]:
        issue_user_invitation(record)
    elif status == "inativo":
        clear_user_invitation(record)
        clear_password_reset(record)
    return record


def public_user() -> dict:
    return {
        "id": "guest",
        "nome": "Visitante",
        "email": "",
        "role": "guest",
        "status": "ativo",
        "permissions": sorted(ROLE_PERMISSIONS["guest"]),
    }


def sanitize_user(user: dict) -> dict:
    role = clean_text(user.get("role"), "guest")
    if role not in ROLES:
        role = "guest"
    return {
        "id": clean_text(user.get("id")),
        "nome": clean_text(user.get("nome")),
        "email": clean_text(user.get("email")).lower(),
        "status": clean_text(user.get("status"), "inativo"),
        "role": role,
        "must_change_password": bool(user.get("must_change_password")),
        "created_at": clean_text(user.get("created_at")),
        "updated_at": clean_text(user.get("updated_at")),
        "permissions": sorted(ROLE_PERMISSIONS.get(role, set())),
    }


def find_user_by_email(email: str) -> dict | None:
    normalized = clean_text(email).lower()
    return next((user for user in load_users() if clean_text(user.get("email")).lower() == normalized), None)


def current_user() -> dict:
    user_id = clean_text(session.get("user_id"))
    if not user_id:
        return public_user()
    user = next((item for item in load_users() if clean_text(item.get("id")) == user_id), None)
    if not user or clean_text(user.get("status"), "inativo") != "ativo":
        session.clear()
        flash_action_warning(
            "Aviso: sessão expirada",
            "Sua sessão terminou ou o usuário não está mais ativo. O sistema bloqueou a continuação para proteger os dados.",
            next_step="Entre novamente com uma conta ativa antes de continuar.",
            target_href="#login-panel",
            target_tab="summary-tab",
            action="Entrar novamente",
        )
        return public_user()
    return sanitize_user(user)


def has_permission(user: dict | None, permission: str) -> bool:
    role = clean_text((user or {}).get("role"), "guest")
    permissions = ROLE_PERMISSIONS.get(role, set())
    return "*" in permissions or permission in permissions


def require_permission(permission: str):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not has_permission(user, permission):
                is_guest = clean_text(user.get("role")) == "guest"
                message_payload = (
                    user_message_payload(
                        "Acesso restrito. Entre na conta para continuar.",
                        "Você precisa estar logado para abrir esta função. O sistema bloqueou a ação para proteger dados de clientes, rotas e financeiro.",
                        item_detail="Entre com seu usuário e tente novamente.",
                        target_href="#login-panel",
                        target_tab="summary-tab",
                        action="Entrar",
                    )
                    if is_guest
                    else user_message_payload(
                        "Acesso restrito para o seu perfil",
                        "Esta função não está liberada para o seu perfil. O sistema bloqueou a ação para evitar alterações indevidas em dados sensíveis.",
                        item_detail="Peça ao administrador para liberar essa função ou use uma conta com perfil adequado.",
                        target_href="#access-management-panel",
                        target_tab="access-tab",
                        action="Ver acessos",
                    )
                )
                record_audit(
                    "access_denied",
                    "permissions",
                    permission,
                    f"Tentativa de acesso sem permissão para {permission}.",
                    after={"permission": permission, "path": request.path, "method": request.method},
                )
                if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
                    return jsonify({"ok": False, "error": f"{message_payload['title']}. {message_payload['intro']}"}), 401 if is_guest else 403
                flash(message_payload, "warning")
                return redirect(url_for("index", auth="required") if is_guest else url_for("index", denied=permission))
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


@app.context_processor
def inject_security_context():
    return {
        "csrf_token": csrf_token,
        "csrf_field_name": CSRF_FIELD_NAME,
        "security_headers": {
            "session_cookie_secure": app.config.get("SESSION_COOKIE_SECURE"),
            "session_cookie_samesite": app.config.get("SESSION_COOKIE_SAMESITE"),
        },
    }


@app.before_request
def protect_post_requests_with_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if app.config.get("TESTING") or not app.config.get("CSRF_ENABLED", True):
        return None
    if csrf_is_valid():
        return None
    record_audit(
        "access_denied",
        "permissions",
        "csrf",
        "Tentativa de envio sem token CSRF válido.",
        after={"path": request.path, "method": request.method},
    )
    message = user_message_payload(
        "Aviso: sessão do formulário expirou",
        "O formulário ficou aberto por tempo demais ou foi enviado sem confirmação de segurança. O sistema bloqueou o envio para proteger seus dados.",
        item_detail="Atualize a página, confira se os dados continuam corretos e envie novamente.",
        target_href="#central-day-panel",
        target_tab="summary-tab",
        action="Voltar ao painel",
    )
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"ok": False, "error": f"{message['title']}. {message['intro']}"}), 400
    flash(message, "warning")
    return redirect(url_for("index", csrf="invalid"))


@app.errorhandler(413)
def handle_file_too_large(_error):
    message = friendly_error_payload(ValueError("Arquivo muito grande."), "upload")
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"ok": False, "error": friendly_error_text(ValueError("Arquivo muito grande."), "upload")}), 413
    flash(message, "danger")
    return redirect(url_for("index")), 413


@app.errorhandler(403)
def handle_forbidden(_error):
    message = friendly_error_payload(ValueError("Acesso restrito para o seu perfil."), "access")
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"ok": False, "error": friendly_error_text(ValueError("Acesso restrito para o seu perfil."), "access")}), 403
    flash(message, "warning")
    return redirect(url_for("index", denied="403")), 403


@app.errorhandler(404)
def handle_not_found(_error):
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"ok": False, "error": "Página não encontrada. O endereço acessado não existe ou foi movido. Volte para a Central do Dia e abra a função pelo menu."}), 404
    flash_action_warning(
        "Aviso: página não encontrada",
        "O endereço acessado não existe ou foi movido. O sistema não abriu a página para evitar uma ação fora do fluxo correto.",
        next_step="Volte para a Central do Dia e abra a função pelo menu.",
        target_href="#central-day-panel",
        target_tab="summary-tab",
        action="Voltar para a Central do Dia",
    )
    return redirect(url_for("index")), 404


@app.errorhandler(500)
def handle_unexpected_error(_error):
    message = user_message_payload(
        "Erro: ação não concluída",
        "Não foi possível concluir agora por uma falha interna. O sistema não exibiu detalhes técnicos para proteger os dados.",
        item_detail="Tente novamente. Se repetir, informe ao administrador qual tela e ação você estava usando.",
        target_href="#central-day-panel",
        target_tab="summary-tab",
        action="Voltar para a Central do Dia",
    )
    if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
        return jsonify({"ok": False, "error": f"{message['title']}. {message['intro']} Próximo passo: {message['items'][0]['detail']}"}), 500
    flash(message, "danger")
    return redirect(url_for("index")), 500


def build_profile_ui(user: dict | None) -> dict:
    role = clean_text((user or {}).get("role"), "guest")
    if role not in ROLES:
        role = "guest"
    visible_by_role = {
        "admin": {"summary", "events", "operations", "clients", "fleet", "warehouse", "agenda", "history", "homologation", "access"},
        "operacional": {"summary", "events", "operations", "clients", "fleet", "agenda", "history"},
        "financeiro": {"summary", "events", "clients", "history"},
        "leitura": {"summary", "events", "clients", "fleet", "agenda", "history"},
        "guest": set(),
    }
    visible = visible_by_role.get(role, visible_by_role["guest"])
    tabs = {
        "summary": "summary" in visible,
        "events": "events" in visible and has_permission(user, "events.view"),
        "operations": "operations" in visible and has_permission(user, "routes.view"),
        "clients": "clients" in visible and has_permission(user, "clients.view"),
        "fleet": "fleet" in visible and (has_permission(user, "fleet.view") or has_permission(user, "inventory.view")),
        "warehouse": "warehouse" in visible and has_permission(user, "warehouse.view"),
        "agenda": "agenda" in visible and has_permission(user, "dashboard.view"),
        "history": "history" in visible and has_permission(user, "dashboard.view"),
        "homologation": "homologation" in visible and has_permission(user, "settings.manage"),
        "access": "access" in visible and has_permission(user, "settings.manage"),
    }
    tab_buttons = {
        "summary-tab": tabs["summary"],
        "events-tab": tabs["events"],
        "operations-tab": tabs["operations"],
        "clients-tab": tabs["clients"],
        "fleet-tab": tabs["fleet"],
        "warehouse-tab": tabs["warehouse"],
        "agenda-tab": tabs["agenda"],
        "history-tab": tabs["history"],
        "homologation-tab": tabs["homologation"],
        "access-tab": tabs["access"],
        "": True,
    }
    return {
        "role": role,
        "label": {
            "admin": "Administrador",
            "operacional": "Operação",
            "financeiro": "Financeiro",
            "leitura": "Somente leitura",
            "guest": "Visitante",
        }.get(role, "Visitante"),
        "tabs": tabs,
        "tab_buttons": tab_buttons,
        "read_only": role == "leitura",
        "can_create_client": tabs["clients"] and has_permission(user, "clients.edit"),
        "can_create_event": tabs["events"] and has_permission(user, "events.create"),
        "can_generate_route": tabs["operations"] and has_permission(user, "routes.generate"),
        "can_generate_service_order": tabs["events"] and has_permission(user, "events.service_order"),
        "can_receive_payment": has_permission(user, "finance.payments"),
        "can_manage_access": has_permission(user, "settings.manage"),
    }


def load_settings() -> dict:
    ensure_storage_dirs()
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return {
        "cost_per_km": float(data.get("cost_per_km") or 0.0),
        "quote_models": data.get("quote_models") if isinstance(data.get("quote_models"), dict) else {},
        "last_backup_at": data.get("last_backup_at", ""),
        "last_backup_file": data.get("last_backup_file", ""),
        "last_backup_warnings": data.get("last_backup_warnings") if isinstance(data.get("last_backup_warnings"), list) else [],
        "last_closeout_at": data.get("last_closeout_at", ""),
    }


def save_settings(settings: dict) -> None:
    ensure_storage_dirs()
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def backup_config() -> BackupConfig:
    return BackupConfig(
        backups_dir=BACKUPS_DIR,
        data_dir=DATA_DIR,
        storage_root=STORAGE_ROOT,
        important_data_paths=IMPORTANT_DATA_PATHS,
        retention_limit=BACKUP_RETENTION_LIMIT,
        load_settings=load_settings,
        save_settings=save_settings,
        now_iso=now_iso,
        record_audit=record_audit,
        clean_text=clean_text,
        format_datetime_br=format_datetime_br,
    )


def list_backup_files() -> list[Path]:
    return backup_service_list_files(backup_config())


def backup_file_created_at(path: Path | None) -> str:
    return backup_service_file_created_at(path)


def prune_old_backups(*, keep: int = BACKUP_RETENTION_LIMIT) -> list[str]:
    return backup_service_prune_old(backup_config(), keep=keep)


def write_data_backup_archive(target, *, generated_at: str, trigger: str) -> dict:
    return backup_service_write_archive(backup_config(), target, generated_at=generated_at, trigger=trigger)


def create_data_backup(*, trigger: str = "manual", audit_action: str | None = "create") -> dict:
    return backup_service_create(backup_config(), trigger=trigger, audit_action=audit_action)


def restore_data_backup(path: Path) -> dict:
    return backup_service_restore(backup_config(), path)


def build_backup_status(settings: dict | None = None) -> dict:
    return backup_service_status(backup_config(), settings)


def maybe_create_automatic_backup() -> None:
    user = current_user()
    if clean_text(user.get("role")) == "guest":
        return
    status = build_backup_status()
    backup_age_days = days_since_iso(status.get("last_backup_at"))
    if backup_age_days is None or backup_age_days >= 1:
        create_data_backup(trigger="automatico", audit_action="automatic")


def audit_entry_date(entry: dict):
    try:
        return datetime.fromisoformat(clean_text(entry.get("created_at"))).date()
    except ValueError:
        return None


def parse_filter_date(value: str | None):
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def build_audit_log_view() -> dict:
    all_entries = load_audit_log()
    filters = {
        "user": clean_text(request.args.get("audit_user")) if has_request_context() else "",
        "action": clean_text(request.args.get("audit_action")) if has_request_context() else "",
        "module": clean_text(request.args.get("audit_module")) if has_request_context() else "",
        "date_from": clean_text(request.args.get("audit_date_from")) if has_request_context() else "",
        "date_to": clean_text(request.args.get("audit_date_to")) if has_request_context() else "",
    }
    date_from = parse_filter_date(filters["date_from"])
    date_to = parse_filter_date(filters["date_to"])
    filtered = []
    for entry in all_entries:
        user_text = " ".join(
            [
                clean_text(entry.get("user_id")),
                clean_text(entry.get("user_name")),
                clean_text(entry.get("user_email")),
                clean_text(entry.get("user_role")),
            ]
        ).lower()
        if filters["user"] and filters["user"].lower() not in user_text:
            continue
        if filters["action"] and clean_text(entry.get("action")) != filters["action"]:
            continue
        if filters["module"] and clean_text(entry.get("module")) != filters["module"]:
            continue
        entry_date = audit_entry_date(entry)
        if date_from and (not entry_date or entry_date < date_from):
            continue
        if date_to and (not entry_date or entry_date > date_to):
            continue
        filtered.append(entry)

    def option_rows(field: str, labels: dict[str, str]) -> list[dict]:
        values = sorted({clean_text(entry.get(field)) for entry in all_entries if clean_text(entry.get(field))})
        return [{"value": value, "label": audit_label(labels, value)} for value in values]

    users = sorted(
        {
            clean_text(entry.get("user_email")) or clean_text(entry.get("user_name")) or clean_text(entry.get("user_id"))
            for entry in all_entries
            if clean_text(entry.get("user_email")) or clean_text(entry.get("user_name")) or clean_text(entry.get("user_id"))
        }
    )
    entries = []
    for entry in filtered[:80]:
        entries.append(
            {
                **entry,
                "action_label": entry.get("action_label") or audit_label(AUDIT_ACTION_LABELS, entry.get("action"), "Ação"),
                "module_label": entry.get("module_label") or audit_label(AUDIT_MODULE_LABELS, entry.get("module"), "Geral"),
                "entity_label": clean_text(entry.get("target_id")) or "geral",
                "actor_label": clean_text(entry.get("user_name")) or clean_text(entry.get("user_email")) or "Sistema",
                "ip_label": clean_text(entry.get("ip_address")) or "n/d",
                "request_label": " ".join([clean_text(entry.get("request_method")), clean_text(entry.get("request_path"))]).strip(),
                "changes": entry.get("changes") or audit_change_preview(entry.get("before"), entry.get("after")),
            }
        )
    return {
        "entries": entries,
        "total": len(all_entries),
        "filtered_total": len(filtered),
        "filters": filters,
        "users": users,
        "actions": option_rows("action", AUDIT_ACTION_LABELS),
        "modules": option_rows("module", AUDIT_MODULE_LABELS),
    }


def build_system_status_snapshot() -> dict:
    ensure_storage_dirs()
    settings = load_settings()
    backup_status = build_backup_status(settings)
    users = load_users()
    active_users = [user for user in users if clean_text(user.get("status")) == "ativo"]
    pending_invitations = [user for user in users if clean_text(user.get("status")) == "convite_pendente"]
    storage_ready = all(path.exists() for path in (DATA_DIR, PREVIEW_DIR, UPLOADS_DIR))
    backup_age_days = days_since_iso(backup_status.get("last_backup_at"))
    closeout_age_days = days_since_iso(settings.get("last_closeout_at"))
    health = {
        "ok": True,
        "storage_ready": storage_ready,
        "has_secret_key": SECRET_KEY_CONFIGURED,
        "has_recent_backup": backup_age_days is not None and backup_age_days <= 7,
        "has_recent_closeout": closeout_age_days is not None and closeout_age_days <= 7,
        "backup_age_days": backup_age_days,
        "closeout_age_days": closeout_age_days,
    }
    metadata = {
        "app_version": APP_VERSION,
        "deploy_target": DEPLOY_TARGET,
        "storage_root": str(STORAGE_ROOT),
        "generated_at": now_iso(),
    }
    counts = {
        "clients": len(load_clients()),
        "vehicles": len(load_vehicles_registry()),
        "events": len(load_events()),
        "equipment": len(load_equipment_registry()),
        "active_users": len(active_users),
        "pending_invitations": len(pending_invitations),
    }
    operations = {
        "last_backup_at": clean_text(backup_status.get("last_backup_at")),
        "last_closeout_at": clean_text(settings.get("last_closeout_at")),
        "backup_age_days": backup_age_days,
        "backup_count": backup_status.get("count", 0),
        "latest_backup_file": backup_status.get("latest_filename", ""),
        "closeout_age_days": closeout_age_days,
        "has_route_pdf": ROUTE_PDF_PATH.exists(),
        "has_route_json": ROUTE_JSON_PATH.exists(),
    }
    return {
        "health": health,
        "metadata": metadata,
        "counts": counts,
        "operations": operations,
    }


def build_security_technical_checklist(security_posture: dict, system_status: dict) -> list[dict]:
    health = system_status.get("health") or {}
    return [
        {
            "item": "Login obrigatório para áreas internas",
            "status": "Verificado",
            "risk": "Baixo",
            "next_action": "Manter rotas internas com permissão obrigatória.",
        },
        {
            "item": "Senhas fortes",
            "status": "Verificado" if security_posture.get("password_rotation_pending", 0) == 0 else "Atenção",
            "risk": "Médio" if security_posture.get("password_rotation_pending", 0) else "Baixo",
            "next_action": "Concluir trocas de senha inicial pendentes.",
        },
        {
            "item": "Hash seguro de senha",
            "status": "Verificado",
            "risk": "Baixo",
            "next_action": "Continuar salvando somente senha criptografada.",
        },
        {
            "item": "Proteção de rotas e permissões por perfil",
            "status": "Verificado",
            "risk": "Baixo",
            "next_action": "Revisar funções quando criar novos acessos.",
        },
        {
            "item": "Sessão com expiração e logout",
            "status": "Verificado",
            "risk": "Baixo",
            "next_action": "Avaliar reduzir a sessão se celulares forem compartilhados.",
        },
        {
            "item": "Variáveis sensíveis fora do código",
            "status": "Verificado" if health.get("has_secret_key") else "Atenção",
            "risk": "Médio" if not health.get("has_secret_key") else "Baixo",
            "next_action": "Definir SANNYGOLD_SECRET_KEY fixa no provedor antes do uso diário.",
        },
        {
            "item": "Secret key padrão removida",
            "status": "Verificado",
            "risk": "Baixo",
            "next_action": "Usar uma chave forte em ambiente de produção.",
        },
        {
            "item": "Logs de ações críticas",
            "status": "Verificado",
            "risk": "Baixo",
            "next_action": "Acompanhar alterações de usuários, financeiro, estoque e cadastros.",
        },
        {
            "item": "Backup manual",
            "status": "Verificado" if health.get("has_recent_backup") else "Atenção",
            "risk": "Baixo" if health.get("has_recent_backup") else "Médio",
            "next_action": "Gerar backup antes de iniciar uso diário da equipe.",
        },
        {
            "item": "Backup automático",
            "status": "Pendente",
            "risk": "Médio",
            "next_action": "Configurar rotina externa ou agendamento no provedor.",
        },
    ]


def homologation_item(
    name: str,
    approved: bool,
    *,
    problem: str,
    next_action: str,
    target_href: str,
    target_tab: str = "",
    action: str = "Abrir módulo",
    error: bool = False,
) -> dict:
    return {
        "name": name,
        "status": "Aprovado" if approved else "Erro" if error else "Pendente",
        "problem": "Sem problema encontrado." if approved else problem,
        "next_action": "Manter validação antes da produção." if approved else next_action,
        "target_href": target_href,
        "target_tab": target_tab,
        "action": action,
    }


def build_homologation_checklist(
    *,
    clients: list[dict],
    events: list[dict],
    vehicles: list[dict],
    inventory: list[dict],
    route_data: dict | None,
    users: list[dict],
    settings: dict,
    system_status: dict,
    field_confirmations: list[dict],
) -> dict:
    active_users = [user for user in users if clean_text(user.get("status")) == "ativo"]
    admin_password_env = os.environ.get("SANNYGOLD_ADMIN_PASSWORD", "")
    has_default_password_env = not admin_password_env or admin_password_env == "Sanny123Gold"
    password_rotation_pending = any(bool(user.get("must_change_password")) for user in active_users)
    event_has_equipment = any(
        any(client.get("client_id") in event.get("client_ids", []) and clean_text(client.get("equipment_number")) for client in clients)
        for event in events
    )
    checklist_marked = any(any(item.get("done") for item in event.get("checklist", [])) for event in events)
    equipment_returned = any(clean_text(item.get("returned_at")) for item in inventory) or any(
        clean_text(item.get("return_confirmed_at")) for item in field_confirmations
    )
    required_env = {
        "SANNYGOLD_SECRET_KEY": SECRET_KEY_CONFIGURED,
        "SANNYGOLD_ADMIN_EMAIL": bool(os.environ.get("SANNYGOLD_ADMIN_EMAIL")),
        "SANNYGOLD_ADMIN_PASSWORD": bool(admin_password_env) and not has_default_password_env,
    }
    persistent_storage_ready = bool(os.environ.get("ROTAFLOW_STORAGE_DIR")) and STORAGE_ROOT.exists()
    route_ready = bool(route_data and route_data.get("routes"))
    pdf_ready = ROUTE_PDF_PATH.exists()
    health_ready = bool(system_status.get("health", {}).get("ok") and system_status.get("health", {}).get("storage_ready"))
    permission_ready = (
        has_permission({"role": "admin"}, "settings.manage")
        and has_permission({"role": "operacional"}, "routes.generate")
        and not has_permission({"role": "operacional"}, "finance.view")
        and not has_permission({"role": "leitura"}, "clients.edit")
    )

    items = [
        homologation_item(
            "1. Criar cliente",
            bool(clients),
            problem="Nenhum cliente cadastrado para validar a operação.",
            next_action="Criar um cliente real ou de teste com endereço completo.",
            target_href="#clients-pane",
            target_tab="clients-tab",
            action="Abrir clientes",
        ),
        homologation_item(
            "2. Criar locação/evento",
            bool(events),
            problem="Nenhuma locação ou evento cadastrado.",
            next_action="Criar uma locação/evento com data, cliente e status definido.",
            target_href="#events-pane",
            target_tab="events-tab",
            action="Abrir eventos",
        ),
        homologation_item(
            "3. Cadastrar veículo",
            bool(vehicles),
            problem="Nenhum veículo cadastrado.",
            next_action="Cadastrar ao menos um veículo para geração de rota.",
            target_href="#fleet-pane",
            target_tab="fleet-tab",
            action="Abrir frota",
        ),
        homologation_item(
            "4. Cadastrar equipamento",
            bool(inventory),
            problem="Nenhum equipamento cadastrado.",
            next_action="Cadastrar ao menos um banheiro, trailer ou equipamento de apoio.",
            target_href="#fleet-pane",
            target_tab="fleet-tab",
            action="Abrir equipamentos",
        ),
        homologation_item(
            "5. Vincular equipamento ao evento",
            event_has_equipment,
            problem="Ainda não há evento com cliente/equipamento vinculado.",
            next_action="Vincular cliente com equipamento a uma locação/evento.",
            target_href="#events-pane",
            target_tab="events-tab",
            action="Revisar evento",
        ),
        homologation_item(
            "6. Gerar rota",
            route_ready,
            problem="Nenhuma rota válida gerada.",
            next_action="Validar dados e gerar uma rota com cliente e veículo.",
            target_href="#operations-pane",
            target_tab="operations-tab",
            action="Gerar rota",
        ),
        homologation_item(
            "7. Gerar PDF/Ordem de Serviço",
            pdf_ready or bool(events),
            problem="Nenhum PDF de rota ou ordem de serviço foi validado.",
            next_action="Gerar rota em PDF ou baixar a OS de um evento.",
            target_href="#operations-pane",
            target_tab="operations-tab",
            action="Abrir PDFs",
        ),
        homologation_item(
            "8. Registrar checklist operacional",
            checklist_marked,
            problem="Nenhum checklist operacional foi marcado em evento.",
            next_action="Editar um evento e marcar os itens conferidos antes da operação.",
            target_href="#events-pane",
            target_tab="events-tab",
            action="Abrir eventos",
        ),
        homologation_item(
            "9. Registrar retorno de equipamento",
            equipment_returned,
            problem="Nenhum retorno de equipamento foi registrado.",
            next_action="Confirmar retorno pelo mapa/rota ou pelo cadastro do equipamento.",
            target_href="#operations-pane",
            target_tab="operations-tab",
            action="Confirmar retorno",
        ),
        homologation_item(
            "10. Gerar backup",
            bool(clean_text(settings.get("last_backup_at"))),
            problem="Backup completo ainda não foi gerado.",
            next_action="Baixar um backup antes de liberar uso diário.",
            target_href=url_for("download_system_backup"),
            action="Gerar backup",
        ),
        homologation_item(
            "11. Validar persistência após reinício/redeploy",
            persistent_storage_ready,
            problem="Diretório persistente não foi confirmado por variável ROTAFLOW_STORAGE_DIR.",
            next_action="Configurar ROTAFLOW_STORAGE_DIR em disco persistente no Render e testar redeploy.",
            target_href="#system-readiness-panel",
            action="Ver status",
            error=DEPLOY_TARGET == "render",
        ),
        homologation_item(
            "12. Validar login",
            bool(active_users),
            problem="Nenhum usuário ativo cadastrado.",
            next_action="Criar ou reativar usuário administrador antes da produção.",
            target_href="#access-pane",
            target_tab="access-tab",
            action="Abrir acessos",
            error=not active_users,
        ),
        homologation_item(
            "13. Validar permissões por perfil",
            permission_ready,
            problem="Matriz básica de permissões não está consistente.",
            next_action="Revisar permissões de admin, operação, financeiro e leitura.",
            target_href="#access-pane",
            target_tab="access-tab",
            action="Abrir acessos",
            error=not permission_ready,
        ),
        homologation_item(
            "14. Validar se não existe senha padrão ativa",
            not has_default_password_env and not password_rotation_pending,
            problem="Senha inicial padrão ou troca de senha pendente ainda existe.",
            next_action="Definir SANNYGOLD_ADMIN_PASSWORD forte e trocar senhas iniciais pendentes.",
            target_href="#access-pane",
            target_tab="access-tab",
            action="Abrir acessos",
            error=has_default_password_env,
        ),
        homologation_item(
            "15. Validar variáveis de ambiente obrigatórias",
            all(required_env.values()),
            problem="Faltam variáveis obrigatórias: " + ", ".join(key for key, ok in required_env.items() if not ok),
            next_action="Configurar variáveis sensíveis no Render, fora do código.",
            target_href="#system-readiness-panel",
            action="Ver ambiente",
            error=not all(required_env.values()),
        ),
        homologation_item(
            "16. Validar endpoint /health ou /status",
            health_ready,
            problem="/health não confirmou armazenamento e execução saudáveis.",
            next_action="Abrir /health e corrigir armazenamento ou inicialização se retornar erro.",
            target_href=url_for("healthcheck"),
            action="Abrir health",
            error=not health_ready,
        ),
    ]
    return {
        "items": items,
        "approved": sum(1 for item in items if item["status"] == "Aprovado"),
        "pending": sum(1 for item in items if item["status"] == "Pendente"),
        "errors": sum(1 for item in items if item["status"] == "Erro"),
    }


def upsert_item(items: list[dict], record: dict, key: str) -> list[dict]:
    by_key = {item[key]: item for item in items if item.get(key)}
    by_key[record[key]] = record
    return list(by_key.values())


def delete_item(items: list[dict], key: str, value: str) -> tuple[list[dict], bool]:
    filtered = [item for item in items if item.get(key) != value]
    return filtered, len(filtered) != len(items)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def format_datetime_br(value: str | None) -> str:
    text = clean_text(value)
    if not text:
        return "nunca"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    return parsed.strftime("%d/%m/%Y %H:%M")


def days_since_iso(value: str | None) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return max((datetime.now() - parsed).days, 0)


def format_date_br(value: str | None) -> str:
    parsed = parse_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else clean_text(value)


def format_currency_br(value) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def login_attempt_key(email: str) -> str:
    return f"{clean_text(email).lower()}|{request.remote_addr or 'local'}"


def login_is_locked(email: str) -> bool:
    key = login_attempt_key(email)
    attempt = LOGIN_ATTEMPTS.get(key) or {}
    locked_until = attempt.get("locked_until")
    if not locked_until:
        return False
    if datetime.now() < locked_until:
        return True
    LOGIN_ATTEMPTS.pop(key, None)
    return False


def record_failed_login(email: str) -> None:
    key = login_attempt_key(email)
    attempt = LOGIN_ATTEMPTS.get(key) or {"count": 0}
    attempt["count"] = int(attempt.get("count") or 0) + 1
    attempt["last_attempt_at"] = datetime.now()
    if attempt["count"] >= MAX_LOGIN_ATTEMPTS:
        attempt["locked_until"] = datetime.now() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
    LOGIN_ATTEMPTS[key] = attempt


def clear_failed_login(email: str) -> None:
    LOGIN_ATTEMPTS.pop(login_attempt_key(email), None)


def criticality_key(level: str | None = "") -> str:
    normalized = clean_text(level).lower()
    if normalized in {"danger", "alta", "bloqueio", "block", "critical"}:
        return "block"
    if normalized in {"warning", "media", "média", "atencao", "atenção", "attention"}:
        return "attention"
    if normalized in {"success", "baixa", "pronto", "ready", "ok"}:
        return "ready"
    return "info"


def criticality_class(level: str | None = "") -> str:
    return f"crit-{criticality_key(level)}"


def criticality_badge_class(level: str | None = "") -> str:
    return f"severity-{criticality_key(level)}"


def criticality_label(level: str | None = "") -> str:
    return {
        "block": "Bloqueio",
        "attention": "Atenção",
        "ready": "Pronto",
        "info": "Informativo",
    }[criticality_key(level)]


app.jinja_env.filters["datetime_br"] = format_datetime_br
app.jinja_env.filters["date_br"] = format_date_br
app.jinja_env.filters["currency_br"] = format_currency_br
app.jinja_env.globals["criticality_class"] = criticality_class
app.jinja_env.globals["criticality_badge_class"] = criticality_badge_class
app.jinja_env.globals["criticality_label"] = criticality_label


def google_maps_enabled() -> bool:
    return bool(clean_text(os.environ.get("GOOGLE_MAPS_API_KEY") or GOOGLE_MAPS_API_KEY))


def google_maps_api_key() -> str:
    return clean_text(os.environ.get("GOOGLE_MAPS_API_KEY") or GOOGLE_MAPS_API_KEY)


def google_maps_directions_url(stops: list[dict], origin_lat: float = HQ_LAT, origin_lng: float = HQ_LNG) -> str:
    valid_stops = [stop for stop in stops if stop.get("lat") is not None and stop.get("lng") is not None]
    if not valid_stops:
        return f"https://www.google.com/maps/search/?api=1&query={origin_lat},{origin_lng}"
    destination = valid_stops[-1]
    params = {
        "api": "1",
        "origin": f"{origin_lat},{origin_lng}",
        "destination": f"{destination.get('lat')},{destination.get('lng')}",
        "travelmode": "driving",
    }
    waypoints = valid_stops[:-1][:8]
    if waypoints:
        params["waypoints"] = "|".join(f"{stop.get('lat')},{stop.get('lng')}" for stop in waypoints)
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params)


def google_maps_embed_directions_url(stops: list[dict], origin_lat: float = HQ_LAT, origin_lng: float = HQ_LNG) -> str:
    key = google_maps_api_key()
    valid_stops = [stop for stop in stops if stop.get("lat") is not None and stop.get("lng") is not None]
    if not key or not valid_stops:
        return ""
    destination = valid_stops[-1]
    params = {
        "key": key,
        "origin": f"{origin_lat},{origin_lng}",
        "destination": f"{destination.get('lat')},{destination.get('lng')}",
        "mode": "driving",
    }
    waypoints = valid_stops[:-1][:20]
    if waypoints:
        params["waypoints"] = "|".join(f"{stop.get('lat')},{stop.get('lng')}" for stop in waypoints)
    return "https://www.google.com/maps/embed/v1/directions?" + urllib.parse.urlencode(params)


def parse_date(value: str | None):
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def event_start_date(event: dict):
    return parse_date(event.get("event_date"))


def event_end_date(event: dict):
    return parse_date(event.get("event_end_date") or event.get("event_date"))


def event_period_label(event: dict) -> str:
    start = clean_text(event.get("event_date"))
    end = clean_text(event.get("event_end_date"))
    if start and end and end != start:
        return f"{start} até {end}"
    return start or "sem data"


def event_duration_days(event: dict) -> int:
    start = event_start_date(event)
    end = event_end_date(event)
    if not start or not end or end < start:
        return 0
    return (end - start).days


def event_billable_days(event: dict | None) -> int:
    if not event:
        return 1
    start = event_start_date(event)
    end = event_end_date(event)
    if not start or not end or end < start:
        return 1
    return max((end - start).days + 1, 1)


def add_months(source_date, months: int):
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return source_date.replace(year=year, month=month, day=day)


def recurrence_step_days(event: dict) -> int:
    frequency = clean_text(event.get("recurrence_frequency"))
    if frequency == "semanal":
        return 7
    if frequency == "quinzenal":
        return 14
    if frequency == "mensal":
        return 30
    return max(int(event.get("recurrence_interval_days") or 30), 1)


def next_recurrence_date(event: dict, reference_date=None) -> str:
    if clean_text(event.get("recurrence_enabled")) not in {"true", "1", "sim", "yes"}:
        return ""
    if clean_text(event.get("recurrence_status"), "ativo") not in RECURRENCE_STATUS_OPTIONS:
        return ""
    if clean_text(event.get("recurrence_status"), "ativo") != "ativo":
        return ""
    start_date = parse_date(event.get("recurrence_start") or event.get("event_date"))
    end_date = parse_date(event.get("recurrence_end"))
    if not start_date:
        return ""
    current = reference_date or datetime.now().date()
    if current < start_date:
        return start_date.isoformat()
    candidate = start_date
    frequency = clean_text(event.get("recurrence_frequency"))
    while candidate <= current:
        if frequency == "mensal":
            candidate = add_months(candidate, 1)
        else:
            candidate = candidate.fromordinal(candidate.toordinal() + recurrence_step_days(event))
    if end_date and candidate > end_date:
        return ""
    return candidate.isoformat()


def normalize_equipment_status(value: str | None) -> str:
    status = clean_text(value, "disponivel") or "disponivel"
    return status if status in EQUIPMENT_STATUS_OPTIONS else "disponivel"


def normalize_business_text(value: str | None) -> str:
    text = clean_text(value).lower()
    replacements = {
        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def equipment_family(equipment_type: str | None) -> str:
    text = normalize_business_text(equipment_type)
    if "climat" in text:
        return "climatizacao"
    if "hidrat" in text or "agua" in text:
        return "hidratacao"
    if "quimic" in text:
        return "banheiro_quimico"
    if "banheiro" in text or "lavabo" in text or "pcd" in text or "trailer" in text or "cabine" in text:
        return "banheiro_luxo"
    return "apoio"


def equipment_family_label(family: str) -> str:
    return {
        "banheiro_luxo": "Banheiro de luxo",
        "banheiro_quimico": "Banheiro químico",
        "climatizacao": "Climatização",
        "hidratacao": "Hidratação",
        "apoio": "Apoio",
    }.get(family, "Apoio")


def build_equipment_family_counts(equipment_items: list[dict]) -> dict:
    counts = {
        "banheiro_luxo": 0,
        "banheiro_quimico": 0,
        "climatizacao": 0,
        "hidratacao": 0,
        "apoio": 0,
    }
    for item in equipment_items:
        counts[equipment_family(item.get("equipment_type"))] += 1
    return counts


def pending_reason_label(code: str) -> str:
    return PENDING_REASON_LABELS.get(code, code.replace("_", " "))


def event_is_active(event: dict) -> bool:
    return normalize_event_status(event.get("status")) in ACTIVE_EVENT_STATUSES


def event_overlaps_date(event: dict, target_date: str) -> bool:
    target = parse_date(target_date)
    start = event_start_date(event)
    end = event_end_date(event)
    if not target or not start or not end:
        return False
    return start <= target <= end


def event_overlaps_period(event: dict, start_date: str, end_date: str | None = None) -> bool:
    target_start = parse_date(start_date)
    target_end = parse_date(end_date or start_date)
    current_start = event_start_date(event)
    current_end = event_end_date(event)
    if not target_start or not target_end or not current_start or not current_end:
        return False
    return current_start <= target_end and target_start <= current_end


def client_has_valid_address(client: dict) -> bool:
    return bool(clean_text(client.get("address")) and client.get("lat") is not None and client.get("lng") is not None)


def get_event_clients(event: dict, clients: list[dict]) -> list[dict]:
    client_ids = set(event.get("client_ids") or [])
    return [client for client in clients if client.get("client_id") in client_ids]


def get_event_vehicles(event: dict, vehicles: list[dict]) -> list[dict]:
    vehicle_ids = set(event.get("vehicle_ids") or [])
    return [vehicle for vehicle in vehicles if vehicle.get("vehicle_id") in vehicle_ids]


def event_financial_value_defined(event: dict) -> bool:
    return any(
        parse_decimal(event.get(field)) > 0
        for field in ("valor_servico", "valor_adicional", "recurring_value")
    ) or bool(event.get("financial_summary"))


def event_route_generated(event: dict, route_data: dict | None) -> bool:
    event_id = clean_text(event.get("event_id"))
    if clean_text(event.get("last_route_generated_at")):
        return True
    route_event_id = clean_text((route_data or {}).get("event_id"))
    route_stops = [stop for route in (route_data or {}).get("routes", []) or [] for stop in route.get("stops", []) or []]
    return bool(event_id and route_event_id == event_id and route_stops)


def event_service_order_generated(event: dict, audit_log: list[dict] | None) -> bool:
    event_id = clean_text(event.get("event_id"))
    if not event_id:
        return False
    for item in audit_log or []:
        if clean_text(item.get("module")) != "events" or clean_text(item.get("target_id")) != event_id:
            continue
        action = normalize_status_key(item.get("action"))
        detail = normalize_status_key(item.get("detail"))
        if action in {"generate_service_order", "download_service_order"}:
            return True
        if action == "download" and "ordem_de_servico" in detail:
            return True
    return False


def event_status_missing_items(event: dict, linked_clients: list[dict], *, can_view_finance: bool = False) -> list[str]:
    missing = []
    if not clean_text(event.get("event_date")):
        missing.append("Data do serviço ausente")
    if not event.get("client_ids") or not linked_clients:
        missing.append("Cliente não vinculado")
    if linked_clients and not any(clean_text(client.get("phone")) for client in linked_clients):
        missing.append("Telefone do cliente ausente")
    if not linked_clients or not any(client_has_valid_address(client) for client in linked_clients):
        missing.append("Endereço incompleto")
    if linked_clients and not any(clean_text(client.get("equipment_type")) for client in linked_clients):
        missing.append("Serviço/equipamento não definido")
    quantity_total = 0
    for client in linked_clients:
        try:
            quantity_total += int(float(client.get("equipment_quantity") or 0))
        except (TypeError, ValueError):
            continue
    if quantity_total <= 0:
        missing.append("Quantidade não informada")
    if not clean_text(event.get("responsible") or event.get("responsavel") or event.get("assigned_to")):
        missing.append("Responsável interno ausente")
    if can_view_finance and not event_financial_value_defined(event):
        missing.append("Valor previsto não informado")
    return missing


def build_event_status_context(
    event: dict,
    linked_clients: list[dict],
    route_data: dict | None,
    audit_log: list[dict] | None,
    *,
    can_view_finance: bool = False,
) -> dict:
    event_id = clean_text(event.get("event_id"))
    raw_status = clean_text(event.get("status"))
    raw_key = normalize_status_key(raw_status)
    stored_status = normalize_event_status(raw_status)
    missing = event_status_missing_items(event, linked_clients, can_view_finance=can_view_finance)
    route_ready = event_route_generated(event, route_data)
    service_order_ready = event_service_order_generated(event, audit_log)

    status = stored_status
    if stored_status not in {"rascunho", "em_andamento", "concluido", "aguardando_pagamento", "pago", "cancelado"}:
        if missing:
            status = "pendente_dados"
        elif not route_ready:
            status = "rota_pendente"
        elif not service_order_ready:
            status = "os_pendente"
        elif stored_status in {"confirmado", "rota_pendente", "os_pendente"}:
            status = "programado"
    if stored_status == "programado" and missing:
        status = "pendente_dados"

    next_step = dict(EVENT_STATUS_NEXT_STEPS.get(status, EVENT_STATUS_NEXT_STEPS["rascunho"]))
    if event_id and next_step.get("target_href") == "#events-pane":
        next_step["target_href"] = f"#event-{event_id}"
    if status == "os_pendente" and event_id and has_request_context():
        next_step["target_href"] = url_for("download_service_order", event_id=event_id)
        next_step["target_tab"] = ""

    return {
        "status": status,
        "source_status": stored_status,
        "raw_status": raw_status,
        "is_mapped_from_old": bool(raw_status and raw_key not in EVENT_STATUS_OPTIONS and EVENT_STATUS_ALIASES.get(raw_key)),
        "is_derived": status != stored_status,
        "label": EVENT_STATUS_LABELS.get(status, event_status_label(status)),
        "description": EVENT_STATUS_DESCRIPTIONS.get(status, ""),
        "badge_class": EVENT_STATUS_BADGE_CLASSES.get(status, "badge-fixed"),
        "next_step": next_step.get("message", ""),
        "action_label": next_step.get("action", "Abrir"),
        "target_tab": next_step.get("target_tab", "events-tab"),
        "target_href": next_step.get("target_href", f"#event-{event_id}" if event_id else "#events-pane"),
        "missing": missing,
        "missing_summary": ", ".join(missing[:4]),
        "route_ready": route_ready,
        "service_order_ready": service_order_ready,
    }


def recommendation_card(
    title: str,
    detail: str,
    action: str,
    href: str,
    *,
    tab: str = "",
    severity: str = "attention",
) -> dict:
    badge_classes = {
        "critical": "badge-danger",
        "attention": "badge-avulso",
        "low": "badge-fixed",
        "ready": "badge-success",
    }
    labels = {
        "critical": "crítica",
        "attention": "atenção",
        "low": "baixa",
        "ready": "pronto",
    }
    return {
        "title": title,
        "detail": detail,
        "action": action,
        "href": href,
        "tab": tab,
        "severity": severity,
        "severity_label": labels.get(severity, labels["attention"]),
        "badge_class": badge_classes.get(severity, badge_classes["attention"]),
    }


def event_receivables(event: dict, receivables: list[dict] | None) -> list[dict]:
    event_id = clean_text(event.get("event_id"))
    if not event_id:
        return []
    return [
        item for item in receivables or []
        if clean_text(item.get("event_id")) == event_id
    ]


def event_payment_registered(event: dict, receivables: list[dict] | None) -> bool:
    if normalize_event_status(event.get("status")) == "pago":
        return True
    related = event_receivables(event, receivables)
    return bool(related) and all(receivable_is_paid(item) for item in related)


def build_event_recommended_actions(
    event: dict,
    linked_clients: list[dict],
    route_data: dict | None,
    audit_log: list[dict] | None,
    receivables: list[dict] | None,
    *,
    can_view_finance: bool = False,
) -> list[dict]:
    event_id = clean_text(event.get("event_id"))
    status = normalize_event_status(event.get("status"))
    target_event = f"#event-{event_id}" if event_id else "#events-pane"
    first_client_id = clean_text((linked_clients[0] if linked_clients else {}).get("client_id"))
    target_client = f"#client-{first_client_id}" if first_client_id else target_event
    active_status = status not in {"concluido", "pago", "cancelado"}
    route_ready = event_route_generated(event, route_data)
    service_order_ready = event_service_order_generated(event, audit_log)
    has_address = any(client_has_valid_address(client) for client in linked_clients)
    has_equipment = any(clean_text(client.get("equipment_type")) for client in linked_clients)
    quantity_total = sum(int(parse_decimal(client.get("equipment_quantity"))) for client in linked_clients)
    paid = event_payment_registered(event, receivables)
    actions: list[dict] = []

    if not has_address:
        actions.append(
            recommendation_card(
                "Completar endereço",
                "Endereço incompleto impede rota, ordem de serviço e orientação da equipe.",
                "Completar endereço",
                target_client,
                tab="clients-tab" if first_client_id else "events-tab",
                severity="critical",
            )
        )
    if not has_equipment or quantity_total <= 0:
        actions.append(
            recommendation_card(
                "Adicionar equipamento",
                "Defina serviço/equipamento e quantidade antes de liberar a operação.",
                "Adicionar equipamento",
                target_client,
                tab="clients-tab" if first_client_id else "events-tab",
                severity="critical",
            )
        )
    if active_status and not route_ready:
        actions.append(
            recommendation_card(
                "Gerar rota",
                "A rota ainda não foi gerada para esta locação.",
                "Gerar rota",
                "#gerador",
                tab="operations-tab",
                severity="attention",
            )
        )
    if active_status and route_ready and not service_order_ready:
        os_href = url_for("download_service_order", event_id=event_id) if event_id and has_request_context() else target_event
        actions.append(
            recommendation_card(
                "Gerar ordem de serviço",
                "A OS ainda não aparece na auditoria desta locação.",
                "Gerar ordem de serviço",
                os_href,
                tab="" if os_href.startswith("/") else "events-tab",
                severity="attention",
            )
        )
    if status in {"concluido", "aguardando_pagamento"} and can_view_finance and not paid:
        actions.append(
            recommendation_card(
                "Lançar recebimento",
                "Locação concluída sem pagamento registrado para este evento.",
                "Lançar recebimento",
                "#receivables-panel",
                tab="summary-tab",
                severity="critical",
            )
        )
    if paid:
        actions.append(
            recommendation_card(
                "Arquivar ou finalizar",
                "Pagamento registrado. Revise se a locação pode ficar apenas no histórico.",
                "Revisar encerramento",
                target_event,
                tab="events-tab",
                severity="ready",
            )
        )
    if not actions and status != "cancelado":
        actions.append(
            recommendation_card(
                "Acompanhar locação",
                "Sem bloqueio crítico detectado. Acompanhe data, equipe e status.",
                "Abrir agenda",
                "#agenda-operacional-panel",
                tab="agenda-tab",
                severity="low",
            )
        )
    return actions[:3]


def build_event_commitments(events: list[dict], clients: list[dict]) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    equipment_usage: dict[str, list[dict]] = {}
    vehicle_usage: dict[str, list[dict]] = {}
    clients_by_id = {client.get("client_id"): client for client in clients if client.get("client_id")}
    for event in events:
        if not event_is_active(event):
            continue
        event_stub = {
            "event_id": clean_text(event.get("event_id")),
            "title": clean_text(event.get("title")),
            "event_date": clean_text(event.get("event_date")),
            "event_end_date": clean_text(event.get("event_end_date")),
            "status": normalize_event_status(event.get("status")),
        }
        for client_id in event.get("client_ids", []) or []:
            client = clients_by_id.get(client_id)
            equipment_id = clean_text((client or {}).get("equipment_number"))
            if equipment_id:
                equipment_usage.setdefault(equipment_id, []).append(event_stub)
        for vehicle_id in event.get("vehicle_ids", []) or []:
            if clean_text(vehicle_id):
                vehicle_usage.setdefault(clean_text(vehicle_id), []).append(event_stub)
    return equipment_usage, vehicle_usage


def create_client_record(form) -> dict:
    clients = load_clients()
    return create_client_record_from_values(
        {
            "client_id": form.get("client_id"),
            "customer_name": form.get("customer_name"),
            "contact_name": form.get("contact_name"),
            "phone": form.get("phone"),
            "cpf_cnpj": form.get("cpf_cnpj"),
            "email": form.get("email"),
            "invoice_status": form.get("invoice_status"),
            "invoice_number": form.get("invoice_number"),
            "address": form.get("client_address"),
            "lat": form.get("client_lat"),
            "lng": form.get("client_lng"),
            "client_type": form.get("client_type"),
            "equipment_type": form.get("equipment_type"),
            "equipment_quantity": form.get("equipment_quantity"),
            "equipment_number": form.get("equipment_number"),
            "billing_model": form.get("billing_model"),
            "cleaning_frequency": form.get("cleaning_frequency"),
            "service_profile": form.get("service_profile"),
            "default_service_minutes": form.get("default_service_minutes"),
            "default_priority": form.get("default_priority"),
            "window_start": form.get("window_start"),
            "window_end": form.get("window_end"),
            "locked_vehicle_id": form.get("locked_vehicle_id"),
            "service_value": form.get("service_value"),
            "team_cost": form.get("team_cost"),
            "equipment_cost": form.get("equipment_cost"),
        },
        existing_clients=clients,
    )


def create_client_record_from_values(values: dict, *, existing_clients: list[dict] | None = None) -> dict:
    clients = existing_clients if existing_clients is not None else load_clients()
    equipment_items = load_equipment_registry()
    client_id = clean_text(values.get("client_id")) or next_numeric_id(clients, "CLI", "client_id")
    equipment_number = clean_text(values.get("equipment_number"))
    linked_equipment = next((item for item in equipment_items if item.get("equipment_id") == equipment_number), None)

    customer_name = clean_text(values.get("customer_name"))
    address = clean_text(values.get("address"))
    lat = clean_text(values.get("lat"))
    lng = clean_text(values.get("lng"))
    if not client_id or not customer_name or not address or not lat or not lng:
        raise ValueError("Não foi possível salvar o cliente porque faltam nome, endereço completo ou coordenadas. Complete o endereço e use a busca de coordenadas antes de salvar.")

    service_minutes = int(clean_text(values.get("default_service_minutes"), "20"))
    priority = int(clean_text(values.get("default_priority"), "3"))
    quantity = int(clean_text(values.get("equipment_quantity"), "1"))
    invoice_status = clean_text(values.get("invoice_status"), "sem_nota") or "sem_nota"
    if invoice_status not in {"com_nota", "sem_nota"}:
        invoice_status = "sem_nota"
    client_type = clean_text(values.get("client_type"), "fixo") or "fixo"
    billing_model = clean_text(values.get("billing_model"), "mensal" if client_type == "fixo" else "avulso") or "mensal"
    if billing_model not in CLIENT_BILLING_MODELS:
        billing_model = "mensal" if client_type == "fixo" else "avulso"
    cleaning_frequency = clean_text(values.get("cleaning_frequency"), "semanal" if client_type == "fixo" else "nao_aplica") or "nao_aplica"
    if cleaning_frequency not in CLIENT_CLEANING_FREQUENCIES:
        cleaning_frequency = "semanal" if client_type == "fixo" else "nao_aplica"
    service_profile = clean_text(values.get("service_profile"), "limpeza_semanal" if client_type == "fixo" else "evento_avulso") or "evento_avulso"
    if service_profile not in CLIENT_SERVICE_PROFILES:
        service_profile = "limpeza_semanal" if client_type == "fixo" else "evento_avulso"
    window_start = clean_text(values.get("window_start"), "08:00") or "08:00"
    window_end = clean_text(values.get("window_end"), "18:00") or "18:00"
    locked_vehicle_id = clean_text(values.get("locked_vehicle_id"))
    if service_minutes <= 0 or priority <= 0 or quantity <= 0:
        raise ValueError("Serviço, prioridade e quantidade devem ser maiores que zero. Esses campos alimentam a rota e a separação de equipamentos.")
    if hhmm_to_minutes(window_start) >= hhmm_to_minutes(window_end):
        raise ValueError("A janela do evento deve ter hora inicial menor que a final. Ajuste o horário de atendimento antes de salvar.")

    if equipment_number:
        conflict = next(
            (
                client for client in clients
                if client.get("equipment_number") == equipment_number and client.get("client_id") != client_id
            ),
            None,
        )
        if conflict:
            raise ValueError(
                f"O equipamento {equipment_number} já está vinculado ao cliente {conflict.get('customer_name') or conflict.get('client_id')}. Libere esse vínculo ou escolha outro equipamento."
            )
        if linked_equipment and normalize_equipment_status(linked_equipment.get("status") or linked_equipment.get("condition")) in BLOCKED_EQUIPMENT_STATUSES:
            raise ValueError(f"O equipamento {equipment_number} está {normalize_equipment_status(linked_equipment.get('status') or linked_equipment.get('condition'))} e não pode ser reservado. Marque como disponível ou escolha outro equipamento.")

    return {
        "client_id": client_id,
        "customer_name": customer_name,
        "contact_name": clean_text(values.get("contact_name")),
        "phone": clean_text(values.get("phone") or values.get("phone_number") or values.get("telephone")),
        "cpf_cnpj": clean_text(values.get("cpf_cnpj")),
        "email": clean_text(values.get("email")),
        "invoice_status": invoice_status,
        "invoice_number": clean_text(values.get("invoice_number")) if invoice_status == "com_nota" else "",
        "address": address,
        "lat": float(lat),
        "lng": float(lng),
        "client_type": client_type,
        "equipment_type": linked_equipment.get("equipment_type") if linked_equipment else clean_text(values.get("equipment_type"), "Banheiro Luxo"),
        "equipment_quantity": quantity,
        "equipment_number": equipment_number,
        "billing_model": billing_model,
        "cleaning_frequency": cleaning_frequency,
        "service_profile": service_profile,
        "default_service_minutes": service_minutes,
        "default_priority": priority,
        "window_start": window_start,
        "window_end": window_end,
        "locked_vehicle_id": locked_vehicle_id,
        "service_value": float(clean_text(values.get("service_value"), "0") or 0),
        "team_cost": float(clean_text(values.get("team_cost"), "0") or 0),
        "equipment_cost": float(clean_text(values.get("equipment_cost"), "0") or 0),
    }


def parse_checkbox_list(form, prefix: str, fallback_items: list[str]) -> list[dict]:
    result = []
    for item in fallback_items:
        result.append({"label": item, "done": bool(form.get(f"{prefix}_{item}"))})
    return result


def create_event_record(form) -> dict:
    events = load_events()
    event_id = clean_text(form.get("event_id")) or next_numeric_id(events, "EVT", "event_id")
    title = clean_text(form.get("title"))
    event_date = clean_text(form.get("event_date"))
    event_end_date = clean_text(form.get("event_end_date")) or event_date
    if not title or not event_date:
        raise ValueError("Informe nome e data inicial do evento. Sem esses dados, a operação não entra corretamente na agenda.")
    start_date = parse_date(event_date)
    end_date = parse_date(event_end_date)
    if not start_date or not end_date:
        raise ValueError("Informe datas válidas para o evento. Datas inválidas bloqueiam agenda, rota e documentos.")
    if end_date < start_date:
        raise ValueError("A data final do evento não pode ser anterior à data inicial. Corrija o período da locação antes de salvar.")

    client_ids = form.getlist("event_client_ids")
    vehicle_ids = form.getlist("event_vehicle_ids")
    checklist_defaults = [
        "checklist_equipamentos",
        "checklist_documentos",
        "checklist_equipe",
        "checklist_financeiro",
    ]
    checklist = parse_checkbox_list(form, "check", checklist_defaults)
    recurrence_enabled = clean_text(form.get("recurrence_enabled"))
    recurrence_status = clean_text(form.get("recurrence_status"), "ativo") or "ativo"
    recurrence_frequency = clean_text(form.get("recurrence_frequency"), "mensal") or "mensal"
    recurrence_start = clean_text(form.get("recurrence_start")) or event_date
    recurrence_end = clean_text(form.get("recurrence_end"))
    recurrence_interval_days = int(clean_text(form.get("recurrence_interval_days"), "30") or 30)

    if recurrence_status not in RECURRENCE_STATUS_OPTIONS:
        recurrence_status = "ativo"
    if recurrence_frequency not in RECURRENCE_FREQUENCIES:
        recurrence_frequency = "mensal"

    record = {
        "event_id": event_id,
        "title": title,
        "event_category": clean_text(form.get("event_category"), "geral") or "geral",
        "event_date": event_date,
        "event_end_date": event_end_date,
        "status": normalize_event_status(form.get("status"), "rascunho"),
        "client_ids": client_ids,
        "vehicle_ids": vehicle_ids,
        "responsible": clean_text(form.get("responsible") or form.get("responsavel") or form.get("assigned_to")),
        "notes": clean_text(form.get("notes")),
        "checklist": checklist,
        "last_route_generated_at": clean_text(form.get("last_route_generated_at")),
        "valor_servico": float(clean_text(form.get("valor_servico"), "0") or 0),
        "valor_adicional": float(clean_text(form.get("valor_adicional"), "0") or 0),
        "desconto": float(clean_text(form.get("desconto"), "0") or 0),
        "custo_equipe": float(clean_text(form.get("custo_equipe"), "0") or 0),
        "quantidade_equipes": int(clean_text(form.get("quantidade_equipes"), "0") or 0),
        "custo_por_equipamento": float(clean_text(form.get("custo_por_equipamento"), "0") or 0),
        "custo_fixo_veiculo": float(clean_text(form.get("custo_fixo_veiculo"), "0") or 0),
        "custo_extra_operacional": float(clean_text(form.get("custo_extra_operacional"), "0") or 0),
        "recurrence_enabled": recurrence_enabled,
        "recurrence_frequency": recurrence_frequency,
        "recurrence_interval_days": recurrence_interval_days,
        "recurrence_start": recurrence_start,
        "recurrence_end": recurrence_end,
        "next_occurrence_date": clean_text(form.get("next_occurrence_date")),
        "recurrence_status": recurrence_status,
        "recurrence_notes": clean_text(form.get("recurrence_notes")),
        "recurring_value": float(clean_text(form.get("recurring_value"), "0") or 0),
    }
    if recurrence_enabled in {"true", "1", "sim", "yes", "on"}:
        record["recurrence_enabled"] = "true"
        record["next_occurrence_date"] = next_recurrence_date(record)
    else:
        record["recurrence_enabled"] = ""
        record["next_occurrence_date"] = ""
    return record


def event_duplication_form_data(form, source: dict) -> MultiDict:
    form_data = MultiDict(form)
    new_date = clean_text(form_data.get("event_date"))
    if not new_date:
        raise ValueError("Informe a nova data da locação duplicada. A data antiga não é copiada automaticamente para evitar erro na agenda.")
    form_data["event_id"] = ""
    form_data["status"] = "rascunho"
    form_data["last_route_generated_at"] = ""
    form_data["recurrence_enabled"] = ""
    form_data["recurrence_start"] = ""
    form_data["recurrence_end"] = ""
    form_data["next_occurrence_date"] = ""
    form_data["recurrence_notes"] = ""
    form_data["recurrence_status"] = "ativo"
    form_data.setlist("event_vehicle_ids", [])
    for key in list(form_data.keys()):
        if key.startswith("check_"):
            del form_data[key]
    form_data["duplicated_from_event_id"] = clean_text(source.get("event_id"))
    return form_data


def validate_client_equipment_conflicts(clients: list[dict]) -> None:
    seen: dict[str, str] = {}
    for client in clients:
        equipment_number = clean_text(client.get("equipment_number"))
        client_name = client.get("customer_name") or client.get("client_id") or "cliente"
        if not equipment_number:
            continue
        if equipment_number in seen:
            raise ValueError(
                f"O equipamento {equipment_number} esta vinculado a mais de um cliente: {seen[equipment_number]} e {client_name}."
            )
        seen[equipment_number] = str(client_name)


def create_vehicle_record(form) -> dict:
    vehicles = load_vehicles_registry()
    vehicle_id = clean_text(form.get("vehicle_id")) or next_numeric_id(vehicles, "VEI", "vehicle_id")
    if not vehicle_id:
        raise ValueError("Informe o ID do veículo. Sem identificação, a frota não pode ser vinculada à rota.")

    capacity = int(clean_text(form.get("capacity"), "1"))
    max_stops = int(clean_text(form.get("max_stops"), "999"))
    max_minutes = int(clean_text(form.get("max_minutes"), "600"))
    if capacity <= 0 or max_stops <= 0 or max_minutes <= 0:
        raise ValueError("Capacidade, máximo de paradas e máximo de minutos devem ser maiores que zero. Esses limites definem se o veículo pode atender a rota.")

    return {
        "vehicle_id": vehicle_id,
        "vehicle_type": clean_text(form.get("vehicle_type"), "Van"),
        "plate": clean_text(form.get("plate")),
        "model": clean_text(form.get("model")),
        "photo_url": uploaded_asset_url("equipment_photo_file") or clean_text(form.get("photo_url")),
        "start_lat": float(clean_text(form.get("start_lat"), str(HQ_LAT)) or HQ_LAT),
        "start_lng": float(clean_text(form.get("start_lng"), str(HQ_LNG)) or HQ_LNG),
        "capacity": capacity,
        "max_stops": max_stops,
        "max_minutes": max_minutes,
    }


def create_equipment_record(form) -> dict:
    equipment_items = load_equipment_registry()
    equipment_id = clean_text(form.get("equipment_id")) or next_numeric_id(equipment_items, "EQ", "equipment_id")
    current = next((item for item in equipment_items if clean_text(item.get("equipment_id")) == equipment_id), {})
    equipment_type = clean_text(form.get("stock_equipment_type"), "Banheiro Luxo")
    if not equipment_id or not equipment_type:
        raise ValueError("Informe o ID e o tipo do equipamento. Sem isso, o item não pode ser reservado, conferido ou vinculado a uma locação.")
    status = normalize_equipment_status(form.get("status") or form.get("condition"))
    return {
        "equipment_id": equipment_id,
        "equipment_type": equipment_type,
        "plate": clean_text(form.get("plate")),
        "photo_url": clean_text(form.get("photo_url")),
        "condition": status,
        "status": status,
        "notes": clean_text(form.get("notes")),
        "returned_at": clean_text(form.get("returned_at")),
        "maintenance_reason": clean_text(form.get("maintenance_reason")) or clean_text(current.get("maintenance_reason")),
        "maintenance_started_at": clean_text(form.get("maintenance_started_at")) or clean_text(current.get("maintenance_started_at")),
        "maintenance_expected_release": clean_text(form.get("maintenance_expected_release")) or clean_text(current.get("maintenance_expected_release")),
        "maintenance_cost": parse_decimal(form.get("maintenance_cost"), parse_decimal(current.get("maintenance_cost"))),
    }


def parse_bulk_clients(raw_text: str) -> list[dict]:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("Cole pelo menos uma linha para importação em lote. Sem linhas, nenhum cliente será criado ou atualizado.")

    clients = load_clients()
    current_number = int("".join(ch for ch in next_numeric_id(clients, "CLI", "client_id") if ch.isdigit()) or "1")
    records: list[dict] = []

    for index, line in enumerate(lines, start=1):
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 4:
            raise ValueError(
                f"Linha {index} inválida. Use este formato: nome | endereço | latitude | longitude | tipo | equipamento | quantidade | equipamento_id | serviço | prioridade | valor_servico | custo_equipe | custo_equipamento | janela_inicio | janela_fim | veiculo_travado | contato | telefone | cpf_cnpj | email | nota | numero_nota"
            )
        window_start = parts[13] if len(parts) > 13 else "08:00"
        window_end = parts[14] if len(parts) > 14 else "18:00"
        if hhmm_to_minutes(window_start) >= hhmm_to_minutes(window_end):
            raise ValueError(f"Linha {index} inválida. A janela inicial deve ser menor que a final para a rota conseguir planejar o atendimento.")
        records.append(
            {
                "client_id": f"CLI-{current_number:03d}",
                "customer_name": parts[0],
                "contact_name": parts[16] if len(parts) > 16 else "",
                "phone": parts[17] if len(parts) > 17 else "",
                "cpf_cnpj": parts[18] if len(parts) > 18 else "",
                "email": parts[19] if len(parts) > 19 else "",
                "invoice_status": parts[20] if len(parts) > 20 else "sem_nota",
                "invoice_number": parts[21] if len(parts) > 21 else "",
                "address": parts[1],
                "lat": float(parts[2]),
                "lng": float(parts[3]),
                "client_type": parts[4] if len(parts) > 4 else "fixo",
                "equipment_type": parts[5] if len(parts) > 5 else "Banheiro Luxo",
                "equipment_quantity": int(parts[6] if len(parts) > 6 else "1"),
                "equipment_number": parts[7] if len(parts) > 7 else "",
                "billing_model": parts[22] if len(parts) > 22 else "",
                "cleaning_frequency": parts[23] if len(parts) > 23 else "",
                "service_profile": parts[24] if len(parts) > 24 else "",
                "default_service_minutes": int(parts[8] if len(parts) > 8 else "20"),
                "default_priority": int(parts[9] if len(parts) > 9 else "3"),
                "service_value": float(parts[10] if len(parts) > 10 else "0"),
                "team_cost": float(parts[11] if len(parts) > 11 else "0"),
                "equipment_cost": float(parts[12] if len(parts) > 12 else "0"),
                "window_start": window_start,
                "window_end": window_end,
                "locked_vehicle_id": parts[15] if len(parts) > 15 else "",
            }
        )
        current_number += 1

    return records


def normalize_excel_header(value: str) -> str:
    normalized = clean_text(value).lower()
    replacements = {
        "ç": "c",
        "ã": "a",
        "á": "a",
        "à": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    for token in (" ", "-", "/", ".", "(", ")", ":"):
        normalized = normalized.replace(token, "_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_")


def parse_xlsx_rows(path: Path) -> list[dict[str, str]]:
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel_ns = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
    with zipfile.ZipFile(path) as workbook:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in workbook.namelist():
            root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
            for item in root.findall("main:si", ns):
                text = "".join(node.text or "" for node in item.findall(".//main:t", ns))
                shared_strings.append(text)

        workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
        first_sheet = workbook_root.find("main:sheets/main:sheet", ns)
        if first_sheet is None:
            return []
        rel_id = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        if not rel_id:
            return []

        rels_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        target = None
        for rel in rels_root.findall("rel:Relationship", rel_ns):
            if rel.attrib.get("Id") == rel_id:
                target = rel.attrib.get("Target")
                break
        if not target:
            return []
        sheet_path = f"xl/{target.lstrip('/')}" if not target.startswith("xl/") else target
        sheet_root = ET.fromstring(workbook.read(sheet_path))

        rows: list[list[str]] = []
        for row in sheet_root.findall(".//main:sheetData/main:row", ns):
            values: list[str] = []
            expected_index = 0
            for cell in row.findall("main:c", ns):
                cell_ref = cell.attrib.get("r", "")
                column_letters = "".join(ch for ch in cell_ref if ch.isalpha())
                column_index = 0
                for letter in column_letters:
                    column_index = column_index * 26 + (ord(letter.upper()) - 64)
                column_index = max(column_index - 1, expected_index)
                while len(values) < column_index:
                    values.append("")
                raw_value = cell.findtext("main:v", default="", namespaces=ns)
                cell_type = cell.attrib.get("t")
                if cell_type == "s":
                    text = shared_strings[int(raw_value)] if raw_value else ""
                elif cell_type == "inlineStr":
                    text = "".join(node.text or "" for node in cell.findall(".//main:t", ns))
                else:
                    text = raw_value or ""
                values.append(text.strip())
                expected_index = len(values)
            rows.append(values)

    if not rows:
        return []
    headers = [normalize_excel_header(value) for value in rows[0]]
    parsed_rows: list[dict[str, str]] = []
    for raw_row in rows[1:]:
        if not any(clean_text(value) for value in raw_row):
            continue
        parsed_rows.append({
            headers[index]: raw_row[index] if index < len(raw_row) else ""
            for index in range(len(headers))
            if headers[index]
        })
    return parsed_rows


def parse_excel_clients(path: Path) -> list[dict]:
    header_aliases = {
        "id": "client_id",
        "client_id": "client_id",
        "codigo": "client_id",
        "nome": "customer_name",
        "cliente": "customer_name",
        "customer_name": "customer_name",
        "contato": "contact_name",
        "contact_name": "contact_name",
        "telefone": "phone",
        "phone": "phone",
        "phone_number": "phone",
        "telephone": "phone",
        "cpf_cnpj": "cpf_cnpj",
        "cpfcnpj": "cpf_cnpj",
        "email": "email",
        "e_mail": "email",
        "nota": "invoice_status",
        "nota_fiscal": "invoice_status",
        "com_sem_nota": "invoice_status",
        "invoice_status": "invoice_status",
        "numero_nota": "invoice_number",
        "numero_nf": "invoice_number",
        "nf": "invoice_number",
        "invoice_number": "invoice_number",
        "endereco": "address",
        "address": "address",
        "latitude": "lat",
        "lat": "lat",
        "longitude": "lng",
        "lng": "lng",
        "tipo": "client_type",
        "client_type": "client_type",
        "tipo_equipamento": "equipment_type",
        "equipamento": "equipment_type",
        "equipment_type": "equipment_type",
        "quantidade": "equipment_quantity",
        "equipment_quantity": "equipment_quantity",
        "equipamento_id": "equipment_number",
        "equipment_number": "equipment_number",
        "cobranca": "billing_model",
        "modelo_cobranca": "billing_model",
        "billing_model": "billing_model",
        "frequencia_limpeza": "cleaning_frequency",
        "limpeza": "cleaning_frequency",
        "cleaning_frequency": "cleaning_frequency",
        "tipo_atendimento": "service_profile",
        "perfil_servico": "service_profile",
        "service_profile": "service_profile",
        "servico": "default_service_minutes",
        "service_minutes": "default_service_minutes",
        "prioridade": "default_priority",
        "priority": "default_priority",
        "valor_servico": "service_value",
        "service_value": "service_value",
        "custo_equipe": "team_cost",
        "team_cost": "team_cost",
        "custo_equipamento": "equipment_cost",
        "equipment_cost": "equipment_cost",
        "janela_inicial": "window_start",
        "window_start": "window_start",
        "janela_final": "window_end",
        "window_end": "window_end",
        "veiculo_travado": "locked_vehicle_id",
        "locked_vehicle_id": "locked_vehicle_id",
    }
    rows = parse_xlsx_rows(path)
    if not rows:
        raise ValueError("A planilha está vazia ou não pôde ser lida.")

    records: list[dict] = []
    current_clients = load_clients()
    for index, row in enumerate(rows, start=2):
        mapped = {header_aliases[key]: value for key, value in row.items() if key in header_aliases}
        try:
            record = create_client_record_from_values(mapped, existing_clients=current_clients + records)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Linha {index} da planilha inválida: {exc}") from exc
        records.append(record)
    return records


def build_simple_xlsx_bytes(headers: list[str], rows: list[list[str]], sheet_name: str = "Dados") -> bytes:
    def column_letter(index: int) -> str:
        result = ""
        current = index + 1
        while current:
            current, remainder = divmod(current - 1, 26)
            result = chr(65 + remainder) + result
        return result

    shared_values: list[str] = []
    shared_index: dict[str, int] = {}

    def shared_ref(value: str) -> int:
        text = str(value)
        if text not in shared_index:
            shared_index[text] = len(shared_values)
            shared_values.append(text)
        return shared_index[text]

    def xml_escape(value: str) -> str:
        return (
            str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    row_xml: list[str] = []
    for row_number, values in enumerate([headers, *rows], start=1):
        cells: list[str] = []
        for column_index, value in enumerate(values):
            ref = f"{column_letter(column_index)}{row_number}"
            cells.append(f'<c r="{ref}" t="s"><v>{shared_ref(value)}</v></c>')
        row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')

    shared_strings = "".join(f"<si><t>{xml_escape(value)}</t></si>" for value in shared_values)
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{xml_escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData></worksheet>'
    )
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared_values)}" uniqueCount="{len(shared_values)}">'
        f"{shared_strings}</sst>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types)
        workbook.writestr("_rels/.rels", root_rels)
        workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        workbook.writestr("xl/sharedStrings.xml", shared_xml)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    buffer.seek(0)
    return buffer.getvalue()


def build_clients_template_xlsx() -> bytes:
    headers = [
        "nome",
        "endereco",
        "latitude",
        "longitude",
        "tipo",
        "equipamento",
        "quantidade",
        "equipamento_id",
        "modelo_cobranca",
        "frequencia_limpeza",
        "tipo_atendimento",
        "servico",
        "prioridade",
        "valor_servico",
        "custo_equipe",
        "custo_equipamento",
        "janela_inicial",
        "janela_final",
        "veiculo_travado",
        "contato",
        "telefone",
        "cpf_cnpj",
        "email",
        "nota",
        "numero_nota",
    ]
    sample = [[
        "Cliente Exemplo",
        "Estrada Bento Pestana, 932 - Baldeador, Niterói - RJ",
        "-22.8753396",
        "-43.068074",
        "fixo",
        "Banheiro Luxo",
        "2",
        "",
        "mensal",
        "semanal",
        "limpeza_semanal",
        "20",
        "3",
        "1200",
        "300",
        "150",
        "08:00",
        "18:00",
        "",
        "Marcos Silva",
        "(21) 99999-0000",
        "00.000.000/0001-00",
        "contato@cliente.com",
        "com_nota",
        "12345",
    ]]
    return build_simple_xlsx_bytes(headers, sample, sheet_name="Clientes")


def build_system_backup_bytes() -> bytes:
    buffer = io.BytesIO()
    write_data_backup_archive(buffer, generated_at=now_iso(), trigger="memoria")
    buffer.seek(0)
    return buffer.getvalue()


def geocode_address(address: str) -> dict:
    key = google_maps_api_key()
    if key:
        query = urllib.parse.urlencode(
            {
                "address": address,
                "key": key,
                "language": "pt-BR",
                "region": "br",
            }
        )
        request_obj = urllib.request.Request(
            f"https://maps.googleapis.com/maps/api/geocode/json?{query}",
            headers={"User-Agent": "SannyGoldRotaFlow/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request_obj, timeout=10) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("status") == "OK" and payload.get("results"):
            top = payload["results"][0]
            location = top.get("geometry", {}).get("location", {})
            return {
                "lat": float(location["lat"]),
                "lng": float(location["lng"]),
                "display_name": top.get("formatted_address") or address,
                "provider": "google",
                "place_id": clean_text(top.get("place_id")),
            }
        if payload.get("status") not in {"ZERO_RESULTS", "OK"}:
            raise ValueError(f"Google Maps não conseguiu geocodificar: {payload.get('status') or 'erro desconhecido'}.")

    query = urllib.parse.urlencode({"format": "jsonv2", "limit": 1, "q": address})
    request_obj = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?{query}",
        headers={"User-Agent": "RotaFlowLocal/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request_obj, timeout=10) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not payload:
        raise ValueError("Endereço não encontrado para geocodificação. Confira rua, número, bairro e cidade antes de buscar novamente.")
    top = payload[0]
    return {"lat": float(top["lat"]), "lng": float(top["lon"]), "display_name": top.get("display_name") or address, "provider": "openstreetmap", "place_id": ""}


def build_deliveries_csv_from_clients() -> Path:
    clients = load_clients()
    if not clients:
        raise ValueError("Cadastre pelo menos um endereço manual ou envie um CSV de entregas. A rota precisa de paradas válidas para ser gerada.")

    fieldnames = [
        "id",
        "customer_name",
        "client_type",
        "equipment_type",
        "equipment_quantity",
        "equipment_number",
        "address",
        "lat",
        "lng",
        "demand",
        "service_minutes",
        "priority",
        "window_start",
        "window_end",
        "preferred_vehicle_id",
    ]

    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", suffix=".csv", delete=False) as temp_file:
        writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
        writer.writeheader()
        for client in clients:
            quantity = int(client.get("equipment_quantity") or 1)
            writer.writerow(
                {
                    "id": client["client_id"],
                    "customer_name": client["customer_name"],
                    "client_type": client.get("client_type") or "fixo",
                    "equipment_type": client.get("equipment_type") or "Equipamento",
                    "equipment_quantity": quantity,
                    "equipment_number": client.get("equipment_number") or "",
                    "address": client.get("address") or "",
                    "lat": client["lat"],
                    "lng": client["lng"],
                    "demand": quantity,
                    "service_minutes": int(client.get("default_service_minutes") or 20),
                    "priority": int(client.get("default_priority") or 3),
                    "window_start": client.get("window_start") or "08:00",
                    "window_end": client.get("window_end") or "18:00",
                    "preferred_vehicle_id": client.get("locked_vehicle_id") or "",
                }
            )
        return Path(temp_file.name)


def build_deliveries_csv_for_clients(clients: list[dict]) -> Path:
    if not clients:
        raise ValueError("Nenhum cliente vinculado ao evento selecionado. Vincule um cliente antes de gerar rota ou PDF operacional.")

    fieldnames = [
        "id",
        "customer_name",
        "client_type",
        "equipment_type",
        "equipment_quantity",
        "equipment_number",
        "address",
        "lat",
        "lng",
        "demand",
        "service_minutes",
        "priority",
        "window_start",
        "window_end",
        "preferred_vehicle_id",
    ]
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", suffix=".csv", delete=False) as temp_file:
        writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
        writer.writeheader()
        for client in clients:
            quantity = int(client.get("equipment_quantity") or 1)
            writer.writerow(
                {
                    "id": client["client_id"],
                    "customer_name": client["customer_name"],
                    "client_type": client.get("client_type") or "fixo",
                    "equipment_type": client.get("equipment_type") or "Equipamento",
                    "equipment_quantity": quantity,
                    "equipment_number": client.get("equipment_number") or "",
                    "address": client.get("address") or "",
                    "lat": client["lat"],
                    "lng": client["lng"],
                    "demand": quantity,
                    "service_minutes": int(client.get("default_service_minutes") or 20),
                    "priority": int(client.get("default_priority") or 3),
                    "window_start": client.get("window_start") or "08:00",
                    "window_end": client.get("window_end") or "18:00",
                    "preferred_vehicle_id": client.get("locked_vehicle_id") or "",
                }
            )
        return Path(temp_file.name)


def build_vehicles_csv_from_registry() -> Path:
    vehicles = load_vehicles_registry()
    if not vehicles:
        raise ValueError("Cadastre pelo menos um veículo manual ou envie um CSV de veículos. A rota precisa de frota disponível para ser distribuída.")

    fieldnames = ["id", "vehicle_type", "plate", "model", "start_lat", "start_lng", "capacity", "max_stops", "max_minutes"]
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", suffix=".csv", delete=False) as temp_file:
        writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
        writer.writeheader()
        for vehicle in vehicles:
            writer.writerow(
                {
                    "id": vehicle["vehicle_id"],
                    "vehicle_type": vehicle.get("vehicle_type") or "",
                    "plate": vehicle.get("plate") or "",
                    "model": vehicle.get("model") or "",
                    "start_lat": HQ_LAT,
                    "start_lng": HQ_LNG,
                    "capacity": vehicle["capacity"],
                    "max_stops": vehicle.get("max_stops") or 999,
                    "max_minutes": vehicle.get("max_minutes") or 600,
                }
            )
        return Path(temp_file.name)


def build_vehicles_csv_for_registry(vehicles: list[dict]) -> Path:
    if not vehicles:
        raise ValueError("Nenhum veículo vinculado ao evento selecionado. Vincule um veículo ou revise a frota antes de gerar a rota.")
    fieldnames = ["id", "vehicle_type", "plate", "model", "start_lat", "start_lng", "capacity", "max_stops", "max_minutes"]
    with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8", suffix=".csv", delete=False) as temp_file:
        writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
        writer.writeheader()
        for vehicle in vehicles:
            writer.writerow(
                {
                    "id": vehicle["vehicle_id"],
                    "vehicle_type": vehicle.get("vehicle_type") or "",
                    "plate": vehicle.get("plate") or "",
                    "model": vehicle.get("model") or "",
                    "start_lat": HQ_LAT,
                    "start_lng": HQ_LNG,
                    "capacity": vehicle["capacity"],
                    "max_stops": vehicle.get("max_stops") or 999,
                    "max_minutes": vehicle.get("max_minutes") or 600,
                }
            )
        return Path(temp_file.name)


def validate_uploaded_file(
    uploaded,
    *,
    field_label: str = "arquivo",
    allowed_extensions: set[str] | None = None,
    allowed_label: str = "",
) -> tuple[str, str]:
    if uploaded is None or uploaded.filename is None or not uploaded.filename.strip():
        raise ValueError(f"Envie o arquivo de {field_label}. Sem o arquivo, o sistema não consegue importar os dados.")
    original_name = uploaded.filename.strip()
    extension = Path(original_name).suffix.lower()
    safe_name = secure_filename(original_name)
    if not safe_name:
        raise ValueError("O nome do arquivo enviado é inválido. Renomeie o arquivo sem símbolos especiais e tente novamente.")
    if allowed_extensions and extension not in allowed_extensions:
        allowed_text = allowed_label or ", ".join(sorted(allowed_extensions))
        raise ValueError(f"Formato de arquivo não permitido. Envie {field_label} em {allowed_text}.")
    return safe_name, extension


def build_upload_path(original_name: str, *, allowed_extensions: set[str] | None = None, fallback_name: str = "arquivo") -> Path:
    ensure_storage_dirs()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:8]
    safe_name = secure_filename(original_name) or fallback_name
    extension = Path(safe_name).suffix.lower()
    if allowed_extensions and extension not in allowed_extensions:
        allowed_text = ", ".join(sorted(allowed_extensions))
        raise ValueError(f"Formato de arquivo não permitido. Envie um arquivo em {allowed_text}.")
    return UPLOADS_DIR / f"{timestamp}-{suffix}-{safe_name}"


def enrich_payload_with_client_details(
    payload: dict,
    clients: list[dict],
    *,
    operation_date: str = "",
    event_end_date: str = "",
    total_diarias: int | str = "",
    event_id: str = "",
    event_title: str = "",
    event_notes: str = "",
) -> dict:
    clients_by_id = {client.get("client_id"): client for client in clients if client.get("client_id")}
    generated_at = datetime.now().isoformat(timespec="seconds")
    normalized_operation_date = operation_date or datetime.now().date().isoformat()
    normalized_event_end_date = event_end_date or normalized_operation_date
    normalized_total_diarias = str(total_diarias or "")
    normalized_event_id = clean_text(event_id)
    normalized_event_title = clean_text(event_title)
    normalized_event_notes = clean_text(event_notes)

    payload["generated_at"] = generated_at
    payload["operation_date"] = normalized_operation_date
    payload["event_end_date"] = normalized_event_end_date
    payload["total_diarias"] = normalized_total_diarias
    payload["event_id"] = normalized_event_id
    payload["event_title"] = normalized_event_title
    payload["event_notes"] = normalized_event_notes

    for route in payload.get("routes", []):
        route["operation_date"] = normalized_operation_date
        route["event_end_date"] = normalized_event_end_date
        route["total_diarias"] = normalized_total_diarias
        route["event_id"] = normalized_event_id
        route["event_title"] = normalized_event_title
        route["event_notes"] = normalized_event_notes
        for stop in route.get("stops", []):
            client = clients_by_id.get(stop.get("delivery_id")) or {}
            stop["operation_date"] = normalized_operation_date
            stop["event_end_date"] = normalized_event_end_date
            stop["total_diarias"] = normalized_total_diarias
            stop["event_id"] = normalized_event_id
            stop["contact_name"] = clean_text(client.get("contact_name"))
            stop["phone"] = clean_text(client.get("phone") or client.get("phone_number") or client.get("telephone"))
            stop["cpf_cnpj"] = clean_text(client.get("cpf_cnpj"))
            stop["email"] = clean_text(client.get("email"))
            stop["invoice_status"] = clean_text(client.get("invoice_status"), "sem_nota") or "sem_nota"
            stop["invoice_number"] = clean_text(client.get("invoice_number"))
            stop["billing_model"] = clean_text(client.get("billing_model"), "mensal" if clean_text(client.get("client_type")) == "fixo" else "avulso")
            stop["cleaning_frequency"] = clean_text(client.get("cleaning_frequency"), "semanal" if clean_text(client.get("client_type")) == "fixo" else "nao_aplica")
            stop["service_profile"] = clean_text(client.get("service_profile"), "limpeza_semanal" if clean_text(client.get("client_type")) == "fixo" else "evento_avulso")
            stop["window_start"] = clean_text(client.get("window_start"), "08:00") or "08:00"
            stop["window_end"] = clean_text(client.get("window_end"), "18:00") or "18:00"
            stop["operation_notes"] = normalized_event_notes

    for item in payload.get("unassigned", []):
        client = clients_by_id.get(item.get("delivery_id")) or {}
        item["operation_date"] = normalized_operation_date
        item["event_end_date"] = normalized_event_end_date
        item["total_diarias"] = normalized_total_diarias
        item["event_id"] = normalized_event_id
        item["contact_name"] = clean_text(client.get("contact_name"))
        item["phone"] = clean_text(client.get("phone") or client.get("phone_number") or client.get("telephone"))
        item["cpf_cnpj"] = clean_text(client.get("cpf_cnpj"))
        item["email"] = clean_text(client.get("email"))
        item["invoice_status"] = clean_text(client.get("invoice_status"), "sem_nota") or "sem_nota"
        item["invoice_number"] = clean_text(client.get("invoice_number"))
        item["billing_model"] = clean_text(client.get("billing_model"), "mensal" if clean_text(client.get("client_type")) == "fixo" else "avulso")
        item["cleaning_frequency"] = clean_text(client.get("cleaning_frequency"), "semanal" if clean_text(client.get("client_type")) == "fixo" else "nao_aplica")
        item["service_profile"] = clean_text(client.get("service_profile"), "limpeza_semanal" if clean_text(client.get("client_type")) == "fixo" else "evento_avulso")
        item["operation_notes"] = normalized_event_notes

    return payload


def save_upload(
    field_name: str,
    *,
    allowed_extensions: set[str] | None = None,
    field_label: str = "arquivo",
    allowed_label: str = "",
) -> Path:
    uploaded = request.files.get(field_name)
    safe_name, _extension = validate_uploaded_file(
        uploaded,
        field_label=field_label,
        allowed_extensions=allowed_extensions,
        allowed_label=allowed_label,
    )
    destination = build_upload_path(safe_name, allowed_extensions=allowed_extensions)
    uploaded.save(destination)
    return destination


def round2(value: float) -> float:
    return round(float(value or 0.0), 2)


def sum_route_distance(payload: dict) -> float:
    return round2(sum(float(route.get("distance_km") or 0.0) for route in payload.get("routes", [])))


def safe_margin(profit: float, revenue: float) -> float:
    revenue = float(revenue or 0.0)
    if revenue <= 0:
        return 0.0
    return round2((float(profit or 0.0) / revenue) * 100)


def build_revenue_allocation(
    payload: dict,
    clients_by_id: dict[str, dict],
    selected_event: dict | None,
) -> tuple[dict[str, float], dict]:
    assigned_stops = [
        stop
        for route in payload.get("routes", [])
        for stop in route.get("stops", [])
        if clean_text(stop.get("delivery_id"))
    ]
    if not assigned_stops:
        return {}, {
            "valor_servico": 0.0,
            "valor_adicional": 0.0,
            "desconto": 0.0,
            "receita_bruta": 0.0,
            "receita_liquida": 0.0,
        }

    total_diarias = event_billable_days(selected_event)
    event_service_daily_value = float((selected_event or {}).get("valor_servico") or 0.0)
    event_additional_value = float((selected_event or {}).get("valor_adicional") or 0.0)
    event_discount = float((selected_event or {}).get("desconto") or 0.0)
    event_service_value = round2(event_service_daily_value * total_diarias)
    explicit_client_total = sum(float((clients_by_id.get(stop.get("delivery_id")) or {}).get("service_value") or 0.0) for stop in assigned_stops)
    has_event_revenue = any(float((selected_event or {}).get(field) or 0.0) > 0 for field in ("valor_servico", "valor_adicional", "desconto"))

    receita_bruta = round2(event_service_value + event_additional_value) if has_event_revenue else round2(explicit_client_total)
    receita_liquida = round2(max(receita_bruta - event_discount, 0.0))
    if not has_event_revenue:
        event_service_value = receita_bruta
        event_additional_value = 0.0
        event_discount = 0.0
        receita_liquida = receita_bruta

    weights: dict[str, float] = {}
    if explicit_client_total > 0:
        for stop in assigned_stops:
            client_id = clean_text(stop.get("delivery_id"))
            weights[client_id] = float((clients_by_id.get(client_id) or {}).get("service_value") or 0.0)
    else:
        for stop in assigned_stops:
            client_id = clean_text(stop.get("delivery_id"))
            weights[client_id] = weights.get(client_id, 0.0) + max(float(stop.get("equipment_quantity") or 1), 1.0)
    total_weight = sum(weights.values()) or float(len(weights) or 1)
    allocation = {
        client_id: round2(receita_liquida * (weight / total_weight))
        for client_id, weight in weights.items()
    }
    difference = round2(receita_liquida - sum(allocation.values()))
    if allocation and difference:
        first_key = next(iter(allocation))
        allocation[first_key] = round2(allocation[first_key] + difference)

    return allocation, {
        "valor_servico": round2(event_service_value),
        "valor_servico_unitario": round2(event_service_daily_value),
        "valor_adicional": round2(event_additional_value),
        "desconto": round2(event_discount),
        "receita_bruta": round2(receita_bruta),
        "receita_liquida": round2(receita_liquida),
        "total_diarias": total_diarias,
        "receita_servico_diarias": round2(event_service_value),
    }


def build_financial_report(payload: dict, clients: list[dict], settings: dict, selected_event: dict | None = None) -> dict:
    clients_by_id = {client.get("client_id"): client for client in clients if client.get("client_id")}
    assigned_routes = [route for route in payload.get("routes", []) if route.get("stops")]
    assigned_stops = [stop for route in assigned_routes for stop in route.get("stops", [])]
    cost_per_km = float(settings.get("cost_per_km") or 0.0)
    km_total_da_rota = sum_route_distance(payload)
    quantidade_equipamentos = sum(int(stop.get("equipment_quantity") or 0) for stop in assigned_stops)
    veiculos_alocados = len(assigned_routes)
    total_diarias = event_billable_days(selected_event)

    revenue_allocation, revenue_summary = build_revenue_allocation(payload, clients_by_id, selected_event)
    receita_liquida = revenue_summary["receita_liquida"]

    event_team_unit_cost = float((selected_event or {}).get("custo_equipe") or 0.0)
    event_team_count = int((selected_event or {}).get("quantidade_equipes") or 0)
    if event_team_unit_cost > 0:
        quantidade_equipes = event_team_count or veiculos_alocados or 1
        custo_total_equipe = round2(event_team_unit_cost * quantidade_equipes * total_diarias)
    else:
        quantidade_equipes = event_team_count or (veiculos_alocados if veiculos_alocados else 0)
        custo_total_equipe = round2(sum(float((clients_by_id.get(stop.get("delivery_id")) or {}).get("team_cost") or 0.0) for stop in assigned_stops))

    event_equipment_unit_cost = float((selected_event or {}).get("custo_por_equipamento") or 0.0)
    if event_equipment_unit_cost > 0:
        custo_total_equipamentos = round2(event_equipment_unit_cost * quantidade_equipamentos * total_diarias)
    else:
        custo_total_equipamentos = round2(sum(float((clients_by_id.get(stop.get("delivery_id")) or {}).get("equipment_cost") or 0.0) for stop in assigned_stops))

    custo_total_deslocamento = round2(cost_per_km * km_total_da_rota)
    custo_fixo_veiculo_unit = float((selected_event or {}).get("custo_fixo_veiculo") or 0.0)
    custo_total_veiculos = round2(custo_fixo_veiculo_unit * veiculos_alocados * total_diarias)
    custo_extra_operacional = round2(float((selected_event or {}).get("custo_extra_operacional") or 0.0))
    custo_operacional_total = round2(
        custo_total_deslocamento + custo_total_equipe + custo_total_equipamentos + custo_total_veiculos + custo_extra_operacional
    )
    lucro_bruto = round2(receita_liquida - custo_operacional_total)
    margem_percentual = safe_margin(lucro_bruto, receita_liquida)

    route_cost_shares: dict[str, float] = {}
    total_route_km = sum(float(route.get("distance_km") or 0.0) for route in assigned_routes)
    total_stop_count = sum(len(route.get("stops", [])) for route in assigned_routes) or 1
    for route in assigned_routes:
        route_key = clean_text(route.get("vehicle_id"))
        if total_route_km > 0:
            route_cost_shares[route_key] = float(route.get("distance_km") or 0.0) / total_route_km
        else:
            route_cost_shares[route_key] = len(route.get("stops", [])) / total_stop_count

    client_rows = []
    route_rows = []
    equipment_rows: dict[str, dict] = {}
    for route in assigned_routes:
        route_key = clean_text(route.get("vehicle_id"))
        route_share = route_cost_shares.get(route_key, 0.0)
        route_logistic_cost = round2(float(route.get("distance_km") or 0.0) * cost_per_km)
        route_team_cost = round2(custo_total_equipe * route_share)
        route_vehicle_cost = round2(custo_total_veiculos * (1 / veiculos_alocados if veiculos_alocados else 0.0))
        route_extra_cost = round2(custo_extra_operacional * route_share)
        route_equipment_qty = sum(int(stop.get("equipment_quantity") or 0) for stop in route.get("stops", []))
        route_equipment_cost = round2(
            (custo_total_equipamentos * (route_equipment_qty / quantidade_equipamentos))
            if quantidade_equipamentos > 0
            else 0.0
        )
        route_revenue = 0.0
        route_client_cost = 0.0

        for stop in route.get("stops", []):
            client_id = clean_text(stop.get("delivery_id"))
            client = clients_by_id.get(client_id) or {}
            client_revenue = round2(revenue_allocation.get(client_id, 0.0))
            client_revenue_share = (client_revenue / receita_liquida) if receita_liquida > 0 else (
                (int(stop.get("equipment_quantity") or 0) / quantidade_equipamentos) if quantidade_equipamentos > 0 else (1 / max(len(assigned_stops), 1))
            )
            client_km_cost = round2(float(stop.get("travel_km") or 0.0) * cost_per_km)
            client_team_cost = round2(custo_total_equipe * client_revenue_share)
            if event_equipment_unit_cost > 0:
                client_equipment_cost = round2(event_equipment_unit_cost * int(stop.get("equipment_quantity") or 0))
            else:
                client_equipment_cost = round2(float(client.get("equipment_cost") or 0.0))
            client_vehicle_cost = round2(custo_total_veiculos * client_revenue_share)
            client_extra_cost = round2(custo_extra_operacional * client_revenue_share)
            client_total_cost = round2(client_km_cost + client_team_cost + client_equipment_cost + client_vehicle_cost + client_extra_cost)
            client_profit = round2(client_revenue - client_total_cost)
            client_margin = safe_margin(client_profit, client_revenue)

            client_rows.append(
                {
                    "event_id": payload.get("event_id") or "",
                    "event_title": payload.get("event_title") or "Operação geral",
                    "client_id": client_id,
                    "client_name": stop.get("customer_name") or client_id,
                    "vehicle_id": route_key,
                    "arrival": stop.get("arrival") or "",
                    "distance_km": round2(float(stop.get("travel_km") or 0.0)),
                    "quantidade_equipamentos": int(stop.get("equipment_quantity") or 0),
                    "receita_liquida": client_revenue,
                    "custo_logistico": client_km_cost,
                    "custo_equipe": client_team_cost,
                    "custo_equipamentos": client_equipment_cost,
                    "custo_veiculo": client_vehicle_cost,
                    "custo_extra_operacional": client_extra_cost,
                    "custo_total": client_total_cost,
                    "lucro_bruto": client_profit,
                    "margem_percentual": client_margin,
                }
            )
            route_revenue += client_revenue
            route_client_cost += client_total_cost

            equipment_key = clean_text(stop.get("equipment_number")) or f"TIPO:{clean_text(stop.get('equipment_type')) or 'Equipamento'}"
            equipment_entry = equipment_rows.setdefault(
                equipment_key,
                {
                    "equipment_id": equipment_key,
                    "equipment_type": stop.get("equipment_type") or "Equipamento",
                    "usage_count": 0,
                    "quantidade_equipamentos": 0,
                    "receita_associada": 0.0,
                    "custo_associado": 0.0,
                    "lucro_estimado": 0.0,
                    "margem_percentual": 0.0,
                },
            )
            equipment_entry["usage_count"] += 1
            equipment_entry["quantidade_equipamentos"] += int(stop.get("equipment_quantity") or 0)
            equipment_entry["receita_associada"] = round2(equipment_entry["receita_associada"] + client_revenue)
            equipment_entry["custo_associado"] = round2(equipment_entry["custo_associado"] + client_total_cost)

        route_total_cost = round2(route_logistic_cost + route_team_cost + route_equipment_cost + route_vehicle_cost + route_extra_cost)
        route_profit = round2(route_revenue - route_total_cost)
        route_rows.append(
            {
                "vehicle_id": route_key,
                "vehicle_type": route.get("vehicle_type") or "",
                "distance_km": round2(float(route.get("distance_km") or 0.0)),
                "receita_liquida": round2(route_revenue),
                "custo_logistico": route_logistic_cost,
                "custo_equipe": route_team_cost,
                "custo_equipamentos": route_equipment_cost,
                "custo_veiculo": route_vehicle_cost,
                "custo_extra_operacional": route_extra_cost,
                "custo_total": route_total_cost,
                "lucro_bruto": route_profit,
                "margem_percentual": safe_margin(route_profit, route_revenue),
                "total_stops": len(route.get("stops", [])),
            }
        )

    equipment_list = []
    for item in equipment_rows.values():
        item["lucro_estimado"] = round2(item["receita_associada"] - item["custo_associado"])
        item["margem_percentual"] = safe_margin(item["lucro_estimado"], item["receita_associada"])
        equipment_list.append(item)

    financial_alerts = []
    if margem_percentual < 15 and receita_liquida > 0:
        financial_alerts.append({"level": "warning", "scope": "evento", "message": "Evento com margem abaixo de 15%."})
    if lucro_bruto < 0:
        financial_alerts.append({"level": "danger", "scope": "evento", "message": "Evento com lucro negativo."})
    for route in route_rows:
        if route["lucro_bruto"] < 0:
            financial_alerts.append({"level": "danger", "scope": "rota", "message": f"Rota {route['vehicle_id']} está operacionalmente válida, mas financeiramente negativa."})
    for equipment in equipment_list:
        if equipment["usage_count"] >= 2 and equipment["margem_percentual"] < 15:
            financial_alerts.append({"level": "warning", "scope": "equipamento", "message": f"{equipment['equipment_id']} tem alto uso e baixa rentabilidade."})

    return {
        "status": "estimado",
        "total_diarias": total_diarias,
        "cost_per_km": round2(cost_per_km),
        "valor_servico": revenue_summary["valor_servico"],
        "valor_servico_unitario": revenue_summary.get("valor_servico_unitario") or 0,
        "valor_adicional": revenue_summary["valor_adicional"],
        "desconto": revenue_summary["desconto"],
        "receita_bruta": revenue_summary["receita_bruta"],
        "receita_liquida": revenue_summary["receita_liquida"],
        "receita_servico_diarias": revenue_summary.get("receita_servico_diarias") or 0,
        "km_total_da_rota": km_total_da_rota,
        "custo_total_deslocamento": custo_total_deslocamento,
        "custo_equipe": round2(event_team_unit_cost),
        "quantidade_equipes": quantidade_equipes,
        "custo_total_equipe": custo_total_equipe,
        "custo_por_equipamento": round2(event_equipment_unit_cost),
        "quantidade_equipamentos": quantidade_equipamentos,
        "custo_total_equipamentos": custo_total_equipamentos,
        "custo_fixo_veiculo": round2(custo_fixo_veiculo_unit),
        "veiculos_alocados": veiculos_alocados,
        "custo_total_veiculos": custo_total_veiculos,
        "custo_extra_operacional": custo_extra_operacional,
        "custo_operacional_total": custo_operacional_total,
        "lucro_bruto": lucro_bruto,
        "margem_percentual": margem_percentual,
        "profit_total": lucro_bruto,
        "revenue_total": revenue_summary["receita_liquida"],
        "operational_total": custo_operacional_total,
        "margin_pct": margem_percentual,
        "events": client_rows,
        "clients": client_rows,
        "routes": route_rows,
        "equipment": sorted(equipment_list, key=lambda item: item["lucro_estimado"], reverse=True),
        "alerts": financial_alerts[:12],
        "audit": {
            "calculated_at": now_iso(),
            "total_diarias": total_diarias,
            "km_utilizado": km_total_da_rota,
            "quantidade_equipamentos": quantidade_equipamentos,
            "status_calculo": "estimado",
            "receita_considerada": revenue_summary,
        },
    }


def capture_route_history(
    payload: dict,
    clients: list[dict],
    vehicles: list[dict],
    financial_report: dict,
    validation_payload: dict | None,
    selected_event: dict | None = None,
) -> None:
    equipment_items = {item["equipment_id"]: item for item in load_equipment_registry() if item.get("equipment_id")}
    equipment_in_route = []
    for route in payload.get("routes", []):
        for stop in route.get("stops", []):
            equipment_id = stop.get("equipment_number")
            if equipment_id and equipment_id in equipment_items:
                equipment_in_route.append(
                    {
                        "equipment_id": equipment_id,
                        "equipment_type": equipment_items[equipment_id].get("equipment_type") or stop.get("equipment_type") or "",
                        "vehicle_id": route.get("vehicle_id") or "",
                        "client_id": stop.get("delivery_id") or "",
                        "client_name": stop.get("customer_name") or "",
                    }
                )

    history = load_route_history()
    history.append(
        {
            "generated_at": payload.get("generated_at") or now_iso(),
            "event_id": clean_text((selected_event or {}).get("event_id")) or clean_text(payload.get("event_id")),
            "event_title": clean_text((selected_event or {}).get("title")) or clean_text(payload.get("event_title")) or "Operação geral",
            "event_date": clean_text((selected_event or {}).get("event_date")) or clean_text(payload.get("operation_date")),
            "summary": payload.get("summary") or {},
            "financial_summary": {
                "profit_total": financial_report.get("profit_total") or 0,
                "revenue_total": financial_report.get("revenue_total") or 0,
                "operational_total": financial_report.get("operational_total") or 0,
                "margin_pct": financial_report.get("margin_pct") or 0,
                "total_diarias": financial_report.get("total_diarias") or 1,
                "receita_bruta": financial_report.get("receita_bruta") or 0,
                "receita_liquida": financial_report.get("receita_liquida") or 0,
                "km_total_da_rota": financial_report.get("km_total_da_rota") or 0,
                "quantidade_equipamentos": financial_report.get("quantidade_equipamentos") or 0,
                "status": financial_report.get("status") or "estimado",
            },
            "financial_events": financial_report.get("events") or [],
            "financial_clients": financial_report.get("clients") or [],
            "financial_routes": financial_report.get("routes") or [],
            "financial_equipment": financial_report.get("equipment") or [],
            "financial_alerts": financial_report.get("alerts") or [],
            "financial_audit": financial_report.get("audit") or {},
            "validation": validation_payload or {},
            "equipment_in_route": equipment_in_route,
            "vehicle_ids": [vehicle.get("vehicle_id") or "" for vehicle in vehicles],
            "client_ids": [client.get("client_id") or "" for client in clients],
        }
    )
    save_route_history(history)


def annotate_route_with_validation(payload: dict, validation_payload: dict | None) -> dict:
    inventory_map = {
        clean_text(item.get("equipment_id")): item
        for item in load_equipment_registry()
        if clean_text(item.get("equipment_id"))
    }
    pending_by_client = {}
    for item in (validation_payload or {}).get("pending_items") or []:
        pending_by_client.setdefault(clean_text(item.get("client_id")), []).append(item)
    for route in payload.get("routes", []):
        for stop in route.get("stops", []):
            equipment_id = clean_text(stop.get("equipment_number"))
            equipment_item = inventory_map.get(equipment_id, {})
            stop["operational_status"] = "carregado" if equipment_id else "sem_equipamento"
            stop["cycle_stage"] = "Carregado para a rota atual" if equipment_id else "Sem equipamento vinculado"
            if equipment_item:
                stop["equipment_condition"] = normalize_equipment_status(equipment_item.get("status") or equipment_item.get("condition"))
            else:
                stop["equipment_condition"] = stop["operational_status"]
    for item in payload.get("unassigned", []):
        reasons = pending_by_client.get(clean_text(item.get("delivery_id")), [])
        item["pending_reasons"] = reasons
        item["pending_reason_summary"] = " | ".join(reason.get("reason") or "" for reason in reasons[:2]) or "Sem motivo detalhado"
    payload["validation"] = validation_payload
    return payload


def apply_route_generation_effects(payload: dict, selected_event: dict | None = None) -> None:
    route_equipment_ids = {
        clean_text(stop.get("equipment_number"))
        for route in payload.get("routes", [])
        for stop in route.get("stops", [])
        if clean_text(stop.get("equipment_number"))
    }
    if route_equipment_ids:
        equipment_items = load_equipment_registry()
        changed = False
        for item in equipment_items:
            if clean_text(item.get("equipment_id")) in route_equipment_ids:
                item["status"] = "carregado"
                item["condition"] = "carregado"
                changed = True
        if changed:
            save_equipment_registry(equipment_items)

    if selected_event:
        events = load_events()
        target = next((event for event in events if event.get("event_id") == selected_event.get("event_id")), None)
        if target:
            target["status"] = "em_andamento"
            target["last_route_generated_at"] = now_iso()
            save_events(events)


def run_route_generation(
    deliveries_path: Path,
    vehicles_path: Path,
    clients_snapshot: list[dict],
    vehicles_snapshot: list[dict],
    validation_payload: dict | None = None,
    *,
    selected_event: dict | None = None,
) -> dict:
    ensure_storage_dirs()
    deliveries = PLANNER.load_deliveries(deliveries_path)
    vehicles = PLANNER.load_vehicles(vehicles_path)
    routes, unassigned = PLANNER.build_routes(deliveries, vehicles, speed_kmph=35.0)
    payload = PLANNER.serialize(routes, unassigned, vehicles)
    payload = enrich_payload_with_client_details(
        payload,
        clients_snapshot,
        operation_date=clean_text((selected_event or {}).get("event_date")) or datetime.now().date().isoformat(),
        event_end_date=clean_text((selected_event or {}).get("event_end_date")) or clean_text((selected_event or {}).get("event_date")),
        total_diarias=event_billable_days(selected_event),
        event_id=clean_text((selected_event or {}).get("event_id")),
        event_title=clean_text((selected_event or {}).get("title")),
        event_notes=clean_text((selected_event or {}).get("notes")),
    )
    payload = annotate_route_with_validation(payload, validation_payload)
    mobile_payload = PLANNER.serialize_mobile(payload)
    for full_route, mobile_route in zip(payload.get("routes", []), mobile_payload.get("routes", [])):
        for full_stop, mobile_stop in zip(full_route.get("stops", []), mobile_route.get("stops", [])):
            mobile_stop["travel_km"] = full_stop.get("travel_km", 0)
            mobile_stop["contact_name"] = full_stop.get("contact_name", "")
            mobile_stop["phone"] = full_stop.get("phone", "")
            mobile_stop["cpf_cnpj"] = full_stop.get("cpf_cnpj", "")
            mobile_stop["email"] = full_stop.get("email", "")
            mobile_stop["window_start"] = full_stop.get("window_start", "")
            mobile_stop["window_end"] = full_stop.get("window_end", "")
            mobile_stop["operation_date"] = full_stop.get("operation_date", "")
            mobile_stop["event_end_date"] = full_stop.get("event_end_date", "")
            mobile_stop["total_diarias"] = full_stop.get("total_diarias", "")
            mobile_stop["operation_notes"] = full_stop.get("operation_notes", "")
    mobile_payload["generated_at"] = payload.get("generated_at") or ""
    mobile_payload["operation_date"] = payload.get("operation_date") or ""
    mobile_payload["event_end_date"] = payload.get("event_end_date") or ""
    mobile_payload["total_diarias"] = payload.get("total_diarias") or ""
    mobile_payload["event_id"] = payload.get("event_id") or ""
    mobile_payload["event_title"] = payload.get("event_title") or ""
    mobile_payload["event_notes"] = payload.get("event_notes") or ""
    settings = load_settings()
    financial_report = build_financial_report(payload, clients_snapshot, settings, selected_event)
    mobile_payload["financial_report"] = financial_report
    mobile_payload["validation"] = validation_payload or {}
    ROUTE_JSON_PATH.write_text(json.dumps(mobile_payload, indent=2), encoding="utf-8")
    PLANNER.write_driver_manifest_pdf(payload, ROUTE_PDF_PATH)
    apply_route_generation_effects(payload, selected_event)
    capture_route_history(payload, clients_snapshot, vehicles_snapshot, financial_report, validation_payload, selected_event)
    return financial_report


def upsert_field_confirmation(items: list[dict], record: dict) -> list[dict]:
    key_fields = ("route_generated_at", "client_id", "equipment_id", "vehicle_id")
    updated = []
    replaced = False
    for item in items:
        if all(clean_text(item.get(field)) == clean_text(record.get(field)) for field in key_fields):
            updated.append({**item, **record})
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(record)
    return updated


def build_field_confirmation_index(items: list[dict]) -> dict[tuple[str, str, str, str], dict]:
    index = {}
    for item in items:
        key = (
            clean_text(item.get("route_generated_at")),
            clean_text(item.get("client_id")),
            clean_text(item.get("equipment_id")),
            clean_text(item.get("vehicle_id")),
        )
        index[key] = item
    return index


def attach_field_confirmations(route_data: dict | None, field_confirmations: list[dict]) -> dict | None:
    if not route_data:
        return None
    indexed = build_field_confirmation_index(field_confirmations)
    route_generated_at = clean_text(route_data.get("generated_at"))
    for route in route_data.get("routes", []):
        for stop in route.get("stops", []):
            key = (
                route_generated_at,
                clean_text(stop.get("delivery_id")),
                clean_text(stop.get("equipment_number")),
                clean_text(route.get("vehicle_id")),
            )
            confirmation = indexed.get(key, {})
            stop["field_confirmation"] = {
                "arrival_confirmed_at": clean_text(confirmation.get("arrival_confirmed_at")),
                "execution_confirmed_at": clean_text(confirmation.get("execution_confirmed_at")),
                "return_confirmed_at": clean_text(confirmation.get("return_confirmed_at")),
                "status_label": (
                    "retorno confirmado"
                    if confirmation.get("return_confirmed_at")
                    else "execucao confirmada"
                    if confirmation.get("execution_confirmed_at")
                    else "chegada confirmada"
                    if confirmation.get("arrival_confirmed_at")
                    else "aguardando confirmação"
                ),
            }
    return route_data


def build_equipment_live_status(
    equipment: dict,
    *,
    linked_event: dict | None = None,
    linked_client: dict | None = None,
    route_link: dict | None = None,
    confirmation: dict | None = None,
) -> tuple[str, str]:
    base_status = normalize_equipment_status(equipment.get("status") or equipment.get("condition"))
    confirmation = confirmation or {}
    linked_event = linked_event or {}
    if base_status in {"manutencao", "indisponivel"}:
        return base_status, "Bloqueado para operação"
    if base_status == "retornado":
        return "retornado", "Aguardando liberação para disponibilidade"
    if confirmation.get("return_confirmed_at"):
        return "retornado", "Retorno confirmado"
    if confirmation.get("execution_confirmed_at"):
        return "instalado", "Equipamento instalado no cliente"
    if confirmation.get("arrival_confirmed_at"):
        return "em_rota", "Equipe chegou ao destino"
    if route_link:
        return "carregado", "Carregado para a rota atual"
    if linked_event and normalize_event_status(linked_event.get("status")) == "concluido" and linked_client:
        return "retirada_pendente", "Evento concluído aguardando retirada"
    if linked_event and linked_client:
        return "reservado", f"Reservado para {linked_event.get('title') or linked_event.get('event_id')}"
    return "disponivel", "Disponível na base"


def build_inventory_view(clients: list[dict], route_data: dict | None, field_confirmations: list[dict] | None = None) -> list[dict]:
    field_confirmations = field_confirmations or []
    confirmation_index = build_field_confirmation_index(field_confirmations)
    route_generated_at = clean_text((route_data or {}).get("generated_at"))
    equipment_map = {item["equipment_id"]: {**item} for item in load_equipment_registry() if item.get("equipment_id")}
    events = load_events()
    clients_by_id = {client.get("client_id"): client for client in clients if client.get("client_id")}
    client_event_map: dict[str, dict] = {}
    for event in events:
        for client_id in event.get("client_ids", []) or []:
            client_event_map[client_id] = event

    assigned_client_by_equipment = {
        client.get("equipment_number"): client
        for client in clients
        if client.get("equipment_number") and client.get("equipment_number") in equipment_map
    }
    route_link_by_equipment: dict[str, dict] = {}
    if route_data:
        for route in route_data.get("routes", []):
            for stop in route.get("stops", []):
                equipment_number = clean_text(stop.get("equipment_number"))
                if equipment_number:
                    route_link_by_equipment[equipment_number] = {
                        "client_id": stop.get("delivery_id") or "",
                        "client_name": stop.get("customer_name") or "",
                        "vehicle_id": route.get("vehicle_id") or "",
                    }

    inventory = []
    for equipment_id, item in equipment_map.items():
        linked_client = assigned_client_by_equipment.get(equipment_id)
        linked_event = client_event_map.get(clean_text((linked_client or {}).get("client_id")))
        route_link = route_link_by_equipment.get(equipment_id, {})
        confirmation = confirmation_index.get(
            (
                route_generated_at,
                clean_text(route_link.get("client_id")),
                equipment_id,
                clean_text(route_link.get("vehicle_id")),
            ),
            {},
        )
        status, cycle_stage = build_equipment_live_status(
            item,
            linked_event=linked_event,
            linked_client=linked_client,
            route_link=route_link,
            confirmation=confirmation,
        )
        inventory.append(
            {
                **item,
                "condition": normalize_equipment_status(item.get("status") or item.get("condition")),
                "status": status,
                "cycle_stage": cycle_stage,
                "equipment_family": equipment_family(item.get("equipment_type")),
                "equipment_family_label": equipment_family_label(equipment_family(item.get("equipment_type"))),
                "linked_client_name": linked_client.get("customer_name") if linked_client else route_link.get("client_name") or "",
                "linked_client_id": linked_client.get("client_id") if linked_client else route_link.get("client_id") or "",
                "linked_event_id": clean_text((linked_event or {}).get("event_id")),
                "linked_event_title": clean_text((linked_event or {}).get("title")),
                "linked_vehicle_id": route_link.get("vehicle_id") or "",
                "arrival_confirmed_at": clean_text(confirmation.get("arrival_confirmed_at")),
                "execution_confirmed_at": clean_text(confirmation.get("execution_confirmed_at")),
                "return_confirmed_at": clean_text(confirmation.get("return_confirmed_at")),
                "returned_at": clean_text(item.get("returned_at")) or clean_text(confirmation.get("return_confirmed_at")),
            }
        )
    return sort_by_label(inventory, "equipment_type", "equipment_id")


def build_pending_item(client: dict, code: str, detail: str, severity: str = "alta") -> dict:
    return {
        "client_id": clean_text(client.get("client_id")),
        "client_name": clean_text(client.get("customer_name")) or clean_text(client.get("client_id")),
        "reason_code": code,
        "reason_label": pending_reason_label(code),
        "reason": detail,
        "severity": severity,
    }


def generation_issue(
    title: str,
    detail: str,
    action: str,
    target_href: str,
    target_tab: str,
    *,
    reason_code: str = "evento_inapto",
    severity: str = "alta",
    client: dict | None = None,
) -> dict:
    item = {
        "title": title,
        "detail": detail,
        "action": action,
        "target_href": target_href,
        "target_tab": target_tab,
        "reason_code": reason_code,
        "reason_label": pending_reason_label(reason_code),
        "reason": detail,
        "severity": severity,
    }
    if client:
        item["client_id"] = clean_text(client.get("client_id"))
        item["client_name"] = clean_text(client.get("customer_name")) or clean_text(client.get("client_id"))
    return item


def flash_generation_block(title: str, intro: str, issues: list[dict]) -> None:
    flash(
        {
            "title": title,
            "intro": intro,
            "items": [
                {
                    "title": item.get("title") or item.get("reason_label") or "Pendência",
                    "detail": item.get("detail") or item.get("reason") or "",
                    "action": item.get("action") or "Corrigir",
                    "target_href": item.get("target_href") or "#operations-pane",
                    "target_tab": item.get("target_tab") or "operations-tab",
                }
                for item in issues[:12]
            ],
        },
        "danger",
    )


def event_responsible_text(event: dict | None, vehicles: list[dict] | None = None) -> str:
    event = event or {}
    vehicles = vehicles or []
    direct = clean_text(
        event.get("responsible")
        or event.get("responsavel")
        or event.get("assigned_to")
        or event.get("motorista")
    )
    if direct:
        return direct
    for vehicle in vehicles:
        vehicle_responsible = clean_text(
            vehicle.get("driver")
            or vehicle.get("motorista")
            or vehicle.get("responsible")
            or vehicle.get("responsavel")
        )
        if vehicle_responsible:
            return vehicle_responsible
    return ""


def event_has_financial_value(event: dict) -> bool:
    return (
        parse_decimal(event.get("valor_servico")) > 0
        or parse_decimal(event.get("valor_adicional")) > 0
        or parse_decimal(event.get("recurring_value")) > 0
    )


def build_route_generation_requirements(
    *,
    selected_event: dict | None,
    clients_snapshot: list[dict],
    vehicles_snapshot: list[dict],
) -> list[dict]:
    issues: list[dict] = []
    if selected_event:
        event_title = clean_text(selected_event.get("title")) or clean_text(selected_event.get("event_id")) or "Evento selecionado"
        if not selected_event.get("client_ids") or not clients_snapshot:
            issues.append(generation_issue("Cliente não vinculado", f"{event_title}: vincule ao menos um cliente antes de gerar a rota.", "Abrir evento", "#events-pane", "events-tab", reason_code="cliente_nao_vinculado"))
        if not clean_text(selected_event.get("event_date")):
            issues.append(generation_issue("Data do evento ausente", f"{event_title}: informe a data do evento/serviço.", "Corrigir data", "#events-pane", "events-tab", reason_code="data_servico_incompleta"))
        if not selected_event.get("vehicle_ids") or not vehicles_snapshot:
            issues.append(generation_issue("Veículo não definido", f"{event_title}: vincule pelo menos um veículo ao evento.", "Definir veículo", "#events-pane", "events-tab", reason_code="sem_veiculo_disponivel"))
        if vehicles_snapshot and not event_responsible_text(selected_event, vehicles_snapshot):
            issues.append(generation_issue("Responsável interno ausente", f"{event_title}: informe quem responde pela operação antes de gerar a rota.", "Informar responsável", "#events-pane", "events-tab", reason_code="sem_responsavel"))
    elif not clients_snapshot:
        issues.append(generation_issue("Nenhum cliente para roteirizar", "Cadastre ou selecione clientes antes de gerar uma rota.", "Cadastrar cliente", "#clients-pane", "clients-tab", reason_code="cliente_nao_vinculado"))

    for client in clients_snapshot:
        client_name = clean_text(client.get("customer_name")) or clean_text(client.get("client_id")) or "Cliente sem nome"
        if not clean_text(client.get("phone")):
            issues.append(generation_issue("Cliente sem telefone", f"{client_name}: informe telefone para contato rápido da equipe.", "Editar cliente", "#clients-pane", "clients-tab", reason_code="cliente_sem_telefone", severity="media", client=client))
    return issues


def build_service_order_requirements(
    event: dict,
    clients: list[dict],
    vehicles: list[dict],
    *,
    require_financial_value: bool = False,
) -> list[dict]:
    client_map = {clean_text(item.get("client_id")): item for item in clients}
    linked_clients = [client_map.get(clean_text(client_id), {}) for client_id in event.get("client_ids", []) or []]
    valid_clients = [client for client in linked_clients if client]
    linked_vehicle_ids = {clean_text(vehicle_id) for vehicle_id in event.get("vehicle_ids", []) or [] if clean_text(vehicle_id)}
    linked_vehicles = [vehicle for vehicle in vehicles if clean_text(vehicle.get("vehicle_id")) in linked_vehicle_ids]
    event_title = clean_text(event.get("title")) or clean_text(event.get("event_id")) or "Evento"
    issues: list[dict] = []

    if not valid_clients:
        issues.append(generation_issue("Cliente não vinculado", f"{event_title}: vincule ao menos um cliente antes de gerar a ordem de serviço.", "Abrir evento", "#events-pane", "events-tab", reason_code="cliente_nao_vinculado"))
    if not clean_text(event.get("event_date")):
        issues.append(generation_issue("Data do serviço ausente", f"{event_title}: informe data do evento/serviço.", "Corrigir data", "#events-pane", "events-tab", reason_code="data_servico_incompleta"))
    if not clean_text(event.get("notes")):
        issues.append(generation_issue("Observação operacional ausente", f"{event_title}: informe observações de montagem, acesso, entrega ou retirada.", "Adicionar observação", "#events-pane", "events-tab", reason_code="sem_observacao_operacional", severity="media"))
    if not event_responsible_text(event, linked_vehicles):
        issues.append(generation_issue("Responsável interno ausente", f"{event_title}: informe quem responde pela operação.", "Informar responsável", "#events-pane", "events-tab", reason_code="sem_responsavel"))
    if require_financial_value and not event_has_financial_value(event):
        issues.append(generation_issue("Valor não informado", f"{event_title}: informe valor quando a OS também for usada para controle financeiro.", "Registrar valor", "#events-pane", "events-tab", reason_code="valor_nao_informado", severity="media"))

    for client in valid_clients:
        client_name = clean_text(client.get("customer_name")) or clean_text(client.get("client_id")) or "Cliente"
        if not client_has_valid_address(client):
            issues.append(generation_issue("Local incompleto", f"{client_name}: informe endereço, latitude e longitude.", "Corrigir local", "#clients-pane", "clients-tab", reason_code="endereco_incompleto", client=client))
        if not clean_text(client.get("window_start")) or not clean_text(client.get("window_end")):
            issues.append(generation_issue("Horário incompleto", f"{client_name}: informe janela de atendimento inicial e final.", "Corrigir horário", "#clients-pane", "clients-tab", reason_code="data_servico_incompleta", client=client))
        if not clean_text(client.get("equipment_type") or client.get("service_profile")):
            issues.append(generation_issue("Serviço/equipamento não definido", f"{client_name}: informe o serviço ou banheiro/equipamento.", "Corrigir serviço", "#clients-pane", "clients-tab", reason_code="sem_equipamento_disponivel", client=client))
        if int(client.get("equipment_quantity") or 0) <= 0:
            issues.append(generation_issue("Quantidade não informada", f"{client_name}: informe quantidade maior que zero.", "Corrigir quantidade", "#clients-pane", "clients-tab", reason_code="evento_inapto", client=client))
    return issues


def validate_operation_scope(
    *,
    selected_event: dict | None,
    clients_snapshot: list[dict],
    vehicles_snapshot: list[dict],
    route_data: dict | None = None,
) -> dict:
    all_clients = load_clients()
    all_events = load_events()
    equipment_registry = load_equipment_registry()
    field_confirmations = load_field_confirmations()
    inventory = build_inventory_view(all_clients, route_data, field_confirmations)
    inventory_map = {item.get("equipment_id"): item for item in inventory if item.get("equipment_id")}
    equipment_commitments, vehicle_commitments = build_event_commitments(all_events, all_clients)
    event_date = clean_text((selected_event or {}).get("event_date")) or datetime.now().date().isoformat()
    event_end_date = clean_text((selected_event or {}).get("event_end_date")) or event_date
    event_id = clean_text((selected_event or {}).get("event_id"))
    selected_client_ids = {clean_text(client_id) for client_id in (selected_event or {}).get("client_ids", []) or [] if clean_text(client_id)}

    event_errors: list[dict] = []
    if selected_event:
        if not clean_text(selected_event.get("event_date")):
            event_errors.append({"reason_code": "evento_inapto", "reason_label": pending_reason_label("evento_inapto"), "reason": "Evento sem data válida."})
        if parse_date(clean_text(selected_event.get("event_end_date")) or clean_text(selected_event.get("event_date"))) is None:
            event_errors.append({"reason_code": "evento_inapto", "reason_label": pending_reason_label("evento_inapto"), "reason": "Evento sem data final válida."})
        elif parse_date(clean_text(selected_event.get("event_end_date")) or clean_text(selected_event.get("event_date"))) < parse_date(clean_text(selected_event.get("event_date"))):
            event_errors.append({"reason_code": "evento_inapto", "reason_label": pending_reason_label("evento_inapto"), "reason": "Período do evento inválido."})
        if normalize_event_status(selected_event.get("status")) in {"concluido", "pago", "cancelado"}:
            event_errors.append({"reason_code": "evento_inapto", "reason_label": pending_reason_label("evento_inapto"), "reason": "Evento já está concluído."})
        if not clients_snapshot or not vehicles_snapshot:
            event_errors.append({"reason_code": "evento_inapto", "reason_label": pending_reason_label("evento_inapto"), "reason": "Evento não possui clientes e veículos mínimos para roteirização."})

    vehicle_capacity_total = sum(int(vehicle.get("capacity") or 0) for vehicle in vehicles_snapshot)
    total_demand = sum(int(client.get("equipment_quantity") or 0) for client in clients_snapshot)
    if vehicles_snapshot and total_demand > vehicle_capacity_total:
        event_errors.append({"reason_code": "capacidade_excedida", "reason_label": pending_reason_label("capacidade_excedida"), "reason": "Demanda maior que a capacidade total da frota elegível."})

    pending_items: list[dict] = []
    route_requirement_issues = build_route_generation_requirements(
        selected_event=selected_event,
        clients_snapshot=clients_snapshot,
        vehicles_snapshot=vehicles_snapshot,
    )
    pending_items.extend(route_requirement_issues)
    eligible_clients = []
    blocked_clients = []
    equipment_conflict_ids: set[str] = set()
    eligible_vehicle_ids: set[str] = set()
    blocked_vehicle_ids: set[str] = set()

    for vehicle in vehicles_snapshot:
        vehicle_id = clean_text(vehicle.get("vehicle_id"))
        conflicts = [
            item for item in vehicle_commitments.get(vehicle_id, [])
            if clean_text(item.get("event_id")) != event_id and event_overlaps_period(item, event_date, event_end_date)
        ]
        if conflicts:
            blocked_vehicle_ids.add(vehicle_id)
        else:
            eligible_vehicle_ids.add(vehicle_id)

    for client in clients_snapshot:
        reasons = []
        equipment_id = clean_text(client.get("equipment_number"))
        equipment = inventory_map.get(equipment_id) if equipment_id else None
        locked_vehicle_id = clean_text(client.get("locked_vehicle_id"))

        if not client_has_valid_address(client):
            reasons.append(build_pending_item(client, "endereco_incompleto", "Cliente sem endereço ou coordenadas válidas."))
        if hhmm_to_minutes(clean_text(client.get("window_start"), "00:00")) >= hhmm_to_minutes(clean_text(client.get("window_end"), "00:00")):
            reasons.append(build_pending_item(client, "janela_inviavel", "Janela de atendimento inválida."))
        if int(client.get("equipment_quantity") or 0) <= 0 or not clean_text(client.get("equipment_type")):
            reasons.append(build_pending_item(client, "evento_inapto", "Quantidade ou tipo de equipamento inválido.", "media"))
        if not equipment_id:
            reasons.append(build_pending_item(client, "sem_equipamento_disponivel", "Cliente não possui equipamento vinculado."))
        elif not equipment:
            reasons.append(build_pending_item(client, "sem_equipamento_disponivel", f"Equipamento {equipment_id} não existe no cadastro de equipamentos."))
        else:
            equipment_status = normalize_equipment_status(equipment.get("status") or equipment.get("condition"))
            if equipment_status in BLOCKED_EQUIPMENT_STATUSES:
                reasons.append(build_pending_item(client, "sem_equipamento_disponivel", f"Equipamento {equipment_id} está {equipment_status}."))
            conflicts = [
                item for item in equipment_commitments.get(equipment_id, [])
                if clean_text(item.get("event_id")) != event_id and event_overlaps_period(item, event_date, event_end_date)
            ]
            equipment_linked_client_id = clean_text(equipment.get("linked_client_id"))
            committed_by_non_current_event = (
                equipment.get("status") in COMMITTED_EQUIPMENT_STATUSES
                and clean_text(equipment.get("linked_event_id")) != event_id
                and equipment_linked_client_id not in selected_client_ids
            )
            if conflicts or committed_by_non_current_event:
                equipment_conflict_ids.add(equipment_id)
                reasons.append(build_pending_item(client, "equipamento_em_conflito", f"Equipamento {equipment_id} comprometido em outro evento ativo no mesmo período."))
        if locked_vehicle_id:
            if locked_vehicle_id not in {clean_text(vehicle.get('vehicle_id')) for vehicle in vehicles_snapshot}:
                reasons.append(build_pending_item(client, "sem_veiculo_disponivel", f"Veículo travado {locked_vehicle_id} não está disponível neste evento.", "media"))
            elif locked_vehicle_id in blocked_vehicle_ids:
                reasons.append(build_pending_item(client, "veiculo_em_conflito", f"Veículo travado {locked_vehicle_id} está em conflito de agenda."))
        if int(client.get("equipment_quantity") or 0) > vehicle_capacity_total and vehicle_capacity_total > 0:
            reasons.append(build_pending_item(client, "capacidade_excedida", "Nenhum veículo elegível suporta a demanda deste cliente."))

        if reasons or event_errors or not eligible_vehicle_ids:
            blocked_clients.append(client)
            pending_items.extend(reasons or [build_pending_item(client, "evento_inapto", "Evento sem recursos mínimos para roteirização.")])
        else:
            eligible_clients.append(client)

    equipment_available = sum(1 for item in inventory if item.get("status") == "disponivel")
    equipment_reserved = sum(1 for item in inventory if item.get("status") == "reservado")
    validation = {
        "validated_at": now_iso(),
        "event_id": event_id,
        "event_title": clean_text((selected_event or {}).get("title")) or "Operação geral",
        "event_date": event_date,
        "event_end_date": event_end_date,
        "event_status": normalize_event_status((selected_event or {}).get("status"), "confirmado") if selected_event else "geral",
        "eligible_client_ids": [client.get("client_id") for client in eligible_clients],
        "blocked_client_ids": [client.get("client_id") for client in blocked_clients],
        "eligible_vehicle_ids": sorted(eligible_vehicle_ids),
        "blocked_vehicle_ids": sorted(blocked_vehicle_ids),
        "summary": {
            "eligible_clients": len(eligible_clients),
            "blocked_clients": len(blocked_clients),
            "equipment_available": equipment_available,
            "equipment_reserved": equipment_reserved,
            "equipment_conflicts": len(equipment_conflict_ids),
            "vehicles_free": len(eligible_vehicle_ids),
            "vehicles_conflict": len(blocked_vehicle_ids),
        },
        "event_errors": event_errors,
        "pending_items": pending_items[:50],
        "inventory_snapshot": [
            {
                "equipment_id": item.get("equipment_id"),
                "status": item.get("status"),
                "cycle_stage": item.get("cycle_stage"),
                "linked_client_id": item.get("linked_client_id"),
                "linked_event_id": item.get("linked_event_id"),
            }
            for item in inventory
        ],
        "is_routable": not event_errors and not route_requirement_issues and bool(eligible_clients) and bool(eligible_vehicle_ids),
    }
    return validation


def validate_event_links(record: dict, *, clients: list[dict], vehicles: list[dict], existing_events: list[dict]) -> None:
    event_id = clean_text(record.get("event_id"))
    event_date = clean_text(record.get("event_date"))
    event_end = clean_text(record.get("event_end_date")) or event_date
    equipment_commitments, vehicle_commitments = build_event_commitments(existing_events, clients)
    clients_by_id = {client.get("client_id"): client for client in clients if client.get("client_id")}

    for vehicle_id in record.get("vehicle_ids") or []:
        conflicts = [
            item for item in vehicle_commitments.get(clean_text(vehicle_id), [])
            if clean_text(item.get("event_id")) != event_id and event_overlaps_period(item, event_date, event_end)
        ]
        if conflicts:
            raise ValueError(f"O veículo {vehicle_id} já está vinculado a outro evento ativo na mesma data.")

    for client_id in record.get("client_ids") or []:
        client = clients_by_id.get(client_id) or {}
        equipment_id = clean_text(client.get("equipment_number"))
        if not equipment_id:
            continue
        conflicts = [
            item for item in equipment_commitments.get(equipment_id, [])
            if clean_text(item.get("event_id")) != event_id and event_overlaps_period(item, event_date, event_end)
        ]
        if conflicts:
            raise ValueError(f"O equipamento {equipment_id} do cliente {client.get('customer_name') or client_id} já está comprometido em outro evento na mesma data.")


def expand_future_occurrences(events: list[dict], horizon_days: int = 120) -> list[dict]:
    today = datetime.now().date()
    horizon_end = today.fromordinal(today.toordinal() + horizon_days)
    occurrences: list[dict] = []
    existing_keys = {
        (clean_text(event.get("event_id")), clean_text(event.get("event_date")))
        for event in events
    }
    for event in events:
        event_date = parse_date(event.get("event_date"))
        event_end = parse_date(event.get("event_end_date") or event.get("event_date"))
        if event_date and event_date >= today:
            occurrences.append(
                {
                    **event,
                    "occurrence_id": f"{clean_text(event.get('event_id'))}:{event_date.isoformat()}",
                    "occurrence_date": event_date.isoformat(),
                    "occurrence_end_date": event_end.isoformat() if event_end else event_date.isoformat(),
                    "is_virtual_occurrence": False,
                    "source_event_id": clean_text(event.get("event_id")),
                }
            )
        if clean_text(event.get("recurrence_enabled")) != "true" or clean_text(event.get("recurrence_status"), "ativo") != "ativo":
            continue
        start_date = parse_date(event.get("recurrence_start") or event.get("event_date"))
        end_date = parse_date(event.get("recurrence_end"))
        if not start_date:
            continue
        candidate = start_date
        while candidate <= horizon_end:
            if candidate >= today:
                occurrence_key = (clean_text(event.get("event_id")), candidate.isoformat())
                if occurrence_key not in existing_keys:
                    end_candidate = candidate.fromordinal(candidate.toordinal() + event_duration_days(event))
                    occurrences.append(
                        {
                            **event,
                            "event_date": candidate.isoformat(),
                            "event_end_date": end_candidate.isoformat(),
                            "occurrence_id": f"{clean_text(event.get('event_id'))}:{candidate.isoformat()}",
                            "occurrence_date": candidate.isoformat(),
                            "occurrence_end_date": end_candidate.isoformat(),
                            "is_virtual_occurrence": True,
                            "source_event_id": clean_text(event.get("event_id")),
                            "title": f"{clean_text(event.get('title'))} • recorrência",
                        }
                    )
            if end_date and candidate >= end_date:
                break
            if clean_text(event.get("recurrence_frequency")) == "mensal":
                candidate = add_months(candidate, 1)
            else:
                candidate = candidate.fromordinal(candidate.toordinal() + recurrence_step_days(event))
    occurrences.sort(key=lambda item: (clean_text(item.get("occurrence_date") or item.get("event_date")), clean_text(item.get("title"))))
    return occurrences


def average_resources_per_event(events: list[dict], clients: list[dict]) -> dict:
    if not events:
        return {"vehicles": 1, "equipment": 1}
    total_vehicles = 0
    total_equipment = 0
    for event in events:
        total_vehicles += len(event.get("vehicle_ids") or [])
        event_client_ids = set(event.get("client_ids") or [])
        total_equipment += sum(
            int(client.get("equipment_quantity") or 0)
            for client in clients
            if clean_text(client.get("client_id")) in event_client_ids
        )
    count = max(len(events), 1)
    return {
        "vehicles": max(round(total_vehicles / count), 1),
        "equipment": max(round(total_equipment / count), 1),
    }


def build_future_capacity_dashboard(events: list[dict], clients: list[dict], vehicles: list[dict], inventory: list[dict], route_history: list[dict], period: str = "weekly") -> dict:
    period = period if period in {"daily", "weekly", "monthly"} else "weekly"
    today = datetime.now().date()
    occurrences = expand_future_occurrences(events)
    avg_usage = average_resources_per_event(events, clients)
    usable_equipment_total = sum(1 for item in inventory if item.get("status") not in {"manutencao", "indisponivel"})
    maintenance_equipment_total = sum(1 for item in inventory if item.get("status") in {"manutencao", "indisponivel"})
    vehicle_total = len(vehicles)
    vehicle_unavailable_total = 0
    grouped: dict[str, dict] = {}
    alerts: list[dict] = []

    clients_by_id = {client.get("client_id"): client for client in clients if client.get("client_id")}
    for occurrence in occurrences:
        occ_date = parse_date(occurrence.get("occurrence_date") or occurrence.get("event_date"))
        if not occ_date:
            continue
        if period == "daily":
            key = occ_date.isoformat()
        elif period == "monthly":
            key = occ_date.strftime("%Y-%m")
        else:
            key = f"{occ_date.strftime('%Y')}-S{occ_date.isocalendar()[1]:02d}"
        bucket = grouped.setdefault(
            key,
            {
                "period_key": key,
                "start_date": occ_date.isoformat(),
                "events": [],
                "event_count": 0,
                "planned_count": 0,
                "execution_count": 0,
                "finalized_count": 0,
                "client_count": 0,
                "vehicle_ids": set(),
                "equipment_ids": set(),
                "total_equipment_quantity": 0,
            },
        )
        bucket["events"].append(occurrence)
        bucket["event_count"] += 1
        bucket["client_count"] += len(occurrence.get("client_ids") or [])
        bucket["vehicle_ids"].update(clean_text(vehicle_id) for vehicle_id in occurrence.get("vehicle_ids") or [] if clean_text(vehicle_id))
        for client_id in occurrence.get("client_ids") or []:
            client = clients_by_id.get(client_id) or {}
            equipment_id = clean_text(client.get("equipment_number"))
            if equipment_id:
                bucket["equipment_ids"].add(equipment_id)
            bucket["total_equipment_quantity"] += int(client.get("equipment_quantity") or 0)
        status = normalize_event_status(occurrence.get("status"))
        if status in {"rascunho", "confirmado", "pendente_dados", "rota_pendente", "os_pendente", "programado"}:
            bucket["planned_count"] += 1
        elif status == "em_andamento":
            bucket["execution_count"] += 1
        elif status in {"concluido", "pago"}:
            bucket["finalized_count"] += 1

    periods = []
    for bucket in grouped.values():
        committed_vehicles = len(bucket["vehicle_ids"])
        committed_equipment = max(len(bucket["equipment_ids"]), bucket["total_equipment_quantity"])
        vehicles_free = max(vehicle_total - committed_vehicles - vehicle_unavailable_total, 0)
        equipment_available = max(usable_equipment_total - committed_equipment, 0)
        estimated_capacity_total = min(
            vehicle_total // max(avg_usage["vehicles"], 1) if vehicle_total else 0,
            usable_equipment_total // max(avg_usage["equipment"], 1) if usable_equipment_total else 0,
        )
        if estimated_capacity_total == 0 and vehicle_total and usable_equipment_total:
            estimated_capacity_total = 1
        capacity_remaining = max(estimated_capacity_total - bucket["event_count"], 0)
        utilization_pct = round2((bucket["event_count"] / estimated_capacity_total) * 100) if estimated_capacity_total > 0 else 0.0

        period_entry = {
            **bucket,
            "vehicle_ids": sorted(bucket["vehicle_ids"]),
            "equipment_ids": sorted(bucket["equipment_ids"]),
            "equipment_total": usable_equipment_total,
            "equipment_available": equipment_available,
            "equipment_reserved": committed_equipment,
            "equipment_maintenance": maintenance_equipment_total,
            "equipment_projected_in_use": committed_equipment,
            "vehicles_total": vehicle_total,
            "vehicles_free": vehicles_free,
            "vehicles_committed": committed_vehicles,
            "vehicles_unavailable": vehicle_unavailable_total,
            "estimated_capacity_total": estimated_capacity_total,
            "capacity_remaining": capacity_remaining,
            "utilization_pct": utilization_pct,
        }
        periods.append(period_entry)

        if equipment_available <= max(1, int(usable_equipment_total * 0.2)) and bucket["event_count"] > 0:
            alerts.append({"level": "danger", "scope": key, "message": f"Risco de falta de equipamento em {key}."})
        if vehicles_free <= max(1, int(vehicle_total * 0.2)) and bucket["event_count"] > 0:
            alerts.append({"level": "danger", "scope": key, "message": f"Risco de falta de veículo em {key}."})
        if utilization_pct >= 85:
            alerts.append({"level": "danger", "scope": key, "message": f"Ocupação excessiva em {key}."})
        elif utilization_pct <= 20 and bucket["event_count"] == 0:
            alerts.append({"level": "warning", "scope": key, "message": f"Baixa ocupação projetada em {key}."})
        if bucket["event_count"] > 0:
            for event in bucket["events"]:
                event_vehicle_share = len(event.get("vehicle_ids") or []) / max(committed_vehicles, 1)
                event_equipment_share = 0.0
                event_client_ids = set(event.get("client_ids") or [])
                event_equipment_qty = sum(
                    int((clients_by_id.get(client_id) or {}).get("equipment_quantity") or 0)
                    for client_id in event_client_ids
                )
                if committed_equipment > 0:
                    event_equipment_share = event_equipment_qty / committed_equipment
                if event_vehicle_share > 0.6 or event_equipment_share > 0.6:
                    alerts.append({"level": "warning", "scope": key, "message": f"Concentração excessiva de recursos no evento {event.get('title')}."})

    periods.sort(key=lambda item: item["period_key"])

    recurring_events = [event for event in events if clean_text(event.get("recurrence_enabled")) == "true"]
    expiring_recurrences = [
        event for event in recurring_events
        if parse_date(event.get("recurrence_end")) and 0 <= (parse_date(event.get("recurrence_end")) - today).days <= 30
    ]

    monthly_history: dict[str, int] = {}
    weekday_history: dict[str, int] = {}
    region_history: dict[str, int] = {}
    category_financial: dict[str, dict] = {}
    for item in route_history:
        event_date = clean_text(item.get("event_date"))
        date_obj = parse_date(event_date)
        if date_obj:
            monthly_history.setdefault(date_obj.strftime("%Y-%m"), 0)
            monthly_history[date_obj.strftime("%Y-%m")] += 1
            weekday_history.setdefault(date_obj.strftime("%A"), 0)
            weekday_history[date_obj.strftime("%A")] += 1
        for client in item.get("financial_clients") or []:
            client_ref = clients_by_id.get(clean_text(client.get("client_id"))) or {}
            address = clean_text(client_ref.get("address"))
            region = address.split("-")[-1].strip() if "-" in address else (address.split(",")[-1].strip() if address else "N/D")
            region_history.setdefault(region, 0)
            region_history[region] += 1
        category = "geral"
        matching_event = next((event for event in events if clean_text(event.get("event_id")) == clean_text(item.get("event_id"))), None)
        if matching_event:
            category = clean_text(matching_event.get("event_category"), "geral") or "geral"
        bucket = category_financial.setdefault(category, {"revenue": 0.0, "profit": 0.0, "count": 0})
        summary = item.get("financial_summary") or {}
        bucket["revenue"] += float(summary.get("revenue_total") or 0.0)
        bucket["profit"] += float(summary.get("profit_total") or 0.0)
        bucket["count"] += 1

    prediction = {
        "top_months": sorted(monthly_history.items(), key=lambda item: item[1], reverse=True)[:4],
        "low_months": sorted(monthly_history.items(), key=lambda item: item[1])[:4],
        "top_weekdays": sorted(weekday_history.items(), key=lambda item: item[1], reverse=True)[:5],
        "top_regions": sorted(region_history.items(), key=lambda item: item[1], reverse=True)[:5],
        "ticket_medio": round2(
            sum(float((item.get("financial_summary") or {}).get("revenue_total") or 0.0) for item in route_history) / max(len(route_history), 1)
        ) if route_history else 0.0,
        "margin_by_category": [
            {
                "category": key,
                "margin_pct": safe_margin(bucket["profit"], bucket["revenue"]),
                "average_revenue": round2(bucket["revenue"] / max(bucket["count"], 1)),
            }
            for key, bucket in category_financial.items()
        ],
    }

    commercial = {
        "dates_with_capacity": [item for item in periods if item["capacity_remaining"] >= max(1, item["estimated_capacity_total"] // 2)][:6],
        "dates_almost_full": [item for item in periods if item["utilization_pct"] >= 75][:6],
        "recurring_active": [
            {
                "event_id": clean_text(event.get("event_id")),
                "title": clean_text(event.get("title")),
                "next_occurrence_date": clean_text(event.get("next_occurrence_date")),
                "recurrence_status": clean_text(event.get("recurrence_status"), "ativo"),
                "recurring_value": float(event.get("recurring_value") or 0.0),
            }
            for event in recurring_events
            if clean_text(event.get("recurrence_status"), "ativo") == "ativo"
        ][:8],
        "expiring_recurrences": [
            {
                "event_id": clean_text(event.get("event_id")),
                "title": clean_text(event.get("title")),
                "recurrence_end": clean_text(event.get("recurrence_end")),
            }
            for event in expiring_recurrences
        ],
        "future_week_occupancy": [
            {"period_key": item["period_key"], "utilization_pct": item["utilization_pct"], "capacity_remaining": item["capacity_remaining"]}
            for item in periods if item["period_key"].startswith(str(today.year))
        ][:8],
    }

    audit = {
        "generated_at": now_iso(),
        "agenda_period": period,
        "future_occurrences": len(occurrences),
        "resources_committed": {
            "equipment_total": usable_equipment_total,
            "vehicle_total": vehicle_total,
        },
        "alerts_generated": len(alerts),
        "recurrence_statuses": {
            "active": sum(1 for event in recurring_events if clean_text(event.get("recurrence_status"), "ativo") == "ativo"),
            "paused": sum(1 for event in recurring_events if clean_text(event.get("recurrence_status")) == "pausado"),
            "ended": sum(1 for event in recurring_events if clean_text(event.get("recurrence_status")) == "encerrado"),
        },
    }
    save_forecast_audit(audit)

    return {
        "selected_period": period,
        "periods": periods[:12],
        "alerts": alerts[:12],
        "prediction": prediction,
        "commercial": commercial,
        "audit": audit,
    }


def build_inventory_view(clients: list[dict], route_data: dict | None, field_confirmations: list[dict] | None = None) -> list[dict]:
    field_confirmations = field_confirmations or []
    confirmation_index = build_field_confirmation_index(field_confirmations)
    route_generated_at = clean_text((route_data or {}).get("generated_at"))
    equipment_map = {item["equipment_id"]: {**item} for item in load_equipment_registry() if item.get("equipment_id")}
    client_event_map: dict[str, dict] = {}
    for event in load_events():
        for client_id in event.get("client_ids", []) or []:
            client_event_map[clean_text(client_id)] = event
    assigned_client_by_equipment = {
        client.get("equipment_number"): client
        for client in clients
        if client.get("equipment_number") and client.get("equipment_number") in equipment_map
    }
    in_route_ids = set()
    route_link_by_equipment: dict[str, dict] = {}
    if route_data:
        for route in route_data.get("routes", []):
            for stop in route.get("stops", []):
                equipment_number = clean_text(stop.get("equipment_number"))
                if equipment_number:
                    in_route_ids.add(equipment_number)
                    route_link_by_equipment[equipment_number] = {
                        "client_id": stop.get("delivery_id") or "",
                        "client_name": stop.get("customer_name") or "",
                        "vehicle_id": route.get("vehicle_id") or "",
                    }

    inventory = []
    for equipment_id, item in equipment_map.items():
        linked_client = assigned_client_by_equipment.get(equipment_id)
        linked_event = client_event_map.get(clean_text((linked_client or {}).get("client_id")))
        route_link = route_link_by_equipment.get(equipment_id, {})
        confirmation = confirmation_index.get(
            (
                route_generated_at,
                clean_text(route_link.get("client_id")),
                equipment_id,
                clean_text(route_link.get("vehicle_id")),
            ),
            {},
        )
        status = "disponivel"
        cycle_stage = "Disponível na base"
        if item.get("condition") == "manutencao":
            status = "manutencao"
            cycle_stage = "Em manutenção"
        elif confirmation.get("return_confirmed_at"):
            status = "disponivel"
            cycle_stage = "Retorno confirmado"
        elif equipment_id in in_route_ids:
            status = "em_rota"
            cycle_stage = "Execução confirmada" if confirmation.get("execution_confirmed_at") else "Em deslocamento"
        elif linked_client:
            status = "reservado"
            cycle_stage = "Reservado para saída"
        inventory.append(
            {
                **item,
                "status": status,
                "cycle_stage": cycle_stage,
                "equipment_family": equipment_family(item.get("equipment_type")),
                "equipment_family_label": equipment_family_label(equipment_family(item.get("equipment_type"))),
                "linked_client_name": linked_client.get("customer_name") if linked_client else route_link.get("client_name") or "",
                "linked_client_id": linked_client.get("client_id") if linked_client else route_link.get("client_id") or "",
                "linked_event_id": clean_text((linked_event or {}).get("event_id")),
                "linked_event_title": clean_text((linked_event or {}).get("title")),
                "linked_vehicle_id": route_link.get("vehicle_id") or "",
                "arrival_confirmed_at": clean_text(confirmation.get("arrival_confirmed_at")),
                "execution_confirmed_at": clean_text(confirmation.get("execution_confirmed_at")),
                "return_confirmed_at": clean_text(confirmation.get("return_confirmed_at")),
                "returned_at": item.get("returned_at") or clean_text(confirmation.get("return_confirmed_at")),
            }
        )
    return sort_by_label(inventory, "equipment_type", "equipment_id")


def build_pending_reasons(validation_payload: dict | None) -> list[dict]:
    if not validation_payload:
        return []
    return list(validation_payload.get("pending_items") or [])[:20]


def build_validation_findings(
    clients: list[dict],
    vehicles: list[dict],
    events: list[dict],
    inventory: list[dict],
    route_data: dict | None,
    validation_payload: dict | None,
) -> list[dict]:
    findings = []
    inventory_ids = {item.get("equipment_id") for item in inventory}
    vehicle_ids = {vehicle.get("vehicle_id") for vehicle in vehicles}
    for client in clients:
        if clean_text(client.get("equipment_number")) and client.get("equipment_number") not in inventory_ids:
            findings.append({"severity": "alta", "title": "Equipamento ausente", "detail": f"{client.get('customer_name') or client.get('client_id')} aponta para {client.get('equipment_number')} sem cadastro."})
        if clean_text(client.get("locked_vehicle_id")) and client.get("locked_vehicle_id") not in vehicle_ids:
            findings.append({"severity": "media", "title": "Veículo travado inválido", "detail": f"{client.get('customer_name') or client.get('client_id')} está travado em {client.get('locked_vehicle_id')} não cadastrado."})
    for event in events:
        if not event.get("client_ids"):
            findings.append({"severity": "media", "title": "Evento sem clientes", "detail": f"{event.get('title') or event.get('event_id')} ainda não possui clientes vinculados."})
        if not event.get("vehicle_ids"):
            findings.append({"severity": "media", "title": "Evento sem veículos", "detail": f"{event.get('title') or event.get('event_id')} ainda não possui veículos vinculados."})
        if normalize_event_status(event.get("status")) in {"em_andamento", "concluido"} and any(not item.get("done") for item in event.get("checklist", [])):
            findings.append({"severity": "media", "title": "Checklist incompleto", "detail": f"{event.get('title') or event.get('event_id')} avançou sem checklist completo."})
    if route_data and ((route_data.get("summary") or {}).get("unassigned_deliveries") or 0) > 0:
        findings.append({"severity": "alta", "title": "Rota com pendências", "detail": "A geração atual terminou com entregas não atribuídas."})
    if validation_payload:
        summary = validation_payload.get("summary") or {}
        if (summary.get("vehicles_conflict") or 0) > 0:
            findings.append({"severity": "alta", "title": "Conflito de veículos", "detail": f"{summary.get('vehicles_conflict')} veículo(s) bloqueados por sobreposição de evento."})
        if (summary.get("equipment_conflicts") or 0) > 0:
            findings.append({"severity": "alta", "title": "Conflito de equipamentos", "detail": f"{summary.get('equipment_conflicts')} equipamento(s) comprometidos em outro evento no mesmo período."})
        for error in validation_payload.get("event_errors") or []:
            findings.append({"severity": "alta", "title": error.get("reason_label") or "Evento inapto", "detail": error.get("reason") or ""})
    return findings[:12]


def build_operational_dashboard(
    route_data: dict | None,
    route_history: list[dict],
    vehicles: list[dict],
    inventory: list[dict],
    clients: list[dict],
    field_confirmations: list[dict],
    validations: list[dict],
    pending_reasons: list[dict],
) -> dict:
    today = datetime.now().date().isoformat()
    events_today = [event for event in route_history if str(event.get("generated_at") or "").startswith(today)]
    current_routes = (route_data or {}).get("routes", [])
    vehicles_in_use = [route for route in current_routes if route.get("stops")]
    equipment_in_use = [item for item in inventory if item.get("status") in {"carregado", "em_rota", "instalado", "retirada_pendente"}]

    shortage_clients = [client for client in clients if not clean_text(client.get("equipment_number"))]
    shortage_alert = None
    if shortage_clients:
        shortage_alert = f"{len(shortage_clients)} cliente(s) sem equipamento vinculado."
    elif not inventory:
        shortage_alert = "Nenhum equipamento cadastrado."

    total_capacity = sum(int(vehicle.get("capacity") or 0) for vehicle in vehicles)
    total_demand = sum(int(client.get("equipment_quantity") or 0) for client in clients)
    agenda_conflict = None
    if route_data and (route_data.get("summary") or {}).get("unassigned_deliveries", 0) > 0:
        agenda_conflict = "Existem entregas nao atribuidas na rota atual."
    elif total_demand > total_capacity and total_capacity > 0:
        agenda_conflict = "A demanda atual supera a capacidade total da frota cadastrada."
    elif not vehicles and clients:
        agenda_conflict = "Ha clientes cadastrados, mas nenhum veiculo disponível."

    delayed_routes = []
    for route in current_routes:
        if not route.get("stops"):
            continue
        total_minutes = int(route.get("total_minutes") or 0)
        last_departure = route["stops"][-1].get("departure") or "00:00"
        if total_minutes > 480 or hhmm_to_minutes(last_departure) > hhmm_to_minutes("18:00"):
            delayed_routes.append(route.get("vehicle_id") or "veiculo")
    route_delay_alert = None
    if delayed_routes:
        route_delay_alert = f"Atraso potencial em: {', '.join(delayed_routes)}."

    current_stop_total = sum(len(route.get("stops", [])) for route in current_routes)
    route_generated_at = clean_text((route_data or {}).get("generated_at"))
    confirmation_index = build_field_confirmation_index(field_confirmations)
    executed_confirmations = 0
    for route in current_routes:
        for stop in route.get("stops", []):
            confirmation = confirmation_index.get(
                (
                    route_generated_at,
                    clean_text(stop.get("delivery_id")),
                    clean_text(stop.get("equipment_number")),
                    clean_text(route.get("vehicle_id")),
                ),
                {},
            )
            if confirmation.get("execution_confirmed_at"):
                executed_confirmations += 1

    return {
        "events_today": len(events_today),
        "events_in_progress": len(vehicles_in_use),
        "vehicles_in_use": len(vehicles_in_use),
        "equipment_in_use": len(equipment_in_use),
        "critical_validations": sum(1 for item in validations if item.get("severity") == "alta"),
        "pending_reasons_count": len(pending_reasons),
        "field_execution_confirmed": executed_confirmations,
        "field_execution_total": current_stop_total,
        "alerts": {
            "shortage": shortage_alert,
            "schedule_conflict": agenda_conflict,
            "route_delay": route_delay_alert,
        },
    }


def build_daily_flow_guidance(
    route_data: dict | None,
    dispatch_today: dict,
    preventive_warnings: list[dict],
    *,
    has_pdf: bool,
    last_backup_at: str,
    last_closeout_at: str,
) -> dict:
    blocking_warnings = [item for item in preventive_warnings if item.get("level") == "danger"]
    attention_warnings = [item for item in preventive_warnings if item.get("level") == "warning"]
    assigned = int(dispatch_today.get("assigned") or 0)
    ready_count = int(dispatch_today.get("ready_count") or 0)
    checklist_total = len(dispatch_today.get("checklist") or [])

    opening_status = "ready"
    opening_detail = "Painel pronto para começar a operação."
    if blocking_warnings:
        opening_status = "block"
        opening_detail = f"{len(blocking_warnings)} bloqueio(s) precisam ser resolvidos antes da liberação."
    elif attention_warnings:
        opening_status = "attention"
        opening_detail = f"{len(attention_warnings)} atenção(ões) recomendadas antes da liberação."

    dispatch_status = "info"
    dispatch_detail = "Valide um evento e gere a rota para liberar a equipe."
    if route_data and assigned > 0 and has_pdf:
        dispatch_status = "ready"
        dispatch_detail = f"Rota e PDF prontos para despacho com {assigned} parada(s)."
    elif route_data and assigned > 0:
        dispatch_status = "attention"
        dispatch_detail = "A rota existe, mas o PDF ainda precisa ser conferido/baixado."
    elif checklist_total:
        dispatch_status = "attention" if ready_count else "block"
        dispatch_detail = f"{ready_count}/{checklist_total} item(ns) do despacho já estão prontos."

    closeout_status = "info"
    closeout_detail = "Feche o dia quando os dados principais e o backup estiverem em dia."
    if last_closeout_at and str(last_closeout_at).startswith(datetime.now().date().isoformat()):
        closeout_status = "ready"
        closeout_detail = "O fechamento diário já foi gerado hoje."
    elif last_backup_at:
        closeout_status = "attention"
        closeout_detail = "Faça o fechamento diário depois do backup e da conferência administrativa."

    if opening_status == "block":
        next_action = {
            "title": "Corrigir bloqueios antes da liberação",
            "detail": opening_detail,
            "target_tab": "summary-tab",
            "target_href": "#dashboard-pendencias",
            "action": "Abrir pendências",
        }
    elif dispatch_status != "ready":
        next_action = {
            "title": "Liberar o despacho de hoje",
            "detail": dispatch_detail,
            "target_tab": "summary-tab",
            "target_href": "#dispatch-today-panel",
            "action": "Revisar despacho",
        }
    else:
        next_action = {
            "title": "Concluir fechamento administrativo",
            "detail": closeout_detail,
            "target_tab": "summary-tab",
            "target_href": "#guided-closeout-panel",
            "action": "Fechar dia",
        }

    return {
        "opening": {"status": opening_status, "detail": opening_detail},
        "dispatch": {"status": dispatch_status, "detail": dispatch_detail},
        "closeout": {"status": closeout_status, "detail": closeout_detail},
        "next_action": next_action,
    }


def build_mobile_sync_dashboard(route_data: dict | None) -> dict:
    routes = list((route_data or {}).get("routes") or [])
    stops = [stop for route in routes for stop in route.get("stops") or []]
    if not stops:
        return {
            "offline_ready": False,
            "generated_at": "",
            "total_stops": 0,
            "confirmed_stops": 0,
            "pending_sync": 0,
            "sync_pct": 0.0,
            "label": "PDF disponível após gerar rota",
            "detail": "Gere o pacote da rota para liberar impressão, PDF e links de endereço.",
            "pending_items": [],
        }

    confirmed_stops = 0
    pending_items = []
    for route in routes:
        for stop in route.get("stops") or []:
            status_label = clean_text(((stop.get("field_confirmation") or {}).get("status_label")), "aguardando confirmação")
            if status_label in {"execucao confirmada", "retorno confirmado"}:
                confirmed_stops += 1
            else:
                pending_items.append(
                    {
                        "client_name": clean_text(stop.get("customer_name")) or clean_text(stop.get("delivery_id")),
                        "vehicle_id": clean_text(route.get("vehicle_id")),
                        "status_label": status_label,
                    }
                )

    total_stops = len(stops)
    pending_sync = total_stops - confirmed_stops
    sync_pct = round2((confirmed_stops / total_stops) * 100) if total_stops else 0.0
    label = "Sincronização em dia" if pending_sync == 0 else f"{pending_sync} envio(s) pendente(s)"
    detail = (
        "Todas as confirmações operacionais principais já foram registradas."
        if pending_sync == 0
        else "O pacote de rota está pronto, mas ainda há registros aguardando conferência/confirmação."
    )
    return {
        "offline_ready": True,
        "generated_at": clean_text(route_data.get("generated_at")),
        "total_stops": total_stops,
        "confirmed_stops": confirmed_stops,
        "pending_sync": pending_sync,
        "sync_pct": sync_pct,
        "label": label,
        "detail": detail,
        "pending_items": pending_items[:4],
    }


def build_dispatch_today_panel(
    route_data: dict | None,
    validation_payload: dict | None,
    vehicles: list[dict],
    inventory: list[dict],
    clients: list[dict],
    has_pdf: bool,
) -> dict:
    summary = (route_data or {}).get("summary") or {}
    routes = (route_data or {}).get("routes") or []
    route_stops = [stop for route in routes for stop in route.get("stops", [])]
    assigned = int(summary.get("assigned_deliveries") or 0)
    unassigned = int(summary.get("unassigned_deliveries") or 0)
    total_deliveries = int(summary.get("total_deliveries") or assigned + unassigned)
    active_routes = [route for route in routes if route.get("stops")]
    pending_items = list((validation_payload or {}).get("pending_items") or [])
    is_routable = bool((validation_payload or {}).get("is_routable"))

    def item(label: str, level: str, detail: str, action: str, target_tab: str, target_href: str) -> dict:
        return {
            "label": label,
            "level": level,
            "detail": detail,
            "action": action,
            "target_tab": target_tab,
            "target_href": target_href,
        }

    if route_data and assigned > 0 and unassigned == 0:
        route_level = "ready"
        route_detail = f"{assigned} parada(s) atribuida(s), sem pendencia de roteirizacao."
    elif route_data and unassigned > 0:
        route_level = "danger"
        route_detail = f"{unassigned} entrega(s) ficaram sem rota."
    elif validation_payload and not is_routable:
        route_level = "danger"
        route_detail = "Validacao encontrou bloqueios antes da geracao."
    else:
        route_level = "warning"
        route_detail = "Valide e gere a rota antes de liberar a saida."

    if has_pdf:
        pdf_level = "ready"
        pdf_detail = "PDF da rota disponível para impressão ou envio interno."
    elif route_data and assigned > 0:
        pdf_level = "warning"
        pdf_detail = "Rota existe, mas o PDF ainda precisa ser gerado."
    else:
        pdf_level = "info"
        pdf_detail = "O PDF sera liberado depois da geracao da rota."

    if not vehicles:
        vehicle_level = "danger"
        vehicle_detail = "Nenhum veiculo cadastrado para despacho."
    elif active_routes:
        vehicle_level = "ready"
        vehicle_detail = f"{len(active_routes)} veiculo(s) com parada atribuida."
    else:
        vehicle_level = "warning"
        vehicle_detail = f"{len(vehicles)} veiculo(s) cadastrado(s), aguardando rota."

    equipment_blocks = [
        pending for pending in pending_items
        if clean_text(pending.get("reason_code")) in {"sem_equipamento_disponivel", "equipamento_em_conflito"}
        or "equipamento" in clean_text(pending.get("reason")).lower()
    ]
    if equipment_blocks:
        equipment_level = "danger"
        equipment_detail = f"{len(equipment_blocks)} pendencia(s) de equipamento para resolver."
    elif not inventory:
        equipment_level = "warning"
        equipment_detail = "Equipamentos vazios ou ainda nao cadastrados."
    elif route_stops:
        equipment_level = "ready"
        equipment_detail = "Equipamentos da rota conferidos no romaneio."
    else:
        equipment_level = "info"
        equipment_detail = f"{len(inventory)} equipamento(s) cadastrado(s), aguardando rota."

    if route_stops:
        missing_contacts = [
            stop for stop in route_stops
            if not clean_text(stop.get("contact_name")) or not clean_text(stop.get("phone"))
        ]
        contact_total = len(route_stops)
    else:
        missing_contacts = [
            client for client in clients
            if not clean_text(client.get("contact_name")) or not clean_text(client.get("phone"))
        ]
        contact_total = len(clients)
    if contact_total == 0:
        contact_level = "info"
        contact_detail = "Nenhum cliente na operacao atual."
    elif missing_contacts:
        contact_level = "warning"
        contact_detail = f"{len(missing_contacts)} contato(s) sem nome ou telefone."
    else:
        contact_level = "ready"
        contact_detail = "Contatos principais completos para a equipe."

    items = [
        item("Rota validada", route_level, route_detail, "Validar/Gerar", "operations-tab", "#operations-pane"),
        item("PDF da rota", pdf_level, pdf_detail, "Abrir PDF" if has_pdf else "Gerar rota", "operations-tab", "/download/route-plan.pdf" if has_pdf else "#operations-pane"),
        item("Veículo", vehicle_level, vehicle_detail, "Ver frota", "fleet-tab", "#fleet-pane"),
        item("Equipamento", equipment_level, equipment_detail, "Ver equipamentos", "fleet-tab", "#fleet-pane"),
        item("Contato", contact_level, contact_detail, "Ver clientes", "clients-tab", "#clients-pane"),
    ]

    return {
        "date": datetime.now().date().isoformat(),
        "assigned": assigned,
        "unassigned": unassigned,
        "total_deliveries": total_deliveries,
        "active_routes": len(active_routes),
        "checklist": items,
        "ready_count": sum(1 for current in items if criticality_key(current.get("level")) == "ready"),
        "blocking_count": sum(1 for current in items if criticality_key(current.get("level")) == "block"),
        "attention_count": sum(1 for current in items if criticality_key(current.get("level")) == "attention"),
    }


def build_financial_dashboard(route_data: dict | None, route_history: list[dict], selected_period: str = "monthly") -> dict:
    today = datetime.now().date().isoformat()
    week = datetime.now().strftime("%Y-%W")
    month = today[:7]
    selected_period = selected_period if selected_period in {"daily", "weekly", "monthly", "all"} else "monthly"
    current_report = (route_data or {}).get("financial_report") or {
        "clients": [],
        "routes": [],
        "equipment": [],
        "profit_total": 0,
        "revenue_total": 0,
        "operational_total": 0,
        "cost_per_km": 0,
        "alerts": [],
    }

    def totals_for(period: str) -> dict:
        matches = [item for item in route_history if str(item.get("generated_at") or "").startswith(period)]
        revenue = round2(sum(float((item.get("financial_summary") or {}).get("revenue_total") or 0.0) for item in matches))
        cost = round2(sum(float((item.get("financial_summary") or {}).get("operational_total") or 0.0) for item in matches))
        profit = round2(sum(float((item.get("financial_summary") or {}).get("profit_total") or 0.0) for item in matches))
        return {
            "revenue": revenue,
            "cost": cost,
            "profit": profit,
            "margin_pct": safe_margin(profit, revenue),
        }

    daily_totals = totals_for(today)
    monthly_totals = totals_for(month)
    weekly_matches = [
        item for item in route_history
        if datetime.fromisoformat(str(item.get("generated_at") or now_iso())).strftime("%Y-%W") == week
    ]
    weekly_revenue = round2(sum(float((item.get("financial_summary") or {}).get("revenue_total") or 0.0) for item in weekly_matches))
    weekly_cost = round2(sum(float((item.get("financial_summary") or {}).get("operational_total") or 0.0) for item in weekly_matches))
    weekly_profit = round2(sum(float((item.get("financial_summary") or {}).get("profit_total") or 0.0) for item in weekly_matches))

    def history_matches_period(item: dict) -> bool:
        generated_at = str(item.get("generated_at") or "")
        if selected_period == "daily":
            return generated_at.startswith(today)
        if selected_period == "monthly":
            return generated_at.startswith(month)
        if selected_period == "weekly":
            try:
                return datetime.fromisoformat(generated_at).strftime("%Y-%W") == week
            except ValueError:
                return False
        return True

    filtered_history = [item for item in route_history if history_matches_period(item)]

    event_totals: dict[str, dict] = {}
    client_totals: dict[str, dict] = {}
    route_totals: dict[str, dict] = {}
    equipment_totals: dict[str, dict] = {}
    event_details: dict[str, dict] = {}
    financial_alerts = list(current_report.get("alerts") or [])
    for item in filtered_history:
        event_key = clean_text(item.get("event_id")) or clean_text(item.get("event_title")) or "Operação geral"
        bucket = event_totals.setdefault(
            event_key,
            {
                "event_id": clean_text(item.get("event_id")),
                "event_title": clean_text(item.get("event_title")) or "Operação geral",
                "event_date": clean_text(item.get("event_date")),
                "revenue_total": 0.0,
                "operational_total": 0.0,
                "profit_total": 0.0,
                "runs": 0,
            },
        )
        financial_summary = item.get("financial_summary") or {}
        bucket["revenue_total"] += float(financial_summary.get("revenue_total") or 0.0)
        bucket["operational_total"] += float(financial_summary.get("operational_total") or 0.0)
        bucket["profit_total"] += float(financial_summary.get("profit_total") or 0.0)
        bucket["runs"] += 1
        if event_key not in event_details:
            event_details[event_key] = {
                "financial_summary": financial_summary,
                "financial_clients": item.get("financial_clients") or [],
                "financial_routes": item.get("financial_routes") or [],
                "financial_equipment": item.get("financial_equipment") or [],
                "financial_alerts": item.get("financial_alerts") or [],
                "financial_audit": item.get("financial_audit") or {},
            }
        for client in item.get("financial_clients") or []:
            key = clean_text(client.get("client_id")) or clean_text(client.get("client_name"))
            client_bucket = client_totals.setdefault(
                key,
                {
                    "client_id": clean_text(client.get("client_id")),
                    "client_name": clean_text(client.get("client_name")) or key,
                    "revenue_total": 0.0,
                    "cost_total": 0.0,
                    "profit_total": 0.0,
                    "runs": 0,
                },
            )
            client_bucket["revenue_total"] += float(client.get("receita_liquida") or 0.0)
            client_bucket["cost_total"] += float(client.get("custo_total") or 0.0)
            client_bucket["profit_total"] += float(client.get("lucro_bruto") or 0.0)
            client_bucket["runs"] += 1
        for route in item.get("financial_routes") or []:
            key = clean_text(route.get("vehicle_id"))
            route_bucket = route_totals.setdefault(
                key,
                {
                    "vehicle_id": key,
                    "distance_km": 0.0,
                    "revenue_total": 0.0,
                    "cost_total": 0.0,
                    "profit_total": 0.0,
                    "runs": 0,
                },
            )
            route_bucket["distance_km"] += float(route.get("distance_km") or 0.0)
            route_bucket["revenue_total"] += float(route.get("receita_liquida") or 0.0)
            route_bucket["cost_total"] += float(route.get("custo_total") or 0.0)
            route_bucket["profit_total"] += float(route.get("lucro_bruto") or 0.0)
            route_bucket["runs"] += 1
        for equipment in item.get("financial_equipment") or []:
            key = clean_text(equipment.get("equipment_id")) or clean_text(equipment.get("equipment_type"))
            equipment_bucket = equipment_totals.setdefault(
                key,
                {
                    "equipment_id": key,
                    "equipment_type": clean_text(equipment.get("equipment_type")) or key,
                    "usage_count": 0,
                    "revenue_total": 0.0,
                    "cost_total": 0.0,
                    "profit_total": 0.0,
                },
            )
            equipment_bucket["usage_count"] += int(equipment.get("usage_count") or 0)
            equipment_bucket["revenue_total"] += float(equipment.get("receita_associada") or 0.0)
            equipment_bucket["cost_total"] += float(equipment.get("custo_associado") or 0.0)
            equipment_bucket["profit_total"] += float(equipment.get("lucro_estimado") or 0.0)
        financial_alerts.extend(item.get("financial_alerts") or [])
    event_margins = []
    for bucket in event_totals.values():
        revenue_total = round(bucket["revenue_total"], 2)
        operational_total = round(bucket["operational_total"], 2)
        profit_total = round(bucket["profit_total"], 2)
        event_margins.append(
            {
                **bucket,
                "revenue_total": revenue_total,
                "operational_total": operational_total,
                "profit_total": profit_total,
                "margin_pct": round((profit_total / revenue_total) * 100, 2) if revenue_total > 0 else 0.0,
                "details": event_details.get(clean_text(bucket.get("event_id")) or clean_text(bucket.get("event_title")) or "Operação geral", {}),
            }
        )
    event_margins.sort(key=lambda item: (item["event_date"], item["event_title"]), reverse=True)

    client_rankings = []
    for bucket in client_totals.values():
        client_rankings.append(
            {
                **bucket,
                "revenue_total": round2(bucket["revenue_total"]),
                "cost_total": round2(bucket["cost_total"]),
                "profit_total": round2(bucket["profit_total"]),
                "margin_pct": safe_margin(bucket["profit_total"], bucket["revenue_total"]),
            }
        )
    client_rankings.sort(key=lambda item: item["profit_total"], reverse=True)

    route_rankings = []
    for bucket in route_totals.values():
        route_rankings.append(
            {
                **bucket,
                "distance_km": round2(bucket["distance_km"]),
                "revenue_total": round2(bucket["revenue_total"]),
                "cost_total": round2(bucket["cost_total"]),
                "profit_total": round2(bucket["profit_total"]),
                "margin_pct": safe_margin(bucket["profit_total"], bucket["revenue_total"]),
            }
        )
    route_rankings.sort(key=lambda item: item["cost_total"], reverse=True)

    equipment_rankings = []
    for bucket in equipment_totals.values():
        equipment_rankings.append(
            {
                **bucket,
                "revenue_total": round2(bucket["revenue_total"]),
                "cost_total": round2(bucket["cost_total"]),
                "profit_total": round2(bucket["profit_total"]),
                "margin_pct": safe_margin(bucket["profit_total"], bucket["revenue_total"]),
            }
        )
    equipment_rankings.sort(key=lambda item: item["profit_total"], reverse=True)

    recurring_low_margin = [
        item for item in client_rankings
        if item["runs"] >= 2 and item["margin_pct"] < 15
    ][:5]
    for item in recurring_low_margin:
        financial_alerts.append({"level": "warning", "scope": "cliente", "message": f"{item['client_name']} é recorrente e está com margem abaixo de 15%."})

    return {
        "selected_period": selected_period,
        "cost_per_km": float(current_report.get("cost_per_km") or 0.0),
        "event_profits": current_report.get("clients") or current_report.get("events") or [],
        "current_report": current_report,
        "current_profit": round(float(current_report.get("profit_total") or 0.0), 2),
        "current_margin_pct": round(float(current_report.get("margin_pct") or 0.0), 2),
        "daily_profit": daily_totals["profit"],
        "monthly_profit": monthly_totals["profit"],
        "event_margins": event_margins[:8],
        "daily_revenue": daily_totals["revenue"],
        "daily_operational": daily_totals["cost"],
        "weekly_revenue": weekly_revenue,
        "weekly_operational": weekly_cost,
        "weekly_profit": weekly_profit,
        "weekly_margin_pct": safe_margin(weekly_profit, weekly_revenue),
        "monthly_revenue": monthly_totals["revenue"],
        "monthly_operational": monthly_totals["cost"],
        "monthly_margin_pct": monthly_totals["margin_pct"],
        "top_events": sorted(event_margins, key=lambda item: item["profit_total"], reverse=True)[:5],
        "top_clients": client_rankings[:5],
        "bottom_clients": sorted(client_rankings, key=lambda item: item["profit_total"])[:5],
        "costliest_routes": route_rankings[:5],
        "top_equipment": equipment_rankings[:5],
        "financial_alerts": financial_alerts[:12],
    }


def financial_date_in_period(date_text: str, period: str, start_date: str = "", end_date: str = "") -> bool:
    value = clean_text(date_text)
    if not value:
        return False
    today = datetime.now().date().isoformat()
    month = today[:7]
    if period == "daily":
        return value.startswith(today)
    if period == "weekly":
        try:
            return datetime.fromisoformat(value[:10]).strftime("%Y-%W") == datetime.now().strftime("%Y-%W")
        except ValueError:
            return False
    if period == "custom":
        if start_date and value[:10] < start_date:
            return False
        if end_date and value[:10] > end_date:
            return False
        return True
    if period == "all":
        return True
    return value.startswith(month)


def build_financial_management_dashboard(
    route_history: list[dict],
    receivables: list[dict],
    entries: list[dict],
    closeouts: list[dict],
    period: str,
    start_date: str = "",
    end_date: str = "",
) -> dict:
    period = period if period in {"daily", "weekly", "monthly", "custom", "all"} else "monthly"
    today = datetime.now().date().isoformat()
    today_date = datetime.now().date()
    period_receivables = [item for item in receivables if financial_date_in_period(item.get("due_date"), period, start_date, end_date)]
    period_entries = [item for item in entries if financial_date_in_period(item.get("entry_date"), period, start_date, end_date)]
    period_history = [item for item in route_history if financial_date_in_period(item.get("generated_at"), period, start_date, end_date)]

    expected_in = round2(sum(float(item.get("amount") or 0) for item in period_receivables if item.get("status") != "pago"))
    received = round2(sum(float(item.get("amount_received") or 0) for item in period_receivables))
    entry_in = round2(sum(float(item.get("amount") or 0) for item in period_entries if item.get("entry_type") == "entrada"))
    entry_out = round2(sum(float(item.get("amount") or 0) for item in period_entries if item.get("entry_type") == "saida"))
    route_revenue = round2(sum(float((item.get("financial_summary") or {}).get("revenue_total") or 0) for item in period_history))
    route_cost = round2(sum(float((item.get("financial_summary") or {}).get("operational_total") or 0) for item in period_history))
    realized_balance = round2(received + entry_in - entry_out)
    projected_balance = round2(expected_in + entry_in + route_revenue - entry_out - route_cost)

    overdue = [
        {
            **item,
            "open_amount": round2(float(item.get("amount") or 0) - float(item.get("amount_received") or 0)),
            "days_overdue": max((datetime.fromisoformat(today).date() - datetime.fromisoformat(clean_text(item.get("due_date"))).date()).days, 0)
            if clean_text(item.get("due_date")) else 0,
        }
        for item in receivables
        if item.get("status") != "pago" and clean_text(item.get("due_date")) and clean_text(item.get("due_date")) < today
    ]
    overdue.sort(key=lambda item: item["days_overdue"], reverse=True)
    due_soon = [
        item for item in receivables
        if item.get("status") != "pago"
        and clean_text(item.get("due_date"))
        and today <= clean_text(item.get("due_date")) <= (datetime.now().date() + timedelta(days=3)).isoformat()
    ]
    paid_receivables = [item for item in receivables if item.get("status") == "pago"]

    alerts = []
    for item in overdue[:5]:
        alerts.append({"level": "danger", "scope": "cobrança", "message": f"{item.get('client_name')} está vencido há {item['days_overdue']} dia(s)."})
    for item in receivables:
        if item.get("status") != "pago" and clean_text(item.get("due_date")) >= today and clean_text(item.get("due_date")) <= (datetime.now().date() + timedelta(days=3)).isoformat():
            alerts.append({"level": "warning", "scope": "recebimento", "message": f"{item.get('client_name')} vence em {item.get('due_date')}."})
    for item in route_history[:5]:
        summary = item.get("financial_summary") or {}
        if float(summary.get("profit_total") or 0) < 0:
            alerts.append({"level": "danger", "scope": "margem", "message": f"{item.get('event_title') or 'Evento'} com margem negativa."})

    client_finance: dict[str, dict] = {}
    for item in receivables:
        key = clean_text(item.get("client_id")) or clean_text(item.get("client_name"))
        bucket = client_finance.setdefault(
            key,
            {"client_id": clean_text(item.get("client_id")), "client_name": clean_text(item.get("client_name")) or key, "billed": 0.0, "received": 0.0, "open": 0.0, "payments": 0},
        )
        amount = float(item.get("amount") or 0)
        amount_received = float(item.get("amount_received") or 0)
        bucket["billed"] += amount
        bucket["received"] += amount_received
        bucket["open"] += max(amount - amount_received, 0)
        bucket["payments"] += 1

    client_rows = [
        {**item, "billed": round2(item["billed"]), "received": round2(item["received"]), "open": round2(item["open"])}
        for item in client_finance.values()
    ]
    client_rows.sort(key=lambda item: item["open"], reverse=True)

    category_totals: dict[str, dict] = {}
    for item in entries:
        category = clean_text(item.get("category"), "outros") or "outros"
        bucket = category_totals.setdefault(category, {"category": category, "entrada": 0.0, "saida": 0.0})
        bucket[item.get("entry_type") if item.get("entry_type") in {"entrada", "saida"} else "saida"] += float(item.get("amount") or 0)

    service_totals: dict[str, dict] = {}
    for item in receivables:
        service_type = clean_text(item.get("service_type"), "Serviço") or "Serviço"
        bucket = service_totals.setdefault(service_type, {"service_type": service_type, "billed": 0.0, "received": 0.0, "open": 0.0, "count": 0})
        amount = float(item.get("amount") or 0)
        received_amount = float(item.get("amount_received") or 0)
        bucket["billed"] += amount
        bucket["received"] += received_amount
        bucket["open"] += max(amount - received_amount, 0)
        bucket["count"] += 1

    gross_revenue = round2(received + entry_in + route_revenue)
    direct_costs = round2(route_cost)
    expenses = round2(entry_out)
    dre_profit = round2(gross_revenue - direct_costs - expenses)
    dre_margin_pct = round2((dre_profit / gross_revenue) * 100) if gross_revenue else 0.0
    presumed_profit_tax_rate = 0.1133
    tax_provision = round2(gross_revenue * presumed_profit_tax_rate)
    due_today_total = round2(
        sum(
            max(float(item.get("amount") or 0) - float(item.get("amount_received") or 0), 0)
            for item in receivables
            if item.get("status") != "pago" and clean_text(item.get("due_date")) == today
        )
    )
    receivable_week_total = round2(
        sum(
            max(float(item.get("amount") or 0) - float(item.get("amount_received") or 0), 0)
            for item in receivables
            if item.get("status") != "pago"
            and clean_text(item.get("due_date"))
            and today <= clean_text(item.get("due_date")) <= (today_date + timedelta(days=7)).isoformat()
        )
    )
    receivable_month_total = round2(
        sum(
            max(float(item.get("amount") or 0) - float(item.get("amount_received") or 0), 0)
            for item in receivables
            if item.get("status") != "pago"
            and clean_text(item.get("due_date"))
            and today <= clean_text(item.get("due_date")) <= (today_date + timedelta(days=30)).isoformat()
        )
    )
    payable_today_total = round2(
        sum(
            float(item.get("amount") or 0)
            for item in entries
            if item.get("entry_type") == "saida" and clean_text(item.get("entry_date")) == today
        )
    )
    fixed_expense_categories = {"combustível", "equipe", "manutenção", "almoxarifado", "impostos", "folha", "pro-labore", "pró-labore"}
    separated_expenses = {
        "operational": round2(sum(float(item.get("amount") or 0) for item in entries if clean_text(item.get("category")).lower() in {"combustível", "equipe", "manutenção", "almoxarifado"} and item.get("entry_type") == "saida")),
        "partners": round2(sum(float(item.get("amount") or 0) for item in entries if clean_text(item.get("category")).lower() in {"pro-labore", "pró-labore", "sócios", "socios"} and item.get("entry_type") == "saida")),
        "taxes": round2(sum(float(item.get("amount") or 0) for item in entries if clean_text(item.get("category")).lower() in {"impostos", "tributos", "iss", "pis", "cofins", "irpj", "csll"} and item.get("entry_type") == "saida")),
        "other": round2(sum(float(item.get("amount") or 0) for item in entries if clean_text(item.get("category")).lower() not in fixed_expense_categories and item.get("entry_type") == "saida")),
    }

    def forecast_until(days: int) -> float:
        limit = (today_date + timedelta(days=days)).isoformat()
        receivable_total = sum(
            max(float(item.get("amount") or 0) - float(item.get("amount_received") or 0), 0)
            for item in receivables
            if item.get("status") != "pago" and clean_text(item.get("due_date")) and today <= clean_text(item.get("due_date")) <= limit
        )
        entry_in_total = sum(
            float(item.get("amount") or 0)
            for item in entries
            if item.get("entry_type") == "entrada" and clean_text(item.get("entry_date")) and today <= clean_text(item.get("entry_date")) <= limit
        )
        entry_out_total = sum(
            float(item.get("amount") or 0)
            for item in entries
            if item.get("entry_type") == "saida" and clean_text(item.get("entry_date")) and today <= clean_text(item.get("entry_date")) <= limit
        )
        return round2(realized_balance + receivable_total + entry_in_total - entry_out_total)

    invoice_summary = {
        "com_nota": sum(1 for item in receivables if clean_text(item.get("invoice_status")) == "com_nota" or clean_text(item.get("invoice_number"))),
        "sem_nota": sum(1 for item in receivables if clean_text(item.get("invoice_status"), "sem_nota") != "com_nota" and not clean_text(item.get("invoice_number"))),
    }

    return {
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "expected_in": expected_in,
        "received": received,
        "entry_in": entry_in,
        "entry_out": entry_out,
        "route_revenue": route_revenue,
        "route_cost": route_cost,
        "realized_balance": realized_balance,
        "projected_balance": projected_balance,
        "due_today_total": due_today_total,
        "receivable_week_total": receivable_week_total,
        "receivable_month_total": receivable_month_total,
        "payable_today_total": payable_today_total,
        "tax_provision": tax_provision,
        "tax_rate_label": "11,33% federal estimado",
        "forecast_30": forecast_until(30),
        "forecast_60": forecast_until(60),
        "forecast_90": forecast_until(90),
        "separated_expenses": separated_expenses,
        "receivables": receivables[:12],
        "receivables_overdue": overdue[:8],
        "receivables_due_soon": due_soon[:8],
        "receivables_paid": paid_receivables[:8],
        "entries": entries[:12],
        "overdue": overdue[:12],
        "alerts": alerts[:12],
        "client_finance": client_rows[:8],
        "category_totals": [
            {**item, "entrada": round2(item["entrada"]), "saida": round2(item["saida"])}
            for item in category_totals.values()
        ][:8],
        "service_totals": sorted(
            [
                {**item, "billed": round2(item["billed"]), "received": round2(item["received"]), "open": round2(item["open"])}
                for item in service_totals.values()
            ],
            key=lambda item: item["billed"],
            reverse=True,
        )[:8],
        "dre": {
            "gross_revenue": gross_revenue,
            "discounts": 0.0,
            "direct_costs": direct_costs,
            "expenses": expenses,
            "profit": dre_profit,
            "profit_after_tax_provision": round2(dre_profit - tax_provision),
            "margin_pct": dre_margin_pct,
        },
        "invoice_summary": invoice_summary,
        "closeouts": closeouts[:8],
    }


def receivable_open_amount(receivable: dict) -> float:
    return round2(max(parse_decimal(receivable.get("amount")) - parse_decimal(receivable.get("amount_received")), 0.0))


def receivable_is_paid(receivable: dict) -> bool:
    return clean_text(receivable.get("status")).lower() == "pago" or receivable_open_amount(receivable) <= 0


def event_financial_value(event: dict, clients_by_id: dict[str, dict]) -> float:
    service_total = parse_decimal(event.get("valor_servico")) * event_billable_days(event)
    additional_total = parse_decimal(event.get("valor_adicional"))
    recurring_total = parse_decimal(event.get("recurring_value"))
    discount_total = parse_decimal(event.get("desconto"))
    event_total = round2(max(service_total + additional_total + recurring_total - discount_total, 0.0))
    if event_total > 0:
        return event_total
    return round2(
        sum(
            parse_decimal((clients_by_id.get(clean_text(client_id)) or {}).get("service_value"))
            for client_id in event.get("client_ids", []) or []
        )
    )


def event_overlaps_month(event: dict, month_start, month_end) -> bool:
    start = event_start_date(event)
    end = event_end_date(event) or start
    if not start or not end:
        return False
    return start <= month_end and end >= month_start


def receivable_sort_date(receivable: dict) -> str:
    return (
        clean_text(receivable.get("received_date"))
        or clean_text(receivable.get("updated_at"))[:10]
        or clean_text(receivable.get("due_date"))
        or clean_text(receivable.get("created_at"))[:10]
    )


def build_financial_decision_panel(receivables: list[dict], events: list[dict], clients: list[dict]) -> dict:
    today = datetime.now().date()
    month_start = today.replace(day=1)
    next_month = add_months(month_start, 1)
    month_end = next_month - timedelta(days=1)
    week_end = today + timedelta(days=7)
    clients_by_id = {clean_text(client.get("client_id")): client for client in clients if clean_text(client.get("client_id"))}
    current_month_receivables = [
        item for item in receivables
        if (due_date := parse_date(item.get("due_date"))) and month_start <= due_date <= month_end
    ]
    linked_receivable_event_ids = {
        clean_text(item.get("event_id"))
        for item in receivables
        if clean_text(item.get("event_id"))
    }

    event_forecast_total = 0.0
    events_without_value: list[dict] = []
    for event in events:
        event_id = clean_text(event.get("event_id"))
        if not event_is_active(event) or not event_overlaps_month(event, month_start, month_end):
            continue
        event_value = event_financial_value(event, clients_by_id)
        if event_value <= 0:
            events_without_value.append(
                {
                    "event_id": event_id,
                    "title": clean_text(event.get("title")) or event_id or "Evento sem título",
                    "event_date": clean_text(event.get("event_date")),
                    "target_href": f"#event-{event_id}" if event_id else "#events-pane",
                }
            )
        elif event_id and event_id not in linked_receivable_event_ids:
            event_forecast_total += event_value

    received_month_total = 0.0
    open_total = 0.0
    overdue_total = 0.0
    due_next_7_total = 0.0
    due_next_7_count = 0
    top_clients: dict[str, dict] = {}
    delayed_clients: dict[str, dict] = {}
    overdue_receivables: list[dict] = []

    for receivable in receivables:
        amount = parse_decimal(receivable.get("amount"))
        open_amount = receivable_open_amount(receivable)
        paid = receivable_is_paid(receivable)
        due_date = parse_date(receivable.get("due_date"))
        received_date = parse_date(receivable.get("received_date") or clean_text(receivable.get("updated_at"))[:10])
        if paid and received_date and month_start <= received_date <= month_end:
            received_month_total += parse_decimal(receivable.get("amount_received")) or amount
        if not paid and open_amount > 0:
            open_total += open_amount
            client_key = clean_text(receivable.get("client_id")) or clean_text(receivable.get("client_name")) or "cliente-sem-id"
            client_name = clean_text(receivable.get("client_name")) or clean_text((clients_by_id.get(client_key) or {}).get("customer_name")) or "Cliente não informado"
            client_bucket = top_clients.setdefault(
                client_key,
                {"client_id": clean_text(receivable.get("client_id")), "client_name": client_name, "open_amount": 0.0, "count": 0},
            )
            client_bucket["open_amount"] += open_amount
            client_bucket["count"] += 1
        is_overdue = not paid and open_amount > 0 and ((due_date and due_date < today) or clean_text(receivable.get("status")).lower() == "vencido")
        if is_overdue:
            days_late = max((today - due_date).days, 0) if due_date else 0
            overdue_total += open_amount
            overdue_item = {
                **receivable,
                "open_amount": open_amount,
                "days_late": days_late,
                "due_date_label": format_date_br(receivable.get("due_date")),
            }
            overdue_receivables.append(overdue_item)
            client_key = clean_text(receivable.get("client_id")) or clean_text(receivable.get("client_name")) or "cliente-sem-id"
            client_name = clean_text(receivable.get("client_name")) or clean_text((clients_by_id.get(client_key) or {}).get("customer_name")) or "Cliente não informado"
            delayed_bucket = delayed_clients.setdefault(
                client_key,
                {
                    "client_id": clean_text(receivable.get("client_id")),
                    "client_name": client_name,
                    "open_amount": 0.0,
                    "count": 0,
                    "oldest_due_date": clean_text(receivable.get("due_date")),
                    "days_late": days_late,
                },
            )
            delayed_bucket["open_amount"] += open_amount
            delayed_bucket["count"] += 1
            delayed_bucket["days_late"] = max(delayed_bucket["days_late"], days_late)
            if clean_text(receivable.get("due_date")) and (
                not delayed_bucket["oldest_due_date"] or clean_text(receivable.get("due_date")) < delayed_bucket["oldest_due_date"]
            ):
                delayed_bucket["oldest_due_date"] = clean_text(receivable.get("due_date"))
        if not paid and due_date and today <= due_date <= week_end:
            due_next_7_total += open_amount
            due_next_7_count += 1

    top_client_rows = [
        {**item, "open_amount": round2(item["open_amount"])}
        for item in top_clients.values()
        if item["open_amount"] > 0
    ]
    top_client_rows.sort(key=lambda item: item["open_amount"], reverse=True)
    delayed_client_rows = [
        {**item, "open_amount": round2(item["open_amount"])}
        for item in delayed_clients.values()
        if item["open_amount"] > 0
    ]
    delayed_client_rows.sort(key=lambda item: (item["days_late"], item["open_amount"]), reverse=True)
    recent_receivables = sorted(receivables, key=receivable_sort_date, reverse=True)[:8]
    recommended_actions = []
    if overdue_receivables:
        recommended_actions.append(
            recommendation_card(
                "Ver cobranças vencidas",
                f"{len(overdue_receivables)} cobrança(s) precisam de ação de cobrança.",
                "Ver cobranças vencidas",
                "#financial-overdue-clients",
                tab="summary-tab",
                severity="critical",
            )
        )
    if events_without_value:
        recommended_actions.append(
            recommendation_card(
                "Corrigir valores",
                f"{len(events_without_value)} evento(s) ativo(s) do mês estão sem valor definido.",
                "Corrigir valores",
                "#financial-decision-panel",
                tab="summary-tab",
                severity="attention",
            )
        )
    if due_next_7_count:
        recommended_actions.append(
            recommendation_card(
                "Conferir próximos vencimentos",
                f"{due_next_7_count} recebimento(s) vencem nos próximos 7 dias.",
                "Conferir vencimentos",
                "#receivables-panel",
                tab="summary-tab",
                severity="attention",
            )
        )
    if not recommended_actions:
        recommended_actions.append(
            recommendation_card(
                "Conferir recebimentos recentes",
                "Sem cobrança vencida ou valor crítico pendente agora.",
                "Ver recebimentos",
                "#financial-recent-receivables",
                tab="summary-tab",
                severity="ready",
            )
        )

    return {
        "period_label": f"{month_start.strftime('%m/%Y')}",
        "expected_month_total": round2(sum(parse_decimal(item.get("amount")) for item in current_month_receivables) + event_forecast_total),
        "received_month_total": round2(received_month_total),
        "open_total": round2(open_total),
        "overdue_total": round2(overdue_total),
        "due_next_7_total": round2(due_next_7_total),
        "due_next_7_count": due_next_7_count,
        "recommended_actions": recommended_actions[:3],
        "events_without_value": events_without_value[:8],
        "top_open_clients": top_client_rows[:6],
        "overdue_clients": delayed_client_rows[:6],
        "recent_receivables": [
            {
                **item,
                "open_amount": receivable_open_amount(item),
                "paid": receivable_is_paid(item),
                "date_label": format_date_br(item.get("received_date") or item.get("due_date")),
            }
            for item in recent_receivables
        ],
        "overdue_receivables": sorted(overdue_receivables, key=lambda item: item["days_late"], reverse=True)[:8],
    }


def build_monthly_closeout(period: str, notes: str = "") -> dict:
    period = clean_text(period) or datetime.now().date().isoformat()[:7]
    if len(period) != 7 or period[4] != "-":
        raise ValueError("Informe o período no formato AAAA-MM.")
    route_history = load_route_history()
    receivables = load_financial_receivables()
    entries = load_financial_entries()
    closeouts = load_financial_closeouts()
    start_date = f"{period}-01"
    end_date = f"{period}-31"
    dashboard = build_financial_management_dashboard(route_history, receivables, entries, closeouts, "custom", start_date, end_date)
    record = {
        "id": f"FEC-{period}",
        "period": period,
        "locked": True,
        "created_at": now_iso(),
        "created_by": clean_text(current_user().get("email")),
        "revenue_total": round2(dashboard["received"] + dashboard["entry_in"] + dashboard["route_revenue"]),
        "expense_total": round2(dashboard["entry_out"] + dashboard["route_cost"]),
        "profit_total": round2(dashboard["received"] + dashboard["entry_in"] + dashboard["route_revenue"] - dashboard["entry_out"] - dashboard["route_cost"]),
        "pending_total": dashboard["expected_in"],
        "projected_balance": dashboard["projected_balance"],
        "overdue_count": len(dashboard["overdue"]),
        "notes": clean_text(notes),
    }
    existing = [item for item in closeouts if clean_text(item.get("period")) != period]
    existing.append(record)
    save_financial_closeouts(existing)
    return record


def build_monthly_closeout_pdf(period: str) -> bytes:
    closeout = next((item for item in load_financial_closeouts() if clean_text(item.get("period")) == period), None)
    if not closeout:
        closeout = build_monthly_closeout(period)
    lines = [
        f"Período: {closeout.get('period')}",
        f"Gerado em: {format_datetime_br(closeout.get('created_at'))}",
        f"Receita total: {format_currency_br(closeout.get('revenue_total'))}",
        f"Despesas totais: {format_currency_br(closeout.get('expense_total'))}",
        f"Lucro: {format_currency_br(closeout.get('profit_total'))}",
        f"Pendente: {format_currency_br(closeout.get('pending_total'))}",
        f"Saldo previsto: {format_currency_br(closeout.get('projected_balance'))}",
        f"Inadimplentes: {closeout.get('overdue_count')}",
        f"Travado: {'sim' if closeout.get('locked') else 'não'}",
        f"Observações: {closeout.get('notes') or 'n/d'}",
    ]
    return build_simple_text_pdf(f"SannyGold - Fechamento Financeiro {period}", lines)


def build_client_report_pdf(client: dict, detail: dict, *, can_view_finance: bool) -> bytes:
    summary = detail.get("smart_summary") or {}
    history = summary.get("history") or {}
    preferences = summary.get("preferences") or {}
    lines = [
        f"Gerado em {format_datetime_br(now_iso())}",
        "",
        "Dados principais",
    ]
    for field in summary.get("primary_fields") or []:
        lines.append(f"- {field.get('label')}: {field.get('value') or 'não informado'}")
    lines.extend(
        [
            "",
            "Classificação",
            f"- {summary.get('profile_label') or 'não informado'}: {summary.get('profile_detail') or 'não informado'}",
            "",
            "Histórico",
            f"- Total de locações/eventos: {history.get('events_total', 0)}",
            f"- Última locação: {history.get('last_rental') or 'não informado'} | {history.get('last_rental_date') or 'não informado'}",
            f"- Próxima locação: {history.get('next_rental') or 'não informado'} | {history.get('next_rental_date') or 'não informado'}",
        ]
    )
    if can_view_finance:
        lines.extend(
            [
                f"- Ticket médio: {format_currency_br(history.get('average_ticket')) if history.get('has_financial_data') else 'não informado'}",
                f"- Valor total faturado/previsto: {format_currency_br(history.get('total_billed')) if history.get('has_financial_data') else 'não informado'}",
                f"- Valor em aberto: {format_currency_br(history.get('open_amount'))}",
                f"- Atrasos anteriores: {history.get('delay_count', 0)}",
            ]
        )
    else:
        lines.append("- Dados financeiros: visíveis apenas para admin ou financeiro.")
    lines.extend(["", "Preferências operacionais"])
    services = preferences.get("services") or []
    equipment = preferences.get("equipment") or []
    notes = preferences.get("notes") or []
    access_restrictions = preferences.get("access_restrictions") or []
    lines.append("- Serviços mais contratados: " + ", ".join(item.get("label") for item in services) if services else "- Serviços mais contratados: não informado")
    lines.append("- Equipamentos mais usados: " + ", ".join(item.get("label") for item in equipment) if equipment else "- Equipamentos mais usados: não informado")
    lines.append(f"- Endereço mais comum: {preferences.get('common_address') or 'não informado'}")
    lines.append(f"- Horários preferidos: {preferences.get('preferred_hours') or 'não informado'}")
    lines.append("- Observações frequentes: " + ", ".join(item.get("label") for item in notes) if notes else "- Observações frequentes: não informado")
    lines.append("- Restrições de acesso: " + ", ".join(item.get("label") for item in access_restrictions) if access_restrictions else "- Restrições de acesso: não informado")
    lines.extend(["", "Alertas"])
    alerts = summary.get("alerts") or []
    if alerts:
        for alert in alerts:
            lines.append(f"- {alert.get('title')}: {alert.get('detail')}")
    else:
        lines.append("- Nenhum alerta crítico para este cliente.")
    return build_simple_text_pdf(f"SannyGold - Cliente {client.get('customer_name') or client.get('client_id')}", lines)


def build_customer_history(clients: list[dict], events: list[dict], route_history: list[dict], confirmations: list[dict]) -> list[dict]:
    events_by_client: dict[str, list[dict]] = {}
    for event in events:
        for client_id in event.get("client_ids", []) or []:
            events_by_client.setdefault(clean_text(client_id), []).append(event)

    confirmations_by_client: dict[str, list[dict]] = {}
    for confirmation in confirmations:
        confirmations_by_client.setdefault(clean_text(confirmation.get("client_id")), []).append(confirmation)

    runs_by_client: dict[str, list[dict]] = {}
    for history_item in route_history:
        for financial_event in history_item.get("financial_events") or []:
            client_id = clean_text(financial_event.get("client_id"))
            runs_by_client.setdefault(client_id, []).append({**financial_event, "generated_at": history_item.get("generated_at")})

    customer_history = []
    for client in clients:
        client_id = clean_text(client.get("client_id"))
        runs = runs_by_client.get(client_id, [])
        event_items = events_by_client.get(client_id, [])
        confirmation_items = confirmations_by_client.get(client_id, [])
        last_run = runs[0] if runs else {}
        recent_runs = sorted(runs, key=lambda item: clean_text(item.get("generated_at")), reverse=True)[:5]
        recent_confirmations = sorted(confirmation_items, key=lambda item: clean_text(item.get("created_at")), reverse=True)[:5]
        customer_history.append(
            {
                "client_id": client_id,
                "customer_name": clean_text(client.get("customer_name")),
                "address": clean_text(client.get("address")),
                "equipment_number": clean_text(client.get("equipment_number")) or "sem vínculo",
                "events_count": len(event_items),
                "routes_count": len(runs),
                "confirmations_count": len(confirmation_items),
                "revenue_total": round2(sum(float(item.get("service_value") or 0) for item in runs)),
                "profit_total": round2(sum(float(item.get("profit") or 0) for item in runs)),
                "last_route_at": clean_text(last_run.get("generated_at")),
                "last_vehicle_id": clean_text(last_run.get("vehicle_id")) or "n/d",
                "active_events": [event for event in event_items if event_is_active(event)][:3],
                "recent_events": sorted(event_items, key=lambda item: clean_text(item.get("event_date")), reverse=True)[:5],
                "recent_routes": recent_runs,
                "recent_confirmations": recent_confirmations,
            }
        )
    return customer_history


def search_text_parts(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        parts: list[str] = []
        for key, nested_value in value.items():
            parts.extend(search_text_parts(key))
            parts.extend(search_text_parts(nested_value))
        return parts
    if isinstance(value, (list, tuple, set)):
        parts = []
        for nested_value in value:
            parts.extend(search_text_parts(nested_value))
        return parts
    text = clean_text(str(value))
    return [text] if text else []


def search_digits(value) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def build_search_text(*values) -> str:
    parts: list[str] = []
    digit_parts: list[str] = []
    for value in values:
        for part in search_text_parts(value):
            parts.append(part)
            digits = search_digits(part)
            if digits:
                digit_parts.append(digits)
    return " ".join(parts + digit_parts)


def build_global_search_items(
    clients: list[dict],
    events: list[dict],
    vehicles: list[dict],
    equipment: list[dict],
    warehouse_dashboard: dict,
    attachments: list[dict] | None = None,
    receivables: list[dict] | None = None,
    route_history: list[dict] | None = None,
    audit_log: list[dict] | None = None,
) -> list[dict]:
    items: list[dict] = []
    clients_by_id = {clean_text(client.get("client_id")): client for client in clients}
    vehicles_by_id = {clean_text(vehicle.get("vehicle_id")): vehicle for vehicle in vehicles}

    def add_item(
        *,
        module: str,
        module_key: str,
        type_label: str,
        title: str,
        detail: str,
        status: str,
        target_tab: str,
        target_href: str,
        aliases: str = "",
        searchable_values: tuple = (),
    ) -> None:
        items.append({
            "module": module,
            "module_key": module_key,
            "type_label": type_label,
            "title": clean_text(title) or type_label,
            "detail": clean_text(detail, "Sem detalhe informado"),
            "status": clean_text(status, "Sem status"),
            "target_tab": clean_text(target_tab),
            "target_href": clean_text(target_href, "#summary-pane"),
            "action": "Abrir",
            "text": build_search_text(module, type_label, title, detail, status, aliases, *searchable_values),
        })

    for client in clients:
        client_aliases = "cliente banheiro locacao locação contrato mensal telefone endereco endereço cobranca cobrança"
        client_id = clean_text(client.get("client_id"))
        client_search = {
            field: client.get(field)
            for field in (
                "client_id",
                "customer_name",
                "contact_name",
                "address",
                "phone",
                "cpf_cnpj",
                "email",
                "equipment_number",
                "equipment_type",
                "invoice_number",
                "notes",
            )
        }
        add_item(
            module="Clientes",
            module_key="clientes",
            type_label="Cliente",
            title=clean_text(client.get("customer_name")) or client_id,
            detail=f"{client_id or 'sem código'} • {client.get('phone') or 'sem telefone'} • {client.get('address') or 'sem endereço'}",
            status=clean_text(client.get("status")) or clean_text(client.get("client_type")) or "Cadastro ativo",
            target_tab="clients-tab",
            target_href=f"#client-{client_id}" if client_id else "#clients-pane",
            aliases=client_aliases,
            searchable_values=(client_search,),
        )
    for event in events:
        linked_clients = [clients_by_id.get(clean_text(client_id), {}) for client_id in event.get("client_ids", []) or []]
        linked_client_text = " ".join(
            " ".join(
                str(client.get(field) or "")
                for field in ("client_id", "customer_name", "contact_name", "phone", "cpf_cnpj", "address", "equipment_number", "equipment_type")
            )
            for client in linked_clients
        )
        event_aliases = "evento ordem servico serviço os rota pdf banheiro quimico químico luxo entrega retirada montagem"
        event_id = clean_text(event.get("event_id"))
        event_search = {
            field: event.get(field)
            for field in (
                "event_id",
                "title",
                "status",
                "event_date",
                "event_end_date",
                "event_category",
                "service_type",
                "equipment_type",
                "equipment_number",
                "equipment_quantity",
                "quantity",
                "responsible",
                "address",
                "event_address",
                "local",
                "location",
                "notes",
                "vehicle_ids",
            )
        }
        add_item(
            module="Eventos/Locações",
            module_key="eventos",
            type_label="Evento/Locação",
            title=clean_text(event.get("title")) or event_id,
            detail=f"{event_id or 'sem código'} • {format_date_br(event.get('event_date')) or event.get('event_date') or 'sem data'} • {', '.join(clean_text(client.get('customer_name')) for client in linked_clients if clean_text(client.get('customer_name'))) or 'sem cliente'}",
            status=event_status_label(event.get("status")) if clean_text(event.get("status")) else "Sem status",
            target_tab="events-tab",
            target_href=f"#event-{event_id}" if event_id else "#events-pane",
            aliases=event_aliases,
            searchable_values=(event_search, linked_client_text),
        )
    for vehicle in vehicles:
        driver = clean_text(vehicle.get("driver")) or clean_text(vehicle.get("motorista")) or clean_text(vehicle.get("responsible")) or clean_text(vehicle.get("driver_name"))
        vehicle_id = clean_text(vehicle.get("vehicle_id"))
        vehicle_search = {
            field: vehicle.get(field)
            for field in ("vehicle_id", "vehicle_type", "plate", "model", "status", "driver", "motorista", "responsible", "driver_name", "notes")
        }
        add_item(
            module="Rotas/Ordens de Serviço",
            module_key="rotas_os",
            type_label="Veículo",
            title=vehicle_id or clean_text(vehicle.get("plate")) or "Veículo",
            detail=f"{vehicle.get('vehicle_type') or vehicle.get('model') or 'veículo'} • placa {vehicle.get('plate') or 'n/d'} • {driver or 'sem motorista'}",
            status=clean_text(vehicle.get("status")) or clean_text(vehicle.get("vehicle_type")) or "Frota",
            target_tab="fleet-tab",
            target_href=f"#vehicle-{vehicle_id}" if vehicle_id else "#fleet-pane",
            aliases="frota veiculo veículo placa rota base motorista responsável responsavel",
            searchable_values=(vehicle_search, driver),
        )
    for item in equipment:
        equipment_id = clean_text(item.get("equipment_id"))
        equipment_search = {
            field: item.get(field)
            for field in ("equipment_id", "equipment_type", "plate", "status", "condition", "linked_client_name", "notes", "maintenance_reason")
        }
        add_item(
            module="Equipamentos",
            module_key="equipamentos",
            type_label="Equipamento",
            title=equipment_id or clean_text(item.get("equipment_type")) or "Equipamento",
            detail=f"{item.get('equipment_type') or 'sem tipo'} • placa {item.get('plate') or 'n/d'} • {item.get('linked_client_name') or 'sem cliente vinculado'}",
            status=normalize_equipment_status(item.get("status") or item.get("condition")),
            target_tab="fleet-tab",
            target_href=f"#equipment-{equipment_id}" if equipment_id else "#fleet-pane",
            aliases="banheiro quimico químico pne luxo trailer cabine climatizador hidratacao hidratação placa manutencao manutenção equipamento",
            searchable_values=(equipment_search,),
        )
    for route_run in route_history or []:
        event_id = clean_text(route_run.get("event_id"))
        route_vehicles = [
            vehicles_by_id.get(clean_text(vehicle_id), {})
            for vehicle_id in route_run.get("vehicle_ids", []) or []
            if clean_text(vehicle_id)
        ]
        route_vehicle_text = " ".join(build_search_text(vehicle) for vehicle in route_vehicles)
        route_client_text = [
            {
                field: financial_event.get(field)
                for field in ("client_id", "client_name", "customer_name", "address", "service_type", "equipment_type", "equipment_number")
            }
            for financial_event in route_run.get("financial_events", []) or []
        ]
        route_search = {
            "event_id": route_run.get("event_id"),
            "event_title": route_run.get("event_title"),
            "event_date": route_run.get("event_date"),
            "generated_at": route_run.get("generated_at"),
            "client_ids": route_run.get("client_ids"),
            "vehicle_ids": route_run.get("vehicle_ids"),
            "equipment_in_route": route_run.get("equipment_in_route"),
            "clients": route_client_text,
        }
        route_title = clean_text(route_run.get("event_title")) or event_id or "Rota gerada"
        add_item(
            module="Rotas/Ordens de Serviço",
            module_key="rotas_os",
            type_label="Rota",
            title=f"Rota • {route_title}",
            detail=f"{format_datetime_br(route_run.get('generated_at')) or route_run.get('generated_at') or 'sem data'} • {len(route_run.get('client_ids') or [])} cliente(s)",
            status=clean_text((route_run.get("validation") or {}).get("status")) or clean_text((route_run.get("financial_summary") or {}).get("status")) or "Gerada",
            target_tab="operations-tab",
            target_href="#operations-pane",
            aliases="rota roteiro ordem servico serviço os motorista veiculo veículo entrega retirada mapa pdf",
            searchable_values=(route_search, route_vehicle_text),
        )
    service_order_logs = [
        log for log in audit_log or []
        if clean_text(log.get("action")) == "generate_service_order"
        or "ordem de serviço" in normalize_business_text(log.get("detail"))
        or "ordem de servico" in normalize_business_text(log.get("detail"))
    ]
    for log in service_order_logs[:30]:
        event_id = clean_text(log.get("target_id"))
        related_event = next((event for event in events if clean_text(event.get("event_id")) == event_id), {})
        add_item(
            module="Rotas/Ordens de Serviço",
            module_key="rotas_os",
            type_label="Ordem de Serviço",
            title=f"OS • {clean_text(related_event.get('title')) or event_id or clean_text(log.get('target')) or 'registro'}",
            detail=f"{event_id or 'sem evento'} • {format_datetime_br(log.get('created_at')) or 'sem data'} • {log.get('user') or 'usuário'}",
            status="Gerada",
            target_tab="events-tab",
            target_href=f"#event-{event_id}" if event_id else "#events-pane",
            aliases="ordem de servico ordem de serviço os pdf operacional impressao impressão",
            searchable_values=(log, related_event),
        )
    for item in warehouse_dashboard.get("items") or []:
        movement_text = " ".join(
            " ".join(
                str(movement.get(field) or "")
                for field in ("movement_type", "observation", "event_id", "event_title", "client_id", "client_name")
            )
            for movement in item.get("recent_movements") or []
        )
        add_item(
            module="Outros",
            module_key="outros",
            type_label="Almoxarifado",
            title=clean_text(item.get("name")),
            detail=f"{item.get('category')} • {item.get('quantity_current')} {item.get('unit')} • {item.get('stock_status_label')}",
            status=clean_text(item.get("stock_status_label")) or clean_text(item.get("status")) or "Estoque",
            target_tab="warehouse-tab",
            target_href="#warehouse-pane",
            aliases="material extra estoque almoxarifado compra reposicao reposição",
            searchable_values=(item, movement_text),
        )
    for movement in warehouse_dashboard.get("movements") or []:
        add_item(
            module="Outros",
            module_key="outros",
            type_label="Movimento de almoxarifado",
            title=clean_text(movement.get("item_name")) or clean_text(movement.get("item_id")),
            detail=f"{movement.get('movement_type')} • evento {movement.get('event_id') or 'n/d'} • cliente {movement.get('client_name') or movement.get('client_id') or 'n/d'}",
            status=clean_text(movement.get("movement_type")) or "Movimento",
            target_tab="warehouse-tab",
            target_href="#warehouse-pane",
            searchable_values=(movement,),
        )
    for attachment in attachments or []:
        scope = clean_text(attachment.get("scope"), "anexo")
        add_item(
            module="Outros",
            module_key="outros",
            type_label="Anexo",
            title=clean_text(attachment.get("title")) or clean_text(attachment.get("id")),
            detail=f"{scope} • cliente {attachment.get('client_id') or 'n/d'} • evento {attachment.get('event_id') or 'n/d'}",
            status=scope,
            target_tab="clients-tab",
            target_href="#attachments-panel",
            aliases="anexo arquivo foto documento comprovante",
            searchable_values=(attachment,),
        )
    for receivable in receivables or []:
        add_item(
            module="Financeiro",
            module_key="financeiro",
            type_label="Recebimento",
            title=clean_text(receivable.get("client_name")) or clean_text(receivable.get("id")),
            detail=f"{receivable.get('id')} • NF {receivable.get('invoice_number') or 'n/d'} • {format_currency_br(receivable.get('amount'))}",
            status=clean_text(receivable.get("status")) or ("Pago" if receivable_is_paid(receivable) else "Em aberto"),
            target_tab="summary-tab",
            target_href="#receivables-panel",
            aliases="financeiro recebimento cobrança cobranca contas receber nota fiscal nf pagamento vencido aberto",
            searchable_values=(receivable,),
        )
    return items[:120]


def build_global_search_groups(global_search_items: list[dict], *, can_view_finance: bool) -> list[dict]:
    module_order = [
        ("clientes", "Clientes"),
        ("eventos", "Eventos/Locações"),
        ("equipamentos", "Equipamentos"),
        ("rotas_os", "Rotas/Ordens de Serviço"),
    ]
    if can_view_finance:
        module_order.append(("financeiro", "Financeiro"))
    if any(clean_text(item.get("module_key")) == "outros" for item in global_search_items):
        module_order.append(("outros", "Outros"))

    grouped: dict[str, list[dict]] = {key: [] for key, _ in module_order}
    for item in global_search_items:
        key = clean_text(item.get("module_key"))
        if key in grouped:
            grouped[key].append(item)

    return [
        {"key": key, "label": label, "count": len(grouped.get(key, [])), "items": grouped.get(key, [])}
        for key, label in module_order
        if grouped.get(key)
    ]


def filter_global_search_items_for_profile(global_search_items: list[dict], profile_ui: dict, *, can_view_finance: bool) -> list[dict]:
    tabs = profile_ui.get("tabs") or {}
    allowed_modules: set[str] = set()
    if tabs.get("clients"):
        allowed_modules.add("clientes")
    if tabs.get("events"):
        allowed_modules.add("eventos")
    if tabs.get("fleet"):
        allowed_modules.add("equipamentos")
    if tabs.get("operations"):
        allowed_modules.add("rotas_os")
    if tabs.get("warehouse"):
        allowed_modules.add("outros")
    if can_view_finance:
        allowed_modules.add("financeiro")
    return [
        item for item in global_search_items
        if clean_text(item.get("module_key")) in allowed_modules
    ]


def build_general_improvements_dashboard(
    clients: list[dict],
    events: list[dict],
    vehicles: list[dict],
    equipment: list[dict],
    financial_management: dict,
    warehouse_dashboard: dict,
    usability_alerts: list[dict],
    dispatch_today: dict,
    receivables: list[dict],
    *,
    route_data: dict | None = None,
    has_pdf: bool = False,
    settings: dict | None = None,
) -> dict:
    def duplicate_rows(items: list[dict], field: str, label: str, display_field: str) -> list[dict]:
        grouped: dict[str, list[dict]] = {}
        for item in items:
            value = normalize_business_text(item.get(field))
            if value:
                grouped.setdefault(value, []).append(item)
        return [
            {
                "label": label,
                "value": value,
                "count": len(group),
                "items": [clean_text(row.get(display_field)) or clean_text(row.get(field)) for row in group[:4]],
            }
            for value, group in grouped.items()
            if len(group) > 1
        ]

    duplicate_alerts = []
    duplicate_alerts.extend(duplicate_rows(clients, "phone", "Telefone duplicado", "customer_name"))
    duplicate_alerts.extend(duplicate_rows(clients, "cpf_cnpj", "CPF/CNPJ duplicado", "customer_name"))
    duplicate_alerts.extend(duplicate_rows(clients, "customer_name", "Nome de cliente parecido", "customer_name"))
    duplicate_alerts.extend(duplicate_rows(vehicles, "plate", "Placa de veículo duplicada", "vehicle_id"))
    duplicate_alerts.extend(duplicate_rows(equipment, "equipment_id", "Equipamento duplicado", "equipment_id"))
    duplicate_alerts.extend(duplicate_rows(equipment, "plate", "Placa de equipamento duplicada", "equipment_id"))
    duplicate_alerts.extend(duplicate_rows(receivables, "invoice_number", "NF duplicada", "client_name"))

    critical_groups = [
        {"label": "Financeiro", "count": len(financial_management.get("overdue", [])), "detail": "cobrança(s) vencida(s)", "target": "#receivables-panel"},
        {"label": "Operação", "count": len(usability_alerts), "detail": "alerta(s) de operação", "target": "#usability-alerts-panel"},
        {"label": "Estoque", "count": (warehouse_dashboard.get("counts", {}).get("low", 0) or 0) + (warehouse_dashboard.get("counts", {}).get("zero", 0) or 0), "detail": "item(ns) baixo(s) ou zerado(s)", "target": "#warehouse-pane"},
        {"label": "Frota", "count": sum(1 for item in equipment if clean_text(item.get("status")) in {"manutencao", "indisponivel"}), "detail": "equipamento(s) indisponível(is)", "target": "#maintenance-panel"},
    ]
    today = datetime.now().date()
    horizon = today + timedelta(days=14)
    upcoming_events = [
        event for event in events
        if event_is_active(event)
        and parse_date(event.get("event_date"))
        and today <= parse_date(event.get("event_date")) <= horizon
    ]
    agenda_issues = []
    for event in upcoming_events:
        missing = []
        if not event.get("client_ids"):
            missing.append("cliente")
        if not event.get("vehicle_ids"):
            missing.append("veículo")
        if any(not item.get("done") for item in event.get("checklist") or []):
            missing.append("checklist")
        if not has_pdf:
            missing.append("PDF/OS")
        if missing:
            agenda_issues.append({
                "level": "danger" if parse_date(event.get("event_date")) == today else "warning",
                "title": clean_text(event.get("title")) or clean_text(event.get("event_id")),
                "detail": f"{format_date_br(event.get('event_date'))}: revisar {', '.join(missing)}",
                "target": f"#event-{clean_text(event.get('event_id'))}",
            })
    active_events = [event for event in events if event_is_active(event)]
    for index, event in enumerate(active_events):
        event_vehicles = {clean_text(vehicle_id) for vehicle_id in event.get("vehicle_ids", []) if clean_text(vehicle_id)}
        if not event_vehicles:
            continue
        for other in active_events[index + 1:]:
            shared = event_vehicles.intersection({clean_text(vehicle_id) for vehicle_id in other.get("vehicle_ids", []) if clean_text(vehicle_id)})
            if shared and event_overlaps_period(other, event.get("event_date"), event.get("event_end_date")):
                agenda_issues.append({
                    "level": "danger",
                    "title": "Conflito de veículo na agenda",
                    "detail": f"{', '.join(sorted(shared))}: {event.get('title')} e {other.get('title')}",
                    "target": "#agenda-pane",
                })
                break
    quality_issues = []
    for client in clients:
        missing = []
        if not clean_text(client.get("phone")):
            missing.append("telefone")
        if not clean_text(client.get("address")):
            missing.append("endereço")
        if not clean_text(client.get("contact_name")):
            missing.append("contato")
        if missing:
            quality_issues.append({
                "level": "warning",
                "title": clean_text(client.get("customer_name")) or clean_text(client.get("client_id")),
                "detail": f"Cadastro sem {', '.join(missing)}",
                "target": f"#client-{clean_text(client.get('client_id'))}",
            })
    for event in active_events:
        missing = []
        if not event.get("client_ids"):
            missing.append("cliente")
        if not event.get("vehicle_ids"):
            missing.append("veículo")
        if parse_decimal(event.get("valor_servico")) <= 0 and parse_decimal(event.get("recurring_value")) <= 0:
            missing.append("valor")
        if missing:
            quality_issues.append({
                "level": "warning",
                "title": clean_text(event.get("title")) or clean_text(event.get("event_id")),
                "detail": f"Evento sem {', '.join(missing)}",
                "target": f"#event-{clean_text(event.get('event_id'))}",
            })
    for item in warehouse_dashboard.get("items") or []:
        if item.get("stock_status") in {"baixo", "zerado"} and not clean_text(item.get("purchase_link") or item.get("purchase_location")):
            quality_issues.append({
                "level": "warning",
                "title": clean_text(item.get("name")),
                "detail": "Estoque crítico sem referência de compra.",
                "target": "#warehouse-pane",
            })
    backup_age = days_since_iso((settings or {}).get("last_backup_at"))
    if backup_age is None or backup_age > 7:
        quality_issues.append({
            "level": "warning",
            "title": "Backup antigo ou ausente",
            "detail": "Baixe um backup completo antes de mudanças importantes.",
            "target": url_for("download_system_backup"),
        })
    quality_score = max(0, 100 - min(100, len(quality_issues) * 7 + len(agenda_issues) * 5))
    selected_improvements = [
        {"number": 1, "label": "Agenda operacional", "status": "Ativo", "detail": f"{len(agenda_issues)} ponto(s) para revisar."},
        {"number": 2, "label": "Qualidade do cadastro", "status": "Ativo", "detail": f"Pontuação {quality_score}%."},
        {"number": 3, "label": "Ordem de serviço em PDF", "status": "Ativo", "detail": "PDF por evento e revisão antes de imprimir."},
        {"number": 4, "label": "Histórico por cliente", "status": "Ativo", "detail": "Linha do tempo por cliente mantida no cadastro."},
        {"number": 6, "label": "Alertas inteligentes", "status": "Ativo", "detail": "Pendências, prazos, financeiro e estoque."},
        {"number": 7, "label": "Financeiro prático", "status": "Ativo", "detail": "Recebimentos, recibos, DRE e fechamento."},
        {"number": 8, "label": "Almoxarifado ligado ao evento", "status": "Ativo", "detail": "Movimentações podem indicar evento e cliente."},
        {"number": 9, "label": "Admin discreto", "status": "Ativo", "detail": "Acessos e auditoria ficam fora do fluxo principal."},
        {"number": 10, "label": "Busca geral", "status": "Ativo", "detail": "Inclui anexos, financeiro e movimentações."},
        {"number": 11, "label": "Relatório semanal", "status": "Ativo", "detail": "Resumo baixável em PDF."},
        {"number": 12, "label": "Observações padrão", "status": "Ativo", "detail": "Modelos para pendência, manutenção, financeiro e cliente."},
        {"number": 13, "label": "Visão por função", "status": "Ativo", "detail": "Atalhos mudam conforme perfil."},
        {"number": 14, "label": "Backup e segurança", "status": "Ativo", "detail": "Backup recente agora considera prazo de 7 dias."},
        {"number": 15, "label": "Preparo para publicação", "status": "Ativo", "detail": "Checklist de Render, segredo, storage e saúde."},
    ]
    publication_readiness = [
        {"label": "Hospedagem Python", "level": "ready" if DEPLOY_TARGET else "warning", "detail": f"Ambiente atual: {DEPLOY_TARGET or 'local'}."},
        {"label": "Chave secreta", "level": "ready" if SECRET_KEY_CONFIGURED else "warning", "detail": "Configure SECRET_KEY antes de liberar uso externo."},
        {"label": "Backup", "level": "ready" if backup_age is not None and backup_age <= 7 else "warning", "detail": f"Último backup: {format_datetime_br((settings or {}).get('last_backup_at'))}."},
        {"label": "Status público", "level": "ready", "detail": "Rotas /health e /system/status.json disponíveis para conferência."},
    ]
    process_statuses = [item["label"] for item in EVENT_STATUS_FLOW]
    workflow_tracks = [
        {
            "label": "Orçamento",
            "detail": "Pedido do cliente, modelo de serviço, quantidade, valor sugerido e resposta comercial.",
            "target": "#quote-models-panel",
        },
        {
            "label": "Evento confirmado",
            "detail": "Cliente, endereço, datas, equipamentos, veículos, checklist e rota ficam vinculados ao evento.",
            "target": "#events-pane",
        },
        {
            "label": "Contrato mensal",
            "detail": "Mensalidade, frequência de limpeza, próxima cobrança e histórico do cliente ficam separados do evento avulso.",
            "target": "#contracts-quotes-panel",
        },
        {
            "label": "Financeiro",
            "detail": "Receber, pagar, provisionar impostos, anexar comprovante opcional e fechar o mês para a contabilidade.",
            "target": "#finance-overview",
        },
        {
            "label": "Equipamentos",
            "detail": "Tipo, placa quando for trailer, status, foto, manutenção e vínculo com cliente.",
            "target": "#fleet-pane",
        },
    ]
    report_shortcuts = [
        {"label": "Relatório de evento", "target": "#reports-panel"},
        {"label": "Relatório de cliente", "target": "#reports-panel"},
        {"label": "Relatório financeiro mensal", "target": "#closeout-panel"},
        {"label": "Relatório de equipamentos", "target": "#reports-panel"},
        {"label": "Relatório de inadimplência", "target": "#receivables-panel"},
        {"label": "Relatório de estoque baixo", "target": "#warehouse-pane"},
        {"label": "Relatório de rentabilidade por tipo de serviço", "target": "#taxes-panel"},
    ]
    open_events = [event for event in events if event_is_active(event)]
    return {
        "duplicate_alerts": duplicate_alerts[:12],
        "duplicate_count": len(duplicate_alerts),
        "critical_groups": critical_groups,
        "critical_total": sum(group["count"] for group in critical_groups),
        "agenda_issues": agenda_issues[:8],
        "agenda_issue_count": len(agenda_issues),
        "quality_issues": quality_issues[:8],
        "quality_issue_count": len(quality_issues),
        "quality_score": quality_score,
        "selected_improvements": selected_improvements,
        "excluded_improvement": {"number": 5, "label": "Histórico por banheiro/equipamento", "detail": "Não ampliado neste pacote, conforme solicitado."},
        "publication_readiness": publication_readiness,
        "process_statuses": process_statuses,
        "event_status_flow": EVENT_STATUS_FLOW,
        "workflow_tracks": workflow_tracks,
        "report_shortcuts": report_shortcuts,
        "home_shortcuts": ["Novo orçamento", "Novo evento", "Clientes", "Financeiro", "Equipamentos", "Relatórios"],
        "client_fields": ["CPF/CNPJ", "WhatsApp", "E-mail", "Endereço", "Tipo de cliente", "Histórico", "Preferência de pagamento"],
        "equipment_fields": ["Tipo", "Placa do trailer", "Status", "Localização atual", "Próxima manutenção", "Foto", "Observações"],
        "pdf_outputs": ["Orçamento em PDF", "Ordem de serviço", "Recibo", "Relatório mensal", "Resumo para conferência"],
        "role_matrix": ["Administrador", "Financeiro", "Operação", "Leitura/visitante"],
        "open_events": len(open_events),
        "dispatch_ready": dispatch_today.get("blocking_count", 0) == 0 and dispatch_today.get("attention_count", 0) == 0,
        "dispatch_ready_count": dispatch_today.get("ready_count", 0),
        "dispatch_total": len(dispatch_today.get("checklist") or []),
    }


def build_client_detail_index(
    clients: list[dict],
    contracts: list[dict],
    service_log: list[dict],
    quotes: list[dict],
    route_history: list[dict],
    events: list[dict] | None = None,
    financial_receivables: list[dict] | None = None,
    can_view_finance: bool = False,
) -> dict[str, dict]:
    today = datetime.now().date()
    contracts_by_client = {clean_text(item.get("client_id")): item for item in contracts}
    clients_by_id = {clean_text(client.get("client_id")): client for client in clients if clean_text(client.get("client_id"))}
    events = events or []
    financial_receivables = financial_receivables or []

    events_by_client: dict[str, list[dict]] = {}
    for event in events:
        for client_id in event.get("client_ids", []) or []:
            key = clean_text(client_id)
            if key:
                events_by_client.setdefault(key, []).append(event)

    cleanings_by_client: dict[str, list[dict]] = {}
    for item in service_log:
        client_id = clean_text(item.get("client_id"))
        if client_id:
            cleanings_by_client.setdefault(client_id, []).append(item)
    routes_by_client: dict[str, list[dict]] = {}
    for route_run in route_history:
        for route in route_run.get("routes", []) or []:
            for stop in route.get("stops", []) or []:
                client_id = clean_text(stop.get("delivery_id"))
                if client_id:
                    routes_by_client.setdefault(client_id, []).append(
                        {
                            "generated_at": clean_text(route_run.get("generated_at")),
                            "vehicle_id": clean_text(route.get("vehicle_id")),
                            "status": clean_text(stop.get("field_confirmation", {}).get("status_label"), "aguardando"),
                        }
                    )
    quotes_by_name: dict[str, list[dict]] = {}
    for quote in quotes:
        name = normalize_business_text(quote.get("customer_name"))
        if name:
            quotes_by_name.setdefault(name, []).append(quote)

    route_stops_by_client: dict[str, list[dict]] = {}
    for route_run in route_history:
        for route in route_run.get("routes", []) or []:
            for stop in route.get("stops", []) or []:
                client_id = clean_text(stop.get("delivery_id"))
                if client_id:
                    route_stops_by_client.setdefault(client_id, []).append(stop)

    def not_informed(value: str | None) -> str:
        return clean_text(value) or "não informado"

    def top_values(values: list[str], limit: int = 3) -> list[dict]:
        counter = Counter(clean_text(value) for value in values if clean_text(value))
        return [{"label": label, "count": count} for label, count in counter.most_common(limit)]

    def first_known(values: list[str]) -> str:
        for value in values:
            text = clean_text(value)
            if text:
                return text
        return ""

    def short_note(value: str, max_len: int = 96) -> str:
        text = " ".join(clean_text(value).split())
        return f"{text[: max_len - 1].rstrip()}…" if len(text) > max_len else text

    def note_matches_access(value: str) -> bool:
        normalized = normalize_business_text(value)
        return any(keyword in normalized for keyword in ("acesso", "portaria", "entrada", "restricao", "restrição", "carga", "descarga"))

    def event_date_label(event: dict | None) -> str:
        event = event or {}
        start = clean_text(event.get("event_date"))
        end = clean_text(event.get("event_end_date"))
        if start and end and end != start:
            return f"{format_date_br(start)} a {format_date_br(end)}"
        return format_date_br(start) if start else "não informado"

    def event_display_name(event: dict | None) -> str:
        event = event or {}
        return clean_text(event.get("title")) or clean_text(event.get("event_id")) or "não informado"

    def client_receivables_for(client: dict) -> list[dict]:
        client_id = clean_text(client.get("client_id"))
        client_name_key = normalize_business_text(client.get("customer_name"))
        return [
            item for item in financial_receivables
            if clean_text(item.get("client_id")) == client_id
            or (client_name_key and normalize_business_text(item.get("client_name")) == client_name_key)
        ]

    result = {}
    for client in clients:
        client_id = clean_text(client.get("client_id"))
        client_name = clean_text(client.get("customer_name")) or client_id
        cleanings = sorted(cleanings_by_client.get(client_id, []), key=lambda item: clean_text(item.get("service_date")), reverse=True)
        routes = sorted(routes_by_client.get(client_id, []), key=lambda item: clean_text(item.get("generated_at")), reverse=True)
        event_items = sorted(events_by_client.get(client_id, []), key=lambda item: clean_text(item.get("event_date")), reverse=True)
        route_stops = route_stops_by_client.get(client_id, [])
        client_quotes = quotes_by_name.get(normalize_business_text(client.get("customer_name")), [])
        contract = contracts_by_client.get(client_id, {})
        past_events = [
            event for event in event_items
            if (start := event_start_date(event)) and start <= today
        ]
        future_events = sorted(
            [
                event for event in event_items
                if (start := event_start_date(event)) and start >= today and normalize_event_status(event.get("status")) != "cancelado"
            ],
            key=lambda item: clean_text(item.get("event_date")),
        )
        last_event = past_events[0] if past_events else {}
        next_event = future_events[0] if future_events else {}
        next_event_start = event_start_date(next_event) if next_event else None
        timeline = []
        if contract:
            timeline.append({
                "label": "Contrato",
                "date": format_date_br(contract.get("start_date")) if contract.get("start_date") else "ativo",
                "detail": f"{format_currency_br(contract.get('monthly_value'))} • {clean_text(contract.get('cleaning_frequency'), 'semanal').replace('_', ' ')}",
                "level": "ready",
            })
        if last_event:
            timeline.append({
                "label": "Última locação",
                "date": event_date_label(last_event),
                "detail": event_display_name(last_event),
                "level": "ready",
            })
        if next_event:
            timeline.append({
                "label": "Próxima locação",
                "date": event_date_label(next_event),
                "detail": event_display_name(next_event),
                "level": "warning" if next_event_start and 0 <= (next_event_start - today).days <= 7 else "info",
            })
        if cleanings:
            timeline.append({
                "label": "Última limpeza",
                "date": format_date_br(cleanings[0].get("service_date")),
                "detail": clean_text(cleanings[0].get("notes")) or clean_text(cleanings[0].get("service_type"), "limpeza"),
                "level": "info",
            })
        for route in routes[:2]:
            timeline.append({
                "label": "Rota",
                "date": format_datetime_br(route.get("generated_at")),
                "detail": f"{route.get('vehicle_id') or 'sem veículo'} • {route.get('status')}",
                "level": "info",
            })
        for quote in quotes_by_name.get(normalize_business_text(client.get("customer_name")), [])[:2]:
            timeline.append({
                "label": "Orçamento",
                "date": format_date_br(quote.get("event_date")) if quote.get("event_date") else "sem data",
                "detail": f"{quote.get('id')} • {quote.get('status')}",
                "level": "warning" if clean_text(quote.get("status")) not in {"aprovado", "finalizado"} else "ready",
            })
        if not timeline:
            timeline.append({
                "label": "Cadastro",
                "date": "atual",
                "detail": "Complete telefone, endereço, banheiro/equipamento e histórico para a linha do tempo crescer.",
                "level": "info",
            })

        receivables = client_receivables_for(client) if can_view_finance else []
        linked_receivable_event_ids = {clean_text(item.get("event_id")) for item in receivables if clean_text(item.get("event_id"))}
        event_values = [
            event_financial_value(event, clients_by_id)
            for event in event_items
            if clean_text(event.get("event_id")) not in linked_receivable_event_ids
        ]
        receivable_total = round2(sum(parse_decimal(item.get("amount")) for item in receivables))
        event_value_total = round2(sum(value for value in event_values if value > 0))
        known_financial_total = round2(receivable_total + event_value_total)
        open_amount = round2(sum(receivable_open_amount(item) for item in receivables if not receivable_is_paid(item)))
        overdue_receivables = []
        delay_count = 0
        for receivable in receivables:
            due_date = parse_date(receivable.get("due_date"))
            received_date = parse_date(receivable.get("received_date") or clean_text(receivable.get("updated_at"))[:10])
            open_value = receivable_open_amount(receivable)
            is_overdue_now = not receivable_is_paid(receivable) and open_value > 0 and (
                clean_text(receivable.get("status")).lower() == "vencido" or (due_date and due_date < today)
            )
            was_late = bool(due_date and received_date and received_date > due_date)
            if is_overdue_now:
                overdue_receivables.append(receivable)
            if is_overdue_now or was_late or clean_text(receivable.get("status")).lower() == "vencido":
                delay_count += 1
        financial_count = len([value for value in event_values if value > 0]) + len([item for item in receivables if parse_decimal(item.get("amount")) > 0])
        average_ticket = round2(known_financial_total / financial_count) if financial_count else 0.0

        last_activity_dates = [
            clean_text(last_event.get("event_date")),
            clean_text(cleanings[0].get("service_date")) if cleanings else "",
            clean_text(routes[0].get("generated_at"))[:10] if routes else "",
        ]
        last_activity_date = parse_date(max([date for date in last_activity_dates if date], default=""))
        inactive_days = (today - last_activity_date).days if last_activity_date and not next_event else 0
        requires_document = (
            clean_text(client.get("invoice_status")) == "com_nota"
            or clean_text(client.get("billing_model")) == "mensal"
            or clean_text(client.get("client_type")) == "fixo"
        )

        alerts = []
        if can_view_finance and overdue_receivables:
            alerts.append({
                "level": "critica",
                "class": "badge-danger",
                "title": "Cliente com pagamento vencido",
                "detail": f"{len(overdue_receivables)} cobrança(s) vencida(s) somando {format_currency_br(sum(receivable_open_amount(item) for item in overdue_receivables))}.",
                "action": "Cobrar",
                "href": "#receivables-panel",
                "tab": "summary-tab",
            })
        if not clean_text(client.get("phone")):
            alerts.append({
                "level": "atenção",
                "class": "badge-avulso",
                "title": "Cliente sem telefone",
                "detail": "Complete telefone ou WhatsApp para venda, operação e cobrança.",
                "action": "Editar cliente",
                "href": "#manual-client-form",
                "tab": "clients-tab",
                "create": "manual-client-form",
            })
        if requires_document and not clean_text(client.get("cpf_cnpj")):
            alerts.append({
                "level": "atenção",
                "class": "badge-avulso",
                "title": "Cliente sem dados fiscais",
                "detail": "CPF/CNPJ está vazio e pode travar nota, contrato ou cobrança.",
                "action": "Editar fiscal",
                "href": "#manual-client-form",
                "tab": "clients-tab",
                "create": "manual-client-form",
            })
        if next_event_start and 0 <= (next_event_start - today).days <= 7:
            alerts.append({
                "level": "atenção",
                "class": "badge-fixed",
                "title": "Cliente com evento próximo",
                "detail": f"{event_display_name(next_event)} em {event_date_label(next_event)}.",
                "action": "Ver evento",
                "href": f"#event-{clean_text(next_event.get('event_id'))}",
                "tab": "events-tab",
            })
        if inactive_days >= 180:
            alerts.append({
                "level": "baixa",
                "class": "badge-fixed",
                "title": "Cliente inativo há muito tempo",
                "detail": f"Sem locação registrada há {inactive_days} dia(s).",
                "action": "Criar locação",
                "href": "#quick-rental-panel",
                "tab": "summary-tab",
            })

        service_values = [
            clean_text(event.get("event_category")).replace("_", " ") for event in event_items
        ] + [
            clean_text(client.get("service_profile")).replace("_", " "),
            clean_text(contract.get("service_profile")).replace("_", " "),
            *[clean_text(quote.get("service_type")).replace("_", " ") for quote in client_quotes],
        ]
        equipment_values = [
            clean_text(client.get("equipment_type")),
            clean_text(contract.get("equipment_type")),
            *[clean_text(stop.get("equipment_type")) for stop in route_stops],
            *[clean_text(quote.get("equipment_type")) for quote in client_quotes],
        ]
        addresses = [clean_text(client.get("address")), *[clean_text(stop.get("address")) for stop in route_stops]]
        notes = [
            clean_text(event.get("notes")) for event in event_items
        ] + [
            clean_text(item.get("notes")) for item in cleanings
        ] + [
            clean_text(quote.get("notes")) for quote in client_quotes
        ]
        access_notes = [note for note in notes if note_matches_access(note)]
        phone_digits = "".join(ch for ch in clean_text(client.get("phone")) if ch.isdigit())
        whatsapp_message = (
            f"Olá, {client_name}. Estamos entrando em contato sobre uma cobrança da SannyGold."
            if can_view_finance and overdue_receivables
            else f"Olá, {client_name}. Estamos confirmando os dados da sua locação com a SannyGold."
        )
        whatsapp_href = f"https://wa.me/{phone_digits}?text={urllib.parse.quote(whatsapp_message)}" if phone_digits else ""
        profile_label = "Cliente novo"
        profile_detail = "Ainda sem histórico suficiente para classificar recorrência."
        profile_badge_class = "badge-fixed"
        if can_view_finance and overdue_receivables:
            profile_label = "Cliente com atraso"
            profile_detail = "Existe cobrança vencida que precisa de ação antes de nova liberação financeira."
            profile_badge_class = "badge-danger"
        elif not clean_text(client.get("phone")) or not client_has_valid_address(client) or (requires_document and not clean_text(client.get("cpf_cnpj"))):
            profile_label = "Cadastro incompleto"
            profile_detail = "Faltam dados importantes para venda, operação ou cobrança."
            profile_badge_class = "badge-avulso"
        elif contract or len(event_items) >= 2:
            profile_label = "Cliente recorrente"
            profile_detail = "Tem contrato ou mais de uma locação/evento no histórico."
            profile_badge_class = "badge-success"
        elif event_items:
            profile_label = "Cliente ativo"
            profile_detail = "Já tem locação/evento registrado no sistema."
            profile_badge_class = "badge-success"

        quick_actions = [
            {"label": "Criar nova locação", "href": "#quick-rental-panel", "tab": "summary-tab", "class": "js-start-client-rental", "external": False},
            {"label": "Ver histórico", "href": "#customer-history", "tab": "clients-tab", "class": "js-tab-link", "external": False},
            {"label": "Gerar relatório do cliente", "href": f"/clients/{urllib.parse.quote(client_id, safe='')}/report.pdf", "tab": "", "class": "", "external": False},
        ]
        if can_view_finance:
            quick_actions.insert(1, {"label": "Lançar recebimento", "href": "#receivables-panel", "tab": "summary-tab", "class": "js-tab-link", "external": False})
        if whatsapp_href:
            quick_actions.append({
                "label": "Enviar cobrança" if can_view_finance and overdue_receivables else "Enviar confirmação",
                "href": whatsapp_href,
                "tab": "",
                "class": "",
                "external": True,
            })
        recommended_actions = []
        if can_view_finance and overdue_receivables:
            recommended_actions.append(
                recommendation_card(
                    "Ver cobrança",
                    f"{len(overdue_receivables)} cobrança(s) vencida(s) exigem acompanhamento.",
                    "Ver cobrança",
                    "#receivables-panel",
                    tab="summary-tab",
                    severity="critical",
                )
            )
        if not clean_text(client.get("phone")):
            recommended_actions.append(
                recommendation_card(
                    "Adicionar telefone",
                    "Sem telefone/WhatsApp, operação e cobrança ficam sem contato rápido.",
                    "Adicionar telefone",
                    "#manual-client-form",
                    tab="clients-tab",
                    severity="attention",
                )
            )
        if next_event:
            recommended_actions.append(
                recommendation_card(
                    "Abrir próxima locação",
                    f"{event_display_name(next_event)} em {event_date_label(next_event)}.",
                    "Abrir próxima locação",
                    f"#event-{clean_text(next_event.get('event_id'))}",
                    tab="events-tab",
                    severity="attention" if next_event_start and 0 <= (next_event_start - today).days <= 7 else "low",
                )
            )
        if inactive_days >= 180:
            recommended_actions.append(
                recommendation_card(
                    "Criar nova abordagem",
                    f"Cliente sem locação registrada há {inactive_days} dia(s).",
                    "Criar abordagem",
                    "#quick-rental-panel",
                    tab="summary-tab",
                    severity="low",
                )
            )
        if not recommended_actions:
            recommended_actions.append(
                recommendation_card(
                    "Revisar cadastro",
                    "Sem alerta crítico agora. Mantenha telefone, endereço e preferências atualizados.",
                    "Revisar cadastro",
                    f"#client-{client_id}",
                    tab="clients-tab",
                    severity="ready",
                )
            )

        smart_summary = {
            "profile_label": profile_label,
            "profile_detail": profile_detail,
            "profile_badge_class": profile_badge_class,
            "primary_fields": [
                {"label": "Nome", "value": not_informed(client.get("customer_name"))},
                {"label": "Telefone/WhatsApp", "value": not_informed(client.get("phone"))},
                {"label": "E-mail", "value": not_informed(client.get("email"))},
                {"label": "CNPJ/CPF", "value": not_informed(client.get("cpf_cnpj"))},
                {"label": "Endereço", "value": not_informed(client.get("address"))},
                {"label": "Responsável de contato", "value": not_informed(client.get("contact_name"))},
            ],
            "history": {
                "events_total": len(event_items),
                "last_rental": event_display_name(last_event),
                "last_rental_date": event_date_label(last_event) if last_event else "não informado",
                "next_rental": event_display_name(next_event),
                "next_rental_date": event_date_label(next_event) if next_event else "não informado",
                "average_ticket": average_ticket,
                "total_billed": known_financial_total,
                "open_amount": open_amount,
                "delay_count": delay_count,
                "has_financial_data": can_view_finance and (financial_count > 0 or open_amount > 0 or delay_count > 0),
            },
            "preferences": {
                "services": top_values(service_values),
                "equipment": top_values(equipment_values),
                "common_address": first_known([item["label"] for item in top_values(addresses, limit=1)]) or "não informado",
                "notes": [{"label": short_note(note), "count": count} for note, count in Counter(short_note(note) for note in notes if clean_text(note)).most_common(3)],
                "access_restrictions": [{"label": short_note(note), "count": count} for note, count in Counter(short_note(note) for note in access_notes if clean_text(note)).most_common(2)],
                "preferred_hours": f"{clean_text(client.get('window_start')) or 'não informado'} - {clean_text(client.get('window_end')) or 'não informado'}",
            },
            "alerts": alerts,
            "alerts_count": len(alerts),
            "quick_actions": quick_actions,
            "recommended_actions": recommended_actions[:3],
        }
        result[client_id] = {
            "contract": contract,
            "cleanings_count": len(cleanings),
            "last_cleaning": cleanings[0] if cleanings else {},
            "recent_cleanings": cleanings[:4],
            "recent_routes": routes[:4],
            "open_quotes": client_quotes[:3],
            "timeline": timeline[:5],
            "smart_summary": smart_summary,
        }
    return result


def build_usability_alerts(
    clients: list[dict],
    vehicles: list[dict],
    equipment: list[dict],
    contracts: list[dict],
    cleaning_agenda: list[dict],
    warehouse_dashboard: dict,
) -> list[dict]:
    alerts: list[dict] = []
    future_cleaning_clients = {
        clean_text(item.get("client_id"))
        for item in cleaning_agenda
        if clean_text(item.get("status")) != "executada"
    }
    for contract in contracts:
        client_id = clean_text(contract.get("client_id"))
        if clean_text(contract.get("status"), "ativo") == "ativo" and client_id not in future_cleaning_clients:
            alerts.append({
                "level": "warning",
                "title": "Contrato sem limpeza futura",
                "detail": clean_text(contract.get("client_name")) or client_id,
                "target_tab": "clients-tab",
                "target_href": "#clients-pane",
            })
    for item in equipment:
        if not clean_text(item.get("photo_url")):
            alerts.append({
                "level": "warning",
                "title": "Equipamento sem foto",
                "detail": f"{item.get('equipment_id')} • {item.get('equipment_type')}",
                "target_tab": "fleet-tab",
                "target_href": "#fleet-pane",
            })
        if equipment_family(item.get("equipment_type")) == "banheiro_luxo" and not clean_text(item.get("plate")):
            alerts.append({
                "level": "warning",
                "title": "Trailer sem placa cadastrada",
                "detail": f"{item.get('equipment_id')} • {item.get('equipment_type')}",
                "target_tab": "fleet-tab",
                "target_href": "#fleet-pane",
            })
    for vehicle in vehicles:
        if not clean_text(vehicle.get("photo_url")):
            alerts.append({
                "level": "warning",
                "title": "Veículo sem foto",
                "detail": f"{vehicle.get('vehicle_id')} • {vehicle.get('vehicle_type')}",
                "target_tab": "fleet-tab",
                "target_href": "#fleet-pane",
            })
        if not clean_text(vehicle.get("plate")):
            alerts.append({
                "level": "danger",
                "title": "Veículo sem placa",
                "detail": clean_text(vehicle.get("vehicle_id")),
                "target_tab": "fleet-tab",
                "target_href": "#fleet-pane",
            })
    for item in warehouse_dashboard.get("items") or []:
        if item.get("stock_status") in {"baixo", "zerado"}:
            alerts.append({
                "level": "danger" if item.get("stock_status") == "zerado" else "warning",
                "title": f"Estoque {item.get('stock_status_label')}",
                "detail": f"{item.get('name')} • {item.get('quantity_current')} {item.get('unit')}",
                "target_tab": "warehouse-tab",
                "target_href": "#warehouse-pane",
            })
    return alerts[:12]


def build_usability_home(
    clients: list[dict],
    events: list[dict],
    vehicles: list[dict],
    equipment: list[dict],
    cleaning_agenda: list[dict],
    warehouse_dashboard: dict,
    usability_alerts: list[dict],
) -> dict:
    today = datetime.now().date().isoformat()
    next_events = sorted(
        [
            item for item in events
            if clean_text(item.get("event_date")) >= today and event_is_active(item)
        ],
        key=lambda item: clean_text(item.get("event_date")),
    )[:5]
    today_cleanings = [item for item in cleaning_agenda if clean_text(item.get("service_date")) == today]
    return {
        "next_events": next_events,
        "today_cleanings": today_cleanings,
        "available_vehicles": len(vehicles),
        "available_equipment": sum(1 for item in equipment if item.get("status") == "disponivel"),
        "fixed_clients": sum(1 for item in clients if clean_text(item.get("client_type"), "fixo") == "fixo"),
        "low_stock": warehouse_dashboard.get("counts", {}).get("low", 0) + warehouse_dashboard.get("counts", {}).get("zero", 0),
        "alerts": usability_alerts,
    }


def build_daily_command_center(
    events: list[dict],
    cleaning_agenda: list[dict],
    financial_management: dict,
    route_data: dict | None,
    inventory: list[dict],
    usability_alerts: list[dict],
    clients: list[dict] | None = None,
    vehicles: list[dict] | None = None,
    *,
    user: dict | None = None,
    can_view_finance: bool = False,
) -> dict:
    clients = clients or []
    vehicles = vehicles or []
    profile_ui = build_profile_ui(user or public_user())
    today_date = datetime.now().date()
    today = today_date.isoformat()
    week_end = (today_date + timedelta(days=7)).isoformat()
    clients_by_id = {clean_text(client.get("client_id")): client for client in clients if clean_text(client.get("client_id"))}
    vehicles_by_id = {clean_text(vehicle.get("vehicle_id")): vehicle for vehicle in vehicles if clean_text(vehicle.get("vehicle_id"))}
    route_event_id = clean_text((route_data or {}).get("event_id"))
    route_stops = [stop for route in (route_data or {}).get("routes", []) or [] for stop in route.get("stops", []) or []]
    audit_log = load_audit_log()

    def event_in_window(event: dict, start_iso: str, end_iso: str) -> bool:
        start = event_start_date(event)
        end = event_end_date(event)
        window_start = parse_date(start_iso)
        window_end = parse_date(end_iso)
        if not start or not end or not window_start or not window_end:
            return False
        return start <= window_end and window_start <= end

    def event_link(event: dict) -> dict:
        event_id = clean_text(event.get("event_id"))
        return {
            "target_tab": "events-tab",
            "target_href": f"#event-{event_id}" if event_id else "#events-pane",
        }

    def action_item(
        label: str,
        href: str,
        tab: str = "summary-tab",
        *,
        create: str = "",
        detail: str = "",
        tone: str = "secondary",
    ) -> dict:
        return {
            "label": label,
            "href": href,
            "tab": tab,
            "create": create,
            "detail": detail,
            "tone": tone,
        }

    def pending_item(
        title: str,
        detail: str,
        action: str,
        href: str,
        tab: str = "summary-tab",
        *,
        level: str = "danger",
        kind: str = "operacao",
        create: str = "",
    ) -> dict:
        return {
            "title": title,
            "detail": detail,
            "action": action,
            "target_href": href,
            "target_tab": tab,
            "level": level,
            "kind": kind,
            "create": create,
        }

    active_window_events = [
        event for event in events
        if event_is_active(event) and event_in_window(event, today, week_end)
    ]
    enriched_window_events = []
    for event in active_window_events:
        linked_clients = [clients_by_id.get(clean_text(client_id), {}) for client_id in event.get("client_ids") or []]
        valid_linked_clients = [client for client in linked_clients if client]
        status_context = build_event_status_context(
            event,
            valid_linked_clients,
            route_data,
            audit_log,
            can_view_finance=can_view_finance,
        )
        enriched_window_events.append(
            {
                **event,
                "status": status_context["status"],
                "status_label": status_context["label"],
                "status_context": status_context,
            }
        )
    active_window_events = enriched_window_events
    active_window_events.sort(key=lambda event: (clean_text(event.get("event_date")), clean_text(event.get("title"))))
    today_events = [
        item for item in active_window_events
        if event_in_window(item, today, today)
    ]
    today_cleanings = [item for item in cleaning_agenda if clean_text(item.get("service_date")) == today]
    upcoming_cleanings = [
        item for item in cleaning_agenda
        if today <= clean_text(item.get("service_date")) <= week_end
    ]
    today_receivables = []
    due_soon = []
    overdue = []
    if can_view_finance:
        today_receivables = [
            item for item in financial_management.get("receivables_due_soon", [])
            if clean_text(item.get("due_date")) == today
        ]
        due_soon = list(financial_management.get("receivables_due_soon", []))
        overdue = list(financial_management.get("overdue", []))

    route_pending_events = [
        event for event in active_window_events
        if (event.get("status_context") or {}).get("status") == "rota_pendente"
    ]

    service_orders_pending = [
        event for event in active_window_events
        if (event.get("status_context") or {}).get("status") == "os_pendente"
    ]

    active_equipment = [
        item for item in inventory
        if clean_text(item.get("status")) in COMMITTED_EQUIPMENT_STATUSES
    ]
    active_equipment.sort(key=lambda item: (clean_text(item.get("status")), clean_text(item.get("equipment_id"))))

    today_vehicle_index: dict[str, dict] = {}
    for event in today_events:
        for vehicle_id in event.get("vehicle_ids") or []:
            normalized_id = clean_text(vehicle_id)
            if not normalized_id:
                continue
            vehicle = vehicles_by_id.get(normalized_id, {})
            today_vehicle_index[normalized_id] = {
                "vehicle_id": normalized_id,
                "vehicle_type": clean_text(vehicle.get("vehicle_type"), "Veículo") or "Veículo",
                "plate": clean_text(vehicle.get("plate")) or "placa n/d",
                "model": clean_text(vehicle.get("model")),
                "driver": clean_text(vehicle.get("driver") or vehicle.get("motorista") or vehicle.get("responsible") or vehicle.get("responsavel")) or "Responsável não informado",
                "event_title": clean_text(event.get("title")),
                "target_tab": "fleet-tab",
                "target_href": "#fleet-pane",
            }
    for route in (route_data or {}).get("routes", []) or []:
        if not route.get("stops"):
            continue
        normalized_id = clean_text(route.get("vehicle_id"))
        if not normalized_id:
            continue
        today_vehicle_index.setdefault(
            normalized_id,
            {
                "vehicle_id": normalized_id,
                "vehicle_type": clean_text(route.get("vehicle_type"), "Veículo") or "Veículo",
                "plate": clean_text(route.get("vehicle_plate")) or "placa n/d",
                "model": clean_text(route.get("vehicle_model")),
                "driver": "Responsável não informado",
                "event_title": clean_text((route_data or {}).get("event_title")) or "Rota atual",
                "target_tab": "operations-tab",
                "target_href": "#route-list",
            },
        )
    today_vehicles = sorted(today_vehicle_index.values(), key=lambda item: item["vehicle_id"])

    critical_pending = []
    for event in active_window_events:
        links = event_link(event)
        event_title = clean_text(event.get("title")) or clean_text(event.get("event_id")) or "Evento sem título"
        linked_clients = [clients_by_id.get(clean_text(client_id), {}) for client_id in event.get("client_ids") or []]
        valid_linked_clients = [client for client in linked_clients if client]
        missing_address_clients = [client for client in linked_clients if not client or not client_has_valid_address(client)]
        missing_equipment_clients = [client for client in linked_clients if not clean_text(client.get("equipment_number"))]
        missing_phone_clients = [client for client in linked_clients if client and not clean_text(client.get("phone"))]

        if not linked_clients or missing_address_clients:
            critical_pending.append(
                pending_item(
                    "Evento sem endereço",
                    f"{event_title}: {len(missing_address_clients) or 1} cliente(s) sem endereço/coordenada.",
                    "Corrigir endereço",
                    "#clients-pane" if valid_linked_clients else links["target_href"],
                    "clients-tab" if valid_linked_clients else links["target_tab"],
                    kind="endereco",
                    create="manual-client-form" if not valid_linked_clients else "",
                )
            )
        if not linked_clients or missing_equipment_clients:
            critical_pending.append(
                pending_item(
                    "Evento sem equipamento",
                    f"{event_title}: vincule banheiro/equipamento antes do despacho.",
                    "Abrir equipamentos",
                    "#fleet-pane",
                    "fleet-tab",
                    kind="equipamento",
                )
            )
        if parse_decimal(event.get("valor_servico")) <= 0 and parse_decimal(event.get("valor_adicional")) <= 0 and parse_decimal(event.get("recurring_value")) <= 0:
            critical_pending.append(
                pending_item(
                    "Evento sem valor",
                    f"{event_title}: valor do serviço ainda zerado.",
                    "Registrar valor",
                    links["target_href"],
                    links["target_tab"],
                    kind="financeiro",
                )
            )
        if not event.get("vehicle_ids"):
            critical_pending.append(
                pending_item(
                    "Rota sem veículo",
                    f"{event_title}: defina ao menos um veículo para gerar a rota.",
                    "Definir veículo",
                    links["target_href"],
                    links["target_tab"],
                    kind="rota",
                )
            )
        if not clean_text(event.get("responsible") or event.get("responsavel") or event.get("assigned_to") or event.get("motorista")):
            critical_pending.append(
                pending_item(
                    "Serviço sem responsável",
                    f"{event_title}: responsável interno não informado.",
                    "Revisar evento",
                    links["target_href"],
                    links["target_tab"],
                    level="warning",
                    kind="responsavel",
                )
            )
        for client in missing_phone_clients[:2]:
            critical_pending.append(
                pending_item(
                    "Cliente sem telefone",
                    f"{clean_text(client.get('customer_name')) or clean_text(client.get('client_id'))}: telefone vazio.",
                    "Editar cliente",
                    "#clients-pane",
                    "clients-tab",
                    level="warning",
                    kind="cliente",
                )
            )

    for item in overdue[:5]:
        critical_pending.append(
            pending_item(
                "Recebimento vencido",
                f"{clean_text(item.get('client_name'), 'Cliente')}: {format_currency_br(item.get('open_amount') or item.get('amount'))} vencido.",
                "Abrir financeiro",
                "#receivables-panel",
                "summary-tab",
                kind="financeiro",
            )
        )
    for item in due_soon[:5]:
        if clean_text(item.get("due_date")) < today:
            continue
        critical_pending.append(
            pending_item(
                "Recebimento próximo",
                f"{clean_text(item.get('client_name'), 'Cliente')}: vence em {format_date_br(item.get('due_date'))}.",
                "Abrir financeiro",
                "#receivables-panel",
                "summary-tab",
                level="warning",
                kind="financeiro",
            )
        )

    critical_pending = critical_pending[:12]
    stock_alerts = [item for item in usability_alerts if "Estoque" in clean_text(item.get("title"))]
    route_stop_count = len(route_stops)
    service_order_items = [
        {
            **event,
            "service_order_url": url_for("download_service_order", event_id=clean_text(event.get("event_id"))),
        }
        for event in service_orders_pending[:8]
        if clean_text(event.get("event_id"))
    ]
    quick_actions = []
    if profile_ui["can_create_client"]:
        quick_actions.append(action_item("Criar cliente", "#clients-pane", "clients-tab", create="manual-client-form", detail="Novo endereço/cliente"))
    if profile_ui["can_create_event"]:
        quick_actions.append(action_item("Criar evento/locação", "#quick-rental-panel", "summary-tab", detail="Cliente + evento"))
    if profile_ui["can_generate_route"]:
        quick_actions.append(action_item("Gerar rota", "#operations-pane", "operations-tab", detail=f"{len(route_pending_events)} pendente(s)", tone="dark"))
    if profile_ui["can_generate_service_order"]:
        quick_actions.append(
            action_item(
                "Gerar ordem de serviço",
                service_order_items[0]["service_order_url"] if service_order_items else "#events-pane",
                "" if service_order_items else "events-tab",
                detail=f"{len(service_orders_pending)} pendente(s)",
            )
        )
    if profile_ui["can_receive_payment"]:
        quick_actions.append(action_item("Lançar recebimento", "#receivables-panel", "summary-tab", detail="Financeiro"))
    quick_actions.append(action_item("Ver pendências", "#attention-now-panel", "summary-tab", detail=f"{len(critical_pending)} item(ns)", tone="danger" if critical_pending else "secondary"))
    return {
        "date": today,
        "week_end": week_end,
        "today_events": today_events[:8],
        "upcoming_events": active_window_events[:10],
        "today_cleanings": today_cleanings[:8],
        "upcoming_cleanings": upcoming_cleanings[:8],
        "today_receivables": today_receivables[:8],
        "route_stops": route_stop_count,
        "route_pending_events": route_pending_events[:8],
        "service_orders_pending": service_order_items,
        "active_equipment": active_equipment[:10],
        "today_vehicles": today_vehicles[:8],
        "critical_pending": critical_pending,
        "critical_count": sum(1 for item in critical_pending if criticality_key(item.get("level")) == "block"),
        "attention_count": sum(1 for item in critical_pending if criticality_key(item.get("level")) == "attention"),
        "stock_alerts": stock_alerts[:4],
        "alerts": usability_alerts[:8],
        "next_actions": [
            {"label": "Cobrar vencidos", "count": len(overdue), "target": "receivables-panel" if can_view_finance else "system-readiness-panel"},
            {"label": "Limpezas de hoje", "count": len(today_cleanings), "target": "contracts-quotes-panel"},
            {"label": "Alertas operacionais", "count": len(usability_alerts), "target": "usability-alerts-panel"},
            {"label": "Paradas em rota", "count": route_stop_count, "target": "route-list"},
        ],
        "quick_actions": quick_actions,
    }


def build_intelligent_pending_panel(
    *,
    user: dict,
    clients: list[dict],
    events: list[dict],
    vehicles: list[dict],
    equipment: list[dict],
    financial_receivables: list[dict],
    route_data: dict | None,
    equipment_raw: list[dict] | None = None,
) -> dict:
    today = datetime.now().date()
    clients_by_id = {clean_text(client.get("client_id")): client for client in clients if clean_text(client.get("client_id"))}
    vehicles_by_id = {clean_text(vehicle.get("vehicle_id")): vehicle for vehicle in vehicles if clean_text(vehicle.get("vehicle_id"))}
    raw_equipment_by_id = {
        clean_text(item.get("equipment_id")): item
        for item in (equipment_raw or equipment)
        if clean_text(item.get("equipment_id"))
    }
    linked_receivable_event_ids = {
        clean_text(item.get("event_id"))
        for item in financial_receivables
        if clean_text(item.get("event_id"))
    }
    generated_service_order_event_ids = {
        clean_text(item.get("target_id"))
        for item in load_audit_log()
        if clean_text(item.get("module")) == "events"
        and (
            clean_text(item.get("action")) == "generate_service_order"
            or "ordem de serviço" in clean_text(item.get("detail")).lower()
        )
    }
    category_meta = {
        "operational": {"label": "Pendências operacionais", "short_label": "Operacional"},
        "financial": {"label": "Pendências financeiras", "short_label": "Financeiro"},
        "registration": {"label": "Pendências de cadastro", "short_label": "Cadastro"},
        "maintenance": {"label": "Pendências de manutenção", "short_label": "Manutenção"},
    }
    severity_meta = {
        "critica": {"label": "Crítica", "rank": 0, "badge_class": "badge-danger", "card_class": "crit-block"},
        "atencao": {"label": "Atenção", "rank": 1, "badge_class": "badge-avulso", "card_class": "crit-attention"},
        "baixa": {"label": "Baixa", "rank": 2, "badge_class": "badge-fixed", "card_class": "crit-info"},
    }
    role = clean_text(user.get("role"), "guest")
    visible_by_role = {
        "admin": {"operational", "financial", "registration", "maintenance"},
        "operacional": {"operational", "registration", "maintenance"},
        "financeiro": {"financial", "registration"},
        "leitura": {"operational", "registration", "maintenance"},
        "guest": set(),
    }
    visible_categories = set(visible_by_role.get(role, set()))
    if not has_permission(user, "finance.view"):
        visible_categories.discard("financial")

    def event_label(event: dict) -> str:
        return clean_text(event.get("title")) or clean_text(event.get("event_id")) or "Evento sem título"

    def event_href(event: dict) -> str:
        event_id = clean_text(event.get("event_id"))
        return f"#event-{event_id}" if event_id else "#events-pane"

    def client_label(client: dict | None, fallback: str = "Cliente") -> str:
        client = client or {}
        return clean_text(client.get("customer_name")) or clean_text(client.get("client_id")) or fallback

    def item_date(*values: str) -> str:
        for value in values:
            text = clean_text(value)
            if text:
                return text
        return ""

    def quantity_value(client: dict) -> float:
        return parse_decimal(client.get("equipment_quantity"))

    items: list[dict] = []

    def add_item(
        *,
        category: str,
        severity: str,
        title: str,
        description: str,
        affected: str,
        action: str,
        target_href: str,
        target_tab: str,
        related_date: str = "",
        responsible: str = "",
        source: str = "",
    ) -> None:
        if category not in category_meta:
            return
        severity_key = severity if severity in severity_meta else "atencao"
        category_info = category_meta[category]
        severity_info = severity_meta[severity_key]
        items.append(
            {
                "category": category,
                "category_label": category_info["label"],
                "category_short_label": category_info["short_label"],
                "severity": severity_key,
                "severity_label": severity_info["label"],
                "severity_rank": severity_info["rank"],
                "severity_badge_class": severity_info["badge_class"],
                "severity_card_class": severity_info["card_class"],
                "title": title,
                "description": description,
                "affected": affected,
                "action": action,
                "target_href": target_href,
                "target_tab": target_tab,
                "related_date": related_date,
                "related_date_label": format_date_br(related_date[:10]) if related_date else "Sem data",
                "responsible": responsible or "Não informado",
                "source": source,
                "filter_text": " ".join([title, description, affected, category_info["label"], severity_info["label"], responsible or ""]),
            }
        )

    active_events = [
        event for event in events
        if normalize_event_status(event.get("status")) not in {"concluido", "cancelado", "pago"}
    ]
    active_events.sort(key=lambda event: (clean_text(event.get("event_date")), event_label(event)))

    for event in active_events:
        event_id = clean_text(event.get("event_id"))
        linked_clients = [clients_by_id.get(clean_text(client_id), {}) for client_id in event.get("client_ids", []) or []]
        valid_clients = [client for client in linked_clients if client]
        linked_vehicles = [
            vehicles_by_id.get(clean_text(vehicle_id), {})
            for vehicle_id in event.get("vehicle_ids", []) or []
            if vehicles_by_id.get(clean_text(vehicle_id))
        ]
        affected_event = event_label(event)
        responsible = event_responsible_text(event, linked_vehicles)
        related_date = item_date(event.get("event_date"), event.get("created_at"), event.get("updated_at"))
        target_href = event_href(event)

        missing_address = not valid_clients or any(not client_has_valid_address(client) for client in valid_clients)
        if missing_address:
            add_item(
                category="operational",
                severity="critica",
                title="Evento sem endereço",
                description="Falta endereço completo ou coordenada em pelo menos um cliente vinculado.",
                affected=affected_event,
                action="Corrigir endereço",
                target_href="#clients-pane" if valid_clients else target_href,
                target_tab="clients-tab" if valid_clients else "events-tab",
                related_date=related_date,
                responsible=responsible,
                source=event_id,
            )
        if not responsible:
            add_item(
                category="operational",
                severity="atencao",
                title="Evento sem responsável",
                description="Informe quem responde internamente pelo serviço antes de liberar rota, OS ou PDF.",
                affected=affected_event,
                action="Informar responsável",
                target_href=target_href,
                target_tab="events-tab",
                related_date=related_date,
                responsible="Não informado",
                source=event_id,
            )
        if not valid_clients or any(not clean_text(client.get("equipment_type") or client.get("equipment_number")) for client in valid_clients):
            add_item(
                category="operational",
                severity="critica",
                title="Evento sem equipamento",
                description="Defina banheiro, trailer, climatizador, hidratação ou outro serviço no cliente/evento.",
                affected=affected_event,
                action="Corrigir equipamento",
                target_href="#clients-pane" if valid_clients else target_href,
                target_tab="clients-tab" if valid_clients else "events-tab",
                related_date=related_date,
                responsible=responsible,
                source=event_id,
            )
        if valid_clients and any(quantity_value(client) <= 0 for client in valid_clients):
            add_item(
                category="operational",
                severity="critica",
                title="Evento sem quantidade",
                description="Informe quantidade maior que zero para o serviço/equipamento.",
                affected=affected_event,
                action="Corrigir quantidade",
                target_href="#clients-pane",
                target_tab="clients-tab",
                related_date=related_date,
                responsible=responsible,
                source=event_id,
            )
        if not event.get("vehicle_ids"):
            add_item(
                category="operational",
                severity="critica",
                title="Rota sem veículo",
                description="Vincule pelo menos um veículo antes de gerar a rota operacional.",
                affected=affected_event,
                action="Definir veículo",
                target_href=target_href,
                target_tab="events-tab",
                related_date=related_date,
                responsible=responsible,
                source=event_id,
            )
        elif not event_responsible_text(event, linked_vehicles):
            add_item(
                category="operational",
                severity="atencao",
                title="Rota sem motorista",
                description="Os veículos vinculados não têm motorista ou responsável informado.",
                affected=affected_event,
                action="Corrigir frota",
                target_href="#fleet-pane",
                target_tab="fleet-tab",
                related_date=related_date,
                responsible="Não informado",
                source=event_id,
            )
        if event_id and event_id not in generated_service_order_event_ids:
            add_item(
                category="operational",
                severity="atencao",
                title="Ordem de serviço não gerada",
                description="A auditoria ainda não registrou geração de OS para este evento.",
                affected=affected_event,
                action="Gerar OS",
                target_href=url_for("download_service_order", event_id=event_id),
                target_tab="",
                related_date=related_date,
                responsible=responsible,
                source=event_id,
            )
        if event_financial_value(event, clients_by_id) <= 0:
            add_item(
                category="financial",
                severity="critica",
                title="Evento sem valor",
                description="O evento não tem valor previsto para cobrança ou controle gerencial.",
                affected=affected_event,
                action="Registrar valor",
                target_href=target_href,
                target_tab="events-tab",
                related_date=related_date,
                responsible=responsible,
                source=event_id,
            )
        event_start = event_start_date(event)
        performed_status = normalize_event_status(event.get("status")) in {"confirmado", "programado", "em_andamento", "concluido"}
        if event_id and performed_status and event_start and event_start <= today and event_financial_value(event, clients_by_id) > 0 and event_id not in linked_receivable_event_ids:
            add_item(
                category="financial",
                severity="atencao",
                title="Locação realizada sem lançamento financeiro",
                description="Há valor previsto, mas nenhuma conta a receber vinculada ao evento.",
                affected=affected_event,
                action="Lançar cobrança",
                target_href="#receivables-panel",
                target_tab="summary-tab",
                related_date=related_date,
                responsible=responsible,
                source=event_id,
            )

    for event in events:
        event_id = clean_text(event.get("event_id"))
        if normalize_event_status(event.get("status")) != "concluido":
            continue
        event_start = event_start_date(event)
        if not event_id or not event_start or event_start > today:
            continue
        if event_financial_value(event, clients_by_id) <= 0 or event_id in linked_receivable_event_ids:
            continue
        linked_vehicle_ids = {clean_text(vehicle_id) for vehicle_id in event.get("vehicle_ids", []) or []}
        linked_vehicles = [vehicle for vehicle in vehicles if clean_text(vehicle.get("vehicle_id")) in linked_vehicle_ids]
        add_item(
            category="financial",
            severity="atencao",
            title="Locação realizada sem lançamento financeiro",
            description="Evento concluído com valor previsto e sem conta a receber vinculada.",
            affected=event_label(event),
            action="Lançar cobrança",
            target_href="#receivables-panel",
            target_tab="summary-tab",
            related_date=item_date(event.get("event_date"), event.get("updated_at")),
            responsible=event_responsible_text(event, linked_vehicles),
            source=event_id,
        )

    client_open_amounts: dict[str, dict] = {}
    for receivable in financial_receivables:
        open_amount = receivable_open_amount(receivable)
        if receivable_is_paid(receivable) or open_amount <= 0:
            continue
        due_date = parse_date(receivable.get("due_date"))
        due_text = clean_text(receivable.get("due_date"))
        client_key = clean_text(receivable.get("client_id")) or clean_text(receivable.get("client_name")) or "cliente-sem-id"
        client_name = clean_text(receivable.get("client_name")) or client_label(clients_by_id.get(client_key), "Cliente não informado")
        if clean_text(receivable.get("status")).lower() == "vencido" or (due_date and due_date < today):
            add_item(
                category="financial",
                severity="critica",
                title="Recebimento vencido",
                description=f"Cobrança em aberto de {format_currency_br(open_amount)}.",
                affected=client_name,
                action="Baixar recebimento",
                target_href="#receivables-panel",
                target_tab="summary-tab",
                related_date=due_text,
                responsible=clean_text(receivable.get("responsible") or receivable.get("created_by")),
                source=clean_text(receivable.get("id")),
            )
        bucket = client_open_amounts.setdefault(
            client_key,
            {"client_name": client_name, "amount": 0.0, "count": 0, "oldest_due": due_text, "responsible": ""},
        )
        bucket["amount"] += open_amount
        bucket["count"] += 1
        bucket["responsible"] = bucket["responsible"] or clean_text(receivable.get("responsible") or receivable.get("created_by"))
        if due_text and (not bucket["oldest_due"] or due_text < bucket["oldest_due"]):
            bucket["oldest_due"] = due_text

    for bucket in sorted(client_open_amounts.values(), key=lambda item: item["amount"], reverse=True)[:12]:
        add_item(
            category="financial",
            severity="atencao",
            title="Cliente com cobrança em aberto",
            description=f"{bucket['count']} cobrança(s) em aberto somando {format_currency_br(bucket['amount'])}.",
            affected=bucket["client_name"],
            action="Abrir cobrança",
            target_href="#receivables-panel",
            target_tab="summary-tab",
            related_date=bucket.get("oldest_due", ""),
            responsible=bucket.get("responsible", ""),
            source=bucket["client_name"],
        )

    for client in clients:
        client_name = client_label(client)
        if not clean_text(client.get("phone")):
            add_item(
                category="registration",
                severity="atencao",
                title="Cliente sem telefone",
                description="Sem telefone, a equipe não consegue confirmar operação ou cobrança com segurança.",
                affected=client_name,
                action="Editar cliente",
                target_href="#clients-pane",
                target_tab="clients-tab",
                related_date=item_date(client.get("created_at"), client.get("updated_at")),
                responsible=clean_text(client.get("contact_name")),
                source=clean_text(client.get("client_id")),
            )
        requires_document = (
            clean_text(client.get("invoice_status")) == "com_nota"
            or clean_text(client.get("billing_model")) == "mensal"
            or clean_text(client.get("client_type")) == "fixo"
        )
        if requires_document and not clean_text(client.get("cpf_cnpj")):
            add_item(
                category="registration",
                severity="baixa",
                title="Cliente sem CNPJ/CPF quando necessário",
                description="Complete o documento para emissão, contrato mensal ou controle fiscal.",
                affected=client_name,
                action="Editar cadastro",
                target_href="#clients-pane",
                target_tab="clients-tab",
                related_date=item_date(client.get("created_at"), client.get("updated_at")),
                responsible=clean_text(client.get("contact_name")),
                source=clean_text(client.get("client_id")),
            )
        if not client_has_valid_address(client):
            add_item(
                category="registration",
                severity="critica",
                title="Cliente sem endereço",
                description="Endereço ou coordenadas ausentes impedem rota e entrega correta.",
                affected=client_name,
                action="Corrigir endereço",
                target_href="#clients-pane",
                target_tab="clients-tab",
                related_date=item_date(client.get("created_at"), client.get("updated_at")),
                responsible=clean_text(client.get("contact_name")),
                source=clean_text(client.get("client_id")),
            )

    for item in equipment:
        equipment_id = clean_text(item.get("equipment_id")) or "Equipamento sem ID"
        raw_item = raw_equipment_by_id.get(clean_text(item.get("equipment_id")), item)
        status = clean_text(raw_item.get("status") or raw_item.get("condition"))
        affected = f"{equipment_id} • {clean_text(item.get('equipment_type'), 'Equipamento')}"
        if not status:
            add_item(
                category="registration",
                severity="atencao",
                title="Equipamento sem status",
                description="Defina se o equipamento está disponível, reservado, em rota, manutenção ou retorno pendente.",
                affected=affected,
                action="Editar equipamento",
                target_href="#fleet-pane",
                target_tab="fleet-tab",
                related_date=item_date(raw_item.get("created_at"), raw_item.get("updated_at"), item.get("created_at"), item.get("updated_at")),
                responsible="",
                source=equipment_id,
            )
        normalized_status = normalize_equipment_status(status)
        maintenance_reason = clean_text(raw_item.get("maintenance_reason") or item.get("maintenance_reason"))
        if normalized_status in {"manutencao", "indisponivel"} or maintenance_reason:
            add_item(
                category="maintenance",
                severity="atencao",
                title="Equipamento em manutenção",
                description=maintenance_reason or "Equipamento bloqueado para operação.",
                affected=affected,
                action="Revisar manutenção",
                target_href="#maintenance-panel",
                target_tab="fleet-tab",
                related_date=item_date(raw_item.get("maintenance_expected_release"), raw_item.get("maintenance_started_at"), raw_item.get("updated_at"), item.get("updated_at")),
                responsible=clean_text(raw_item.get("responsible") or raw_item.get("responsavel") or item.get("responsible") or item.get("responsavel")),
                source=equipment_id,
            )
        if normalized_status in {"retirada_pendente", "retornado", "instalado"}:
            add_item(
                category="maintenance",
                severity="critica" if normalized_status == "retirada_pendente" else "atencao",
                title="Equipamento com retorno pendente",
                description="Confirme retorno ou libere o equipamento para disponibilidade.",
                affected=affected,
                action="Confirmar retorno",
                target_href="#fleet-pane",
                target_tab="fleet-tab",
                related_date=item_date(item.get("returned_at"), item.get("updated_at")),
                responsible=clean_text(item.get("responsible") or item.get("responsavel")),
                source=equipment_id,
            )

    for vehicle in vehicles:
        vehicle_id = clean_text(vehicle.get("vehicle_id")) or "Veículo sem ID"
        missing_fields = [
            label for label, value in (
                ("tipo", vehicle.get("vehicle_type")),
                ("placa", vehicle.get("plate")),
                ("capacidade", vehicle.get("capacity")),
            )
            if not clean_text(str(value) if value is not None else "")
        ]
        if missing_fields:
            add_item(
                category="maintenance",
                severity="atencao",
                title="Veículo sem informação básica",
                description=f"Complete {', '.join(missing_fields)} para evitar erro na operação.",
                affected=vehicle_id,
                action="Editar frota",
                target_href="#fleet-pane",
                target_tab="fleet-tab",
                related_date=item_date(vehicle.get("created_at"), vehicle.get("updated_at")),
                responsible=clean_text(vehicle.get("driver") or vehicle.get("motorista") or vehicle.get("responsible")),
                source=vehicle_id,
            )

    visible_items = [item for item in items if item["category"] in visible_categories]
    visible_items.sort(key=lambda item: (item["severity_rank"], item["category"], item["related_date"] or "9999-99-99", item["affected"]))
    grouped = []
    for key, meta in category_meta.items():
        category_items = [item for item in visible_items if item["category"] == key]
        if key in visible_categories:
            grouped.append({**meta, "key": key, "items": category_items, "count": len(category_items)})

    category_options = [
        {"key": group["key"], "label": group["short_label"], "count": group["count"]}
        for group in grouped
    ]
    severity_options = [
        {"key": key, "label": meta["label"], "count": sum(1 for item in visible_items if item["severity"] == key)}
        for key, meta in severity_meta.items()
    ]
    return {
        "items": visible_items,
        "groups": grouped,
        "category_options": category_options,
        "severity_options": severity_options,
        "total": len(visible_items),
        "critical_total": sum(1 for item in visible_items if item["severity"] == "critica"),
        "attention_total": sum(1 for item in visible_items if item["severity"] == "atencao"),
        "low_total": sum(1 for item in visible_items if item["severity"] == "baixa"),
        "all_total": len(items),
        "visible_categories": sorted(visible_categories),
        "prepared_for_future": [
            "Rota sem motorista usa motorista/responsável do veículo ou do evento enquanto não existir uma escala dedicada.",
            "Ordem de serviço não gerada usa auditoria de geração de OS enquanto não existir tabela própria de documentos.",
            "Locação realizada sem lançamento financeiro usa vínculo evento-conta a receber enquanto a migração para SQLite não estiver ativa.",
        ],
    }


def build_guided_operation_flow(
    *,
    clients: list[dict],
    events: list[dict],
    vehicles: list[dict],
    equipment: list[dict],
    route_data: dict | None,
    has_pdf: bool,
    last_backup_at: str,
    can_backup: bool = False,
) -> dict:
    event_has_equipment = any(
        any(client.get("client_id") in event.get("client_ids", []) and clean_text(client.get("equipment_number")) for client in clients)
        for event in events
    )
    steps = [
        {
            "label": "Cliente",
            "status": "ready" if clients else "pending",
            "detail": "Cliente cadastrado" if clients else "Crie o primeiro cliente com endereço completo.",
            "target_tab": "clients-tab",
            "target_href": "#clients-pane",
            "action": "Abrir clientes",
        },
        {
            "label": "Locação/evento",
            "status": "ready" if events else "pending",
            "detail": "Evento cadastrado" if events else "Crie uma locação com data, cliente e tipo de serviço.",
            "target_tab": "events-tab",
            "target_href": "#events-pane",
            "action": "Abrir eventos",
        },
        {
            "label": "Equipamento",
            "status": "ready" if event_has_equipment else "attention" if equipment else "pending",
            "detail": "Equipamento vinculado" if event_has_equipment else "Vincule um equipamento ao cliente/evento.",
            "target_tab": "fleet-tab",
            "target_href": "#fleet-pane",
            "action": "Abrir equipamentos",
        },
        {
            "label": "Veículo",
            "status": "ready" if vehicles else "pending",
            "detail": "Veículo disponível" if vehicles else "Cadastre ao menos um veículo para roteirização.",
            "target_tab": "fleet-tab",
            "target_href": "#fleet-pane",
            "action": "Abrir frota",
        },
        {
            "label": "Rota",
            "status": "ready" if route_data and route_data.get("routes") else "pending",
            "detail": "Rota gerada" if route_data and route_data.get("routes") else "Valide dados e gere a rota.",
            "target_tab": "operations-tab",
            "target_href": "#operations-pane",
            "action": "Gerar rota",
        },
        {
            "label": "PDF/OS",
            "status": "ready" if has_pdf else "attention" if events else "pending",
            "detail": "PDF/OS pronto para conferência" if has_pdf else "Baixe a OS ou gere o PDF da rota.",
            "target_tab": "operations-tab",
            "target_href": "#operations-pane",
            "action": "Abrir PDFs",
        },
        {
            "label": "Backup",
            "status": "ready" if last_backup_at else "attention",
            "detail": "Backup recente registrado" if last_backup_at else "Gere backup antes de liberar uso diário.",
            "target_tab": "" if can_backup else "summary-tab",
            "target_href": url_for("download_system_backup") if can_backup else "#system-readiness-panel",
            "action": "Gerar backup" if can_backup else "Ver status",
        },
    ]
    return {
        "steps": steps,
        "ready": sum(1 for step in steps if step["status"] == "ready"),
        "total": len(steps),
        "pending": sum(1 for step in steps if step["status"] != "ready"),
    }


def build_team_enablement_guide(*, can_view_finance: bool, can_manage_access: bool) -> dict:
    role_paths = [
        {
            "role": "Operação",
            "start": "Central do Dia",
            "focus": "Eventos, banheiros, frota, equipamentos, rota, PDF e links de endereço.",
            "target_tab": "summary-tab",
            "target_href": "#central-day-panel",
        },
        {
            "role": "Administrativo",
            "start": "Clientes e Eventos",
            "focus": "Cadastro completo, documentos, observações úteis e fechamento administrativo.",
            "target_tab": "clients-tab",
            "target_href": "#clients-pane",
        },
        {
            "role": "Almoxarifado",
            "start": "Estoque",
            "focus": "Entrada, baixa, estoque baixo, itens zerados e materiais para limpeza.",
            "target_tab": "warehouse-tab",
            "target_href": "#warehouse-pane",
        },
    ]
    if can_view_finance:
        role_paths.append(
            {
                "role": "Financeiro",
                "start": "Financeiro",
                "focus": "Recebimentos, vencidos, notas, comprovantes, fluxo de caixa e fechamento mensal.",
                "target_tab": "summary-tab",
                "target_href": "#finance-overview",
            }
        )
    if can_manage_access:
        role_paths.append(
            {
                "role": "Administrador",
                "start": "Acessos",
                "focus": "Usuários, permissões, senhas pendentes, backup, segurança e homologação.",
                "target_tab": "access-tab",
                "target_href": "#access-pane",
            }
        )

    return {
        "role_paths": role_paths,
        "daily_order": [
            "Abrir Central do Dia e resolver pendências vermelhas primeiro.",
            "Criar ou revisar cliente, evento, banheiro/equipamento e veículo.",
            "Validar operação antes de gerar rota.",
            "Gerar PDF, ordem de serviço e links de endereço quando houver despacho.",
            "Registrar pagamentos, manutenção, ajustes internos, fechamento e backup.",
        ],
        "language_rules": [
            {"term": "Banheiros", "use": "Produto principal da operação."},
            {"term": "Equipamentos", "use": "Apoio ou ativo operacional, como climatizador e hidratação."},
            {"term": "Retirada", "use": "Use para recolhimento do banheiro/equipamento no cliente."},
            {"term": "Recebimento", "use": "Use no financeiro para pagamento do cliente."},
            {"term": "Pendência", "use": "Algo que precisa de ação antes de liberar ou fechar."},
        ],
        "minimum_records": [
            {"record": "Cliente", "fields": "Nome, telefone, endereço, contato, tipo de serviço e cobrança."},
            {"record": "Evento", "fields": "Data, período, clientes, status, checklist e observações úteis."},
            {"record": "Banheiro/equipamento", "fields": "ID, tipo, status, placa quando houver, foto e manutenção."},
            {"record": "Financeiro", "fields": "Cliente, valor, vencimento, status, NF e comprovante quando existir."},
        ],
        "print_package": [
            "PDF da rota ou ordem de serviço.",
            "Endereço completo e link do Google Maps quando ajudar.",
            "Contato do cliente e horário combinado.",
            "Banheiros/equipamentos, quantidade, ID interno e placa quando houver.",
            "Observações que realmente precisam chegar a quem executa.",
        ],
        "guardrails": [
            "Pesquisar antes de cadastrar para evitar duplicidade.",
            "Não liberar rota com bloqueio vermelho.",
            "Não usar equipamento indisponível ou em manutenção.",
            "Registrar recebimento no financeiro no mesmo dia em que confirmar pagamento.",
            "Usar um acesso por pessoa para manter histórico e responsabilidade claros.",
        ],
    }


def client_completion_warnings(record: dict) -> list[str]:
    warnings = []
    if not clean_text(record.get("phone")):
        warnings.append("falta telefone para contato rápido")
    if not clean_text(record.get("contact_name")):
        warnings.append("falta nome do contato")
    if not clean_text(record.get("cpf_cnpj")):
        warnings.append("CPF/CNPJ ainda não foi informado")
    if not clean_text(record.get("equipment_type")):
        warnings.append("tipo de banheiro/equipamento não foi preenchido")
    if parse_decimal(record.get("service_value")) <= 0:
        warnings.append("valor do serviço ainda está zerado")
    if not clean_text(record.get("invoice_number")) and clean_text(record.get("invoice_status"), "sem_nota") == "com_nota":
        warnings.append("nota marcada como emitida sem número de NF")
    return warnings[:4]


def event_completion_warnings(record: dict) -> list[str]:
    warnings = []
    if not record.get("client_ids"):
        warnings.append("nenhum cliente vinculado")
    if not record.get("vehicle_ids"):
        warnings.append("nenhum veículo vinculado")
    if any(not item.get("done") for item in record.get("checklist", [])):
        warnings.append("checklist ainda possui itens pendentes")
    if parse_decimal(record.get("valor_servico")) <= 0 and parse_decimal(record.get("recurring_value")) <= 0:
        warnings.append("financeiro do evento ainda está zerado")
    if not clean_text(record.get("notes")):
        warnings.append("observações do evento estão vazias")
    return warnings[:4]


def build_event_risk_scores(
    events: list[dict],
    clients: list[dict],
    financial_management: dict,
    route_data: dict | None,
    has_pdf: bool,
) -> list[dict]:
    today = datetime.now().date()
    route_event_id = clean_text((route_data or {}).get("event_id"))
    clients_by_id = {clean_text(client.get("client_id")): client for client in clients}
    receivables_by_event: dict[str, list[dict]] = {}
    for item in financial_management.get("receivables", []):
        event_id = clean_text(item.get("event_id"))
        if event_id:
            receivables_by_event.setdefault(event_id, []).append(item)

    rows = []
    for event in events:
        normalized_status = normalize_event_status(event.get("status"))
        if normalized_status in {"pago", "cancelado"}:
            continue
        event_id = clean_text(event.get("event_id"))
        score = 0
        reasons = []
        event_date = parse_date(event.get("event_date"))
        days_until = (event_date - today).days if event_date else None

        if not event.get("client_ids"):
            score += 25
            reasons.append("sem cliente")
        if not event.get("vehicle_ids"):
            score += 15
            reasons.append("sem veículo")
        linked_clients = [clients_by_id.get(clean_text(client_id), {}) for client_id in event.get("client_ids", [])]
        missing_contact = [client for client in linked_clients if not clean_text(client.get("phone")) or not clean_text(client.get("address"))]
        if missing_contact:
            score += 10
            reasons.append(f"{len(missing_contact)} cliente(s) com contato/endereço incompleto")
        checklist = event.get("checklist") or []
        if checklist and any(not item.get("done") for item in checklist):
            score += 15
            reasons.append("checklist pendente")
        if days_until is not None and 0 <= days_until <= 3 and not (has_pdf and route_event_id == event_id):
            score += 20
            reasons.append("evento próximo sem PDF da rota")
        open_receivables = [
            item for item in receivables_by_event.get(event_id, [])
            if clean_text(item.get("status")) != "pago"
        ]
        if open_receivables and normalized_status in {"concluido", "aguardando_pagamento", "em_andamento"}:
            score += 20
            reasons.append("financeiro aberto")
        if normalized_status == "concluido" and open_receivables:
            score += 15
            reasons.append("concluído sem recebimento total")

        label = "Baixo"
        level = "ready"
        if score >= 60:
            label = "Alto"
            level = "danger"
        elif score >= 30:
            label = "Médio"
            level = "warning"
        rows.append({
            "event_id": event_id,
            "title": clean_text(event.get("title")) or event_id,
            "score": score,
            "label": label,
            "level": level,
            "date": clean_text(event.get("event_date")),
            "days_until": days_until,
            "reasons": reasons or ["sem risco relevante"],
            "target_tab": "events-tab",
            "target_href": f"#event-{event_id}",
        })
    rows.sort(key=lambda item: item["score"], reverse=True)
    return rows[:8]


def build_stock_usage_forecast(warehouse_dashboard: dict) -> list[dict]:
    today = datetime.now().date()
    cutoff = today - timedelta(days=30)
    movements_by_item: dict[str, float] = {}
    for movement in warehouse_dashboard.get("movements") or []:
        movement_type = clean_text(movement.get("movement_type"))
        created_at = clean_text(movement.get("created_at"))
        try:
            movement_date = datetime.fromisoformat(created_at).date() if created_at else today
        except ValueError:
            movement_date = today
        if movement_date < cutoff:
            continue
        if movement_type in {"saida", "baixa limpeza"}:
            item_id = clean_text(movement.get("item_id"))
            movements_by_item[item_id] = movements_by_item.get(item_id, 0.0) + parse_decimal(movement.get("quantity_changed"))

    rows = []
    for item in warehouse_dashboard.get("items") or []:
        item_id = clean_text(item.get("id"))
        quantity = parse_decimal(item.get("quantity_current"))
        consumed = movements_by_item.get(item_id, 0.0)
        daily_use = consumed / 30 if consumed > 0 else 0
        days_left = int(quantity / daily_use) if daily_use > 0 else None
        level = "ready"
        label = "Sem consumo recente"
        if item.get("stock_status") == "zerado" or days_left == 0:
            level = "danger"
            label = "Acabou"
        elif days_left is not None and days_left <= 7:
            level = "danger"
            label = f"Pode acabar em {days_left} dia(s)"
        elif item.get("stock_status") == "baixo" or (days_left is not None and days_left <= 15):
            level = "warning"
            label = f"Repor em breve ({days_left} dia(s))" if days_left is not None else "Estoque baixo"
        elif days_left is not None:
            label = f"{days_left} dia(s) estimado(s)"
        rows.append({
            "id": item_id,
            "name": clean_text(item.get("name")) or item_id,
            "quantity": quantity,
            "unit": clean_text(item.get("unit")),
            "daily_use": round2(daily_use),
            "days_left": days_left,
            "label": label,
            "level": level,
        })
    rows.sort(key=lambda item: ({"danger": 0, "warning": 1, "ready": 2}.get(item["level"], 3), item["days_left"] if item["days_left"] is not None else 9999))
    return rows[:8]


def build_event_progress(
    event: dict,
    route_data: dict | None,
    has_pdf: bool,
    can_view_finance: bool,
) -> dict:
    event_id = clean_text(event.get("event_id"))
    status = normalize_event_status(event.get("status"))
    checklist = event.get("checklist") or []
    checklist_done = bool(checklist) and all(bool(item.get("done")) for item in checklist)
    route_event_id = clean_text((route_data or {}).get("event_id"))
    route_ready = bool(has_pdf and route_data and (not route_event_id or route_event_id == event_id))
    financial_summary = event.get("financial_summary") or {}
    has_financial_value = any(
        parse_decimal(event.get(field)) > 0
        for field in ("valor_servico", "valor_adicional", "recurring_value")
    ) or bool(financial_summary)
    finished_statuses = {"concluido", "pago", "cancelado"}
    raw_steps = [
        {
            "key": "cadastro",
            "label": "Cadastro",
            "done": bool(clean_text(event.get("title")) and clean_text(event.get("event_date"))),
            "detail": "Nome e data do evento.",
        },
        {
            "key": "clientes",
            "label": "Clientes",
            "done": bool(event.get("client_ids")),
            "detail": "Cliente(s) ligados ao evento.",
        },
        {
            "key": "banheiros",
            "label": "Banheiros",
            "done": bool(event.get("client_ids") and (event.get("vehicles_count", 0) or event.get("vehicle_ids"))),
            "detail": "Banheiros/equipamentos e veículo definidos.",
        },
        {
            "key": "pdf",
            "label": "Rota/PDF",
            "done": route_ready,
            "detail": "Rota, OS ou PDF pronto para conferência.",
        },
        {
            "key": "financeiro",
            "label": "Financeiro",
            "done": has_financial_value or not can_view_finance,
            "detail": "Valores, cobrança ou resumo financeiro.",
        },
        {
            "key": "fechamento",
            "label": "Fechamento",
            "done": status in finished_statuses and checklist_done,
            "detail": "Status final e checklist revisado.",
        },
    ]
    first_open_index = next((index for index, step in enumerate(raw_steps) if not step["done"]), None)
    steps = []
    for index, step in enumerate(raw_steps):
        state = "done" if step["done"] else "current" if index == first_open_index else "pending"
        steps.append({**step, "state": state})

    missing_actions = []
    if not raw_steps[0]["done"]:
        missing_actions.append({"label": "Completar cadastro", "target_tab": "events-tab", "target_href": "#event-create-panel", "highlight_target": "#event-form"})
    if not raw_steps[1]["done"]:
        missing_actions.append({"label": "Vincular cliente", "target_tab": "events-tab", "target_href": "#event-create-panel", "highlight_target": "#event_client_ids"})
    if not raw_steps[2]["done"]:
        missing_actions.append({"label": "Definir veículos", "target_tab": "events-tab", "target_href": "#event-create-panel", "highlight_target": "#event_vehicle_ids"})
    if not raw_steps[3]["done"]:
        missing_actions.append({"label": "Gerar PDF/OS", "target_tab": "operations-tab", "target_href": "#operations-pane", "highlight_target": "#gerador"})
    if not raw_steps[4]["done"]:
        missing_actions.append({"label": "Registrar valor", "target_tab": "events-tab", "target_href": "#event-create-panel", "highlight_target": "#valor_servico"})
    if not raw_steps[5]["done"]:
        missing_actions.append({"label": "Revisar checklist", "target_tab": "events-tab", "target_href": f"#event-{event_id}", "highlight_target": f"#event-{event_id}"})
    percent = int(round((sum(1 for step in raw_steps if step["done"]) / max(len(raw_steps), 1)) * 100))
    return {
        "steps": steps,
        "missing_actions": missing_actions[:3],
        "percent": percent,
        "label": f"{percent}% pronto",
    }


def build_event_timeline(
    event: dict,
    linked_clients: list[dict],
    linked_vehicles: list[dict],
    route_data: dict | None,
    has_pdf: bool,
    can_view_finance: bool,
) -> list[dict]:
    event_id = clean_text(event.get("event_id"))
    route_event_id = clean_text((route_data or {}).get("event_id"))
    route_ready = bool(has_pdf and route_data and (not route_event_id or route_event_id == event_id))
    financial_summary = event.get("financial_summary") or {}
    has_financial_value = any(
        parse_decimal(event.get(field)) > 0
        for field in ("valor_servico", "valor_adicional", "recurring_value")
    ) or bool(financial_summary)
    checklist = event.get("checklist") or []
    checklist_done = bool(checklist) and all(bool(item.get("done")) for item in checklist)

    return [
        {
            "label": "1. Cadastro",
            "detail": "Nome e data preenchidos." if clean_text(event.get("title")) and clean_text(event.get("event_date")) else "Falta nome ou data.",
            "level": "ready" if clean_text(event.get("title")) and clean_text(event.get("event_date")) else "danger",
        },
        {
            "label": "2. Cliente",
            "detail": f"{len(linked_clients)} cliente(s) vinculado(s)." if linked_clients else "Vincule pelo menos um cliente.",
            "level": "ready" if linked_clients else "warning",
        },
        {
            "label": "3. Banheiros e frota",
            "detail": f"{len(linked_vehicles)} veículo(s) e {event.get('equipment_count', 0)} banheiro(s)/equipamento(s).",
            "level": "ready" if linked_vehicles or event.get("equipment_count") else "warning",
        },
        {
            "label": "4. PDF/impresso",
            "detail": "Rota ou OS pronta para conferir." if route_ready else "Gere ou revise a OS antes de imprimir.",
            "level": "ready" if route_ready else "warning",
        },
        {
            "label": "5. Financeiro",
            "detail": "Valor ou resumo financeiro registrado." if has_financial_value or not can_view_finance else "Inclua valor/cobrança quando aplicável.",
            "level": "ready" if has_financial_value or not can_view_finance else "info",
        },
        {
            "label": "6. Fechamento",
            "detail": "Checklist do evento revisado." if checklist_done else "Revise o checklist antes de finalizar.",
            "level": "ready" if checklist_done else "info",
        },
    ]


def build_smart_system_dashboard(
    *,
    attention_center: dict,
    preventive_warnings: list[dict],
    financial_management: dict,
    general_improvements: dict,
    future_dashboard: dict,
    warehouse_dashboard: dict,
    reports_hub: list[dict],
    dispatch_today: dict,
    global_search_items: list[dict],
    customer_history: list[dict],
    recent_audit_log: list[dict],
    clients: list[dict],
    events: list[dict],
    contracts: list[dict],
    cleaning_agenda: list[dict],
    maintenance_preventive_dashboard: dict,
    route_data: dict | None,
    has_pdf: bool,
    can_view_finance: bool,
    user_role: str,
) -> dict:
    def badge_level(level: str) -> str:
        normalized = criticality_key(level)
        if normalized == "block":
            return "danger"
        if normalized == "attention":
            return "warning"
        if normalized == "ready":
            return "ready"
        return "info"

    next_steps = []
    for item in attention_center.get("items", [])[:6]:
        next_steps.append({
            "level": badge_level(item.get("level")),
            "title": clean_text(item.get("title")),
            "detail": clean_text(item.get("detail")),
            "target_tab": clean_text(item.get("target_tab")),
            "target_href": clean_text(item.get("target_href"), "#summary-pane"),
            "action": clean_text(item.get("action"), "Abrir"),
        })
    if not next_steps:
        next_steps.append({
            "level": "ready",
            "title": "Operação sem bloqueio crítico",
            "detail": "Use o roteiro rápido para preparar o próximo despacho ou fechamento.",
            "target_tab": "summary-tab",
            "target_href": "#guided-operation-flow",
            "action": "Ver roteiro",
        })

    preventive_items = []
    for item in preventive_warnings[:5]:
        preventive_items.append({
            "level": badge_level(item.get("level")),
            "title": clean_text(item.get("title")),
            "detail": clean_text(item.get("detail")),
            "target_tab": clean_text(item.get("target_tab"), "summary-tab"),
            "target_href": clean_text(item.get("target_href"), "#summary-pane"),
        })
    for item in maintenance_preventive_dashboard.get("alerts", [])[:3]:
        preventive_items.append({
            "level": "warning" if clean_text(item.get("level")) != "danger" else "danger",
            "title": f"Manutenção preventiva: {clean_text(item.get('equipment_id'))}",
            "detail": clean_text(item.get("message")),
            "target_tab": "fleet-tab",
            "target_href": "#maintenance-panel",
        })
    if can_view_finance:
        for item in financial_management.get("alerts", [])[:3]:
            preventive_items.append({
                "level": "danger" if clean_text(item.get("level")) == "danger" else "warning",
                "title": f"Financeiro: {clean_text(item.get('scope'), 'alerta')}",
                "detail": clean_text(item.get("message")),
                "target_tab": "summary-tab",
                "target_href": "#receivables-panel",
            })
    preventive_items = preventive_items[:8]
    if not preventive_items:
        preventive_items.append({
            "level": "ready",
            "title": "Sem alerta preventivo aberto",
            "detail": "Estoque, operação, financeiro e manutenção não têm alerta prioritário agora.",
            "target_tab": "summary-tab",
            "target_href": "#attention-now-panel",
        })

    validation_items = [
        {
            "level": badge_level(item.get("level")),
            "label": clean_text(item.get("label")),
            "detail": clean_text(item.get("detail")),
            "target_tab": clean_text(item.get("target_tab")),
            "target_href": clean_text(item.get("target_href")),
            "action": clean_text(item.get("action")),
        }
        for item in dispatch_today.get("checklist", [])
    ]

    clients_by_id = {clean_text(client.get("client_id")): client for client in clients}
    financial_by_client = {
        clean_text(item.get("client_id")) or clean_text(item.get("client_name")): item
        for item in financial_management.get("client_finance", [])
    }
    client_insights = []
    for item in sorted(customer_history, key=lambda row: (row.get("routes_count", 0), row.get("revenue_total", 0)), reverse=True)[:6]:
        client_id = clean_text(item.get("client_id"))
        client = clients_by_id.get(client_id, {})
        finance = financial_by_client.get(client_id) or financial_by_client.get(clean_text(item.get("customer_name"))) or {}
        next_action = "Manter histórico atualizado"
        if not clean_text(client.get("phone")):
            next_action = "Completar telefone"
        elif not clean_text(client.get("address")):
            next_action = "Completar endereço"
        elif can_view_finance and float(finance.get("open") or 0) > 0:
            next_action = "Ver cobrança aberta"
        elif item.get("routes_count", 0) == 0:
            next_action = "Criar primeira locação"
        client_insights.append({
            "client_id": client_id,
            "name": clean_text(item.get("customer_name")) or client_id,
            "detail": f"{item.get('routes_count', 0)} rota(s) • último atendimento {format_datetime_br(item.get('last_route_at'))}",
            "finance": f"aberto {format_currency_br(finance.get('open'))}" if can_view_finance and finance else "",
            "next_action": next_action,
            "target_tab": "clients-tab",
            "target_href": f"#client-{client_id}",
        })
    if not client_insights:
        client_insights.append({
            "client_id": "",
            "name": "Sem histórico suficiente",
            "detail": "Cadastre clientes e gere rotas para formar recomendações por cliente.",
            "finance": "",
            "next_action": "Cadastrar cliente",
            "target_tab": "clients-tab",
            "target_href": "#clients-pane",
        })

    financial_recommendations = []
    if can_view_finance:
        overdue = financial_management.get("overdue", [])
        due_soon = financial_management.get("receivables_due_soon", [])
        if overdue:
            financial_recommendations.append({
                "level": "danger",
                "title": "Cobrar vencidos",
                "detail": f"{len(overdue)} cobrança(s) vencida(s), maior atraso: {overdue[0].get('days_overdue', 0)} dia(s).",
                "target": "#receivables-panel",
            })
        if due_soon:
            financial_recommendations.append({
                "level": "warning",
                "title": "Cobranças vencendo",
                "detail": f"{len(due_soon)} recebimento(s) vencem hoje ou nos próximos 3 dias.",
                "target": "#receivables-panel",
            })
        invoice_pending = financial_management.get("invoice_summary", {}).get("sem_nota", 0)
        if invoice_pending:
            financial_recommendations.append({
                "level": "warning",
                "title": "Notas fiscais pendentes",
                "detail": f"{invoice_pending} cobrança(s) sem número de NF informado.",
                "target": "#taxes-panel",
            })
        margin_pct = float(financial_management.get("dre", {}).get("margin_pct") or 0)
        if margin_pct < 15 and (financial_management.get("dre", {}).get("gross_revenue") or 0) > 0:
            financial_recommendations.append({
                "level": "warning",
                "title": "Margem baixa",
                "detail": f"Margem do período em {margin_pct:.2f}%. Revise custos, descontos e despesas.",
                "target": "#financial-reports-panel",
            })
        if not financial_recommendations:
            financial_recommendations.append({
                "level": "ready",
                "title": "Financeiro sem alerta imediato",
                "detail": "Vencidos, notas e margem não exigem ação prioritária agora.",
                "target": "#finance-overview",
            })
    else:
        financial_recommendations.append({
            "level": "info",
            "title": "Financeiro protegido",
            "detail": "As recomendações financeiras aparecem apenas para quem tem permissão.",
            "target": "#summary-pane",
        })

    forecast_cards = []
    for level_item in future_dashboard.get("alerts", [])[:3]:
        forecast_cards.append({
            "level": "danger" if clean_text(level_item.get("level")) == "danger" else "warning",
            "title": clean_text(level_item.get("scope"), "Previsão"),
            "detail": clean_text(level_item.get("message")),
        })
    top_months = future_dashboard.get("prediction", {}).get("top_months", [])
    if top_months:
        month, count = top_months[0]
        forecast_cards.append({
            "level": "info",
            "title": "Mês mais recorrente no histórico",
            "detail": f"{month}: {count} operação(ões) registradas.",
        })
    dates_almost_full = future_dashboard.get("commercial", {}).get("dates_almost_full", [])
    if dates_almost_full:
        forecast_cards.append({
            "level": "warning",
            "title": "Capacidade futura apertada",
            "detail": f"{dates_almost_full[0].get('period_key')} com {dates_almost_full[0].get('utilization_pct')}% de ocupação projetada.",
        })
    if not forecast_cards:
        forecast_cards.append({
            "level": "info",
            "title": "Previsão em aprendizado",
            "detail": "O sistema usará histórico de eventos, rotas e recorrências para destacar demanda futura.",
        })

    dynamic_checklists = [
        {
            "label": "Evento avulso",
            "status": "ready" if dispatch_today.get("ready_count", 0) >= 3 else "warning",
            "items": ["cliente confirmado", "banheiros separados", "rota validada", "PDF ou OS conferido", "financeiro registrado"],
            "target_tab": "events-tab",
            "target_href": "#events-pane",
        },
        {
            "label": "Contrato mensal",
            "status": "ready" if contracts else "warning",
            "items": ["mensalidade definida", "limpeza recorrente", "próxima cobrança", "histórico do cliente", "insumos previstos"],
            "target_tab": "clients-tab",
            "target_href": "#contracts-quotes-panel",
        },
        {
            "label": "Limpeza recorrente",
            "status": "ready" if cleaning_agenda else "info",
            "items": ["cliente fixo", "data da limpeza", "materiais baixados", "observação registrada", "próxima execução"],
            "target_tab": "clients-tab",
            "target_href": "#contracts-quotes-panel",
        },
        {
            "label": "Despacho com PDF",
            "status": "ready" if has_pdf and route_data else "warning",
            "items": ["rota validada", "PDF gerado", "links de endereço revisados", "contato visível", "placas conferidas"],
            "target_tab": "operations-tab",
            "target_href": "#operations-pane",
        },
    ]
    if can_view_finance:
        dynamic_checklists.append({
            "label": "Fechamento financeiro",
            "status": "warning" if financial_management.get("overdue") else "ready",
            "items": ["recebimentos", "notas fiscais", "comprovantes", "despesas", "PDF do fechamento"],
            "target_tab": "summary-tab",
            "target_href": "#closeout-panel",
        })

    module_counts: dict[str, int] = {}
    for item in global_search_items:
        module = clean_text(item.get("module"), "Geral")
        module_counts[module] = module_counts.get(module, 0) + 1

    today = datetime.now().date()
    today_text = today.isoformat()
    event_risk_scores = build_event_risk_scores(events, clients, financial_management, route_data, has_pdf)
    stock_forecast = build_stock_usage_forecast(warehouse_dashboard)
    today_events = [
        event for event in events
        if clean_text(event.get("event_date")) <= today_text <= (clean_text(event.get("event_end_date")) or clean_text(event.get("event_date")))
    ]
    daily_summary = []
    if attention_center.get("danger_total"):
        daily_summary.append({"level": "danger", "title": "Resolver críticos", "detail": f"{attention_center.get('danger_total')} item(ns) críticos precisam de ação."})
    if today_events:
        daily_summary.append({"level": "warning", "title": "Eventos de hoje", "detail": f"{len(today_events)} evento(s) aparecem na agenda de hoje."})
    if financial_management.get("overdue"):
        daily_summary.append({"level": "danger", "title": "Cobranças vencidas", "detail": f"{len(financial_management.get('overdue', []))} recebimento(s) em atraso."})
    if route_data and not has_pdf:
        daily_summary.append({"level": "warning", "title": "Rota sem PDF", "detail": "Há rota gerada, mas o PDF precisa ser conferido."})
    stock_danger = [item for item in stock_forecast if item["level"] == "danger"]
    if stock_danger:
        daily_summary.append({"level": "danger", "title": "Estoque crítico", "detail": f"{len(stock_danger)} material(is) podem faltar."})
    if not daily_summary:
        daily_summary.append({"level": "ready", "title": "Dia sem bloqueio central", "detail": "Comece pela agenda, revise próximas cobranças e mantenha backup em dia."})

    clients_by_id = {clean_text(client.get("client_id")): client for client in clients}
    finance_by_client = {
        clean_text(item.get("client_id")) or clean_text(item.get("client_name")): item
        for item in financial_management.get("client_finance", [])
    }
    contract_client_ids = {clean_text(item.get("client_id")) for item in contracts}
    cleaning_client_ids = {clean_text(item.get("client_id")) for item in cleaning_agenda}
    client_attention = []
    for client in clients:
        client_id = clean_text(client.get("client_id"))
        score = 0
        reasons = []
        finance = finance_by_client.get(client_id) or finance_by_client.get(clean_text(client.get("customer_name"))) or {}
        if not clean_text(client.get("phone")):
            score += 20
            reasons.append("sem telefone")
        if not clean_text(client.get("address")):
            score += 20
            reasons.append("sem endereço")
        if not clean_text(client.get("equipment_type")):
            score += 10
            reasons.append("sem tipo de banheiro/equipamento")
        if parse_decimal(finance.get("open")) > 0:
            score += 25
            reasons.append("financeiro aberto")
        if client_id in contract_client_ids and client_id not in cleaning_client_ids:
            score += 15
            reasons.append("contrato sem limpeza futura")
        if score:
            client_attention.append({
                "client_id": client_id,
                "name": clean_text(client.get("customer_name")) or client_id,
                "score": score,
                "reasons": reasons,
                "target_tab": "clients-tab",
                "target_href": f"#client-{client_id}",
            })
    client_attention.sort(key=lambda item: item["score"], reverse=True)

    deadline_alerts = []
    receivables_by_event: dict[str, list[dict]] = {}
    for receivable in financial_management.get("receivables", []):
        event_id = clean_text(receivable.get("event_id"))
        if event_id:
            receivables_by_event.setdefault(event_id, []).append(receivable)
    for event in events:
        event_date = parse_date(event.get("event_date"))
        if not event_date or not event_is_active(event):
            continue
        days_until = (event_date - today).days
        if 0 <= days_until <= 7:
            missing = []
            if not event.get("client_ids"):
                missing.append("cliente")
            if not event.get("vehicle_ids"):
                missing.append("veículo")
            if any(not item.get("done") for item in event.get("checklist", [])):
                missing.append("checklist")
            if not (has_pdf and clean_text((route_data or {}).get("event_id")) == clean_text(event.get("event_id"))):
                missing.append("PDF/rota")
            if any(clean_text(item.get("status")) != "pago" for item in receivables_by_event.get(clean_text(event.get("event_id")), [])):
                missing.append("financeiro")
            if missing:
                deadline_alerts.append({
                    "level": "danger" if days_until <= 1 else "warning",
                    "title": clean_text(event.get("title")) or clean_text(event.get("event_id")),
                    "detail": f"faltam {days_until} dia(s): revisar {', '.join(missing)}",
                    "target_tab": "events-tab",
                    "target_href": f"#event-{clean_text(event.get('event_id'))}",
                })

    blocked_equipment_ids = {
        clean_text(item.get("equipment_id"))
        for item in maintenance_preventive_dashboard.get("alerts", [])
        if clean_text(item.get("level")) == "danger"
    }
    inconsistencies = []
    for event in events:
        event_id = clean_text(event.get("event_id"))
        if normalize_event_status(event.get("status")) == "concluido" and any(clean_text(item.get("status")) != "pago" for item in receivables_by_event.get(event_id, [])):
            inconsistencies.append({"level": "danger", "title": "Evento concluído sem pagamento", "detail": clean_text(event.get("title")) or event_id, "target_tab": "events-tab", "target_href": f"#event-{event_id}"})
    for contract in contracts:
        client_id = clean_text(contract.get("client_id"))
        if clean_text(contract.get("status"), "ativo") == "ativo" and client_id and client_id not in cleaning_client_ids:
            inconsistencies.append({"level": "warning", "title": "Cliente mensal sem próxima limpeza", "detail": clean_text(contract.get("client_name")) or client_id, "target_tab": "clients-tab", "target_href": "#contracts-quotes-panel"})
    for client in clients:
        equipment_id = clean_text(client.get("equipment_number"))
        if equipment_id in blocked_equipment_ids:
            inconsistencies.append({"level": "danger", "title": "Equipamento em manutenção vinculado", "detail": f"{equipment_id} • {client.get('customer_name')}", "target_tab": "fleet-tab", "target_href": "#maintenance-panel"})
    if not inconsistencies:
        inconsistencies.append({"level": "ready", "title": "Sem inconsistência crítica", "detail": "Eventos, contratos e vínculos não têm conflito principal agora.", "target_tab": "summary-tab", "target_href": "#smart-system-panel"})

    def bucket_item(level: str, title: str, detail: str, target_tab: str = "summary-tab", target_href: str = "#smart-system-panel") -> dict:
        return {"level": level, "title": title, "detail": detail, "target_tab": target_tab, "target_href": target_href}

    resolver_agora = [
        bucket_item(item.get("level"), item.get("title"), item.get("detail"), item.get("target_tab", "summary-tab"), item.get("target_href", "#smart-system-panel"))
        for item in next_steps + preventive_items + deadline_alerts + inconsistencies
        if item.get("level") == "danger"
    ][:5]
    revisar_hoje = [
        bucket_item(item.get("level"), item.get("title"), item.get("detail"), item.get("target_tab", "summary-tab"), item.get("target_href", "#smart-system-panel"))
        for item in next_steps + preventive_items + deadline_alerts + inconsistencies
        if item.get("level") == "warning"
    ][:5]
    acompanhar = [
        bucket_item(item.get("level"), item.get("title"), item.get("detail"), item.get("target_tab", "summary-tab"), item.get("target_href", "#smart-system-panel"))
        for item in next_steps + preventive_items
        if item.get("level") in {"ready", "info"}
    ][:5]
    priority_buckets = [
        {"label": "Resolver agora", "level": "danger", "items": resolver_agora or [bucket_item("ready", "Sem bloqueio crítico", "Continue pela agenda e validação.", "summary-tab", "#central-day-panel")]},
        {"label": "Revisar hoje", "level": "warning", "items": revisar_hoje or [bucket_item("ready", "Nada urgente para revisar", "Mantenha cadastros e financeiro atualizados.", "summary-tab", "#smart-system-panel")]},
        {"label": "Acompanhar depois", "level": "info", "items": acompanhar or [bucket_item("info", "Sem acompanhamento pendente", "Use relatórios para conferência semanal.", "summary-tab", "#reports-panel")]},
    ]

    weekly_report = {
        "events": sum(1 for event in events if parse_date(event.get("event_date")) and 0 <= (parse_date(event.get("event_date")) - today).days <= 7),
        "receivables": len(financial_management.get("receivables_due_soon", [])),
        "overdue": len(financial_management.get("overdue", [])),
        "maintenance": len(maintenance_preventive_dashboard.get("alerts", [])),
        "stock_critical": len([item for item in stock_forecast if item["level"] == "danger"]),
    }

    role = clean_text(user_role, "guest")
    favorite_map = {
        "admin": [("Acessos", "#access-pane", "access-tab"), ("Backup", "#system-readiness-panel", "summary-tab"), ("Homologação", "#homologation-pane", "homologation-tab")],
        "financeiro": [("Recebimentos", "#receivables-panel", "summary-tab"), ("Fechamento", "#closeout-panel", "summary-tab"), ("Relatórios", "#reports-panel", "summary-tab")],
        "operacional": [("Começar o dia", "#smart-start-day", "summary-tab"), ("Validar/Gerar", "#operations-pane", "operations-tab"), ("Frota", "#fleet-pane", "fleet-tab")],
        "leitura": [("Resumo", "#summary-pane", "summary-tab"), ("Agenda", "#agenda-pane", "agenda-tab"), ("Histórico", "#history-pane", "history-tab")],
        "guest": [("Resumo público", "#public-dashboard", ""), ("Entrar", "#settings-menu-button", "")],
    }
    favorites = [
        {"label": label, "target_href": href, "target_tab": tab}
        for label, href, tab in favorite_map.get(role, favorite_map["guest"])
    ]

    route_stops = [stop for route in (route_data or {}).get("routes", []) for stop in route.get("stops", [])]
    pdf_review = {
        "has_route": bool(route_stops),
        "stops_count": len(route_stops),
        "missing_contact": sum(1 for stop in route_stops if not clean_text(stop.get("contact_name")) or not clean_text(stop.get("phone"))),
        "missing_equipment": sum(1 for stop in route_stops if not clean_text(stop.get("equipment_number"))),
        "items": [
            {
                "client": clean_text(stop.get("customer_name")) or clean_text(stop.get("delivery_id")),
                "address": clean_text(stop.get("address")),
                "contact": clean_text(stop.get("contact_name")) or "sem contato",
                "equipment": f"{stop.get('equipment_quantity') or 1}x {stop.get('equipment_type') or 'banheiro/equipamento'} • {stop.get('equipment_number') or 'sem ID'}",
                "notes": clean_text(stop.get("operation_notes") or stop.get("notes")),
            }
            for stop in route_stops[:5]
        ],
    }

    quick_templates = [
        {"label": "Evento avulso", "kind": "event", "status": "confirmado", "category": "evento", "billing": "avulso", "notes": "Evento avulso com entrega, permanência e logística combinadas."},
        {"label": "Contrato mensal", "kind": "event", "status": "confirmado", "category": "contrato", "billing": "mensal", "notes": "Contrato mensal com banheiro instalado e limpeza recorrente."},
        {"label": "Limpeza recorrente", "kind": "event", "status": "programado", "category": "contrato", "billing": "mensal", "notes": "Atendimento de limpeza recorrente com baixa de insumos."},
        {"label": "Cliente fixo mensal", "kind": "client", "client_type": "fixo", "billing": "mensal", "equipment_type": "Banheiro Químico", "service_profile": "limpeza_semanal", "notes": "Cliente fixo mensal com banheiro instalado e limpeza recorrente."},
        {"label": "Banheiro químico", "kind": "equipment", "equipment_type": "Banheiro Químico", "condition": "disponivel", "notes": "Cabine de banheiro químico sem placa, controlar por ID interno."},
        {"label": "Banheiro de luxo", "kind": "equipment", "equipment_type": "Banheiro Luxo", "condition": "disponivel", "notes": "Trailer ou banheiro de luxo. Preencha placa quando existir."},
        {"label": "Material extra", "kind": "warehouse", "category": "Apoio de evento", "unit": "un", "stock_minimum": "2", "notes": "Material extra enviado em evento. Registrar movimentação e conferência no almoxarifado."},
        {"label": "Ordem de serviço", "kind": "event", "status": "os_pendente", "category": "ordem_servico", "billing": "avulso", "notes": "Evento preparado para gerar OS, revisar endereço, cliente, banheiros e veículo antes de imprimir."},
        {"label": "Orçamento", "kind": "event", "status": "rascunho", "category": "orcamento", "billing": "orcamento", "notes": "Pedido em orçamento aguardando aprovação do cliente."},
    ]

    change_history = [
        {
            "module": clean_text(item.get("module")),
            "action": clean_text(item.get("action")),
            "target": clean_text(item.get("target_id")) or "geral",
            "user": clean_text(item.get("user_name") or item.get("user_email")),
            "created_at": format_datetime_br(item.get("created_at")),
        }
        for item in recent_audit_log[:6]
    ]

    start_day_actions = [
        {"label": "Abrir pendências", "detail": "Ver só o que precisa de ação.", "target_href": "#attention-now-panel", "target_tab": "summary-tab"},
        {"label": "Eventos de hoje", "detail": f"{len(today_events)} evento(s) na data.", "target_href": "#daily-command-center", "target_tab": "summary-tab"},
        {"label": "Validar rota", "detail": f"{dispatch_today.get('ready_count', 0)}/{len(dispatch_today.get('checklist') or [])} item(ns) prontos.", "target_href": "#operations-pane", "target_tab": "operations-tab"},
        {"label": "Financeiro", "detail": f"{len(financial_management.get('overdue', []))} vencido(s).", "target_href": "#receivables-panel", "target_tab": "summary-tab"},
        {"label": "Estoque crítico", "detail": f"{len(stock_danger)} item(ns) em risco.", "target_href": "#warehouse-pane", "target_tab": "warehouse-tab"},
    ]
    role_start_map = {
        "admin": ["Abrir pendências", "Eventos de hoje", "Validar rota"],
        "operacional": ["Abrir pendências", "Eventos de hoje", "Validar rota"],
        "financeiro": ["Abrir pendências", "Financeiro", "Eventos de hoje"],
        "leitura": ["Eventos de hoje", "Abrir pendências", "Estoque crítico"],
        "guest": ["Eventos de hoje", "Abrir pendências", "Validar rota"],
    }
    role_start_labels = role_start_map.get(role, role_start_map["guest"])
    role_start_actions = [
        action
        for label in role_start_labels
        for action in start_day_actions
        if action["label"] == label
    ][:3]
    close_day_steps = [
        {"label": "Pagamentos", "done": not financial_management.get("overdue"), "detail": "Baixar recebimentos e revisar vencidos.", "target_href": "#receivables-panel", "target_tab": "summary-tab"},
        {"label": "Eventos", "done": not today_events, "detail": "Conferir status dos eventos do dia.", "target_href": "#events-pane", "target_tab": "events-tab"},
        {"label": "Manutenção", "done": not maintenance_preventive_dashboard.get("alerts"), "detail": "Registrar itens com revisão necessária.", "target_href": "#maintenance-panel", "target_tab": "fleet-tab"},
        {"label": "Estoque", "done": not stock_danger, "detail": "Repor materiais críticos ou zerados.", "target_href": "#warehouse-pane", "target_tab": "warehouse-tab"},
        {"label": "Backup e relatório", "done": False, "detail": "Baixar fechamento do dia e backup quando necessário.", "target_href": url_for("download_daily_closeout"), "target_tab": ""},
    ]

    primary_pool = resolver_agora or revisar_hoje or acompanhar or [
        bucket_item("ready", "Começar pela agenda", "Abra a Central do Dia e siga o roteiro de operação.", "summary-tab", "#central-day-panel")
    ]
    primary_item = primary_pool[0]
    primary_action_label = {
        "danger": "Resolver agora",
        "warning": "Revisar hoje",
        "ready": "Continuar rotina",
        "info": "Acompanhar",
    }.get(clean_text(primary_item.get("level"), "info"), "Abrir")
    missing_client_core = sum(
        1
        for client in clients
        if not clean_text(client.get("phone")) or not clean_text(client.get("address"))
    )
    active_event_core_issues = sum(
        1
        for event in events
        if event_is_active(event) and (not event.get("client_ids") or not event.get("vehicle_ids"))
    )
    maintenance_alert_count = len(maintenance_preventive_dashboard.get("alerts", []))
    pdf_issue_count = int(pdf_review.get("missing_contact") or 0) + int(pdf_review.get("missing_equipment") or 0)
    pdf_attention_count = pdf_issue_count if pdf_review.get("has_route") else 1
    quality_issue_count = (
        missing_client_core
        + active_event_core_issues
        + pdf_attention_count
        + len(resolver_agora)
        + len(revisar_hoje)
        + len([item for item in inconsistencies if item.get("level") in {"danger", "warning"}])
    )
    quality_score = max(0, 100 - min(100, quality_issue_count * 8))

    def review_level(count: int, *, enabled: bool = True) -> str:
        if not enabled:
            return "info"
        if count >= 3:
            return "danger"
        if count:
            return "warning"
        return "ready"

    attention_mode = {
        "primary": {
            "level": clean_text(primary_item.get("level"), "info"),
            "title": clean_text(primary_item.get("title"), "Começar o dia"),
            "detail": clean_text(primary_item.get("detail"), "Revise prioridades antes de abrir módulos separados."),
            "target_tab": clean_text(primary_item.get("target_tab"), "summary-tab"),
            "target_href": clean_text(primary_item.get("target_href"), "#smart-start-day"),
            "action": primary_action_label,
        },
        "metrics": [
            {"label": "Bloqueios", "value": len(resolver_agora), "level": review_level(len(resolver_agora))},
            {"label": "Revisar hoje", "value": len(revisar_hoje), "level": review_level(len(revisar_hoje))},
            {"label": "PDF/impresso", "value": pdf_attention_count, "level": review_level(pdf_attention_count)},
            {"label": "Qualidade", "value": f"{quality_score}%", "level": "ready" if quality_score >= 85 else "warning" if quality_score >= 65 else "danger"},
        ],
        "review_checks": [
            {
                "label": "Cliente",
                "level": review_level(missing_client_core),
                "count": missing_client_core,
                "detail": f"{missing_client_core} cadastro(s) sem telefone ou endereço completo.",
                "target_tab": "clients-tab",
                "target_href": "#clients-pane",
            },
            {
                "label": "Evento",
                "level": review_level(active_event_core_issues + len(deadline_alerts)),
                "count": active_event_core_issues + len(deadline_alerts),
                "detail": f"{active_event_core_issues} ativo(s) sem cliente/veículo e {len(deadline_alerts)} prazo(s) críticos.",
                "target_tab": "events-tab",
                "target_href": "#events-pane",
            },
            {
                "label": "Banheiros/equipamentos",
                "level": review_level(len(stock_danger) + maintenance_alert_count),
                "count": len(stock_danger) + maintenance_alert_count,
                "detail": f"{len(stock_danger)} estoque(s) crítico(s) e {maintenance_alert_count} alerta(s) de manutenção.",
                "target_tab": "fleet-tab",
                "target_href": "#maintenance-panel",
            },
            {
                "label": "Financeiro",
                "level": review_level(len(financial_management.get("overdue", [])), enabled=can_view_finance),
                "count": len(financial_management.get("overdue", [])) if can_view_finance else 0,
                "detail": f"{len(financial_management.get('overdue', []))} cobrança(s) vencida(s)." if can_view_finance else "Visível apenas para perfil financeiro ou administrador.",
                "target_tab": "summary-tab",
                "target_href": "#receivables-panel" if can_view_finance else "#summary-pane",
            },
            {
                "label": "PDF/impresso",
                "level": review_level(pdf_attention_count),
                "count": pdf_attention_count,
                "detail": "Rota pronta para revisão antes de entregar em PDF/impresso." if pdf_review.get("has_route") and pdf_issue_count == 0 else "Gere ou revise rota, contatos, banheiros e placas antes do PDF.",
                "target_tab": "operations-tab",
                "target_href": "#operations-pane",
            },
        ],
        "quality_score": quality_score,
        "quality_issue_count": quality_issue_count,
        "weekly_focus": [
            {"label": "Eventos 7 dias", "value": weekly_report["events"]},
            {"label": "Recebimentos", "value": weekly_report["receivables"]},
            {"label": "Vencidos", "value": weekly_report["overdue"]},
            {"label": "Estoque crítico", "value": weekly_report["stock_critical"]},
            {"label": "Manutenção", "value": weekly_report["maintenance"]},
        ],
    }
    completion_hub_items = [
        {
            "level": review_level(missing_client_core),
            "title": "Clientes incompletos",
            "detail": f"{missing_client_core} cliente(s) sem telefone ou endereço.",
            "target_tab": "clients-tab",
            "target_href": "#clients-pane",
            "highlight_target": "#client-search",
            "action": "Completar clientes",
        },
        {
            "level": review_level(active_event_core_issues + len(deadline_alerts)),
            "title": "Eventos para completar",
            "detail": f"{active_event_core_issues} evento(s) sem cliente/veículo e {len(deadline_alerts)} prazo(s) em atenção.",
            "target_tab": "events-tab",
            "target_href": "#events-pane",
            "highlight_target": "#event-filter",
            "action": "Abrir eventos",
        },
        {
            "level": review_level(pdf_attention_count),
            "title": "PDF e links de endereço",
            "detail": "Gere ou revise a rota antes de entregar PDF, impresso ou links para a equipe.",
            "target_tab": "operations-tab",
            "target_href": "#operations-pane",
            "highlight_target": "#gerador",
            "action": "Revisar PDF",
        },
        {
            "level": review_level(len(stock_danger) + maintenance_alert_count),
            "title": "Banheiros/equipamentos",
            "detail": f"{len(stock_danger)} estoque(s) crítico(s) e {maintenance_alert_count} alerta(s) de manutenção.",
            "target_tab": "fleet-tab",
            "target_href": "#maintenance-panel",
            "highlight_target": "#maintenance-panel",
            "action": "Ver equipamentos",
        },
    ]
    if can_view_finance:
        completion_hub_items.append({
            "level": review_level(len(financial_management.get("overdue", []))),
            "title": "Cobranças pendentes",
            "detail": f"{len(financial_management.get('overdue', []))} cobrança(s) vencida(s) para revisar.",
            "target_tab": "summary-tab",
            "target_href": "#receivables-panel",
            "highlight_target": "#receivables-panel",
            "action": "Abrir financeiro",
        })
    else:
        completion_hub_items.append({
            "level": "info",
            "title": "Financeiro protegido",
            "detail": "Pendências financeiras aparecem para administrador ou financeiro.",
            "target_tab": "summary-tab",
            "target_href": "#summary-pane",
            "highlight_target": "#summary-pane",
            "action": "Ver resumo",
        })

    command_search = [
        {"label": "Clientes sem contato", "query": "sem telefone", "module": "clientes", "target_tab": "clients-tab", "target_href": "#clients-pane"},
        {"label": "Eventos da semana", "query": "evento", "module": "eventos", "target_tab": "events-tab", "target_href": "#events-pane"},
        {"label": "Placas e frota", "query": "placa", "module": "frota", "target_tab": "fleet-tab", "target_href": "#fleet-pane"},
        {"label": "Banheiros", "query": "banheiro", "module": "equipamentos", "target_tab": "fleet-tab", "target_href": "#fleet-pane"},
        {"label": "NF e notas", "query": "nf", "module": "financeiro" if can_view_finance else "", "target_tab": "summary-tab", "target_href": "#receivables-panel" if can_view_finance else "#global-search-panel"},
        {"label": "Estoque crítico", "query": "baixo", "module": "almoxarifado", "target_tab": "warehouse-tab", "target_href": "#warehouse-pane"},
    ]
    search_examples = [
        "telefone do cliente",
        "placa ABC1D23",
        "NF 123",
        "banheiro químico",
        "evento deste fim de semana",
        "material extra",
    ]
    registration_guides = [
        {
            "title": "Cadastrar evento sem se perder",
            "steps": ["Nome e data", "Cliente", "Banheiros e veículo", "Checklist", "Valor ou observação"],
            "target_tab": "events-tab",
            "target_href": "#event-create-panel",
        },
        {
            "title": "Cadastrar cliente fixo",
            "steps": ["Nome", "Telefone", "Endereço", "Tipo de banheiro", "Cobrança"],
            "target_tab": "clients-tab",
            "target_href": "#manual-client-form",
        },
        {
            "title": "Preparar PDF/impresso",
            "steps": ["Evento correto", "Endereço conferido", "Contato visível", "Banheiros definidos", "OS ou rota baixada"],
            "target_tab": "operations-tab",
            "target_href": "#operations-pane",
        },
    ]
    save_validation = [
        {"title": "Evento", "detail": "Avisar antes de salvar se faltar data, cliente, veículo ou valor quando aplicável."},
        {"title": "Cliente", "detail": "Avisar se telefone, endereço, latitude/longitude ou tipo de banheiro estiver incompleto."},
        {"title": "Equipamento", "detail": "Lembrar que placa é opcional, mas ID e tipo precisam estar claros."},
        {"title": "Material", "detail": "Avisar se saldo mínimo, categoria ou local de armazenamento estiver sem preenchimento."},
    ]
    print_package = {
        "items": [
            "Ordem de serviço do evento",
            "Link de endereço por cliente",
            "Contato principal",
            "Banheiros/equipamentos vinculados",
            "Checklist de conferência",
        ],
        "note": "Preparado para material impresso, PDF e envio de links, sem criar fluxo mobile de equipe de campo.",
    }

    return {
        "next_steps": next_steps[:6],
        "preventive_alerts": preventive_items[:8],
        "validation_items": validation_items,
        "validation_ready": dispatch_today.get("ready_count", 0),
        "validation_total": len(dispatch_today.get("checklist") or []),
        "client_insights": client_insights[:6],
        "search_total": len(global_search_items),
        "search_modules": [{"module": key, "count": value} for key, value in sorted(module_counts.items())],
        "search_fields": ["nome", "telefone", "CPF/CNPJ", "placa", "NF", "evento", "endereço", "banheiro/equipamento", "observações"],
        "duplicate_alerts": general_improvements.get("duplicate_alerts", [])[:5],
        "duplicate_count": general_improvements.get("duplicate_count", 0),
        "financial_recommendations": financial_recommendations[:5],
        "forecast_cards": forecast_cards[:5],
        "reports": reports_hub[:6],
        "dynamic_checklists": dynamic_checklists,
        "event_risk_scores": event_risk_scores,
        "daily_summary": daily_summary[:5],
        "client_attention": client_attention[:6],
        "stock_forecast": stock_forecast,
        "deadline_alerts": deadline_alerts[:6],
        "weekly_report": weekly_report,
        "inconsistencies": inconsistencies[:6],
        "priority_buckets": priority_buckets,
        "favorites": favorites,
        "pdf_review": pdf_review,
        "print_package": print_package,
        "quick_templates": quick_templates,
        "change_history": change_history,
        "start_day_actions": start_day_actions,
        "role_start_actions": role_start_actions,
        "registration_guides": registration_guides,
        "save_validation": save_validation,
        "close_day_steps": close_day_steps,
        "attention_mode": attention_mode,
        "completion_hub": {"items": completion_hub_items},
        "command_search": command_search,
        "search_examples": search_examples,
        "action_filter_counts": {
            "resolver_agora": len(resolver_agora),
            "revisar_hoje": len(revisar_hoje),
            "acompanhar": len(acompanhar),
        },
        "attention_total": attention_center.get("open_total", 0),
        "attention_critical": attention_center.get("danger_total", 0),
        "scope_note": "Sugestão automática de equipamento ideal não incluída por escolha de escopo.",
    }


def build_role_focus_cards(user: dict, can_view_finance: bool) -> list[dict]:
    role = clean_text(user.get("role"), "guest")
    if role == "admin":
        return [
            {"label": "Homologação", "detail": "Revise produção, ambiente e permissões.", "target_tab": "homologation-tab", "target_href": "#homologation-pane", "action": "Abrir homologação"},
            {"label": "Acessos", "detail": "Crie usuários e acompanhe senhas pendentes.", "target_tab": "access-tab", "target_href": "#access-pane", "action": "Abrir acessos"},
            {"label": "Backup", "detail": "Gere cópia antes de mudanças importantes.", "target_tab": "", "target_href": url_for("download_system_backup"), "action": "Gerar backup"},
        ]
    if role == "financeiro" or can_view_finance:
        return [
            {"label": "Recebimentos", "detail": "Veja vencidos, hoje e próximos dias.", "target_tab": "summary-tab", "target_href": "#receivables-panel", "action": "Abrir financeiro"},
            {"label": "Fluxo de caixa", "detail": "Registre entradas, despesas e anexos opcionais.", "target_tab": "summary-tab", "target_href": "#cashflow-panel", "action": "Abrir caixa"},
            {"label": "Fechamento", "detail": "Acompanhe mês, provisões e relatórios.", "target_tab": "summary-tab", "target_href": "#closeout-panel", "action": "Abrir fechamento"},
        ]
    if role == "operacional":
        return [
            {"label": "Central do Dia", "detail": "Comece por pendências, agenda e rota.", "target_tab": "summary-tab", "target_href": "#central-day-panel", "action": "Abrir central"},
            {"label": "Eventos", "detail": "Crie locações e vincule cliente, veículo e equipamento.", "target_tab": "events-tab", "target_href": "#events-pane", "action": "Abrir eventos"},
            {"label": "Almoxarifado", "detail": "Registre entrada ou saída de materiais internos.", "target_tab": "warehouse-tab", "target_href": "#warehouse-pane", "action": "Abrir estoque"},
        ]
    return [
        {"label": "Resumo", "detail": "Acompanhe a operação sem alterar dados.", "target_tab": "summary-tab", "target_href": "#summary-pane", "action": "Abrir resumo"},
        {"label": "Agenda", "detail": "Veja próximos eventos e capacidade.", "target_tab": "agenda-tab", "target_href": "#agenda-pane", "action": "Abrir agenda"},
        {"label": "Histórico", "detail": "Consulte registros e PDFs disponíveis.", "target_tab": "history-tab", "target_href": "#history-pane", "action": "Abrir histórico"},
    ]


def build_attention_center(
    *,
    preventive_warnings: list[dict],
    financial_management: dict,
    warehouse_dashboard: dict,
    system_status: dict,
    guided_operation_flow: dict,
    can_backup: bool = False,
) -> dict:
    items: list[dict] = []
    for warning in preventive_warnings[:6]:
        items.append({
            "level": warning.get("level") or "warning",
            "title": warning.get("title") or "Pendência operacional",
            "detail": warning.get("detail") or "Revisar item da operação.",
            "target_tab": warning.get("target_tab") or "summary-tab",
            "target_href": warning.get("target_href") or "#summary-pane",
            "action": warning.get("action") or "Abrir",
        })
    overdue = financial_management.get("overdue", [])
    if overdue:
        items.append({
            "level": "danger",
            "title": "Cobranças vencidas",
            "detail": f"{len(overdue)} cobrança(s) precisam de ação.",
            "target_tab": "summary-tab",
            "target_href": "#receivables-panel",
            "action": "Abrir financeiro",
        })
    warehouse_counts = warehouse_dashboard.get("counts") or {}
    stock_alerts = (warehouse_counts.get("low", 0) or 0) + (warehouse_counts.get("zero", 0) or 0)
    if stock_alerts:
        items.append({
            "level": "danger" if warehouse_counts.get("zero") else "warning",
            "title": "Estoque em alerta",
            "detail": f"{stock_alerts} material(is) baixo(s) ou zerado(s).",
            "target_tab": "warehouse-tab",
            "target_href": "#warehouse-pane",
            "action": "Abrir almoxarifado",
        })
    if not system_status.get("health", {}).get("has_recent_backup"):
        items.append({
            "level": "warning",
            "title": "Backup pendente",
            "detail": "Gere um backup antes do uso diário ou após mudanças importantes.",
            "target_tab": "" if can_backup else "summary-tab",
            "target_href": url_for("download_system_backup") if can_backup else "#system-readiness-panel",
            "action": "Gerar backup" if can_backup else "Ver status",
        })
    for step in guided_operation_flow.get("steps", []):
        if step.get("status") != "ready":
            items.append({
                "level": "warning" if step.get("status") == "attention" else "danger",
                "title": f"Fluxo incompleto: {step.get('label')}",
                "detail": step.get("detail"),
                "target_tab": step.get("target_tab"),
                "target_href": step.get("target_href"),
                "action": step.get("action"),
            })
            break
    return {
        "items": items[:8],
        "open_total": len(items),
        "danger_total": sum(1 for item in items if item.get("level") == "danger"),
        "warning_total": sum(1 for item in items if item.get("level") == "warning"),
    }


def build_search_module_counts(global_search_items: list[dict], *, can_view_finance: bool) -> list[dict]:
    module_order = [
        ("clientes", "Clientes"),
        ("eventos", "Eventos/Locações"),
        ("equipamentos", "Equipamentos"),
        ("rotas_os", "Rotas/OS"),
    ]
    if can_view_finance:
        module_order.append(("financeiro", "Financeiro"))
    if any(clean_text(item.get("module_key")) == "outros" for item in global_search_items):
        module_order.append(("outros", "Outros"))
    counts = {key: 0 for key, _ in module_order}
    for item in global_search_items:
        key = clean_text(item.get("module_key"))
        if key in counts:
            counts[key] += 1
    return [{"key": key, "label": label, "count": counts.get(key, 0)} for key, label in module_order]


def build_compact_system_dashboard(
    *,
    user: dict,
    clients: list[dict],
    events: list[dict],
    vehicles: list[dict],
    equipment: list[dict],
    warehouse_dashboard: dict,
    financial_management: dict,
    reports_hub: list[dict],
    attention_center: dict,
    equipment_family_counts: dict,
    has_pdf: bool,
    can_view_finance: bool,
    can_manage_access: bool,
) -> dict:
    today = datetime.now().date()
    today_text = today.isoformat()
    week_end = today + timedelta(days=7)
    today_events = [event for event in events if event_overlaps_date(event, today_text)]
    week_events = [
        event
        for event in events
        if event_overlaps_period(event, today_text, week_end.isoformat())
    ]
    bathroom_total = (
        int(equipment_family_counts.get("banheiro_luxo") or 0)
        + int(equipment_family_counts.get("banheiro_quimico") or 0)
    )
    support_total = (
        int(equipment_family_counts.get("climatizacao") or 0)
        + int(equipment_family_counts.get("hidratacao") or 0)
        + int(equipment_family_counts.get("apoio") or 0)
    )
    warehouse_counts = warehouse_dashboard.get("counts") or {}
    overdue_count = len(financial_management.get("overdue", [])) if can_view_finance else 0
    open_alerts = int(attention_center.get("open_total") or 0)
    stock_attention_count = int(warehouse_counts.get("low") or 0) + int(warehouse_counts.get("zero") or 0)
    quick_finance_href = "#receivables-panel" if can_view_finance else "#system-readiness-panel"
    quick_finance_detail = f"{overdue_count} cobrança(s) vencida(s)" if can_view_finance else "Financeiro protegido por permissão"
    role = clean_text(user.get("role"), "guest")
    profile_ui = build_profile_ui(user)
    role_views = {
        "admin": {
            "label": "Administrador",
            "summary": "Comece por pendências, segurança, acessos e backup; financeiro e operação continuam a um clique.",
            "primary": "#attention-now-panel",
            "tab": "summary-tab",
            "actions": [
                {"label": "Pendências", "href": "#attention-now-panel", "tab": "summary-tab"},
                {"label": "Acessos", "href": "#access-management-panel", "tab": "access-tab"},
                {"label": "Backup", "href": url_for("download_system_backup"), "tab": ""},
                {"label": "Homologação", "href": "#homologation-pane", "tab": "homologation-tab"},
            ],
        },
        "operacional": {
            "label": "Operação",
            "summary": "Mostra agenda, locações, banheiros, rota/PDF, estoque e pendências antes dos relatórios.",
            "primary": "#central-day-panel",
            "tab": "summary-tab",
            "actions": [
                {"label": "Central do dia", "href": "#central-day-panel", "tab": "summary-tab"},
                {"label": "Criar locação", "href": "#quick-rental-panel", "tab": "summary-tab"},
                {"label": "Banheiros", "href": "#fleet-pane", "tab": "fleet-tab"},
                {"label": "Gerar PDF", "href": "#operations-pane", "tab": "operations-tab"},
            ],
        },
        "financeiro": {
            "label": "Financeiro",
            "summary": "Abre recebimentos, vencidos, baixa de pagamento e fechamento mensal sem passar pela operação.",
            "primary": quick_finance_href,
            "tab": "summary-tab",
            "actions": [
                {"label": "Recebimentos", "href": quick_finance_href, "tab": "summary-tab"},
                {"label": "Baixar pagamento", "href": quick_finance_href, "tab": "summary-tab"},
                {"label": "Fluxo de caixa", "href": "#cashflow-panel", "tab": "summary-tab"},
                {"label": "Fechamento", "href": "#closeout-panel", "tab": "summary-tab"},
            ],
        },
        "leitura": {
            "label": "Leitura",
            "summary": "Mantém consultas, agenda, histórico, PDF e relatórios visíveis sem destacar ações de edição.",
            "primary": "#summary-pane",
            "tab": "summary-tab",
            "actions": [
                {"label": "Resumo", "href": "#summary-pane", "tab": "summary-tab"},
                {"label": "Agenda", "href": "#agenda-pane", "tab": "agenda-tab"},
                {"label": "Histórico", "href": "#history-pane", "tab": "history-tab"},
                {"label": "Relatórios", "href": "#reports-panel", "tab": "summary-tab"},
            ],
        },
        "guest": {
            "label": "Visitante",
            "summary": "Mostra resumo público e entrada no sistema.",
            "primary": "#public-dashboard",
            "tab": "",
            "actions": [
                {"label": "Resumo", "href": "#public-dashboard", "tab": ""},
                {"label": "Entrar", "href": "#settings-menu-button", "tab": ""},
            ],
        },
    }
    role_view = role_views.get(role, role_views["guest"])

    menu_groups = [
        {
            "key": "today",
            "label": "Hoje",
            "detail": f"{len(today_events)} evento(s) hoje • {open_alerts} alerta(s)",
            "items": [
                {
                    "label": "Central do Dia",
                    "detail": f"{len(today_events)} evento(s) de hoje",
                    "count": len(today_events),
                    "href": "#central-day-panel",
                    "tab": "summary-tab",
                    "tone": "primary",
                    "current": True,
                },
                {
                    "label": "Pendências Inteligentes",
                    "detail": f"{open_alerts} alerta(s) aberto(s)",
                    "count": open_alerts,
                    "href": "#intelligent-pending-panel",
                    "tab": "summary-tab",
                    "tone": "danger" if open_alerts else "default",
                },
                {
                    "label": "Agenda dos próximos 7 dias",
                    "detail": f"{len(week_events)} evento(s) na semana",
                    "count": len(week_events),
                    "href": "#agenda-pane",
                    "tab": "agenda-tab",
                    "tone": "default",
                },
            ],
        },
        {
            "key": "operation",
            "label": "Operação",
            "detail": "Cadastro, execução, rota, OS, equipamentos e frota.",
            "items": [
                {
                    "label": "Locação Rápida",
                    "detail": "Criar pedido guiado",
                    "count": 0,
                    "href": "#quick-rental-panel",
                    "tab": "summary-tab",
                    "tone": "primary",
                    "permission": "events.create",
                },
                {
                    "label": "Clientes",
                    "detail": f"{len(clients)} cadastro(s)",
                    "count": len(clients),
                    "href": "#clients-pane",
                    "tab": "clients-tab",
                    "tone": "default",
                },
                {
                    "label": "Eventos/Locações",
                    "detail": f"{len(events)} total • {len(week_events)} na semana",
                    "count": len(events),
                    "href": "#events-pane",
                    "tab": "events-tab",
                    "tone": "default",
                },
                {
                    "label": "Rotas",
                    "detail": "Validar e gerar rota",
                    "count": 0,
                    "href": "#operations-pane",
                    "tab": "operations-tab",
                    "tone": "default",
                },
                {
                    "label": "Ordens de Serviço",
                    "detail": "Gerar OS/PDF operacional",
                    "count": 0,
                    "href": "#operations-pane",
                    "tab": "operations-tab",
                    "tone": "default",
                    "permission": "events.service_order",
                },
                {
                    "label": "Equipamentos",
                    "detail": f"{bathroom_total + support_total} item(ns) principais",
                    "count": bathroom_total + support_total,
                    "href": "#fleet-pane",
                    "tab": "fleet-tab",
                    "tone": "primary",
                },
                {
                    "label": "Frota",
                    "detail": f"{len(vehicles)} veículo(s)",
                    "count": len(vehicles),
                    "href": "#fleet-pane",
                    "tab": "fleet-tab",
                    "tone": "default",
                },
            ],
        },
        {
            "key": "finance",
            "label": "Financeiro",
            "detail": f"{overdue_count} cobrança(s) vencida(s)" if can_view_finance else "Protegido por perfil",
            "items": [
                {
                    "label": "Painel Financeiro",
                    "detail": "Previsto, recebido e vencido",
                    "count": overdue_count,
                    "href": "#financial-decision-panel",
                    "tab": "summary-tab",
                    "tone": "danger" if overdue_count else "default",
                    "module": "finance",
                },
                {
                    "label": "Contas a Receber",
                    "detail": "Cobranças e vencimentos",
                    "count": len(financial_management.get("receivables", [])) if can_view_finance else 0,
                    "href": "#receivables-panel",
                    "tab": "summary-tab",
                    "tone": "danger" if overdue_count else "default",
                    "module": "finance",
                },
                {
                    "label": "Recebimentos",
                    "detail": "Baixas recentes",
                    "count": 0,
                    "href": "#financial-recent-receivables",
                    "tab": "summary-tab",
                    "tone": "default",
                    "module": "finance",
                },
                {
                    "label": "Clientes em Atraso",
                    "detail": "Cobrança prioritária",
                    "count": overdue_count,
                    "href": "#financial-overdue-clients",
                    "tab": "summary-tab",
                    "tone": "danger" if overdue_count else "default",
                    "module": "finance",
                },
                {
                    "label": "Relatórios financeiros",
                    "detail": "PDF e Excel financeiro",
                    "count": 0,
                    "href": "#financial-reports-panel",
                    "tab": "summary-tab",
                    "tone": "default",
                    "module": "finance",
                },
            ],
        },
        {
            "key": "management",
            "label": "Gestão",
            "detail": "Administração, auditoria, backup e configurações.",
            "items": [
                {
                    "label": "Relatórios gerais",
                    "detail": f"{len(reports_hub)} pacote(s) para PDF/Excel",
                    "count": len(reports_hub),
                    "href": "#reports-panel",
                    "tab": "summary-tab",
                    "tone": "default",
                    "module": "admin",
                },
                {
                    "label": "Auditoria",
                    "detail": "Histórico de ações críticas",
                    "count": 0,
                    "href": "#admin-audit-panel",
                    "tab": "access-tab",
                    "tone": "admin",
                    "module": "admin",
                },
                {
                    "label": "Backups",
                    "detail": "Gerar e baixar cópia local",
                    "count": 0,
                    "href": "#admin-backup-panel",
                    "tab": "access-tab",
                    "tone": "admin",
                    "module": "admin",
                },
                {
                    "label": "Usuários",
                    "detail": "Convites, perfis e senhas",
                    "count": 0,
                    "href": "#access-management-panel",
                    "tab": "access-tab",
                    "tone": "admin",
                    "module": "admin",
                },
                {
                    "label": "Configurações",
                    "detail": "Conta, permissões e segurança",
                    "count": 0,
                    "href": "#settings-menu-button",
                    "tab": "",
                    "tone": "admin",
                    "module": "admin",
                },
            ],
        },
        {
            "key": "help",
            "label": "Ajuda",
            "detail": "Orientação curta para a equipe.",
            "items": [
                {
                    "label": "Manual rápido",
                    "detail": "Ajuda Rápida da equipe",
                    "count": 0,
                    "href": "#quick-help-panel",
                    "tab": "summary-tab",
                    "tone": "default",
                },
                {
                    "label": "Treinamento",
                    "detail": "Simulação visual sem alterar dados reais",
                    "count": 0,
                    "href": "#training-panel",
                    "tab": "history-tab",
                    "tone": "default",
                },
                {
                    "label": "Dúvidas frequentes",
                    "detail": "Abrir assistente operacional",
                    "count": 0,
                    "href": "#help-assistant-button",
                    "tab": "",
                    "tone": "default",
                    "open_help": True,
                },
                {
                    "label": "Suporte interno",
                    "detail": "Registrar dúvida para análise",
                    "count": 0,
                    "href": "#help-assistant-button",
                    "tab": "",
                    "tone": "default",
                    "open_help": True,
                },
            ],
        },
    ]

    primary_actions = [
        {"label": "Criar locação", "href": "#quick-rental-panel", "tab": "summary-tab", "create": ""},
        {"label": "Novo evento", "href": "#events-pane", "tab": "events-tab", "create": "event-create-panel"},
        {"label": "Novo cliente", "href": "#clients-pane", "tab": "clients-tab", "create": "manual-client-form"},
        {"label": "Buscar tudo", "href": "#global-search-panel", "tab": "summary-tab", "create": ""},
        {"label": "Gerar rota/PDF", "href": "#operations-pane", "tab": "operations-tab", "create": ""},
    ]
    if can_view_finance:
        primary_actions.append({"label": "Baixar pagamento", "href": "#receivables-panel", "tab": "summary-tab", "create": ""})

    sticky_actions = [
        {"label": "Novo cliente", "href": "#clients-pane", "tab": "clients-tab", "create": "manual-client-form"},
        {"label": "Novo orçamento", "href": "#contracts-quotes-panel", "tab": "clients-tab", "create": ""},
        {"label": "Novo evento", "href": "#events-pane", "tab": "events-tab", "create": "event-create-panel"},
        {"label": "Gerar PDF", "href": "#operations-pane", "tab": "operations-tab", "create": ""},
        {"label": "Buscar", "href": "#global-search-panel", "tab": "summary-tab", "create": ""},
    ]
    if can_view_finance:
        sticky_actions.append({"label": "Pagamento", "href": "#receivables-panel", "tab": "summary-tab", "create": ""})

    more_actions = [
        {"label": "Frota e equipamentos", "href": "#fleet-pane", "tab": "fleet-tab"},
        {"label": "Almoxarifado", "href": "#warehouse-pane", "tab": "warehouse-tab"},
        {"label": "Relatórios completos", "href": "#reports-panel", "tab": "summary-tab"},
        {"label": "Status do sistema", "href": "#system-readiness-panel", "tab": "summary-tab"},
        {"label": "Fechar dia", "href": url_for("download_daily_closeout"), "tab": ""},
    ]
    if can_manage_access:
        more_actions.extend(
            [
                {"label": "Acessos da equipe", "href": "#access-management-panel", "tab": "access-tab"},
                {"label": "Homologação", "href": "#homologation-pane", "tab": "homologation-tab"},
                {"label": "Backup", "href": url_for("download_system_backup"), "tab": ""},
            ]
        )

    search_shortcuts = [
        {"label": "Cliente", "query": "", "module": "clientes", "target_tab": "summary-tab", "target_href": "#global-search-panel"},
        {"label": "Evento", "query": "", "module": "eventos", "target_tab": "summary-tab", "target_href": "#global-search-panel"},
        {"label": "Banheiros", "query": "banheiro", "module": "equipamentos", "target_tab": "fleet-tab", "target_href": "#fleet-pane"},
        {"label": "Apoio", "query": "", "module": "equipamentos", "target_tab": "fleet-tab", "target_href": "#fleet-pane"},
        {"label": "Placa", "query": "placa", "module": "", "target_tab": "summary-tab", "target_href": "#global-search-panel"},
        {"label": "NF", "query": "nf", "module": "", "target_tab": "summary-tab", "target_href": "#global-search-panel"},
        {"label": "Material", "query": "", "module": "almoxarifado", "target_tab": "warehouse-tab", "target_href": "#warehouse-pane"},
    ]
    if can_view_finance:
        search_shortcuts.append({"label": "Cobrança", "query": "vencido", "module": "financeiro", "target_tab": "summary-tab", "target_href": "#receivables-panel"})

    command_palette = [
        {"label": "Criar locação", "keywords": "novo criar locacao aluguel cliente evento banheiro rapido", "kind": "acao", "href": "#quick-rental-panel", "tab": "summary-tab", "create": "", "query": "", "module": ""},
        {"label": "Novo cliente", "keywords": "cliente cadastro telefone endereco cpf cnpj contato", "kind": "cadastro", "href": "#clients-pane", "tab": "clients-tab", "create": "manual-client-form", "query": "", "module": ""},
        {"label": "Novo evento", "keywords": "evento obra agenda data locacao checklist", "kind": "cadastro", "href": "#events-pane", "tab": "events-tab", "create": "event-create-panel", "query": "", "module": ""},
        {"label": "Buscar cliente", "keywords": "buscar encontrar cliente telefone endereco documento", "kind": "busca", "href": "#global-search-panel", "tab": "summary-tab", "create": "", "query": "", "module": "clientes"},
        {"label": "Buscar evento", "keywords": "buscar encontrar evento agenda semana status", "kind": "busca", "href": "#global-search-panel", "tab": "summary-tab", "create": "", "query": "", "module": "eventos"},
        {"label": "Banheiros e placas", "keywords": "banheiro equipamento placa frota manutencao disponivel", "kind": "busca", "href": "#fleet-pane", "tab": "fleet-tab", "create": "", "query": "banheiro", "module": "equipamentos"},
        {"label": "Gerar rota/PDF", "keywords": "rota pdf imprimir ordem servico endereco mapa validar", "kind": "operacao", "href": "#operations-pane", "tab": "operations-tab", "create": "", "query": "", "module": ""},
        {"label": "Estoque crítico", "keywords": "estoque almoxarifado material baixo zerado limpeza", "kind": "rotina", "href": "#warehouse-pane", "tab": "warehouse-tab", "create": "", "query": "baixo", "module": "almoxarifado"},
        {"label": "Resolver pendências", "keywords": "resolver pendencia alerta critico atenção agora", "kind": "rotina", "href": "#attention-now-panel", "tab": "summary-tab", "create": "", "query": "", "module": ""},
    ]
    if can_view_finance:
        command_palette.extend([
            {"label": "Baixar pagamento", "keywords": "pagamento receber baixa financeiro vencido cobrança boleto pix", "kind": "financeiro", "href": "#receivables-panel", "tab": "summary-tab", "create": "", "query": "vencido", "module": "financeiro"},
            {"label": "Fechamento mensal", "keywords": "fechamento mensal dre lucro caixa relatório", "kind": "financeiro", "href": "#closeout-panel", "tab": "summary-tab", "create": "", "query": "", "module": ""},
        ])
    if can_manage_access:
        command_palette.extend([
            {"label": "Acessos da equipe", "keywords": "usuario senha convite permissao acesso equipe admin", "kind": "admin", "href": "#access-management-panel", "tab": "access-tab", "create": "", "query": "", "module": ""},
            {"label": "Backup do sistema", "keywords": "backup baixar segurança dados zip", "kind": "admin", "href": url_for("download_system_backup"), "tab": "", "create": "", "query": "", "module": ""},
        ])

    list_filters = [
        {"label": "Hoje", "target": "", "query": "", "select": "", "value": "", "period": "today"},
        {"label": "Semana", "target": "", "query": "", "select": "", "value": "", "period": "week"},
        {"label": "Pendente", "target": "", "query": "", "select": "event-status-filter", "value": "pendente_dados", "period": ""},
        {"label": "Pago", "target": "", "query": "", "select": "event-status-filter", "value": "pago", "period": ""},
        {"label": "Atrasado", "target": "global-search", "query": "vencido", "select": "global-search-module", "value": "financeiro" if can_view_finance else "", "period": ""},
        {"label": "Banheiros", "target": "equipment-filter", "query": "", "select": "equipment-family-filter", "value": "banheiros", "period": ""},
        {"label": "Apoio", "target": "equipment-filter", "query": "", "select": "equipment-family-filter", "value": "apoio", "period": ""},
    ]

    priority_groups = [
        {
            "label": "Agora",
            "tone": "danger" if open_alerts or overdue_count or warehouse_counts.get("zero") else "ready",
            "detail": f"{open_alerts + overdue_count + int(warehouse_counts.get('zero') or 0)} ponto(s) para resolver antes do restante.",
            "actions": [
                {"label": "Pendências", "href": "#attention-now-panel", "tab": "summary-tab"},
                {"label": "Cobranças", "href": quick_finance_href, "tab": "summary-tab"},
                {"label": "Estoque crítico", "href": "#warehouse-pane", "tab": "warehouse-tab"},
            ],
        },
        {
            "label": "Hoje",
            "tone": "primary",
            "detail": f"{len(today_events)} evento(s) hoje e {len(week_events)} na semana.",
            "actions": [
                {"label": "Foco do dia", "href": "#day-focus-panel", "tab": "summary-tab"},
                {"label": "Criar locação", "href": "#quick-rental-panel", "tab": "summary-tab"},
                {"label": "Gerar rota/PDF", "href": "#operations-pane", "tab": "operations-tab"},
            ],
        },
        {
            "label": "Depois",
            "tone": "default",
            "detail": "Consulta, histórico e relatórios ficam recolhidos para não poluir a rotina.",
            "actions": [
                {"label": "Agenda", "href": "#agenda-pane", "tab": "agenda-tab"},
                {"label": "Histórico", "href": "#history-pane", "tab": "history-tab"},
                {"label": "Relatórios", "href": "#reports-panel", "tab": "summary-tab"},
            ],
        },
    ]
    if can_manage_access:
        priority_groups.append(
            {
                "label": "Admin",
                "tone": "admin",
                "detail": "Acessos e homologação ficam visíveis, mas fora do caminho principal.",
                "actions": [
                    {"label": "Acessos", "href": "#access-management-panel", "tab": "access-tab"},
                    {"label": "Homologação", "href": "#homologation-pane", "tab": "homologation-tab"},
                    {"label": "Backup", "href": url_for("download_system_backup"), "tab": ""},
                ],
            }
        )

    day_focus = {
        "summary": "Modo foco do dia: abrir só o que precisa de ação, gerar PDF e deixar o restante recolhido.",
        "metrics": [
            {"label": "Eventos hoje", "value": len(today_events), "level": "primary"},
            {"label": "Alertas", "value": open_alerts, "level": "danger" if open_alerts else "ready"},
            {"label": "Vencidas", "value": overdue_count if can_view_finance else "-", "level": "danger" if overdue_count else "ready"},
            {"label": "Estoque", "value": stock_attention_count, "level": "warning" if stock_attention_count else "ready"},
        ],
        "actions": [
            {"label": "Resolver pendências", "detail": "Comece pelo que pode travar a rotina.", "href": "#attention-now-panel", "tab": "summary-tab"},
            {"label": "Eventos de hoje", "detail": f"{len(today_events)} evento(s) no dia.", "href": "#daily-command-center", "tab": "summary-tab"},
            {"label": "Gerar rota/PDF", "detail": "Preparar material impresso e links.", "href": "#operations-pane", "tab": "operations-tab"},
            {"label": "Cobranças", "detail": quick_finance_detail, "href": quick_finance_href, "tab": "summary-tab"},
        ],
    }

    quick_drawer_actions = [
        {"label": "Editar cliente", "detail": "Abre cadastro compacto com campos principais primeiro.", "href": "#clients-pane", "tab": "clients-tab", "create": "manual-client-form"},
        {"label": "Editar evento", "detail": "Abre criação/edição com checklist e financeiro recolhidos.", "href": "#events-pane", "tab": "events-tab", "create": "event-create-panel"},
        {"label": "Editar banheiro/equipamento", "detail": "Abre cadastro com placa opcional e status operacional.", "href": "#fleet-pane", "tab": "fleet-tab", "create": "equipment-create-panel"},
        {"label": "Novo orçamento", "detail": "Registra pedido comercial sem sair da rotina.", "href": "#contracts-quotes-panel", "tab": "clients-tab", "create": ""},
        {"label": "Pagamento rápido", "detail": quick_finance_detail, "href": quick_finance_href, "tab": "summary-tab", "create": ""},
    ]

    collapsible_panels = [
        {"label": "Anexos", "href": "#attachments-panel", "tab": "clients-tab"},
        {"label": "Histórico de clientes", "href": "#customer-history", "tab": "clients-tab"},
        {"label": "Histórico de equipamentos", "href": "#equipment-history-panel", "tab": "fleet-tab"},
        {"label": "Busca completa", "href": "#global-search-panel", "tab": "summary-tab"},
    ]

    batch_actions = [
        {"label": "Copiar resumo", "action": "copy"},
        {"label": "Destacar selecionados", "action": "highlight"},
        {"label": "Abrir primeiro", "action": "open-first"},
        {"label": "Abrir exportações", "action": "exports"},
        {"label": "Limpar seleção", "action": "clear"},
    ]

    archive_defaults = [
        {"label": "Eventos antigos concluídos", "detail": "Ficam escondidos no modo enxuto e voltam em Mostrar arquivados."},
        {"label": "Cobranças pagas", "detail": "Pagas saem da rotina principal para reduzir ruído."},
        {"label": "Listas resolvidas", "detail": "Itens concluídos continuam acessíveis por busca, filtro ou relatório."},
    ]

    smart_form_modes = [
        {"label": "Essencial", "detail": "Cliente, endereço, data, banheiro, quantidade e valor aparecem primeiro."},
        {"label": "Mensal", "detail": "Ao escolher cliente fixo, cobrança mensal e limpeza semanal já ficam sugeridas."},
        {"label": "Avançado sob demanda", "detail": "NF, anexos, observações e campos raros ficam recolhidos até precisar."},
    ]

    create_permissions = {
        "manual-client-form": "clients.edit",
        "event-create-panel": "events.create",
        "equipment-create-panel": "inventory.edit",
    }

    def action_is_visible(action: dict) -> bool:
        tab = clean_text(action.get("tab"))
        if tab and not profile_ui["tab_buttons"].get(tab, False):
            return False
        module = clean_text(action.get("module"))
        if module == "finance" and not can_view_finance:
            return False
        if module == "admin" and not can_manage_access:
            return False
        permission = clean_text(action.get("permission"))
        if permission and not has_permission(user, permission):
            return False
        create_target = clean_text(action.get("create"))
        if create_target and not has_permission(user, create_permissions.get(create_target, "dashboard.view")):
            return False
        href = clean_text(action.get("href"))
        label = clean_text(action.get("label")).lower()
        if "financeiro" in label or "receb" in label or "pagamento" in label or "cobran" in label or href == "#receivables-panel":
            return can_view_finance
        if "cliente" in label and any(word in label for word in ("novo", "criar", "editar")):
            return profile_ui["can_create_client"]
        if "locação" in label or "locacao" in label or ("evento" in label and any(word in label for word in ("novo", "criar", "editar"))):
            return has_permission(user, "events.create") and profile_ui["tabs"]["events"]
        if "orçamento" in label and any(word in label for word in ("novo", "criar", "salvar")):
            return has_permission(user, "clients.edit") and profile_ui["tabs"]["clients"]
        if "equipamento" in label and any(word in label for word in ("novo", "criar", "editar")):
            return has_permission(user, "inventory.edit") and profile_ui["tabs"]["fleet"]
        if "backup" in label or href == url_for("download_system_backup"):
            return can_manage_access
        if href == url_for("download_daily_closeout"):
            return has_permission(user, "events.close")
        if label == "relatórios" or label == "relatórios completos":
            return role in {"admin", "financeiro", "leitura"}
        return True

    def filter_actions(actions: list[dict]) -> list[dict]:
        return [action for action in actions if action_is_visible(action)]

    def filter_menu_groups(groups: list[dict]) -> list[dict]:
        visible_groups = []
        for group in groups:
            visible_items = filter_actions(group.get("items") or [])
            if visible_items:
                visible_groups.append({**group, "items": visible_items})
        return visible_groups

    role_view = {**role_view, "actions": filter_actions(role_view.get("actions") or [])}
    menu_groups = filter_menu_groups(menu_groups)
    nav_groups = [item for group in menu_groups for item in group.get("items", [])]
    primary_actions = filter_actions(primary_actions)
    sticky_actions = filter_actions(sticky_actions)
    more_actions = filter_actions(more_actions)
    search_shortcuts = [item for item in search_shortcuts if action_is_visible({"label": item.get("label"), "href": item.get("target_href"), "tab": item.get("target_tab")})]
    command_palette = filter_actions(command_palette)
    quick_drawer_actions = filter_actions(quick_drawer_actions)
    collapsible_panels = filter_actions(collapsible_panels)
    for group in priority_groups:
        group["actions"] = filter_actions(group.get("actions") or [])
    priority_groups = [group for group in priority_groups if group.get("actions")]
    day_focus = {**day_focus, "actions": filter_actions(day_focus.get("actions") or [])}

    return {
        "menu_groups": menu_groups,
        "nav_groups": nav_groups,
        "role_view": role_view,
        "primary_actions": primary_actions,
        "sticky_actions": sticky_actions,
        "more_actions": more_actions,
        "priority_groups": priority_groups,
        "day_focus": day_focus,
        "quick_drawer_actions": quick_drawer_actions,
        "collapsible_panels": collapsible_panels,
        "command_palette": command_palette,
        "batch_actions": batch_actions,
        "archive_defaults": archive_defaults,
        "smart_form_modes": smart_form_modes,
        "search_shortcuts": search_shortcuts,
        "list_filters": list_filters,
        "today_iso": today_text,
        "week_end_iso": week_end.isoformat(),
        "bathroom_total": bathroom_total,
        "support_total": support_total,
        "pdf_package": {
            "ready": has_pdf,
            "status": "PDF pronto" if has_pdf else "Aguardando rota",
            "detail": "Rota, ordem de serviço, endereços e fechamento reunidos para imprimir ou enviar.",
        },
    }


def build_reports_hub(
    *,
    can_view_finance: bool,
    clients: list[dict],
    events: list[dict],
    vehicles: list[dict],
    equipment: list[dict],
    warehouse_dashboard: dict,
    financial_management: dict,
) -> list[dict]:
    reports = [
        {
            "label": "Clientes",
            "detail": f"{len(clients)} cadastro(s)",
            "status": "pronto" if clients else "sem dados",
            "target_href": "#clients-pane",
            "target_tab": "clients-tab",
            "pdf_href": url_for("download_module_pdf", module="clients"),
            "xlsx_href": url_for("download_module_xlsx", module="clients"),
        },
        {
            "label": "Eventos",
            "detail": f"{len(events)} evento(s)",
            "status": "pronto" if events else "sem dados",
            "target_href": "#events-pane",
            "target_tab": "events-tab",
            "pdf_href": url_for("download_module_pdf", module="events"),
            "xlsx_href": url_for("download_module_xlsx", module="events"),
        },
        {
            "label": "Frota",
            "detail": f"{len(vehicles)} veículo(s)",
            "status": "pronto" if vehicles else "sem dados",
            "target_href": "#fleet-pane",
            "target_tab": "fleet-tab",
            "pdf_href": url_for("download_module_pdf", module="vehicles"),
            "xlsx_href": url_for("download_module_xlsx", module="vehicles"),
        },
        {
            "label": "Equipamentos",
            "detail": f"{len(equipment)} equipamento(s)",
            "status": "pronto" if equipment else "sem dados",
            "target_href": "#fleet-pane",
            "target_tab": "fleet-tab",
            "pdf_href": url_for("download_module_pdf", module="equipment"),
            "xlsx_href": url_for("download_module_xlsx", module="equipment"),
        },
        {
            "label": "Almoxarifado",
            "detail": f"{warehouse_dashboard.get('counts', {}).get('total', 0)} material(is)",
            "status": "atenção" if warehouse_dashboard.get("counts", {}).get("low") or warehouse_dashboard.get("counts", {}).get("zero") else "pronto",
            "target_href": "#warehouse-pane",
            "target_tab": "warehouse-tab",
            "pdf_href": url_for("download_warehouse_pdf"),
            "xlsx_href": url_for("download_module_xlsx", module="warehouse"),
            "extra_href": url_for("download_warehouse_low_stock_pdf"),
            "extra_label": "Estoque baixo",
        },
    ]
    if can_view_finance:
        reports.extend(
            [
                {
                    "label": "Financeiro",
                    "detail": f"{len(financial_management.get('receivables', []))} lançamento(s) recentes",
                    "status": "atenção" if financial_management.get("overdue") else "pronto",
                    "target_href": "#receivables-panel",
                    "target_tab": "summary-tab",
                    "pdf_href": url_for("download_module_pdf", module="financial"),
                    "xlsx_href": url_for("download_module_xlsx", module="financial"),
                },
                {
                    "label": "Inadimplência",
                    "detail": f"{len(financial_management.get('overdue', []))} vencido(s)",
                    "status": "atenção" if financial_management.get("overdue") else "pronto",
                    "target_href": "#receivables-panel",
                    "target_tab": "summary-tab",
                    "pdf_href": url_for("download_module_pdf", module="financial"),
                    "xlsx_href": url_for("download_module_xlsx", module="financial"),
                },
            ]
        )
    return reports


def build_daily_management_checklist(
    *,
    attention_center: dict,
    guided_operation_flow: dict,
    system_status: dict,
    security_posture: dict,
    can_view_finance: bool,
    can_manage_access: bool,
) -> list[dict]:
    items = [
        {
            "label": "Resolver pendências críticas",
            "done": attention_center.get("danger_total", 0) == 0,
            "detail": f"{attention_center.get('danger_total', 0)} crítico(s) aberto(s).",
            "target_tab": "summary-tab",
            "target_href": "#attention-now-panel",
        },
        {
            "label": "Conferir roteiro operacional",
            "done": guided_operation_flow.get("pending", 0) == 0,
            "detail": f"{guided_operation_flow.get('ready', 0)}/{guided_operation_flow.get('total', 0)} etapa(s) prontas.",
            "target_tab": "summary-tab",
            "target_href": "#guided-operation-flow",
        },
        {
            "label": "Gerar ou revisar backup",
            "done": bool(system_status.get("health", {}).get("has_recent_backup")),
            "detail": "Backup registrado." if system_status.get("health", {}).get("has_recent_backup") else "Backup ainda pendente.",
            "target_tab": "summary-tab",
            "target_href": "#system-readiness-panel",
        },
    ]
    if can_manage_access:
        items.append({
            "label": "Revisar senhas pendentes",
            "done": security_posture.get("password_rotation_pending", 0) == 0,
            "detail": f"{security_posture.get('password_rotation_pending', 0)} troca(s) pendente(s).",
            "target_tab": "access-tab",
            "target_href": "#access-pane",
        })
    if can_view_finance:
        items.append(
            {
                "label": "Conferir financeiro do dia",
                "done": attention_center.get("danger_total", 0) == 0,
                "detail": "Verificar vencidos e recebimentos antes do fechamento.",
                "target_tab": "summary-tab",
                "target_href": "#receivables-panel",
            }
        )
    return items


def build_operational_kanban(quotes: list[dict], financial_management: dict, events: list[dict], inventory: list[dict]) -> list[dict]:
    columns = [
        {"key": "rascunho", "title": "Rascunho", "items": []},
        {"key": "pagamento", "title": "Aguardando pagamento", "items": []},
        {"key": "separar", "title": "Separar equipamento", "items": []},
        {"key": "rota", "title": "Em rota", "items": []},
        {"key": "instalado", "title": "Instalado", "items": []},
        {"key": "retirar", "title": "Retirar", "items": []},
        {"key": "concluido", "title": "Concluído", "items": []},
    ]
    by_key = {column["key"]: column for column in columns}
    for quote in quotes[:8]:
        by_key["rascunho"]["items"].append({"title": clean_text(quote.get("customer_name")), "detail": f"{quote.get('equipment_quantity')}x {quote.get('equipment_type')}", "badge": clean_text(quote.get("status"), "novo")})
    for receivable in financial_management.get("overdue", [])[:8]:
        by_key["pagamento"]["items"].append({"title": clean_text(receivable.get("client_name")), "detail": f"{format_currency_br(receivable.get('open_amount'))} vencido", "badge": f"{receivable.get('days_overdue')} dia(s)"})
    for event in events:
        status = clean_text(event.get("status"), "rascunho")
        normalized_status = normalize_event_status(status)
        if normalized_status == "rascunho":
            by_key["rascunho"]["items"].append({"title": clean_text(event.get("title")), "detail": clean_text(event.get("event_date")), "badge": event_status_label(status)})
        elif normalized_status in {"confirmado", "pendente_dados", "rota_pendente", "os_pendente", "programado"}:
            by_key["separar"]["items"].append({"title": clean_text(event.get("title")), "detail": clean_text(event.get("event_date")), "badge": f"{event.get('equipment_count', 0)} equip."})
        elif normalized_status == "em_andamento":
            by_key["rota"]["items"].append({"title": clean_text(event.get("title")), "detail": clean_text(event.get("event_date")), "badge": event_status_label(status)})
        elif normalized_status in {"concluido", "pago"}:
            by_key["concluido"]["items"].append({"title": clean_text(event.get("title")), "detail": clean_text(event.get("event_date")), "badge": event_status_label(status)})
    for item in inventory:
        status = clean_text(item.get("status"))
        if status == "instalado":
            by_key["instalado"]["items"].append({"title": clean_text(item.get("equipment_id")), "detail": clean_text(item.get("linked_client_name")), "badge": clean_text(item.get("equipment_type"))})
        elif status == "retirada_pendente":
            by_key["retirar"]["items"].append({"title": clean_text(item.get("equipment_id")), "detail": clean_text(item.get("linked_client_name")), "badge": "retirar"})
    for column in columns:
        column["items"] = column["items"][:8]
    return columns


def build_equipment_history(equipment: list[dict], clients: list[dict], route_history: list[dict], service_log: list[dict]) -> list[dict]:
    clients_by_equipment: dict[str, list[str]] = {}
    for client in clients:
        equipment_id = clean_text(client.get("equipment_number"))
        if equipment_id:
            clients_by_equipment.setdefault(equipment_id, []).append(clean_text(client.get("customer_name")) or clean_text(client.get("client_id")))
    routes_by_equipment: dict[str, list[dict]] = {}
    for run in route_history:
        for route in run.get("routes", []) or []:
            for stop in route.get("stops", []) or []:
                equipment_id = clean_text(stop.get("equipment_number"))
                if equipment_id:
                    routes_by_equipment.setdefault(equipment_id, []).append({"date": clean_text(run.get("generated_at")), "client": clean_text(stop.get("customer_name")), "vehicle": clean_text(route.get("vehicle_id"))})
    cleanings_by_equipment: dict[str, int] = {}
    for item in service_log:
        equipment_id = clean_text(item.get("equipment_id"))
        if equipment_id:
            cleanings_by_equipment[equipment_id] = cleanings_by_equipment.get(equipment_id, 0) + 1
    rows = []
    for item in equipment:
        equipment_id = clean_text(item.get("equipment_id"))
        rows.append({
            "equipment_id": equipment_id,
            "equipment_type": clean_text(item.get("equipment_type")),
            "status": clean_text(item.get("status")),
            "plate": clean_text(item.get("plate")),
            "photo_url": clean_text(item.get("photo_url")),
            "current_clients": clients_by_equipment.get(equipment_id, []),
            "routes": routes_by_equipment.get(equipment_id, [])[:4],
            "cleanings": cleanings_by_equipment.get(equipment_id, 0),
            "maintenance_reason": clean_text(item.get("maintenance_reason")),
        })
    return rows[:20]


def build_operational_memory_dashboard(
    *,
    clients: list[dict],
    events: list[dict],
    equipment: list[dict],
    vehicles: list[dict],
    contracts: list[dict],
    quotes: list[dict],
    attachments: list[dict],
    service_log: list[dict],
    route_history: list[dict],
    field_confirmations: list[dict],
    financial_management: dict,
    customer_history: list[dict],
    equipment_history: list[dict],
    recent_audit_log: list[dict],
    warehouse_dashboard: dict,
    settings: dict,
    global_search_items: list[dict],
    can_view_finance: bool,
) -> dict:
    today = datetime.now().date()
    today_text = today.isoformat()
    events_by_client: dict[str, list[dict]] = {}
    for event in events:
        for client_id in event.get("client_ids") or []:
            events_by_client.setdefault(clean_text(client_id), []).append(event)

    attachments_by_client: dict[str, list[dict]] = {}
    for attachment in attachments:
        client_id = clean_text(attachment.get("client_id"))
        if client_id:
            attachments_by_client.setdefault(client_id, []).append(attachment)

    receivables = financial_management.get("receivables", []) if can_view_finance else []
    finance_by_client: dict[str, dict] = {}
    for row in financial_management.get("client_finance", []) if can_view_finance else []:
        key = clean_text(row.get("client_id")) or clean_text(row.get("client_name"))
        finance_by_client[key] = row
        if clean_text(row.get("client_name")):
            finance_by_client[clean_text(row.get("client_name"))] = row

    client_history_map = {clean_text(item.get("client_id")): item for item in customer_history}
    client_rows = []
    for client in clients:
        client_id = clean_text(client.get("client_id"))
        history = client_history_map.get(client_id, {})
        related_events = events_by_client.get(client_id, [])
        finance = finance_by_client.get(client_id) or finance_by_client.get(clean_text(client.get("customer_name"))) or {}
        missing = []
        if not clean_text(client.get("phone")):
            missing.append("telefone")
        if not clean_text(client.get("address")):
            missing.append("endereço")
        if not clean_text(client.get("contact_name")):
            missing.append("contato")
        if not clean_text(client.get("equipment_type")):
            missing.append("tipo de banheiro/equipamento")
        if can_view_finance and parse_decimal(finance.get("open")) > 0:
            missing.append("financeiro aberto")
        last_dates = [
            clean_text(history.get("last_route_at")),
            *[clean_text(event.get("event_date")) for event in related_events],
            *[clean_text(item.get("created_at")) for item in attachments_by_client.get(client_id, [])],
        ]
        last_touch = max([value for value in last_dates if value], default="")
        if missing:
            next_action = f"Completar {missing[0]}"
        elif not attachments_by_client.get(client_id):
            next_action = "Anexar contrato/comprovante"
        elif can_view_finance and parse_decimal(finance.get("open")) > 0:
            next_action = "Resolver financeiro"
        else:
            next_action = "Manter histórico atualizado"
        client_rows.append({
            "client_id": client_id,
            "name": clean_text(client.get("customer_name")) or client_id,
            "address": clean_text(client.get("address")),
            "events": len(related_events),
            "routes": int(history.get("routes_count") or 0),
            "attachments": len(attachments_by_client.get(client_id, [])),
            "open_amount": round2(finance.get("open") or 0),
            "last_touch": last_touch,
            "missing": missing,
            "next_action": next_action,
            "target_tab": "clients-tab",
            "target_href": f"#client-{client_id}",
        })
    client_rows.sort(key=lambda item: (len(item["missing"]), item["open_amount"], item["events"], item["routes"]), reverse=True)

    equipment_rows = []
    equipment_history_by_id = {clean_text(item.get("equipment_id")): item for item in equipment_history}
    for item in equipment:
        equipment_id = clean_text(item.get("equipment_id"))
        history = equipment_history_by_id.get(equipment_id, {})
        route_items = history.get("routes", [])
        last_route = max([clean_text(route.get("date")) for route in route_items if clean_text(route.get("date"))], default="")
        maintenance_reason = clean_text(item.get("maintenance_reason")) or clean_text(history.get("maintenance_reason"))
        if maintenance_reason or clean_text(item.get("status")) in {"manutencao", "indisponivel"}:
            next_action = "Resolver manutenção"
        elif equipment_family(item.get("equipment_type")) == "banheiro_luxo" and not clean_text(item.get("plate")):
            next_action = "Conferir placa"
        elif not route_items and not history.get("current_clients"):
            next_action = "Vincular a cliente/evento"
        else:
            next_action = "Histórico em uso"
        equipment_rows.append({
            "equipment_id": equipment_id,
            "equipment_type": clean_text(item.get("equipment_type")),
            "status": clean_text(item.get("status")),
            "plate": clean_text(item.get("plate")),
            "routes": len(route_items),
            "cleanings": int(history.get("cleanings") or 0),
            "current_clients": history.get("current_clients", []),
            "last_route": last_route,
            "maintenance_reason": maintenance_reason,
            "next_action": next_action,
            "target_tab": "fleet-tab",
            "target_href": f"#equipment-{equipment_id}",
        })
    equipment_rows.sort(key=lambda item: (1 if item["maintenance_reason"] else 0, 1 if item["next_action"] != "Histórico em uso" else 0, item["routes"]), reverse=True)

    pending_context = []
    for client in client_rows:
        if client["missing"]:
            pending_context.append({
                "level": "warning",
                "area": "Cliente",
                "title": client["name"],
                "reason": f"Falta {', '.join(client['missing'][:3])}",
                "owner": "Administrativo",
                "age": client["last_touch"] or "sem histórico",
                "target_tab": client["target_tab"],
                "target_href": client["target_href"],
            })
    for event in events:
        missing = []
        if not event.get("client_ids"):
            missing.append("cliente")
        if not event.get("vehicle_ids"):
            missing.append("veículo")
        if any(not checklist.get("done") for checklist in event.get("checklist", []) or []):
            missing.append("checklist")
        event_date = parse_date(event.get("event_date"))
        if missing:
            level = "danger" if event_date and 0 <= (event_date - today).days <= 2 else "warning"
            pending_context.append({
                "level": level,
                "area": "Evento",
                "title": clean_text(event.get("title")) or clean_text(event.get("event_id")),
                "reason": f"Revisar {', '.join(missing)}",
                "owner": "Operação",
                "age": clean_text(event.get("event_date")) or "sem data",
                "target_tab": "events-tab",
                "target_href": f"#event-{clean_text(event.get('event_id'))}",
            })
    if can_view_finance:
        for item in financial_management.get("overdue", [])[:8]:
            pending_context.append({
                "level": "danger",
                "area": "Financeiro",
                "title": clean_text(item.get("client_name")) or clean_text(item.get("id")),
                "reason": f"{format_currency_br(item.get('open_amount'))} vencido há {item.get('days_overdue', 0)} dia(s)",
                "owner": "Financeiro",
                "age": clean_text(item.get("due_date")),
                "target_tab": "summary-tab",
                "target_href": "#receivables-panel",
            })
    for item in warehouse_dashboard.get("items", [])[:12]:
        if item.get("stock_status") in {"baixo", "zerado"}:
            pending_context.append({
                "level": "danger" if item.get("stock_status") == "zerado" else "warning",
                "area": "Almoxarifado",
                "title": clean_text(item.get("name")),
                "reason": f"{item.get('stock_status_label')} com {item.get('quantity_current')} {item.get('unit')}",
                "owner": "Estoque",
                "age": clean_text(item.get("updated_at")) or "saldo atual",
                "target_tab": "warehouse-tab",
                "target_href": "#warehouse-pane",
            })
    pending_context.sort(key=lambda item: 0 if item["level"] == "danger" else 1)

    today_events = [
        event for event in events
        if clean_text(event.get("event_date")) <= today_text <= (clean_text(event.get("event_end_date")) or clean_text(event.get("event_date")))
    ]
    today_receivables = [
        item for item in receivables
        if clean_text(item.get("due_date")) == today_text and clean_text(item.get("status")) != "pago"
    ]
    daily_recall = [
        {
            "label": "Eventos lembrados hoje",
            "value": len(today_events),
            "detail": "agenda e permanência do dia",
            "target_tab": "agenda-tab",
            "target_href": "#agenda-pane",
        },
        {
            "label": "Cobranças lembradas hoje",
            "value": len(today_receivables) if can_view_finance else 0,
            "detail": "vencimentos abertos" if can_view_finance else "visível para financeiro",
            "target_tab": "summary-tab",
            "target_href": "#receivables-panel",
        },
        {
            "label": "Pendências com contexto",
            "value": len(pending_context),
            "detail": "com responsável e motivo",
            "target_tab": "summary-tab",
            "target_href": "#operational-memory-panel",
        },
        {
            "label": "Itens pesquisáveis",
            "value": len(global_search_items),
            "detail": "clientes, placas, anexos e financeiro",
            "target_tab": "summary-tab",
            "target_href": "#global-search-panel",
        },
    ]

    audit_count = len(load_audit_log())
    memory_coverage = [
        {"label": "Clientes com linha do tempo", "value": sum(1 for item in client_rows if item["events"] or item["routes"] or item["attachments"]), "total": len(clients)},
        {"label": "Banheiros/equipamentos com histórico", "value": sum(1 for item in equipment_rows if item["routes"] or item["cleanings"] or item["current_clients"]), "total": len(equipment)},
        {"label": "Anexos ligados ao negócio", "value": len([item for item in attachments if clean_text(item.get("client_id")) or clean_text(item.get("event_id"))]), "total": len(attachments)},
        {"label": "Alterações auditadas", "value": len(recent_audit_log), "total": min(audit_count, 1000)},
        {"label": "Registros pesquisáveis", "value": len(global_search_items), "total": len(global_search_items)},
    ]

    decision_log = [
        {
            "module": clean_text(item.get("module"), "sistema"),
            "action": clean_text(item.get("action"), "ação"),
            "target": clean_text(item.get("target_id")) or clean_text(item.get("detail")),
            "user": clean_text(item.get("user_email")) or clean_text(item.get("user_id")),
            "created_at": clean_text(item.get("created_at")),
            "detail": clean_text(item.get("detail")),
        }
        for item in recent_audit_log[:8]
    ]

    observation_templates = [
        {
            "label": "Pendência operacional",
            "fields": ["motivo", "responsável", "prazo", "próximo passo"],
            "example": "Cliente pediu trocar horário; responsável: operação; revisar até hoje.",
        },
        {
            "label": "Manutenção",
            "fields": ["banheiro/equipamento", "problema", "custo previsto", "liberação"],
            "example": "TRL-001 com revisão elétrica; liberar após manutenção.",
        },
        {
            "label": "Financeiro",
            "fields": ["valor", "vencimento", "forma", "comprovante/NF"],
            "example": "Pagamento parcial via Pix; anexar comprovante e emitir NF.",
        },
        {
            "label": "Cliente/endereço",
            "fields": ["acesso", "contato", "restrição", "preferência"],
            "example": "Entrada pela portaria lateral; falar com responsável antes de despachar.",
        },
    ]

    finance_memory = {
        "visible": can_view_finance,
        "open_total": round2(sum(parse_decimal(item.get("open")) for item in financial_management.get("client_finance", []))) if can_view_finance else 0,
        "overdue_count": len(financial_management.get("overdue", [])) if can_view_finance else 0,
        "receivables_count": len(receivables),
        "paid_count": len(financial_management.get("receivables_paid", [])) if can_view_finance else 0,
        "closeouts_count": len(financial_management.get("closeouts", [])) if can_view_finance else 0,
        "invoice_missing": financial_management.get("invoice_summary", {}).get("sem_nota", 0) if can_view_finance else 0,
    }

    backup_memory = {
        "last_backup": clean_text(settings.get("last_backup_at")),
        "last_closeout": clean_text(settings.get("last_closeout_at")),
        "audit_count": audit_count,
        "recent_changes": len(recent_audit_log),
    }

    return {
        "daily_recall": daily_recall,
        "coverage": memory_coverage,
        "client_memory": client_rows[:8],
        "equipment_memory": equipment_rows[:8],
        "pending_context": pending_context[:10],
        "decision_log": decision_log,
        "observation_templates": observation_templates,
        "finance_memory": finance_memory,
        "backup_memory": backup_memory,
        "counts": {
            "clients": len(clients),
            "events": len(events),
            "equipment": len(equipment),
            "vehicles": len(vehicles),
            "contracts": len(contracts),
            "quotes": len(quotes),
            "attachments": len(attachments),
            "routes": len(route_history),
            "cleanings": len(service_log),
            "confirmations": len(field_confirmations),
            "searchable": len(global_search_items),
        },
    }


def build_service_order_pdf(event: dict, clients: list[dict], vehicles: list[dict], equipment: list[dict]) -> bytes:
    client_map = {clean_text(item.get("client_id")): item for item in clients}
    vehicle_map = {clean_text(item.get("vehicle_id")): item for item in vehicles}
    equipment_map = {clean_text(item.get("equipment_id")): item for item in equipment}
    lines = [
        f"Evento: {event.get('event_id')} - {event.get('title')}",
        f"Período: {format_date_br(event.get('event_date'))} até {format_date_br(event.get('event_end_date') or event.get('event_date'))}",
        f"Status: {event.get('status')}",
        f"Observações: {event.get('notes') or 'n/d'}",
        "",
        "Clientes e equipamentos:",
    ]
    for client_id in event.get("client_ids", []) or []:
        client = client_map.get(clean_text(client_id), {})
        equipment_item = equipment_map.get(clean_text(client.get("equipment_number")), {})
        address = clean_text(client.get("address"))
        lines.append(
            f"- {client.get('customer_name') or client_id} | {address or 'sem endereço'} | "
            f"{client.get('phone') or 'sem telefone'} | {client.get('equipment_quantity') or 1}x {client.get('equipment_type') or 'Equipamento'} | "
            f"{client.get('equipment_number') or 'sem ID'} | placa {equipment_item.get('plate') or 'n/d'}"
        )
        if address:
            maps_url = "https://www.google.com/maps/search/?" + urllib.parse.urlencode({"api": "1", "query": address})
            lines.append(f"  Link de endereço: {maps_url}")
    lines.append("")
    lines.append("Veículos:")
    for vehicle_id in event.get("vehicle_ids", []) or []:
        vehicle = vehicle_map.get(clean_text(vehicle_id), {})
        lines.append(f"- {vehicle_id} | {vehicle.get('vehicle_type') or 'veículo'} | placa {vehicle.get('plate') or 'n/d'}")
    lines.extend([
        "",
        "Checklist para imprimir/conferir:",
        "- Confirmar cliente, endereço e contato antes da saída da base.",
        "- Conferir ID dos banheiros/equipamentos e placa quando existir.",
        "- Entregar link de endereço junto com a OS quando ajudar a equipe.",
        "- Registrar pendência se algo físico não bater com este documento.",
    ])
    return build_simple_text_pdf(f"SannyGold - Ordem de Serviço {event.get('event_id')}", lines)


def build_calendar_weeks(events: list[dict], horizon_days: int = 35) -> list[list[dict]]:
    today = datetime.now().date()
    start = today - timedelta(days=today.weekday())
    occurrences = expand_future_occurrences(events, horizon_days=horizon_days)
    by_date: dict[str, list[dict]] = {}
    for occurrence in occurrences:
        event_date = clean_text(occurrence.get("event_date"))
        if event_date:
            status = normalize_event_status(occurrence.get("status"), "rascunho")
            by_date.setdefault(event_date, []).append(
                {
                    **occurrence,
                    "status": status,
                    "status_label": event_status_label(status),
                }
            )

    weeks = []
    current = start
    for _ in range(5):
        week = []
        for _ in range(7):
            key = current.isoformat()
            week.append(
                {
                    "date": key,
                    "label": current.strftime("%d/%m"),
                    "is_today": current == today,
                    "events": by_date.get(key, [])[:4],
                }
            )
            current += timedelta(days=1)
        weeks.append(week)
    return weeks


def address_region_label(address: str | None) -> str:
    text = clean_text(address)
    if not text:
        return "não informado"
    normalized = text.replace(" - ", ",").replace(" -", ",").replace("- ", ",")
    parts = [clean_text(part) for part in normalized.split(",") if clean_text(part)]
    if len(parts) >= 4:
        return f"{parts[-3]} / {parts[-2]}"
    if len(parts) >= 2:
        return f"{parts[-2]} / {parts[-1]}"
    return parts[0]


def build_operational_agenda(events: list[dict], clients: list[dict], vehicles: list[dict], audit_log: list[dict]) -> dict:
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    month_start = today.replace(day=1)
    month_end = add_months(month_start, 1) - timedelta(days=1)
    service_order_generated = {
        clean_text(item.get("target_id"))
        for item in audit_log
        if clean_text(item.get("action")) == "generate_service_order" and clean_text(item.get("module")) == "events"
    }
    clients_by_id = {clean_text(client.get("client_id")): client for client in clients if clean_text(client.get("client_id"))}
    vehicles_by_id = {clean_text(vehicle.get("vehicle_id")): vehicle for vehicle in vehicles if clean_text(vehicle.get("vehicle_id"))}

    occurrences = []
    seen_occurrences: set[tuple[str, str]] = set()
    for event in events:
        event_date = event_start_date(event)
        if not event_date:
            continue
        occurrence = {
            **event,
            "occurrence_id": f"{clean_text(event.get('event_id'))}:{event_date.isoformat()}",
            "occurrence_date": event_date.isoformat(),
            "occurrence_end_date": (event_end_date(event) or event_date).isoformat(),
            "is_virtual_occurrence": False,
            "source_event_id": clean_text(event.get("event_id")),
        }
        occurrences.append(occurrence)
        seen_occurrences.add((clean_text(event.get("event_id")), event_date.isoformat()))

    for occurrence in expand_future_occurrences(events, horizon_days=60):
        if not occurrence.get("is_virtual_occurrence"):
            continue
        key = (clean_text(occurrence.get("source_event_id") or occurrence.get("event_id")), clean_text(occurrence.get("occurrence_date") or occurrence.get("event_date")))
        if key in seen_occurrences:
            continue
        occurrences.append(occurrence)
        seen_occurrences.add(key)

    def safe_int(value) -> int:
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

    def option_rows(values: set[str]) -> list[dict]:
        return [{"value": value, "label": value} for value in sorted(value for value in values if value)]

    agenda_items = []
    status_options: set[str] = set()
    service_options: set[str] = set()
    responsible_options: set[str] = set()
    client_options: set[str] = set()
    region_options: set[str] = set()
    weekday_labels = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

    for occurrence in occurrences:
        occurrence_date = parse_date(occurrence.get("occurrence_date") or occurrence.get("event_date"))
        if not occurrence_date:
            continue
        linked_clients = [clients_by_id.get(clean_text(client_id)) for client_id in occurrence.get("client_ids") or []]
        linked_clients = [client for client in linked_clients if client]
        linked_vehicles = [vehicles_by_id.get(clean_text(vehicle_id)) for vehicle_id in occurrence.get("vehicle_ids") or []]
        linked_vehicles = [vehicle for vehicle in linked_vehicles if vehicle]
        client_names = [clean_text(client.get("customer_name"), clean_text(client.get("client_id"))) for client in linked_clients]
        service_labels = sorted({
            clean_text(client.get("equipment_type"))
            for client in linked_clients
            if clean_text(client.get("equipment_type"))
        })
        quantity = sum(safe_int(client.get("equipment_quantity")) for client in linked_clients)
        primary_client = client_names[0] if client_names else "sem cliente"
        service_label = ", ".join(service_labels) if service_labels else clean_text(occurrence.get("event_category"), "serviço não informado")
        service_key = service_label
        region_label = address_region_label((linked_clients[0] if linked_clients else {}).get("address"))
        responsible = clean_text(occurrence.get("responsible")) or ", ".join(clean_text(vehicle.get("driver")) for vehicle in linked_vehicles if clean_text(vehicle.get("driver"))) or "não informado"
        status = normalize_event_status(occurrence.get("status"), "rascunho")
        active_status = status not in {"concluido", "pago", "cancelado"}
        days_from_today = (occurrence_date - today).days
        pending = []
        if not linked_clients:
            pending.append("cliente não vinculado")
        if not any(clean_text(client.get("phone")) for client in linked_clients):
            pending.append("telefone do cliente ausente")
        if not any(clean_text(client.get("address")) for client in linked_clients):
            pending.append("endereço incompleto")
        if not service_labels:
            pending.append("serviço/equipamento não definido")
        if quantity <= 0:
            pending.append("quantidade não informada")
        if not clean_text(occurrence.get("responsible")):
            pending.append("responsável interno ausente")
        if parse_decimal(occurrence.get("valor_servico")) <= 0 and parse_decimal(occurrence.get("recurring_value")) <= 0:
            pending.append("valor não informado")
        if active_status and not occurrence.get("vehicle_ids"):
            pending.append("veículo não definido")
        if active_status and 0 <= days_from_today <= 7 and not clean_text(occurrence.get("last_route_generated_at")):
            pending.append("rota ainda não gerada")
        source_event_id = clean_text(occurrence.get("source_event_id") or occurrence.get("event_id"))
        if active_status and 0 <= days_from_today <= 7 and source_event_id not in service_order_generated:
            pending.append("ordem de serviço não gerada")

        item = {
            "event_id": clean_text(occurrence.get("event_id")),
            "source_event_id": source_event_id,
            "occurrence_id": clean_text(occurrence.get("occurrence_id")),
            "date": occurrence_date.isoformat(),
            "weekday": weekday_labels[occurrence_date.weekday()],
            "title": clean_text(occurrence.get("title"), "Evento sem nome"),
            "client": ", ".join(client_names) if client_names else "sem cliente",
            "client_key": primary_client,
            "service": service_label,
            "service_key": service_key,
            "quantity": quantity,
            "status": status,
            "status_label": event_status_label(status),
            "responsible": responsible,
            "responsible_key": responsible,
            "region": region_label,
            "region_key": region_label,
            "pending": pending[:6],
            "pending_count": len(pending),
            "has_pending": bool(pending),
            "pending_filter": "com_pendencia" if pending else "sem_pendencia",
            "target_href": f"#event-{source_event_id}" if source_event_id else "#events-pane",
            "is_virtual_occurrence": bool(occurrence.get("is_virtual_occurrence")),
            "filter_text": " ".join(
                [
                    clean_text(occurrence.get("event_id")),
                    clean_text(occurrence.get("title")),
                    " ".join(client_names),
                    service_label,
                    responsible,
                    region_label,
                    status,
                    " ".join(pending),
                ]
            ),
        }
        agenda_items.append(item)
        status_options.add(status)
        service_options.add(service_key)
        responsible_options.add(responsible)
        client_options.add(primary_client)
        region_options.add(region_label)

    agenda_items.sort(key=lambda item: (item["date"], item["title"]))

    view_specs = [
        ("today", "Hoje", today, today, "Eventos e locações do dia."),
        ("week", "Semana", week_start, week_end, "Semana atual, de segunda a domingo."),
        ("month", "Mês", month_start, month_end, "Mês atual com eventos previstos e já lançados."),
        ("next7", "Próximos 7 dias", today, today + timedelta(days=6), "Janela curta para despacho, rota e OS."),
        ("next30", "Próximos 30 dias", today, today + timedelta(days=29), "Visão de preparação e capacidade."),
    ]
    views = []
    for key, label, start_date, end_date, description in view_specs:
        items = [
            item for item in agenda_items
            if start_date <= parse_date(item["date"]) <= end_date
        ]
        grouped: dict[str, dict] = {}
        for item in items:
            group = grouped.setdefault(
                item["date"],
                {
                    "date": item["date"],
                    "weekday": item["weekday"],
                    "items": [],
                    "pending_count": 0,
                },
            )
            group["items"].append(item)
            group["pending_count"] += item["pending_count"]
        groups = [grouped[date_key] for date_key in sorted(grouped)]
        views.append(
            {
                "key": key,
                "label": label,
                "description": description,
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "count": len(items),
                "pending_events": sum(1 for item in items if item["has_pending"]),
                "pending_count": sum(item["pending_count"] for item in items),
                "groups": groups,
                "default_open": key in {"today", "next7"},
            }
        )

    return {
        "items": agenda_items,
        "total": len(agenda_items),
        "pending_total": sum(1 for item in agenda_items if item["has_pending"]),
        "filters": {
            "status": [{"value": value, "label": event_status_label(value)} for value in sorted(status_options)],
            "service": option_rows(service_options),
            "responsible": option_rows(responsible_options),
            "client": option_rows(client_options),
            "region": option_rows(region_options),
            "pending": [
                {"value": "com_pendencia", "label": "Com pendência"},
                {"value": "sem_pendencia", "label": "Sem pendência"},
            ],
        },
        "views": views,
    }


def build_preventive_warnings(
    clients: list[dict],
    vehicles: list[dict],
    equipment: list[dict],
    events: list[dict],
    validation_payload: dict,
    warehouse_dashboard: dict,
    has_pdf: bool,
    route_data: dict | None,
) -> list[dict]:
    warnings = []
    clients_without_coordinates = [client for client in clients if client.get("lat") is None or client.get("lng") is None]
    if clients_without_coordinates:
        warnings.append({"level": "warning", "title": "Clientes sem coordenada", "detail": f"{len(clients_without_coordinates)} cadastro(s) precisam de latitude e longitude.", "target_tab": "clients-tab", "target_href": "#clients-pane", "action": "Abrir clientes"})
    if not vehicles:
        warnings.append({"level": "danger", "title": "Nenhum veículo cadastrado", "detail": "Cadastre ao menos um veículo antes de gerar rota.", "target_tab": "fleet-tab", "target_href": "#fleet-pane", "action": "Abrir frota"})
    if not equipment:
        warnings.append({"level": "warning", "title": "Equipamentos vazios", "detail": "Cadastre equipamentos para controlar vínculo e manutenção.", "target_tab": "fleet-tab", "target_href": "#fleet-pane", "action": "Abrir equipamentos"})
    warehouse_counts = warehouse_dashboard.get("counts") or {}
    if warehouse_counts.get("zero"):
        warnings.append({"level": "danger", "title": "Almoxarifado com item zerado", "detail": f"{warehouse_counts.get('zero')} material(is) estão sem saldo.", "target_tab": "warehouse-tab", "target_href": "#warehouse-pane", "action": "Abrir almoxarifado"})
    elif warehouse_counts.get("low"):
        warnings.append({"level": "warning", "title": "Almoxarifado com estoque baixo", "detail": f"{warehouse_counts.get('low')} material(is) chegaram ao mínimo.", "target_tab": "warehouse-tab", "target_href": "#warehouse-pane", "action": "Abrir almoxarifado"})
    if route_data and not has_pdf:
        warnings.append({"level": "warning", "title": "Rota sem PDF", "detail": "Existe rota gerada, mas o PDF ainda não está disponível.", "target_tab": "operations-tab", "target_href": "#operations-pane", "action": "Gerar PDF"})

    equipment_usage: dict[str, list[str]] = {}
    for client in clients:
        equipment_id = clean_text(client.get("equipment_number"))
        if equipment_id:
            equipment_usage.setdefault(equipment_id, []).append(clean_text(client.get("customer_name")) or clean_text(client.get("client_id")))
    conflicts = {equipment_id: names for equipment_id, names in equipment_usage.items() if len(names) > 1}
    if conflicts:
        first_id, names = next(iter(conflicts.items()))
        warnings.append({"level": "danger", "title": "Equipamento duplicado", "detail": f"{first_id} aparece em {len(names)} clientes.", "target_tab": "clients-tab", "target_href": "#clients-pane", "action": "Revisar clientes"})

    blocked_ids = {
        clean_text(item.get("equipment_id"))
        for item in equipment
        if clean_text(item.get("status")) in BLOCKED_EQUIPMENT_STATUSES or clean_text(item.get("condition")) in BLOCKED_EQUIPMENT_STATUSES
    }
    blocked_linked = [equipment_id for equipment_id in blocked_ids if equipment_id and equipment_usage.get(equipment_id)]
    if blocked_linked:
        warnings.append({"level": "danger", "title": "Equipamento bloqueado em uso", "detail": f"{blocked_linked[0]} está vinculado e marcado como manutenção/indisponível.", "target_tab": "fleet-tab", "target_href": "#fleet-pane", "action": "Abrir equipamentos"})

    for event in events:
        if event_is_active(event) and not event.get("client_ids"):
            warnings.append({"level": "warning", "title": f"Evento sem cliente: {event.get('title')}", "detail": "Vincule clientes antes da validação.", "target_tab": "events-tab", "target_href": "#events-pane", "action": "Revisar evento"})
        checklist = event.get("checklist") or []
        if event_is_active(event) and checklist and any(not item.get("done") for item in checklist):
            warnings.append({"level": "warning", "title": f"Checklist pendente: {event.get('title')}", "detail": "Conclua o checklist antes da execução.", "target_tab": "events-tab", "target_href": "#events-pane", "action": "Revisar evento"})
    for item in (validation_payload.get("pending_items") or [])[:4]:
        warnings.append({"level": item.get("severity") or "warning", "title": item.get("reason_label") or pending_reason_label(item.get("reason_code", "")), "detail": item.get("reason") or item.get("client_name") or "Pendência operacional.", "target_tab": "operations-tab", "target_href": "#operations-pane", "action": "Ver validação"})
    return warnings[:8]


def build_real_map_routes(route_data: dict | None) -> list[dict]:
    if not route_data:
        return []
    map_routes = []
    for route in route_data.get("routes") or []:
        stops = route.get("stops") or []
        if not stops:
            continue
        map_routes.append(
            {
                "vehicle_id": clean_text(route.get("vehicle_id")),
                "stops_count": len(stops),
                "google_maps_url": google_maps_directions_url(stops),
                "google_maps_embed_url": google_maps_embed_directions_url(stops),
                "first_stop": stops[0],
                "last_stop": stops[-1],
            }
        )
    return map_routes


def build_daily_closeout_payload() -> dict:
    route_data = load_route_data() or {}
    route_history = load_route_history()
    confirmations = load_field_confirmations()
    inventory = build_inventory_view(load_clients(), route_data, confirmations)
    today = datetime.now().date().isoformat()
    latest = route_history[0] if route_history else {}
    return {
        "closed_at": now_iso(),
        "date": today,
        "route_summary": route_data.get("summary") or {},
        "latest_route_generated_at": latest.get("generated_at", ""),
        "financial_summary": latest.get("financial_summary") or {},
        "pending_confirmations": [
            item for item in inventory
            if item.get("status") in {"carregado", "em_rota", "instalado", "retirada_pendente"}
        ],
        "confirmations_count": len(confirmations),
    }


def build_daily_closeout_zip() -> bytes:
    payload = build_daily_closeout_payload()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("fechamento-diario.json", json.dumps(payload, indent=2, ensure_ascii=False))
        if ROUTE_JSON_PATH.exists():
            archive.write(ROUTE_JSON_PATH, "route-plan-mobile.json")
        if ROUTE_PDF_PATH.exists():
            archive.write(ROUTE_PDF_PATH, "route-plan.pdf")
    buffer.seek(0)
    return buffer.getvalue()


def build_weekly_management_report_pdf(*, can_view_finance: bool = False) -> bytes:
    today = datetime.now().date()
    week_end = today + timedelta(days=7)
    clients = load_clients()
    events = load_events()
    users = load_users()
    settings = load_settings()
    warehouse_dashboard = build_warehouse_dashboard()
    inventory = build_inventory_view(clients, load_route_data(), load_field_confirmations())
    upcoming_events = [
        event for event in events
        if parse_date(event.get("event_date"))
        and today <= parse_date(event.get("event_date")) <= week_end
    ]
    incomplete_clients = [
        client for client in clients
        if not clean_text(client.get("phone")) or not clean_text(client.get("address")) or not clean_text(client.get("contact_name"))
    ]
    active_events_without_links = [
        event for event in events
        if event_is_active(event) and (not event.get("client_ids") or not event.get("vehicle_ids"))
    ]
    stock_alerts = [
        item for item in warehouse_dashboard.get("items", [])
        if item.get("stock_status") in {"baixo", "zerado"}
    ]
    maintenance_items = [
        item for item in inventory
        if clean_text(item.get("status")) in {"manutencao", "indisponivel"} or clean_text(item.get("maintenance_reason"))
    ]
    pending_users = [user for user in users if clean_text(user.get("status")) == "convite_pendente"]
    lines = [
        f"Gerado em {format_datetime_br(now_iso())}",
        f"Período: {format_date_br(today.isoformat())} até {format_date_br(week_end.isoformat())}",
        "",
        "Resumo executivo",
        f"- Eventos nos próximos 7 dias: {len(upcoming_events)}",
        f"- Clientes com cadastro incompleto: {len(incomplete_clients)}",
        f"- Eventos ativos sem cliente ou veículo: {len(active_events_without_links)}",
        f"- Materiais baixos ou zerados: {len(stock_alerts)}",
        f"- Equipamentos em manutenção/indisponíveis: {len(maintenance_items)}",
        f"- Convites de acesso pendentes: {len(pending_users)}",
        f"- Último backup: {format_datetime_br(settings.get('last_backup_at'))}",
        "",
        "Agenda da semana",
    ]
    for event in sorted(upcoming_events, key=lambda item: clean_text(item.get("event_date")))[:20]:
        lines.append(
            f"- {format_date_br(event.get('event_date'))}: {event.get('title') or event.get('event_id')} | "
            f"{event.get('status')} | clientes {len(event.get('client_ids') or [])} | veículos {len(event.get('vehicle_ids') or [])}"
        )
    if not upcoming_events:
        lines.append("- Nenhum evento programado para os próximos 7 dias.")
    lines.extend(["", "Cadastros para completar"])
    for client in incomplete_clients[:12]:
        missing = []
        if not clean_text(client.get("phone")):
            missing.append("telefone")
        if not clean_text(client.get("address")):
            missing.append("endereço")
        if not clean_text(client.get("contact_name")):
            missing.append("contato")
        lines.append(f"- {client.get('customer_name') or client.get('client_id')}: {', '.join(missing)}")
    if not incomplete_clients:
        lines.append("- Nenhum cadastro essencial pendente.")
    lines.extend(["", "Almoxarifado"])
    for item in stock_alerts[:12]:
        lines.append(
            f"- {item.get('name')} | {item.get('stock_status_label')} | saldo {item.get('quantity_current')} {item.get('unit')} | comprar: {item.get('purchase_link') or item.get('purchase_location') or 'n/d'}"
        )
    if not stock_alerts:
        lines.append("- Nenhum material baixo ou zerado.")
    if can_view_finance:
        financial_management = build_financial_management_dashboard(
            load_route_history(),
            load_financial_receivables(),
            load_financial_entries(),
            load_financial_closeouts(),
            "weekly",
            "",
            "",
        )
        lines.extend(["", "Financeiro"])
        lines.append(f"- Cobranças vencidas: {len(financial_management.get('overdue', []))}")
        lines.append(f"- Recebíveis próximos: {len(financial_management.get('receivables_due_soon', []))}")
        lines.append(f"- Receita bruta do período: {format_currency_br(financial_management.get('dre', {}).get('gross_revenue'))}")
        lines.append(f"- Lucro estimado: {format_currency_br(financial_management.get('dre', {}).get('profit'))}")
    else:
        lines.extend(["", "Financeiro", "- Dados financeiros ocultos para este perfil."])
    lines.extend(
        [
            "",
            "Próximas ações recomendadas",
            "- Resolver cadastros incompletos antes de gerar PDFs.",
            "- Baixar ou revisar ordem de serviço/PDF dos eventos próximos.",
            "- Repor materiais críticos do almoxarifado.",
            "- Fazer backup após alterações importantes.",
        ]
    )
    return build_simple_text_pdf("SannyGold - Relatório Semanal", lines)


def build_team_weekly_review(
    *,
    users: list[dict],
    clients: list[dict],
    events: list[dict],
    inventory: list[dict],
    settings: dict,
    security_posture: dict,
) -> dict:
    incomplete_clients = [
        client for client in clients
        if not clean_text(client.get("customer_name"))
        or not clean_text(client.get("phone"))
        or not clean_text(client.get("address"))
        or not clean_text(client.get("equipment_type"))
    ]
    open_events = [event for event in events if normalize_event_status(event.get("status")) not in {"concluido", "pago", "cancelado"}]
    maintenance_items = [
        item for item in inventory
        if clean_text(item.get("status")) in {"manutencao", "indisponivel"}
        or clean_text(item.get("maintenance_reason"))
    ]
    inactive_users = [user for user in users if clean_text(user.get("status")) == "inativo"]
    pending_invitations = [user for user in users if clean_text(user.get("status")) == "convite_pendente"]
    items = [
        {
            "title": "Acessos e senhas",
            "detail": f"{len(pending_invitations)} convite(s), {security_posture.get('password_rotation_pending', 0)} troca(s) pendente(s) e {len(inactive_users)} acesso(s) inativo(s).",
            "level": "warning" if security_posture.get("password_rotation_pending") or pending_invitations else "ready",
        },
        {
            "title": "Cadastros de clientes",
            "detail": f"{len(incomplete_clients)} cliente(s) sem dados essenciais para operação.",
            "level": "warning" if incomplete_clients else "ready",
        },
        {
            "title": "Eventos em aberto",
            "detail": f"{len(open_events)} evento(s) ainda não concluído(s).",
            "level": "warning" if open_events else "ready",
        },
        {
            "title": "Equipamentos em atenção",
            "detail": f"{len(maintenance_items)} equipamento(s) em manutenção, indisponível ou com observação técnica.",
            "level": "warning" if maintenance_items else "ready",
        },
        {
            "title": "Backup",
            "detail": f"Último backup: {format_datetime_br(settings.get('last_backup_at'))}.",
            "level": "warning" if not clean_text(settings.get("last_backup_at")) else "ready",
        },
    ]
    return {
        "items": items,
        "attention_count": sum(1 for item in items if item["level"] == "warning"),
        "ready_count": sum(1 for item in items if item["level"] == "ready"),
    }


def build_dashboard_context() -> dict:
    user = current_user()
    can_view_finance = has_permission(user, "finance.view")
    profile_ui = build_profile_ui(user)
    selected_financial_period = clean_text(request.args.get("financial_period"), "monthly") or "monthly"
    selected_financial_start = clean_text(request.args.get("financial_start"))
    selected_financial_end = clean_text(request.args.get("financial_end"))
    selected_agenda_period = clean_text(request.args.get("agenda_period"), "weekly") or "weekly"
    field_confirmations = load_field_confirmations()
    route_data = attach_field_confirmations(load_route_data(), field_confirmations)
    clients = load_clients()
    vehicles = load_vehicles_registry()
    events = load_events()
    inventory = build_inventory_view(clients, route_data, field_confirmations)
    route_history = load_route_history()
    contracts = load_contracts()
    quotes = load_quotes()
    service_log = load_service_log()
    attachments = load_attachments()
    financial_receivables = load_financial_receivables()
    financial_entries = load_financial_entries()
    financial_closeouts = load_financial_closeouts()
    validation_payload = load_operation_validation()
    settings = load_settings()
    validations = build_validation_findings(clients, vehicles, events, inventory, route_data, validation_payload)
    pending_reasons = build_pending_reasons(validation_payload)
    operational_dashboard = build_operational_dashboard(
        route_data,
        route_history,
        vehicles,
        inventory,
        clients,
        field_confirmations,
        validations,
        pending_reasons,
    )
    dispatch_today = build_dispatch_today_panel(
        route_data,
        validation_payload,
        vehicles,
        inventory,
        clients,
        ROUTE_PDF_PATH.exists(),
    )
    mobile_sync_dashboard = build_mobile_sync_dashboard(route_data)
    financial_dashboard = build_financial_dashboard(route_data, route_history, selected_financial_period)
    financial_management = build_financial_management_dashboard(
        route_history,
        financial_receivables,
        financial_entries,
        financial_closeouts,
        selected_financial_period,
        selected_financial_start,
        selected_financial_end,
    )
    financial_decision_panel = build_financial_decision_panel(financial_receivables, events, clients)
    future_dashboard = build_future_capacity_dashboard(events, clients, vehicles, inventory, route_history, selected_agenda_period)
    warehouse_dashboard = build_warehouse_dashboard()
    cleaning_agenda = build_cleaning_agenda(clients, service_log)
    usability_alerts = build_usability_alerts(clients, vehicles, inventory, contracts, cleaning_agenda, warehouse_dashboard)
    usability_home = build_usability_home(clients, events, vehicles, inventory, cleaning_agenda, warehouse_dashboard, usability_alerts)
    daily_command_center = build_daily_command_center(
        events,
        cleaning_agenda,
        financial_management,
        route_data,
        inventory,
        usability_alerts,
        clients,
        vehicles,
        user=user,
        can_view_finance=can_view_finance,
    )
    intelligent_pending_panel = build_intelligent_pending_panel(
        user=user,
        clients=clients,
        events=events,
        vehicles=vehicles,
        equipment=inventory,
        equipment_raw=load_equipment_registry(),
        financial_receivables=financial_receivables,
        route_data=route_data,
    )
    operational_kanban = build_operational_kanban(quotes, financial_management, events, inventory)
    general_improvements = build_general_improvements_dashboard(
        clients,
        events,
        vehicles,
        inventory,
        financial_management,
        warehouse_dashboard,
        usability_alerts,
        dispatch_today,
        financial_receivables,
        route_data=route_data,
        has_pdf=ROUTE_PDF_PATH.exists(),
        settings=settings,
    )
    equipment_history = build_equipment_history(inventory, clients, route_history, service_log)
    maintenance_preventive_dashboard = build_maintenance_preventive_dashboard(inventory, service_log)
    preventive_warnings = build_preventive_warnings(
        clients,
        vehicles,
        inventory,
        events,
        validation_payload,
        warehouse_dashboard,
        ROUTE_PDF_PATH.exists(),
        route_data,
    )
    users = load_users()
    security_posture = build_security_posture(
        secret_key=app.config.get("SECRET_KEY", DEFAULT_SECRET_KEY),
        secret_key_configured=SECRET_KEY_CONFIGURED,
        users=users,
        current_user=user,
        last_backup_at=clean_text(settings.get("last_backup_at")),
        session_lifetime_hours=int(app.permanent_session_lifetime.total_seconds() // 3600),
    )
    team_weekly_review = build_team_weekly_review(
        users=users,
        clients=clients,
        events=events,
        inventory=inventory,
        settings=settings,
        security_posture=security_posture,
    )
    executive_dashboard = build_executive_dashboard(
        clients=clients,
        events=events,
        route_history=route_history,
        financial_management=financial_management,
        future_dashboard=future_dashboard,
        security_posture=security_posture,
    )
    system_status = build_system_status_snapshot()
    backup_status = build_backup_status(settings)
    homologation_checklist = build_homologation_checklist(
        clients=clients,
        events=events,
        vehicles=vehicles,
        inventory=inventory,
        route_data=route_data,
        users=users,
        settings=settings,
        system_status=system_status,
        field_confirmations=field_confirmations,
    )
    role_home_labels = {
        "admin": "Tela inicial personalizada: visão completa da empresa",
        "operacional": "Tela inicial personalizada: operação, eventos, equipamentos e almoxarifado",
        "financeiro": "Tela inicial personalizada: contas, recebimentos, inadimplência e fechamento",
        "leitura": "Tela inicial personalizada: resumo em modo leitura",
        "guest": "Tela inicial personalizada: visão pública",
    }
    role_labels = {
        "admin": "Administrador",
        "operacional": "Operação",
        "financeiro": "Financeiro",
        "leitura": "Somente leitura",
        "guest": "Visitante",
    }
    audit_log = load_audit_log()
    recent_audit_log = audit_log[:8]
    audit_log_view = build_audit_log_view()
    operational_agenda = build_operational_agenda(events, clients, vehicles, audit_log)
    equipment_family_counts = build_equipment_family_counts(inventory)
    recent_shortcuts = [
        {
            "label": f"{item.get('module')} • {item.get('target_id') or item.get('action')}",
            "detail": f"{item.get('action')} • {format_datetime_br(item.get('created_at'))}",
        }
        for item in recent_audit_log[:5]
    ]
    daily_flow = build_daily_flow_guidance(
        route_data,
        dispatch_today,
        preventive_warnings,
        has_pdf=ROUTE_PDF_PATH.exists(),
        last_backup_at=clean_text(settings.get("last_backup_at")),
        last_closeout_at=clean_text(settings.get("last_closeout_at")),
    )
    guided_operation_flow = build_guided_operation_flow(
        clients=clients,
        events=events,
        vehicles=vehicles,
        equipment=inventory,
        route_data=route_data,
        has_pdf=ROUTE_PDF_PATH.exists(),
        last_backup_at=clean_text(settings.get("last_backup_at")),
        can_backup=has_permission(user, "settings.manage"),
    )
    attention_center = build_attention_center(
        preventive_warnings=preventive_warnings,
        financial_management=financial_management,
        warehouse_dashboard=warehouse_dashboard,
        system_status=system_status,
        guided_operation_flow=guided_operation_flow,
        can_backup=has_permission(user, "settings.manage"),
    )
    role_focus_cards = build_role_focus_cards(user, can_view_finance)
    team_enablement_guide = build_team_enablement_guide(
        can_view_finance=can_view_finance,
        can_manage_access=has_permission(user, "settings.manage"),
    )
    global_search_items = filter_global_search_items_for_profile(build_global_search_items(
        clients,
        events,
        vehicles,
        inventory,
        warehouse_dashboard,
        attachments,
        financial_receivables if can_view_finance else [],
        route_history,
        audit_log,
    ), profile_ui, can_view_finance=can_view_finance)
    reports_hub = build_reports_hub(
        can_view_finance=can_view_finance,
        clients=clients,
        events=events,
        vehicles=vehicles,
        equipment=inventory,
        warehouse_dashboard=warehouse_dashboard,
        financial_management=financial_management,
    )
    compact_system = build_compact_system_dashboard(
        user=user,
        clients=clients,
        events=events,
        vehicles=vehicles,
        equipment=inventory,
        warehouse_dashboard=warehouse_dashboard,
        financial_management=financial_management,
        reports_hub=reports_hub,
        attention_center=attention_center,
        equipment_family_counts=equipment_family_counts,
        has_pdf=ROUTE_PDF_PATH.exists(),
        can_view_finance=can_view_finance,
        can_manage_access=has_permission(user, "settings.manage"),
    )
    customer_history = build_customer_history(clients, events, route_history, field_confirmations)
    operational_memory_dashboard = build_operational_memory_dashboard(
        clients=clients,
        events=events,
        equipment=inventory,
        vehicles=vehicles,
        contracts=contracts,
        quotes=quotes,
        attachments=attachments,
        service_log=service_log,
        route_history=route_history,
        field_confirmations=field_confirmations,
        financial_management=financial_management,
        customer_history=customer_history,
        equipment_history=equipment_history,
        recent_audit_log=recent_audit_log,
        warehouse_dashboard=warehouse_dashboard,
        settings=settings,
        global_search_items=global_search_items,
        can_view_finance=can_view_finance,
    )
    smart_system_dashboard = build_smart_system_dashboard(
        attention_center=attention_center,
        preventive_warnings=preventive_warnings,
        financial_management=financial_management,
        general_improvements=general_improvements,
        future_dashboard=future_dashboard,
        warehouse_dashboard=warehouse_dashboard,
        reports_hub=reports_hub,
        dispatch_today=dispatch_today,
        global_search_items=global_search_items,
        customer_history=customer_history,
        recent_audit_log=recent_audit_log,
        clients=clients,
        events=events,
        contracts=contracts,
        cleaning_agenda=cleaning_agenda,
        maintenance_preventive_dashboard=maintenance_preventive_dashboard,
        route_data=route_data,
        has_pdf=ROUTE_PDF_PATH.exists(),
        can_view_finance=can_view_finance,
        user_role=clean_text(user.get("role")),
    )
    daily_management_checklist = build_daily_management_checklist(
        attention_center=attention_center,
        guided_operation_flow=guided_operation_flow,
        system_status=system_status,
        security_posture=security_posture,
        can_view_finance=can_view_finance,
        can_manage_access=has_permission(user, "settings.manage"),
    )
    clients_by_id = {client.get("client_id"): client for client in clients}
    vehicles_by_id = {vehicle.get("vehicle_id"): vehicle for vehicle in vehicles}
    latest_financial_by_event: dict[str, dict] = {}
    for item in route_history:
        event_key = clean_text(item.get("event_id"))
        if event_key and event_key not in latest_financial_by_event:
            latest_financial_by_event[event_key] = item.get("financial_summary") or {}
    enriched_events = []
    for event in events:
        linked_clients = [clients_by_id[client_id] for client_id in event.get("client_ids", []) if client_id in clients_by_id]
        linked_vehicles = [vehicles_by_id[vehicle_id] for vehicle_id in event.get("vehicle_ids", []) if vehicle_id in vehicles_by_id]
        equipment_count = sum(1 for client in linked_clients if clean_text(client.get("equipment_number")))
        checklist = [
            {**item, "label": "checklist_equipe" if clean_text(item.get("label")) == "checklist_motorista" else item.get("label")}
            for item in event.get("checklist", [])
        ]
        event_record = {
            **event,
            "checklist": checklist,
            "clients_count": len(linked_clients),
            "vehicles_count": len(linked_vehicles),
            "equipment_count": equipment_count,
            "financial_summary": latest_financial_by_event.get(clean_text(event.get("event_id")), {}),
            "event_period_label": event_period_label(event),
        }
        status_context = build_event_status_context(
            event_record,
            linked_clients,
            route_data,
            audit_log,
            can_view_finance=can_view_finance,
        )
        event_record["raw_status"] = clean_text(event.get("status"))
        event_record["status"] = status_context["status"]
        event_record["status_label"] = status_context["label"]
        event_record["status_context"] = status_context
        event_record["recommended_actions"] = build_event_recommended_actions(
            event_record,
            linked_clients,
            route_data,
            audit_log,
            financial_receivables,
            can_view_finance=can_view_finance,
        )
        progress = build_event_progress(event_record, route_data, ROUTE_PDF_PATH.exists(), can_view_finance)
        event_record["progress_steps"] = progress["steps"]
        event_record["progress_missing_actions"] = progress["missing_actions"]
        event_record["progress_percent"] = progress["percent"]
        event_record["progress_label"] = progress["label"]
        event_record["event_timeline"] = build_event_timeline(
            event_record,
            linked_clients,
            linked_vehicles,
            route_data,
            ROUTE_PDF_PATH.exists(),
            can_view_finance,
        )
        enriched_events.append(event_record)
    return {
        "route_data": route_data,
        "has_pdf": ROUTE_PDF_PATH.exists(),
        "has_json": ROUTE_JSON_PATH.exists(),
        "last_backup_at": clean_text(backup_status.get("last_backup_at")),
        "last_backup_label": backup_status.get("last_backup_label"),
        "backup_status": backup_status,
        "clients": clients,
        "vehicles_registry": vehicles,
        "events": enriched_events,
        "equipment_registry": inventory,
        "available_equipment": [item for item in inventory if item["status"] == "disponivel"],
        "route_history": route_history[:10],
        "operational_dashboard": operational_dashboard,
        "dispatch_today": dispatch_today,
        "daily_flow": daily_flow,
        "guided_operation_flow": guided_operation_flow,
        "attention_center": attention_center,
        "role_focus_cards": role_focus_cards,
        "team_enablement_guide": team_enablement_guide,
        "operational_validations": validations,
        "pending_reasons": pending_reasons,
        "operation_validation": validation_payload,
        "financial_dashboard": financial_dashboard,
        "financial_management": financial_management,
        "financial_decision_panel": financial_decision_panel,
        "customer_history": customer_history,
        "calendar_weeks": build_calendar_weeks(events),
        "operational_agenda": operational_agenda,
        "preventive_warnings": preventive_warnings,
        "real_map_routes": build_real_map_routes(route_data),
        "google_maps_enabled": google_maps_enabled(),
        "google_maps_api_key": google_maps_api_key(),
        "last_closeout_label": format_datetime_br(settings.get("last_closeout_at")),
        "financial_period": selected_financial_period,
        "financial_start": selected_financial_start,
        "financial_end": selected_financial_end,
        "executive_dashboard": executive_dashboard,
        "future_dashboard": future_dashboard,
        "warehouse_dashboard": warehouse_dashboard,
        "contracts": contracts,
        "quotes": quotes[:12],
        "attachments": attachments[:12],
        "cleaning_agenda": cleaning_agenda,
        "service_log": service_log[:12],
        "client_details": build_client_detail_index(
            clients,
            contracts,
            service_log,
            quotes,
            route_history,
            events=events,
            financial_receivables=financial_receivables,
            can_view_finance=can_view_finance,
        ),
        "usability_alerts": usability_alerts,
        "usability_home": usability_home,
        "daily_command_center": daily_command_center,
        "intelligent_pending_panel": intelligent_pending_panel,
        "operational_kanban": operational_kanban,
        "general_improvements": general_improvements,
        "smart_system_dashboard": smart_system_dashboard,
        "operational_memory_dashboard": operational_memory_dashboard,
        "equipment_history": equipment_history,
        "contract_financial_dashboard": build_contract_financial_dashboard(contracts, service_log),
        "maintenance_preventive_dashboard": maintenance_preventive_dashboard,
        "mobile_sync_dashboard": mobile_sync_dashboard,
        "security_posture": security_posture,
        "security_technical_checklist": build_security_technical_checklist(security_posture, system_status),
        "homologation_checklist": homologation_checklist,
        "team_weekly_review": team_weekly_review,
        "system_status": system_status,
        "global_search_items": global_search_items,
        "global_search_groups": build_global_search_groups(global_search_items, can_view_finance=can_view_finance),
        "search_module_counts": build_search_module_counts(global_search_items, can_view_finance=can_view_finance),
        "reports_hub": reports_hub,
        "compact_system": compact_system,
        "help_assistant": build_help_assistant_context(user),
        "daily_management_checklist": daily_management_checklist,
        "quick_rental_summary": session.get("quick_rental_summary") if has_request_context() else {},
        "maintenance_items": [item for item in inventory if item.get("status") in {"manutencao", "indisponivel"} or item.get("maintenance_reason")],
        "can_view_finance": can_view_finance,
        "profile_ui": profile_ui,
        "role_home_label": role_home_labels.get(clean_text(user.get("role")), role_home_labels["guest"]),
        "event_status_flow": EVENT_STATUS_FLOW,
        "event_status_labels": EVENT_STATUS_LABELS,
        "recent_shortcuts": recent_shortcuts,
        "recent_audit_log": recent_audit_log,
        "agenda_period": selected_agenda_period,
        "forecast_audit": load_forecast_audit(),
        "audit_log_view": audit_log_view,
        "inventory_counts": {
            "total": len(inventory),
            "available": sum(1 for item in inventory if item["status"] == "disponivel"),
            "in_route": sum(1 for item in inventory if item["status"] in {"carregado", "em_rota", "instalado", "retirada_pendente"}),
            "maintenance": sum(1 for item in inventory if item["status"] in {"manutencao", "indisponivel"}),
            "reserved": sum(1 for item in inventory if item["status"] == "reservado"),
        },
        "equipment_family_counts": equipment_family_counts,
        "equipment_type_suggestions": EQUIPMENT_TYPE_SUGGESTIONS,
        "quick_rental_service_options": QUICK_RENTAL_SERVICE_OPTIONS,
        "settings": settings,
        "current_user": user,
        "is_authenticated": user["role"] != "guest",
        "users": [serialize_access_user(item) for item in users],
        "roles": sorted(ROLES),
        "role_labels": role_labels,
        "permission_catalog": sorted(
            {
                "clients.view",
                "clients.edit",
                "events.create",
                "events.close",
                "events.service_order",
                "fleet.view",
                "finance.view",
                "finance.edit",
                "finance.payments",
                "finance.close",
                "finance.export",
                "settings.manage",
                "warehouse.view",
                "warehouse.edit",
                "warehouse.manage",
            }
        ),
        "role_permission_matrix": {role: sorted(permissions) for role, permissions in ROLE_PERMISSIONS.items()},
        "hq": {
            "address": HQ_ADDRESS,
            "lat": HQ_LAT,
            "lng": HQ_LNG,
        },
    }


@app.route("/", methods=["GET"])
def index():
    ensure_storage_dirs()
    maybe_create_automatic_backup()
    return render_template("index.html", **build_dashboard_context())


@app.route("/health", methods=["GET"])
def healthcheck():
    snapshot = build_system_status_snapshot()
    status_code = 200 if snapshot["health"]["ok"] and snapshot["health"]["storage_ready"] else 503
    return jsonify({"ok": status_code == 200, "status": "OK" if status_code == 200 else "ERRO", **snapshot}), status_code


@app.route("/status", methods=["GET"])
def statuscheck():
    return healthcheck()


@app.route("/system/status.json", methods=["GET"])
@require_permission("dashboard.view")
def system_status_json():
    return jsonify({"ok": True, **build_system_status_snapshot()})


@app.route("/ajuda", methods=["GET"])
@app.route("/ajuda-rapida", methods=["GET"])
@require_permission("dashboard.view")
def quick_help_page():
    return redirect(url_for("index", _anchor="quick-help-panel"))


@app.route("/assistente", methods=["GET"])
@require_permission("dashboard.view")
def help_assistant_page():
    return redirect(url_for("index", help="open", _anchor="help-assistant-button"))


@app.route("/admin/ajuda", methods=["GET"])
@require_permission("settings.manage")
def admin_help_page():
    return redirect(url_for("index", _anchor="help-admin-panel"))


@app.route("/admin/chamados-suporte", methods=["GET"])
@require_permission("settings.manage")
def admin_support_tickets_page():
    return redirect(url_for("index", _anchor="support-tickets-admin-panel"))


@app.route("/assistant/search", methods=["GET"])
@require_permission("dashboard.view")
def help_assistant_search():
    query = clean_text(request.args.get("q"))
    entry_id = clean_text(request.args.get("id"))
    entries = load_help_knowledge_base()
    entry = next((item for item in entries if clean_text(item.get("id")) == entry_id), None) if entry_id else None
    if not entry:
        entry = search_help_knowledge_base(entries, query)
    if entry:
        public_entry = public_help_entry(entry)
        metrics = load_help_metrics()
        increment_help_counter(metrics, "question_counts", public_entry["id"])
        save_help_metrics(metrics)
        return jsonify({"ok": True, "found": True, "entry": public_entry})
    return jsonify(
        {
            "ok": True,
            "found": False,
            "message": "Não encontrei uma resposta segura para essa dúvida. Posso registrar isso para o suporte analisar.",
        }
    )


@app.route("/assistant/unanswered", methods=["POST"])
@require_permission("dashboard.view")
def save_help_unanswered_question():
    payload = help_request_payload()
    text = clean_text(payload.get("text") or payload.get("question") or payload.get("duvida"))
    if not text:
        return jsonify({"ok": False, "error": "Digite a dúvida antes de registrar."}), 400
    items = load_help_unanswered_questions()
    user = help_user_snapshot()
    record = {
        "id": next_numeric_id(items, "DUV", "id"),
        "text": text[:1000],
        "texto_duvida": text[:1000],
        "created_at": now_iso(),
        "screen": help_current_screen(payload),
        "status": "nova",
        "support_note": "",
        "observacao_suporte": "",
        **user,
    }
    items.append(record)
    save_help_unanswered_questions(items)
    record_audit("unanswered", "help_assistant", record["id"], "Dúvida sem resposta registrada.", after=record)
    return jsonify({"ok": True, "question": record})


@app.route("/assistant/support-click", methods=["POST"])
@require_permission("dashboard.view")
def register_help_support_click():
    metrics = load_help_metrics()
    metrics["support_clicks"] = int(metrics.get("support_clicks") or 0) + 1
    save_help_metrics(metrics)
    return jsonify({"ok": True, "support_clicks": metrics["support_clicks"]})


@app.route("/assistant/support", methods=["POST"])
@require_permission("dashboard.view")
def save_help_support_ticket():
    payload = help_request_payload()
    message = clean_text(payload.get("message") or payload.get("mensagem"))
    if not message:
        return jsonify({"ok": False, "error": "Explique rapidamente o problema antes de enviar."}), 400
    priority = clean_text(payload.get("priority") or payload.get("prioridade"), "media").lower()
    if priority not in {"baixa", "media", "média", "alta"}:
        priority = "media"
    if priority == "média":
        priority = "media"
    tickets = load_help_support_tickets()
    record = {
        "id": next_numeric_id(tickets, "SUP", "id"),
        "message": message[:1500],
        "mensagem": message[:1500],
        "screen": help_current_screen(payload),
        "created_at": now_iso(),
        "status": "novo",
        "priority": priority,
        "prioridade": priority,
        "support_note": "",
        "observacao_suporte": "",
        **help_user_snapshot(),
    }
    tickets.append(record)
    save_help_support_tickets(tickets)
    record_audit("support_ticket", "help_assistant", record["id"], "Chamado de suporte criado.", after=record)
    return jsonify({"ok": True, "ticket": record})


@app.route("/assistant/feedback", methods=["POST"])
@require_permission("dashboard.view")
def save_help_feedback():
    payload = help_request_payload()
    answer_id = clean_text(payload.get("answer_id") or payload.get("id"))
    useful = clean_text(payload.get("useful")).lower() in {"1", "true", "sim", "yes", "util", "útil"}
    if not answer_id:
        return jsonify({"ok": False, "error": "Resposta não identificada."}), 400
    metrics = load_help_metrics()
    increment_help_counter(metrics, "useful_counts" if useful else "not_useful_counts", answer_id)
    save_help_metrics(metrics)
    return jsonify({"ok": True})


@app.route("/observations/quick", methods=["POST"])
@require_permission("dashboard.view")
def save_quick_observation():
    area = clean_text(request.form.get("area"), "Central do Dia") or "Central do Dia"
    reference = clean_text(request.form.get("reference"))[:120]
    note = clean_text(request.form.get("note") or request.form.get("notes"))[:800]
    if not note:
        flash_action_error(
            ValueError(
                "Escreva a observação antes de salvar. Use esse campo para registrar acesso difícil, "
                "contato no local, atraso, problema no equipamento ou qualquer aviso importante."
            ),
            "general",
        )
        return redirect(url_for("index", _anchor="mobile-quick-observation"))
    record = {
        "id": f"OBS-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6].upper()}",
        "area": area[:80],
        "reference": reference,
        "note": note,
        "created_at": now_iso(),
    }
    detail_reference = f" • {reference}" if reference else ""
    record_audit(
        "quick_observation",
        "observations",
        record["id"],
        f"Observação rápida registrada em {record['area']}{detail_reference}.",
        after=record,
    )
    flash("Observação rápida registrada. Ela ficou salva na auditoria para consulta da administração.", "success")
    return redirect(url_for("index", _anchor="mobile-quick-observation"))


@app.route("/admin/help/knowledge", methods=["POST"])
@require_permission("settings.manage")
def save_help_knowledge_entry():
    try:
        items = load_help_knowledge_base()
        record = create_help_knowledge_record(request.form)
        before = next((item for item in items if clean_text(item.get("id")) == clean_text(record.get("id"))), None)
        save_help_knowledge_base(upsert_item(items, record, "id"))
        record_audit("save", "help_knowledge", record["id"], f"Pergunta {record['titulo']} salva.", before=before, after=record)
        flash(f"Pergunta '{record['titulo']}' salva na base do assistente.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "general")
    return redirect(url_for("index", _anchor="help-admin-panel"))


@app.route("/admin/help/unanswered/<question_id>", methods=["POST"])
@require_permission("settings.manage")
def update_help_unanswered_question(question_id: str):
    try:
        items = load_help_unanswered_questions()
        target = next((item for item in items if clean_text(item.get("id")) == clean_text(question_id)), None)
        if not target:
            raise ValueError("Dúvida não encontrada.")
        status = clean_text(request.form.get("status"), "nova")
        if status not in {"nova", "em_analise", "em análise", "resolvida"}:
            raise ValueError("Status da dúvida inválido.")
        target["status"] = "em_analise" if status == "em análise" else status
        target["support_note"] = clean_text(request.form.get("support_note") or request.form.get("observacao_suporte"))
        target["observacao_suporte"] = target["support_note"]
        target["updated_at"] = now_iso()
        save_help_unanswered_questions(items)
        record_audit("update", "help_unanswered", question_id, "Dúvida atualizada pelo suporte.", after=target)
        flash(f"Dúvida {question_id} atualizada.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "general")
    return redirect(url_for("index", _anchor="help-admin-panel"))


@app.route("/admin/support-tickets/<ticket_id>", methods=["POST"])
@require_permission("settings.manage")
def update_help_support_ticket(ticket_id: str):
    try:
        tickets = load_help_support_tickets()
        target = next((item for item in tickets if clean_text(item.get("id")) == clean_text(ticket_id)), None)
        if not target:
            raise ValueError("Chamado não encontrado.")
        status = clean_text(request.form.get("status"), "novo")
        if status not in {"novo", "em_analise", "em análise", "resolvido"}:
            raise ValueError("Status do chamado inválido.")
        priority = clean_text(request.form.get("priority") or request.form.get("prioridade"), target.get("priority", "media")).lower()
        if priority not in {"baixa", "media", "média", "alta"}:
            priority = "media"
        target["status"] = "em_analise" if status == "em análise" else status
        target["priority"] = "media" if priority == "média" else priority
        target["prioridade"] = target["priority"]
        target["support_note"] = clean_text(request.form.get("support_note") or request.form.get("observacao_suporte"))
        target["observacao_suporte"] = target["support_note"]
        target["updated_at"] = now_iso()
        save_help_support_tickets(tickets)
        record_audit("update", "help_support", ticket_id, "Chamado atualizado pelo suporte.", after=target)
        flash(f"Chamado {ticket_id} atualizado.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "general")
    return redirect(url_for("index", _anchor="support-tickets-admin-panel"))


@app.route("/auth/login", methods=["POST"])
def login():
    email = clean_text(request.form.get("email")).lower()
    password = request.form.get("password", "")
    if not email or not password:
        flash_action_error(ValueError("Informe email e senha para entrar. Sem esses dois dados o sistema não consegue identificar o usuário."), "login")
        return redirect(url_for("index"))
    if login_is_locked(email):
        flash_action_error(ValueError(f"Muitas tentativas de login. Tente novamente em {LOGIN_LOCKOUT_MINUTES} minutos ou peça redefinição de senha."), "login")
        return redirect(url_for("index"))

    user = find_user_by_email(email)
    if not user:
        record_failed_login(email)
        flash_action_error(ValueError("Usuário não encontrado. Confira o e-mail digitado ou peça ao administrador para criar o acesso."), "login")
        return redirect(url_for("index"))
    status = clean_text(user.get("status"), "inativo")
    if status == "convite_pendente":
        flash_action_warning("Aviso: convite pendente", "Convite pendente. O usuário ainda precisa criar a senha inicial antes do primeiro acesso.", next_step="Abra o link de convite enviado pelo administrador ou peça um novo convite.", target_href="#login-panel", target_tab="summary-tab", action="Voltar ao login")
        return redirect(url_for("index"))
    if status != "ativo":
        flash_action_error(ValueError("Usuário inativo. Peça a um administrador para reativar o acesso antes de entrar."), "login")
        return redirect(url_for("index"))
    if not clean_text(user.get("senha_hash")):
        flash_action_warning("Aviso: senha ainda não criada", "Acesso sem senha criada. O sistema não permite entrada enquanto não houver senha segura cadastrada.", next_step="Peça ao administrador um novo link de convite ou redefinição.", target_href="#login-panel", target_tab="summary-tab", action="Voltar ao login")
        return redirect(url_for("index"))
    if not check_password_hash(clean_text(user.get("senha_hash")), password):
        record_failed_login(email)
        flash_action_error(ValueError("Senha incorreta. Digite a senha novamente ou peça redefinição se não lembrar."), "login")
        return redirect(url_for("index"))

    clear_failed_login(email)
    session.clear()
    session.permanent = True
    session["user_id"] = clean_text(user.get("id"))
    session["login_at"] = now_iso()
    record_audit("login", "auth", clean_text(user.get("id")), "Login realizado.")
    if password_change_required(user):
        flash_action_warning("Aviso: troca de senha pendente", "Troca de senha pendente. A senha inicial precisa ser atualizada para manter o acesso seguro.", next_step="Abra o painel de conta e defina uma senha nova antes de continuar operando em equipe.", target_href="#access-pane", target_tab="access-tab", action="Atualizar senha")
    flash("Login realizado com sucesso. Seu acesso foi validado e a tela inicial já está disponível.", "success")
    return redirect(url_for("index"))


@app.route("/auth/logout", methods=["POST"])
def logout():
    record_audit("logout", "auth", clean_text(session.get("user_id")), "Logout manual.")
    session.clear()
    flash("Você saiu da conta com segurança. O sistema voltou ao modo visitante.", "success")
    return redirect(url_for("index"))


@app.route("/account/password", methods=["POST"])
@require_permission("dashboard.view")
def change_password():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    user_id = clean_text(session.get("user_id"))
    users = load_users()
    user = next((item for item in users if clean_text(item.get("id")) == user_id), None)
    issues = password_policy_issues(new_password, [clean_text((user or {}).get("nome")), clean_text((user or {}).get("email"))])
    if issues:
        flash_action_error(ValueError(f"{issues[0]} Corrija a nova senha antes de salvar."), "login")
        return redirect(url_for("index"))
    if not user or not check_password_hash(clean_text(user.get("senha_hash")), current_password):
        flash_action_error(ValueError("Senha atual incorreta. Informe a senha usada hoje para autorizar a troca."), "login")
        return redirect(url_for("index"))

    user["senha_hash"] = generate_password_hash(new_password, method="pbkdf2:sha256")
    user["must_change_password"] = False
    user["updated_at"] = now_iso()
    save_users(users)
    record_audit("change_password", "auth", user_id, "Senha alterada pelo usuário.")
    flash("Senha atualizada com sucesso. Use a nova senha no próximo login.", "success")
    return redirect(url_for("index"))


@app.route("/auth/forgot-password", methods=["POST"])
def request_password_reset():
    email = clean_text(request.form.get("email")).lower()
    users = load_users()
    user = next((item for item in users if clean_text(item.get("email")).lower() == email), None)
    if user and clean_text(user.get("status")) == "ativo":
        issue_password_reset(user)
        save_users(users)
        record_audit("request_password_reset", "auth", clean_text(user.get("id")), "Redefinição de senha solicitada.")
    flash("Solicitação recebida. Se o e-mail estiver cadastrado e ativo, um link de redefinição ficará disponível para envio pelo painel de acessos.", "success")
    return redirect(url_for("index"))


@app.route("/convite/<token>", methods=["GET", "POST"])
def accept_invitation(token: str):
    users, user, error = resolve_access_token(token, "invite", "invitation_token", "invitation_expires_at")
    if error or not user:
        flash_action_error(ValueError(error or "Convite inválido. Peça ao administrador um novo convite."), "login")
        return redirect(url_for("index"))
    if clean_text(user.get("status")) != "convite_pendente":
        flash_action_warning("Aviso: convite indisponível", "Este convite já foi concluído ou cancelado. O sistema não permite reutilizar links antigos.", next_step="Peça ao administrador um novo convite se precisar acessar.", target_href="#login-panel", target_tab="summary-tab", action="Voltar ao login")
        return redirect(url_for("index"))
    if request.method == "GET":
        return render_template(
            "password_setup.html",
            mode="invite",
            title="Criar senha de acesso",
            action_url=url_for("accept_invitation", token=token),
            user=sanitize_user(user),
            expires_label=format_datetime_br(user.get("invitation_expires_at")),
        )

    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")
    if new_password != confirm_password:
        flash_action_error(ValueError("A confirmação da senha não confere. Digite a mesma senha nos dois campos."), "login")
        return redirect(url_for("accept_invitation", token=token))
    issues = password_policy_issues(new_password, [clean_text(user.get("nome")), clean_text(user.get("email"))])
    if issues:
        flash_action_error(ValueError(f"{issues[0]} Corrija a senha antes de concluir o convite."), "login")
        return redirect(url_for("accept_invitation", token=token))

    user["senha_hash"] = generate_password_hash(new_password, method="pbkdf2:sha256")
    user["status"] = "ativo"
    user["must_change_password"] = False
    user["invitation_accepted_at"] = now_iso()
    clear_user_invitation(user)
    clear_password_reset(user)
    user["updated_at"] = now_iso()
    save_users(users)
    clear_failed_login(user.get("email"))
    session.clear()
    session.permanent = True
    session["user_id"] = clean_text(user.get("id"))
    session["login_at"] = now_iso()
    record_audit("accept_invitation", "auth", clean_text(user.get("id")), "Convite aceito e senha criada pelo usuário.")
    flash("Senha criada com sucesso. Seu acesso já está ativo e a tela inicial foi liberada.", "success")
    return redirect(url_for("index"))


@app.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    users, user, error = resolve_access_token(token, "password_reset", "reset_token", "reset_expires_at")
    if error or not user:
        flash_action_error(ValueError(error or "Link de redefinição inválido. Peça ao administrador um novo link."), "login")
        return redirect(url_for("index"))
    if clean_text(user.get("status")) != "ativo":
        flash_action_warning("Aviso: acesso inativo", "Acesso inativo ou ainda não ativado. O sistema não permite redefinir senha para usuário sem acesso ativo.", next_step="Peça suporte ao administrador antes de tentar novamente.", target_href="#login-panel", target_tab="summary-tab", action="Voltar ao login")
        return redirect(url_for("index"))
    if request.method == "GET":
        return render_template(
            "password_setup.html",
            mode="reset",
            title="Redefinir senha",
            action_url=url_for("reset_password", token=token),
            user=sanitize_user(user),
            expires_label=format_datetime_br(user.get("reset_expires_at")),
        )

    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")
    if new_password != confirm_password:
        flash_action_error(ValueError("A confirmação da senha não confere. Digite a mesma senha nos dois campos."), "login")
        return redirect(url_for("reset_password", token=token))
    issues = password_policy_issues(new_password, [clean_text(user.get("nome")), clean_text(user.get("email"))])
    if issues:
        flash_action_error(ValueError(f"{issues[0]} Corrija a senha antes de redefinir."), "login")
        return redirect(url_for("reset_password", token=token))

    user["senha_hash"] = generate_password_hash(new_password, method="pbkdf2:sha256")
    user["must_change_password"] = False
    clear_password_reset(user)
    user["updated_at"] = now_iso()
    save_users(users)
    clear_failed_login(user.get("email"))
    session.clear()
    session.permanent = True
    session["user_id"] = clean_text(user.get("id"))
    session["login_at"] = now_iso()
    record_audit("reset_password", "auth", clean_text(user.get("id")), "Senha redefinida pelo usuário.")
    flash("Senha redefinida com sucesso. Seu acesso foi liberado com a nova senha.", "success")
    return redirect(url_for("index"))


@app.route("/users", methods=["POST"])
@require_permission("settings.manage")
def save_user():
    try:
        users = load_users()
        record = create_user_record(request.form, users)
        before = next((item for item in users if clean_text(item.get("id")) == clean_text(record.get("id"))), None)
        save_users(upsert_item(users, record, "id"))
        record_audit("save", "users", record["id"], f"Usuário {record['email']} salvo.", before=sanitize_user(before or {}), after=sanitize_user(record))
        if clean_text(record.get("status")) == "convite_pendente":
            flash(f"Convite criado para {record['email']}. Link: {invitation_url(record)}", "success")
        else:
            flash(f"Usuário {record['email']} salvo com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "access")
    return redirect(url_for("index"))


@app.route("/users/<user_id>/invite/reissue", methods=["POST"])
@require_permission("settings.manage")
def reissue_user_invitation(user_id: str):
    try:
        users = load_users()
        user = next((item for item in users if clean_text(item.get("id")) == clean_text(user_id)), None)
        if not user:
            raise ValueError("Usuário não encontrado.")
        if clean_text(user.get("status")) == "ativo":
            raise ValueError("Usuário ativo não precisa de convite. Use redefinição de senha se necessário.")
        issue_user_invitation(user)
        save_users(users)
        record_audit("reissue_invitation", "users", user_id, f"Convite reenviado para {user.get('email')}.")
        flash(f"Novo convite gerado para {user.get('email')}. Link: {invitation_url(user)}", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "access")
    return redirect(url_for("index", _anchor="access-management-panel"))


@app.route("/users/<user_id>/invite/cancel", methods=["POST"])
@require_permission("settings.manage")
def cancel_user_invitation(user_id: str):
    try:
        users = load_users()
        user = next((item for item in users if clean_text(item.get("id")) == clean_text(user_id)), None)
        if not user:
            raise ValueError("Usuário não encontrado.")
        if clean_text(user.get("status")) != "convite_pendente":
            raise ValueError("Apenas convites pendentes podem ser cancelados.")
        user["status"] = "inativo"
        clear_user_invitation(user)
        user["updated_at"] = now_iso()
        save_users(users)
        record_audit("cancel_invitation", "users", user_id, f"Convite cancelado para {user.get('email')}.")
        flash(f"Convite de {user.get('email')} cancelado.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "access")
    return redirect(url_for("index", _anchor="access-management-panel"))


@app.route("/users/<user_id>/password-reset", methods=["POST"])
@require_permission("settings.manage")
def create_user_password_reset(user_id: str):
    try:
        users = load_users()
        user = next((item for item in users if clean_text(item.get("id")) == clean_text(user_id)), None)
        if not user:
            raise ValueError("Usuário não encontrado.")
        if clean_text(user.get("status")) != "ativo":
            raise ValueError("Redefinição só pode ser gerada para usuário ativo.")
        issue_password_reset(user)
        save_users(users)
        record_audit("create_password_reset", "users", user_id, f"Link de redefinição gerado para {user.get('email')}.")
        flash(f"Link de redefinição gerado para {user.get('email')}: {password_reset_url(user)}", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "access")
    return redirect(url_for("index", _anchor="access-management-panel"))


@app.route("/warehouse/items", methods=["POST"])
@require_permission("warehouse.manage")
def save_warehouse_item():
    try:
        record = create_warehouse_item_record(request.form)
        before = next((item for item in load_warehouse_items() if clean_text(item.get("id")) == clean_text(record.get("id"))), None)
        save_warehouse_items(upsert_item(load_warehouse_items(), record, "id"))
        record_audit("save", "warehouse", record["id"], f"Material {record['name']} salvo.", before=before, after=record)
        flash(f"Material {record['name']} salvo no almoxarifado.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "warehouse")
    return redirect(url_for("index"))


@app.route("/warehouse/items/<item_id>/movement", methods=["POST"])
@require_permission("warehouse.edit")
def save_warehouse_movement(item_id: str):
    try:
        movement = apply_warehouse_movement(item_id, request.form, current_user())
        record_audit("movement", "warehouse", item_id, f"{movement['movement_type']} de {movement['item_name']}.", after=movement)
        flash(
            f"Movimentação registrada: {movement['movement_type']} de {movement['item_name']}.",
            "success",
        )
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "warehouse")
    return redirect(url_for("index"))


@app.route("/quotes", methods=["POST"])
@require_permission("clients.edit")
def save_quote():
    try:
        items = load_quotes()
        record = create_quote_record(request.form, items)
        save_quotes(upsert_item(items, record, "id"))
        record_audit("save", "quotes", record["id"], f"Orçamento {record['id']} salvo.", after=record)
        flash(f"Orçamento {record['id']} salvo com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "client")
    return redirect(url_for("index"))


@app.route("/quick-rental", methods=["POST"])
@require_permission("clients.edit")
def save_quick_rental():
    try:
        form = request.form
        clients = load_clients()
        selected_client_id = clean_text(form.get("client_id"))
        existing_client = next((client for client in clients if clean_text(client.get("client_id")) == selected_client_id), None) if selected_client_id else None
        service_type, equipment_type, service_label = quick_rental_service_from_form(form)
        if not equipment_type and existing_client:
            equipment_type = record_text(existing_client, "equipment_type")
            service_label = equipment_type
        customer_name = clean_text(form.get("customer_name")) or record_text(existing_client, "customer_name")
        phone = clean_text(form.get("phone")) or record_text(existing_client, "phone")
        address = clean_text(form.get("address")) or record_text(existing_client, "address")
        lat = clean_text(form.get("lat")) or record_text(existing_client, "lat")
        lng = clean_text(form.get("lng")) or record_text(existing_client, "lng")
        event_date = clean_text(form.get("event_date"))
        try:
            quantity = int(clean_text(form.get("equipment_quantity"), "0") or 0)
        except (TypeError, ValueError):
            quantity = 0
        service_value = parse_decimal(form.get("service_value"))
        responsible = clean_text(form.get("responsible"))
        notes = clean_text(form.get("notes"))
        missing = validate_quick_rental_required_fields(
            customer_name=customer_name,
            phone=phone,
            event_date=event_date,
            address=address,
            equipment_type=equipment_type,
            quantity=quantity,
            service_value=service_value,
            responsible=responsible,
            notes=notes,
        )
        if missing:
            raise ValueError(f"Preencha os campos obrigatórios da locação rápida: {', '.join(missing)}.")
        if address and (not lat or not lng):
            try:
                geo = geocode_address(address)
                lat = str(geo["lat"])
                lng = str(geo["lng"])
            except Exception:
                lat = str(HQ_LAT)
                lng = str(HQ_LNG)
        client_type = clean_text(form.get("client_type")) or record_text(existing_client, "client_type") or "avulso"
        billing_model = clean_text(form.get("billing_model")) or record_text(existing_client, "billing_model") or ("mensal" if client_type == "fixo" else "avulso")
        client_values = {
            "client_id": record_text(existing_client, "client_id"),
            "customer_name": customer_name,
            "contact_name": clean_text(form.get("contact_name")) or record_text(existing_client, "contact_name"),
            "phone": phone,
            "address": address,
            "lat": lat,
            "lng": lng,
            "client_type": client_type,
            "equipment_type": equipment_type,
            "equipment_quantity": str(quantity),
            "equipment_number": clean_text(form.get("equipment_number")) or record_text(existing_client, "equipment_number"),
            "billing_model": billing_model,
            "cleaning_frequency": clean_text(form.get("cleaning_frequency")) or record_text(existing_client, "cleaning_frequency") or ("semanal" if billing_model == "mensal" else "nao_aplica"),
            "service_profile": record_text(existing_client, "service_profile") or ("limpeza_semanal" if billing_model == "mensal" else "evento_avulso"),
            "default_service_minutes": clean_text(form.get("default_service_minutes")) or record_text(existing_client, "default_service_minutes") or "20",
            "default_priority": clean_text(form.get("default_priority")) or record_text(existing_client, "default_priority") or "3",
            "window_start": clean_text(form.get("window_start")) or record_text(existing_client, "window_start") or "08:00",
            "window_end": clean_text(form.get("window_end")) or record_text(existing_client, "window_end") or "18:00",
            "locked_vehicle_id": record_text(existing_client, "locked_vehicle_id"),
            "service_value": str(service_value),
            "team_cost": clean_text(form.get("team_cost")) or record_text(existing_client, "team_cost") or "0",
            "equipment_cost": clean_text(form.get("equipment_cost")) or record_text(existing_client, "equipment_cost") or "0",
            "invoice_status": clean_text(form.get("invoice_status")) or record_text(existing_client, "invoice_status") or "sem_nota",
        }
        client_record = create_client_record_from_values(client_values, existing_clients=clients)
        save_clients(upsert_item(clients, client_record, "client_id"))
        upsert_contract_from_client(client_record)

        event_form = MultiDict(
            {
                "title": clean_text(form.get("title")) or f"Locação - {client_record['customer_name']}",
                "event_category": "locacao",
                "event_date": event_date,
                "event_end_date": clean_text(form.get("event_end_date")) or event_date,
                "status": "confirmado",
                "valor_servico": str(client_record["service_value"]),
                "custo_equipe": str(client_record["team_cost"]),
                "custo_por_equipamento": str(client_record["equipment_cost"]),
                "responsible": responsible,
                "notes": notes,
            }
        )
        event_form.setlist("event_client_ids", [client_record["client_id"]])
        event_form.setlist("event_vehicle_ids", [])
        event_record = create_event_record(event_form)
        save_events(upsert_item(load_events(), event_record, "event_id"))
        session["quick_rental_summary"] = {
            "client_id": clean_text(client_record.get("client_id")),
            "client_name": clean_text(client_record.get("customer_name")),
            "phone": clean_text(client_record.get("phone")),
            "event_id": clean_text(event_record.get("event_id")),
            "event_title": clean_text(event_record.get("title")),
            "event_date": clean_text(event_record.get("event_date")),
            "event_end_date": clean_text(event_record.get("event_end_date")),
            "address": clean_text(client_record.get("address")),
            "service_type": service_type,
            "service_label": service_label,
            "equipment_type": clean_text(client_record.get("equipment_type")),
            "equipment_quantity": int(client_record.get("equipment_quantity") or 0),
            "service_value": parse_decimal(client_record.get("service_value")),
            "responsible": responsible,
            "notes": notes,
        }
        record_audit("quick_rental", "events", event_record["event_id"], f"Locação rápida criada para {client_record['customer_name']}.", after=event_record)
        flash(f"Locação criada: {client_record['customer_name']} entrou em clientes e no evento {event_record['event_id']}.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "quick_rental")
        return redirect(url_for("index", _anchor="quick-rental-panel"))
    return redirect(url_for("index", _anchor="quick-rental-summary-panel"))


@app.route("/portal/orcamento", methods=["POST"])
def public_quote_request():
    try:
        items = load_quotes()
        record = create_quote_record(request.form, items, source="portal")
        save_quotes(upsert_item(items, record, "id"))
        flash("Solicitação de orçamento recebida. A equipe SannyGold entrará em contato.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "client")
    return redirect(url_for("index"))


@app.route("/clients/<client_id>/cleaning-service", methods=["POST"])
@require_permission("warehouse.edit")
def register_cleaning_service(client_id: str):
    try:
        clients = load_clients()
        client = next((item for item in clients if clean_text(item.get("client_id")) == clean_text(client_id)), None)
        if not client:
            raise ValueError("Cliente não encontrado.")
        service_date = clean_text(request.form.get("service_date")) or datetime.now().date().isoformat()
        equipment_id = clean_text(client.get("equipment_number"))
        service_items = load_service_log()
        record = {
            "id": next_numeric_id(service_items, "LIMP", "id"),
            "client_id": clean_text(client.get("client_id")),
            "client_name": clean_text(client.get("customer_name")),
            "equipment_id": equipment_id,
            "service_type": "limpeza",
            "service_date": service_date,
            "notes": clean_text(request.form.get("notes")),
            "created_at": now_iso(),
        }
        service_items.append(record)
        save_service_log(service_items)

        warehouse_items = load_warehouse_items()
        movements = load_warehouse_movements()
        user = current_user()
        for item in warehouse_items:
            field_name = f"supply_{item.get('id')}"
            quantity = parse_decimal(request.form.get(field_name))
            if quantity <= 0:
                continue
            previous = parse_decimal(item.get("quantity_current"))
            if previous - quantity < 0:
                raise ValueError(f"Estoque insuficiente para {item.get('name')}.")
            item["quantity_current"] = round2(previous - quantity)
            movement = {
                "id": next_numeric_id(movements, "MOV", "id"),
                "item_id": clean_text(item.get("id")),
                "item_name": clean_text(item.get("name")),
                "movement_type": "baixa limpeza",
                "quantity_changed": quantity,
                "previous_balance": previous,
                "final_balance": item["quantity_current"],
                "observation": f"Limpeza semanal {client.get('customer_name')}",
                "user_id": clean_text(user.get("id")),
                "user_name": clean_text(user.get("nome")),
                "user_email": clean_text(user.get("email")),
                "created_at": now_iso(),
            }
            movements.append(movement)
        save_warehouse_items(warehouse_items)
        save_warehouse_movements(movements)
        record_audit("cleaning", "clients", client_id, f"Limpeza registrada para {client.get('customer_name')}.", after=record)
        flash(f"Limpeza de {client.get('customer_name')} registrada com baixa de insumos.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "warehouse")
    return redirect(url_for("index"))


@app.route("/warehouse/items.pdf", methods=["GET"])
@require_permission("warehouse.view")
def download_warehouse_pdf():
    record_audit("generate_pdf", "warehouse", "items", "PDF do almoxarifado gerado.")
    return send_file(
        io.BytesIO(build_warehouse_pdf()),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"sannygold-almoxarifado-{datetime.now().date().isoformat()}.pdf",
    )


@app.route("/warehouse/low-stock.pdf", methods=["GET"])
@require_permission("warehouse.view")
def download_warehouse_low_stock_pdf():
    record_audit("generate_pdf", "warehouse", "low-stock", "PDF de estoque baixo gerado.")
    return send_file(
        io.BytesIO(build_low_stock_warehouse_pdf()),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"sannygold-estoque-baixo-{datetime.now().date().isoformat()}.pdf",
    )


@app.route("/reports/<module>.pdf", methods=["GET"])
def download_module_pdf(module: str):
    try:
        title, payload, permission = build_module_pdf(module)
    except ValueError:
        return "Relatório não encontrado. Abra o painel de relatórios e escolha uma opção disponível.", 404
    if not has_permission(current_user(), permission):
        record_audit(
            "access_denied",
            "permissions",
            permission,
            f"Tentativa de acesso sem permissão ao relatório {title}.",
            after={"permission": permission, "module": module, "path": request.path, "method": request.method},
        )
        flash_action_warning("Acesso restrito para este relatório", "Seu perfil não pode baixar este relatório. O sistema bloqueou o arquivo porque ele pode conter dados operacionais, financeiros ou administrativos.", next_step="Peça ao administrador para liberar o relatório ou use um perfil autorizado.", target_href="#access-management-panel", target_tab="access-tab", action="Ver acessos")
        return redirect(url_for("index", auth="required"))
    record_audit("generate_pdf", "reports", module, f"Relatório PDF {title} gerado.")
    return send_file(
        io.BytesIO(payload),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"sannygold-{module}-{datetime.now().date().isoformat()}.pdf",
    )


@app.route("/clients/<client_id>/report.pdf", methods=["GET"])
@require_permission("clients.view")
def download_client_report(client_id: str):
    client_id = clean_text(client_id)
    clients = load_clients()
    client = next((item for item in clients if clean_text(item.get("client_id")) == client_id), None)
    if not client:
        return "Cliente não encontrado. Abra a lista de clientes e escolha um cadastro existente.", 404
    can_view_finance = has_permission(current_user(), "finance.view")
    detail = build_client_detail_index(
        clients,
        load_contracts(),
        load_service_log(),
        load_quotes(),
        load_route_history(),
        events=load_events(),
        financial_receivables=load_financial_receivables(),
        can_view_finance=can_view_finance,
    ).get(client_id, {})
    record_audit("generate_pdf", "clients", client_id, f"Relatório do cliente {client.get('customer_name') or client_id} gerado.")
    return send_file(
        io.BytesIO(build_client_report_pdf(client, detail, can_view_finance=can_view_finance)),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"sannygold-cliente-{client_id}-{datetime.now().date().isoformat()}.pdf",
    )


@app.route("/exports/<module>.xlsx", methods=["GET"])
def download_module_xlsx(module: str):
    try:
        title, payload, permission = build_module_xlsx(module)
    except ValueError:
        return "Exportação não encontrada. Abra o painel de relatórios e escolha uma opção disponível.", 404
    if not has_permission(current_user(), permission):
        record_audit(
            "access_denied",
            "permissions",
            permission,
            f"Tentativa de acesso sem permissão à exportação {title}.",
            after={"permission": permission, "module": module, "path": request.path, "method": request.method},
        )
        flash_action_warning("Acesso restrito para esta exportação", "Seu perfil não pode baixar esta exportação. O sistema bloqueou o arquivo para proteger dados da operação.", next_step="Peça ao administrador para liberar a exportação ou use um perfil autorizado.", target_href="#access-management-panel", target_tab="access-tab", action="Ver acessos")
        return redirect(url_for("index", auth="required"))
    record_audit("download", "exports", module, f"Exportação Excel {title} baixada.")
    return send_file(
        io.BytesIO(payload),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"sannygold-{module}-{datetime.now().date().isoformat()}.xlsx",
    )


@app.route("/generate", methods=["POST"])
@require_permission("routes.generate")
def generate():
    deliveries_temp_path: Path | None = None
    vehicles_temp_path: Path | None = None
    try:
        all_clients = load_clients()
        all_vehicles = load_vehicles_registry()
        clients_snapshot = all_clients
        vehicles_snapshot = all_vehicles
        uploaded_deliveries = request.files.get("deliveries_file")
        uploaded_vehicles = request.files.get("vehicles_file")
        selected_event_id = clean_text(request.form.get("event_id"))
        selected_event = next((event for event in load_events() if event.get("event_id") == selected_event_id), None) if selected_event_id else None

        if selected_event:
            clients_snapshot = [client for client in all_clients if client.get("client_id") in selected_event.get("client_ids", [])]
            vehicles_snapshot = [vehicle for vehicle in all_vehicles if vehicle.get("vehicle_id") in selected_event.get("vehicle_ids", [])]

        validation_payload = validate_operation_scope(
            selected_event=selected_event,
            clients_snapshot=clients_snapshot,
            vehicles_snapshot=vehicles_snapshot,
            route_data=load_route_data(),
        )
        save_operation_validation(validation_payload)
        if not validation_payload.get("is_routable"):
            issues = (validation_payload.get("event_errors") or []) + (validation_payload.get("pending_items") or [])
            flash_generation_block(
                "Rota bloqueada por dados incompletos",
                "Corrija os itens abaixo antes de gerar rota, PDF operacional ou links de endereço.",
                issues,
            )
            return redirect(url_for("index", _anchor="gerador"))

        if uploaded_deliveries and uploaded_deliveries.filename and uploaded_deliveries.filename.strip():
            deliveries_path = save_upload(
                "deliveries_file",
                allowed_extensions=ROUTE_UPLOAD_EXTENSIONS,
                field_label="CSV de entregas",
                allowed_label=".csv",
            )
        else:
            deliveries_temp_path = build_deliveries_csv_for_clients(clients_snapshot) if selected_event else build_deliveries_csv_from_clients()
            deliveries_path = deliveries_temp_path

        if uploaded_vehicles and uploaded_vehicles.filename and uploaded_vehicles.filename.strip():
            vehicles_path = save_upload(
                "vehicles_file",
                allowed_extensions=ROUTE_UPLOAD_EXTENSIONS,
                field_label="CSV de veículos",
                allowed_label=".csv",
            )
        else:
            vehicles_temp_path = build_vehicles_csv_for_registry(vehicles_snapshot) if selected_event else build_vehicles_csv_from_registry()
            vehicles_path = vehicles_temp_path

        run_route_generation(
            deliveries_path,
            vehicles_path,
            clients_snapshot,
            vehicles_snapshot,
            validation_payload=validation_payload,
            selected_event=selected_event,
        )
        record_audit("generate", "routes", selected_event_id, "Rota gerada com validação prévia.")
        flash("Rotas geradas com sucesso. JSON e PDF atualizados em preview/.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "route")
    finally:
        for temp_path in (deliveries_temp_path, vehicles_temp_path):
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
    return redirect(url_for("index"))


@app.route("/clients", methods=["POST"])
@require_permission("clients.edit")
def save_client():
    try:
        record = create_client_record(request.form)
        events = load_events()
        equipment_commitments, _ = build_event_commitments(events, load_clients())
        equipment_id = clean_text(record.get("equipment_number"))
        same_client_committed = any(
            record.get("client_id") in (event.get("client_ids") or [])
            for event in events
            if event_is_active(event)
        )
        if equipment_id and equipment_commitments.get(equipment_id) and not same_client_committed:
            raise ValueError(f"O equipamento {equipment_id} já está comprometido em um evento ativo e não pode ser reutilizado agora.")
        before = next((item for item in load_clients() if clean_text(item.get("client_id")) == clean_text(record.get("client_id"))), None)
        save_clients(upsert_item(load_clients(), record, "client_id"))
        upsert_contract_from_client(record)
        record_audit("save", "clients", record["client_id"], f"Cliente {record['customer_name']} salvo.", before=before, after=record)
        flash(f"Cliente {record['customer_name']} salvo com sucesso. Endereço e dados operacionais foram atualizados.", "success")
        warnings = client_completion_warnings(record)
        if warnings:
            flash_action_warning(
                "Aviso: cliente salvo com pendências",
                f"Cadastro salvo, mas revise: {', '.join(warnings)}. Essas pendências podem bloquear rota, cobrança ou ordem de serviço.",
                next_step="Abra o cadastro do cliente, complete os dados faltantes e salve novamente.",
                target_href=f"#client-{record['client_id']}",
                target_tab="clients-tab",
                action="Corrigir cliente",
            )
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "client")
    return redirect(url_for("index"))


@app.route("/clients/bulk", methods=["POST"])
@require_permission("clients.edit")
def save_clients_bulk():
    try:
        records = parse_bulk_clients(clean_text(request.form.get("bulk_clients")))
        items = load_clients()
        for record in records:
            items = upsert_item(items, record, "client_id")
        validate_client_equipment_conflicts(items)
        save_clients(items)
        for record in records:
            upsert_contract_from_client(record)
        record_audit("bulk_import", "clients", "", f"{len(records)} clientes adicionados em lote.")
        flash(f"{len(records)} enderecos adicionados em lote com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "client")
    return redirect(url_for("index"))


@app.route("/clients/import-excel", methods=["POST"])
@require_permission("clients.edit")
def import_clients_excel():
    upload_path: Path | None = None
    try:
        uploaded = request.files.get("excel_clients_file")
        filename = clean_text((uploaded or {}).filename)
        if not filename:
            raise ValueError("Envie um arquivo Excel de clientes.")
        if not filename.lower().endswith(".xlsx"):
            raise ValueError("Envie um arquivo .xlsx para importação em massa.")
        upload_path = save_upload(
            "excel_clients_file",
            allowed_extensions=EXCEL_UPLOAD_EXTENSIONS,
            field_label="planilha de clientes",
            allowed_label=".xlsx",
        )
        records = parse_excel_clients(upload_path)
        items = load_clients()
        for record in records:
            items = upsert_item(items, record, "client_id")
        validate_client_equipment_conflicts(items)
        save_clients(items)
        for record in records:
            upsert_contract_from_client(record)
        record_audit("excel_import", "clients", "", f"{len(records)} clientes importados por Excel.")
        flash(f"{len(records)} clientes importados da planilha com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "upload")
    finally:
        if upload_path and upload_path.exists():
            upload_path.unlink(missing_ok=True)
    return redirect(url_for("index"))


@app.route("/clients/template.xlsx", methods=["GET"])
@require_permission("clients.view")
def download_clients_template():
    return send_file(
        io.BytesIO(build_clients_template_xlsx()),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="modelo-clientes-sannygold.xlsx",
    )


register_backup_routes(
    app,
    SimpleNamespace(
        create_data_backup=create_data_backup,
        flash_action_error=flash_action_error,
        flash_action_success=flash_action_success,
        flash_action_warning=flash_action_warning,
        list_backup_files=list_backup_files,
        record_audit=record_audit,
        require_permission=require_permission,
        restore_data_backup=restore_data_backup,
    ),
)


@app.route("/daily-closeout.zip", methods=["GET"])
@require_permission("events.close")
def download_daily_closeout():
    settings = load_settings()
    settings["last_closeout_at"] = now_iso()
    save_settings(settings)
    record_audit("download", "closeout", "daily", "Fechamento diário baixado.")
    return send_file(
        io.BytesIO(build_daily_closeout_zip()),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"sannygold-fechamento-{datetime.now().date().isoformat()}.zip",
    )


@app.route("/reports/weekly.pdf", methods=["GET"])
@require_permission("dashboard.view")
def download_weekly_report_pdf():
    payload = build_weekly_management_report_pdf(can_view_finance=has_permission(current_user(), "finance.view"))
    record_audit("generate_pdf", "reports", "weekly", "Relatório semanal PDF gerado.")
    return send_file(
        io.BytesIO(payload),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"sannygold-relatorio-semanal-{datetime.now().date().isoformat()}.pdf",
    )


@app.route("/clients/<client_id>/delete", methods=["POST"])
@require_permission("clients.edit")
def delete_client(client_id: str):
    current_clients = load_clients()
    before = next((item for item in current_clients if clean_text(item.get("client_id")) == clean_text(client_id)), None)
    clients, deleted = delete_item(current_clients, "client_id", client_id)
    if deleted:
        save_clients(clients)
        record_audit("delete", "clients", client_id, f"Cliente {client_id} removido.", before=before)
        flash(f"Cliente {client_id} removido com sucesso. Ele não aparecerá mais nas novas rotas.", "success")
    else:
        flash_action_error(ValueError(f"Cliente {client_id} não encontrado. Atualize a tela e selecione um cliente existente."), "client")
    return redirect(url_for("index"))


@app.route("/vehicles", methods=["POST"])
@require_permission("fleet.edit")
def save_vehicle():
    try:
        record = create_vehicle_record(request.form)
        before = next((item for item in load_vehicles_registry() if clean_text(item.get("vehicle_id")) == clean_text(record.get("vehicle_id"))), None)
        save_vehicles_registry(upsert_item(load_vehicles_registry(), record, "vehicle_id"))
        record_audit("save", "fleet", record["vehicle_id"], f"Veículo {record['vehicle_id']} salvo.", before=before, after=record)
        flash(f"Veículo {record['vehicle_id']} salvo com sucesso. Ele já pode ser usado no planejamento de rotas.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "fleet")
    return redirect(url_for("index"))


@app.route("/vehicles/<vehicle_id>/delete", methods=["POST"])
@require_permission("fleet.edit")
def delete_vehicle(vehicle_id: str):
    current_vehicles = load_vehicles_registry()
    before = next((item for item in current_vehicles if clean_text(item.get("vehicle_id")) == clean_text(vehicle_id)), None)
    vehicles, deleted = delete_item(current_vehicles, "vehicle_id", vehicle_id)
    if deleted:
        save_vehicles_registry(vehicles)
        record_audit("delete", "fleet", vehicle_id, f"Veículo {vehicle_id} removido.", before=before)
        flash(f"Veículo {vehicle_id} removido com sucesso. Ele não ficará disponível para novas rotas.", "success")
    else:
        flash_action_error(ValueError(f"Veículo {vehicle_id} não encontrado. Atualize a tela e selecione um veículo existente."), "fleet")
    return redirect(url_for("index"))


@app.route("/equipment", methods=["POST"])
@require_permission("inventory.edit")
def save_equipment():
    try:
        record = create_equipment_record(request.form)
        if normalize_equipment_status(record.get("status")) in BLOCKED_EQUIPMENT_STATUSES and clean_text(record.get("equipment_id")):
            linked_clients = [client for client in load_clients() if clean_text(client.get("equipment_number")) == clean_text(record.get("equipment_id"))]
            if linked_clients:
                raise ValueError("Não é possível marcar um item vinculado a cliente como manutenção/indisponível sem liberar o vínculo antes.")
        before = next((item for item in load_equipment_registry() if clean_text(item.get("equipment_id")) == clean_text(record.get("equipment_id"))), None)
        save_equipment_registry(upsert_item(load_equipment_registry(), record, "equipment_id"))
        record_audit("save", "equipment", record["equipment_id"], f"Equipamento {record['equipment_id']} salvo.", before=before, after=record)
        flash(f"Equipamento {record['equipment_id']} salvo com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "fleet")
    return redirect(url_for("index"))


@app.route("/equipment/<equipment_id>/delete", methods=["POST"])
@require_permission("inventory.edit")
def delete_equipment(equipment_id: str):
    current_items = load_equipment_registry()
    before = next((item for item in current_items if clean_text(item.get("equipment_id")) == clean_text(equipment_id)), None)
    items, deleted = delete_item(current_items, "equipment_id", equipment_id)
    if deleted:
        save_equipment_registry(items)
        record_audit("delete", "equipment", equipment_id, f"Equipamento {equipment_id} removido.", before=before)
        flash(f"Equipamento {equipment_id} removido com sucesso. Ele não ficará disponível para novas locações.", "success")
    else:
        flash_action_error(ValueError(f"Equipamento {equipment_id} não encontrado. Atualize a tela e selecione um equipamento existente."), "fleet")
    return redirect(url_for("index"))


@app.route("/equipment/<equipment_id>/maintenance", methods=["POST"])
@require_permission("inventory.edit")
def send_equipment_to_maintenance(equipment_id: str):
    items = load_equipment_registry()
    target = next((item for item in items if clean_text(item.get("equipment_id")) == equipment_id), None)
    if not target:
        flash_action_error(ValueError(f"Equipamento {equipment_id} não encontrado. Atualize a tela e selecione um equipamento existente."), "fleet")
        return redirect(url_for("index"))
    before = dict(target)
    target["condition"] = "manutencao"
    target["status"] = "manutencao"
    target["maintenance_reason"] = clean_text(request.form.get("maintenance_reason")) or "Manutenção preventiva"
    target["maintenance_started_at"] = now_iso()
    target["maintenance_expected_release"] = clean_text(request.form.get("maintenance_expected_release"))
    target["maintenance_cost"] = parse_decimal(request.form.get("maintenance_cost"))
    save_equipment_registry(items)
    record_audit("maintenance", "equipment", equipment_id, f"Manutenção registrada para {equipment_id}.", before=before, after=target)
    flash(f"Manutenção registrada para {equipment_id}. O item saiu da disponibilidade operacional.", "success")
    return redirect(url_for("index"))


@app.route("/equipment/<equipment_id>/return", methods=["POST"])
@require_permission("inventory.edit")
def return_equipment_to_stock(equipment_id: str):
    items = load_equipment_registry()
    target = next((item for item in items if item.get("equipment_id") == equipment_id), None)
    if not target:
        flash_action_error(ValueError(f"Equipamento {equipment_id} não encontrado. Atualize a tela e selecione um equipamento existente."), "fleet")
        return redirect(url_for("index"))
    before = dict(target)

    current_status = normalize_equipment_status(target.get("status") or target.get("condition"))
    if current_status not in {"instalado", "retirada_pendente", "retornado"}:
        flash_action_error(ValueError("Retorno do equipamento só pode ser confirmado após o ciclo operacional concluir instalação ou retirada. Isso evita liberar item que ainda está em uso."), "fleet")
        return redirect(url_for("index"))

    target["condition"] = "retornado"
    target["status"] = "retornado"
    target["returned_at"] = datetime.now().isoformat(timespec="seconds")
    save_equipment_registry(items)
    clients = load_clients()
    changed = False
    for client in clients:
        if client.get("equipment_number") == equipment_id:
            client["equipment_number"] = ""
            changed = True
    if changed:
        save_clients(clients)
    record_audit("return", "equipment", equipment_id, f"Equipamento {equipment_id} marcado como retornado.", before=before, after=target)
    flash(f"Equipamento {equipment_id} marcado como retornado. Agora ele pode ser conferido antes de voltar para disponível.", "success")
    return redirect(url_for("index"))


@app.route("/equipment/<equipment_id>/release", methods=["POST"])
@require_permission("inventory.edit")
def release_equipment_to_available(equipment_id: str):
    items = load_equipment_registry()
    target = next((item for item in items if item.get("equipment_id") == equipment_id), None)
    if not target:
        flash_action_error(ValueError(f"Equipamento {equipment_id} não encontrado. Atualize a tela e selecione um equipamento existente."), "fleet")
        return redirect(url_for("index"))
    before = dict(target)
    if normalize_equipment_status(target.get("status") or target.get("condition")) != "retornado":
        flash_action_error(ValueError("Só é possível liberar para disponível após o item estar como retornado. Isso evita disponibilizar equipamento que ainda não voltou."), "fleet")
        return redirect(url_for("index"))
    target["condition"] = "disponivel"
    target["status"] = "disponivel"
    target["maintenance_reason"] = ""
    target["maintenance_expected_release"] = ""
    save_equipment_registry(items)
    record_audit("release", "equipment", equipment_id, f"Equipamento {equipment_id} liberado para disponível.", before=before, after=target)
    flash(f"Equipamento {equipment_id} liberado para disponível. Ele já pode ser usado em nova locação.", "success")
    return redirect(url_for("index"))


@app.route("/field-confirmations", methods=["POST"])
@require_permission("operations.validate")
def save_field_confirmation():
    route_data = load_route_data()
    if not route_data:
        flash_action_error(ValueError("Gere uma rota antes de confirmar execução. Sem rota gerada, não há parada operacional para confirmar."), "route")
        return redirect(url_for("index"))

    client_id = clean_text(request.form.get("client_id"))
    equipment_id = clean_text(request.form.get("equipment_id"))
    vehicle_id = clean_text(request.form.get("vehicle_id"))
    action = clean_text(request.form.get("action"))
    if action not in {"arrival", "execution", "return"}:
        flash_action_error(ValueError("Ação operacional inválida. Escolha uma ação disponível no painel para registrar a confirmação."), "route")
        return redirect(url_for("index"))

    current_route = next((route for route in route_data.get("routes", []) if clean_text(route.get("vehicle_id")) == vehicle_id), None)
    current_stop = next((stop for stop in (current_route or {}).get("stops", []) if clean_text(stop.get("delivery_id")) == client_id), None)
    if not current_route or not current_stop:
        flash_action_error(ValueError("Parada operacional não encontrada para confirmação. Atualize a rota ou selecione uma parada existente."), "route")
        return redirect(url_for("index"))

    timestamp = now_iso()
    confirmations = load_field_confirmations()
    existing = build_field_confirmation_index(confirmations).get(
        (
            clean_text(route_data.get("generated_at")),
            client_id,
            equipment_id,
            vehicle_id,
        ),
        {},
    )
    record = {
        "route_generated_at": clean_text(route_data.get("generated_at")),
        "event_id": clean_text(route_data.get("event_id")),
        "event_title": clean_text(route_data.get("event_title")) or "Operação geral",
        "operation_date": clean_text(route_data.get("operation_date")),
        "client_id": client_id,
        "client_name": clean_text(current_stop.get("customer_name")),
        "equipment_id": equipment_id,
        "vehicle_id": vehicle_id,
        "arrival_confirmed_at": clean_text(existing.get("arrival_confirmed_at")),
        "execution_confirmed_at": clean_text(existing.get("execution_confirmed_at")),
        "return_confirmed_at": clean_text(existing.get("return_confirmed_at")),
    }
    if action == "arrival":
        record["arrival_confirmed_at"] = timestamp
    elif action == "execution":
        record["arrival_confirmed_at"] = record["arrival_confirmed_at"] or timestamp
        record["execution_confirmed_at"] = timestamp
    elif action == "return":
        record["arrival_confirmed_at"] = record["arrival_confirmed_at"] or timestamp
        record["execution_confirmed_at"] = record["execution_confirmed_at"] or timestamp
        record["return_confirmed_at"] = timestamp

        items = load_equipment_registry()
        target = next((item for item in items if item.get("equipment_id") == equipment_id), None)
        if target:
            target["condition"] = "retornado"
            target["returned_at"] = timestamp
            save_equipment_registry(items)
        clients = load_clients()
        changed = False
        for client in clients:
            if client.get("equipment_number") == equipment_id and client.get("client_id") == client_id:
                client["equipment_number"] = ""
                changed = True
        if changed:
            save_clients(clients)

    items = load_equipment_registry()
    target = next((item for item in items if item.get("equipment_id") == equipment_id), None)
    if target:
        if action == "arrival":
            target["status"] = "em_rota"
            target["condition"] = "em_rota"
        elif action == "execution":
            target["status"] = "instalado"
            target["condition"] = "instalado"
        elif action == "return":
            target["status"] = "retornado"
            target["condition"] = "retornado"
            target["returned_at"] = timestamp
        save_equipment_registry(items)

    save_field_confirmations(upsert_field_confirmation(confirmations, record))
    record_audit("field_confirmation", "operations", client_id, f"Confirmação operacional: {action}.", after=record)
    flash("Confirmação operacional registrada com sucesso. O histórico da rota foi atualizado.", "success")
    return redirect(url_for("index"))


@app.route("/settings/financial", methods=["POST"])
@require_permission("finance.edit")
def save_financial_settings():
    try:
        settings = load_settings()
        settings["cost_per_km"] = float(clean_text(request.form.get("cost_per_km"), "0") or 0)
        settings["quote_models"] = settings.get("quote_models") or {}
        save_settings(settings)
        record_audit("save", "finance", "settings", "Configuração financeira atualizada.")
        flash("Configuração financeira atualizada com sucesso. Os próximos cálculos usarão os novos parâmetros.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "finance")
    return redirect(url_for("index"))


@app.route("/settings/quote-models", methods=["POST"])
@require_permission("finance.edit")
def save_quote_models():
    try:
        settings = load_settings()
        settings["quote_models"] = {
            "banheiro_luxo_daily": parse_decimal(request.form.get("banheiro_luxo_daily")),
            "banheiro_luxo_monthly": parse_decimal(request.form.get("banheiro_luxo_monthly")),
            "banheiro_quimico_daily": parse_decimal(request.form.get("banheiro_quimico_daily")),
            "climatizador_daily": parse_decimal(request.form.get("climatizador_daily")),
            "hidratacao_daily": parse_decimal(request.form.get("hidratacao_daily")),
            "limpeza_extra": parse_decimal(request.form.get("limpeza_extra")),
        }
        save_settings(settings)
        record_audit("save", "quotes", "models", "Modelos de orçamento atualizados.")
        flash("Modelos de orçamento atualizados com sucesso. Novos orçamentos usarão esses valores de referência.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "finance")
    return redirect(url_for("index", _anchor="quote-models-panel"))


@app.route("/attachments", methods=["POST"])
@require_permission("clients.edit")
def save_attachment():
    try:
        items = load_attachments()
        record = {
            "id": next_numeric_id(items, "ANX", "id"),
            "scope": clean_text(request.form.get("scope"), "cliente") or "cliente",
            "client_id": clean_text(request.form.get("client_id")),
            "event_id": clean_text(request.form.get("event_id")),
            "title": clean_text(request.form.get("title")) or "Anexo",
            "attachment_url": uploaded_asset_url("attachment_file") or clean_text(request.form.get("attachment_url")),
            "notes": clean_text(request.form.get("notes")),
            "created_at": now_iso(),
        }
        if not record["attachment_url"]:
            raise ValueError("Informe um link ou arquivo para o anexo.")
        items.append(record)
        save_attachments(items)
        record_audit("save", "attachments", record["id"], "Anexo salvo.", after=record)
        flash("Anexo salvo com sucesso. Ele ficará disponível no histórico do cliente ou evento selecionado.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "upload")
    return redirect(url_for("index", _anchor="attachments-panel"))


@app.route("/attachments/<attachment_id>/delete", methods=["POST"])
@require_permission("clients.edit")
def delete_attachment(attachment_id: str):
    items = load_attachments()
    before = next((item for item in items if clean_text(item.get("id")) == clean_text(attachment_id)), None)
    items, deleted = delete_item(items, "id", attachment_id)
    if not deleted or not before:
        flash_action_error(ValueError(f"Anexo {attachment_id} não encontrado. Atualize a tela e selecione um anexo existente."), "upload")
        return redirect(url_for("index", _anchor="attachments-panel"))

    deleted_file = ""
    local_path = uploaded_asset_path_from_url(before.get("attachment_url"))
    if local_path and local_path.exists():
        try:
            local_path.unlink()
            deleted_file = local_path.name
        except OSError:
            deleted_file = ""
    save_attachments(items)
    record_audit(
        "delete",
        "attachments",
        attachment_id,
        f"Anexo {attachment_id} removido.",
        before=before,
        after={"deleted_file": deleted_file, "external_link_removed": not bool(deleted_file)},
    )
    flash("Anexo removido com sucesso. O registro saiu do histórico visível e a auditoria guardou quem removeu.", "success")
    return redirect(url_for("index", _anchor="attachments-panel"))


@app.route("/events/<event_id>/service-order.pdf", methods=["GET"])
@require_permission("events.service_order")
def download_service_order(event_id: str):
    event = next((item for item in load_events() if clean_text(item.get("event_id")) == clean_text(event_id)), None)
    if not event:
        flash_action_error(ValueError("Evento não encontrado para gerar OS. Atualize a tela e selecione um evento existente antes de gerar o documento."), "service_order")
        return redirect(url_for("index"))
    clients = load_clients()
    vehicles = load_vehicles_registry()
    issues = build_service_order_requirements(
        event,
        clients,
        vehicles,
        require_financial_value=has_permission(current_user(), "finance.view"),
    )
    if issues:
        flash_generation_block(
            "Ordem de serviço bloqueada por dados incompletos",
            "Corrija os itens abaixo antes de gerar a OS/PDF para impressão ou entrega à equipe.",
            issues,
        )
        return redirect(url_for("index", _anchor=f"event-{clean_text(event_id)}"))
    payload = build_service_order_pdf(event, clients, vehicles, load_equipment_registry())
    record_audit("generate_service_order", "events", event_id, "Ordem de serviço/PDF gerada.")
    return send_file(
        io.BytesIO(payload),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"sannygold-os-{event_id}.pdf",
    )


@app.route("/events/<event_id>/financial", methods=["POST"])
@require_permission("finance.edit")
def update_event_financial_value(event_id: str):
    try:
        events = load_events()
        target = next((item for item in events if clean_text(item.get("event_id")) == clean_text(event_id)), None)
        if not target:
            raise ValueError("Evento não encontrado para atualizar valor.")
        before = dict(target)
        for field in ("valor_servico", "valor_adicional", "desconto", "recurring_value"):
            if field in request.form:
                target[field] = parse_decimal(request.form.get(field))
        if event_financial_value(target, {client.get("client_id"): client for client in load_clients()}) <= 0:
            raise ValueError("Informe um valor maior que zero para o evento.")
        target["updated_at"] = now_iso()
        save_events(events)
        record_audit("save", "events", event_id, "Valor financeiro do evento atualizado.", before=before, after=target)
        flash("Valor financeiro do evento atualizado com sucesso. O painel financeiro já pode considerar esse novo valor.", "success")
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "finance")
    return redirect(url_for("index", _anchor="financial-decision-panel"))


register_finance_routes(
    app,
    SimpleNamespace(
        build_monthly_closeout=build_monthly_closeout,
        build_monthly_closeout_pdf=build_monthly_closeout_pdf,
        build_receipt_pdf=build_receipt_pdf,
        clean_text=clean_text,
        create_financial_entry_record=create_financial_entry_record,
        create_financial_receivable_record=create_financial_receivable_record,
        delete_item=delete_item,
        flash_action_error=flash_action_error,
        flash_action_success=flash_action_success,
        friendly_error_text=friendly_error_text,
        generate_monthly_contract_receivables=generate_monthly_contract_receivables,
        load_financial_entries=load_financial_entries,
        load_financial_receivables=load_financial_receivables,
        now_iso=now_iso,
        parse_decimal=parse_decimal,
        record_audit=record_audit,
        require_permission=require_permission,
        save_financial_entries=save_financial_entries,
        save_financial_receivables=save_financial_receivables,
        upsert_item=upsert_item,
    ),
)


@app.route("/events", methods=["POST"])
@require_permission("events.create")
def save_event():
    try:
        events = load_events()
        source_event_id = clean_text(request.form.get("duplicated_from_event_id"))
        source_event = None
        form_data = request.form
        if source_event_id:
            source_event = next((item for item in events if clean_text(item.get("event_id")) == source_event_id), None)
            if not source_event:
                raise ValueError("Evento original não encontrado para duplicar. Atualize a tela e selecione uma locação existente.")
            form_data = event_duplication_form_data(request.form, source_event)

        record = create_event_record(form_data)
        if source_event_id:
            record["duplicated_from_event_id"] = source_event_id
        validate_event_links(record, clients=load_clients(), vehicles=load_vehicles_registry(), existing_events=events)
        before = None if source_event_id else next((item for item in events if clean_text(item.get("event_id")) == clean_text(record.get("event_id"))), None)
        save_events(upsert_item(events, record, "event_id"))
        if source_event_id:
            record_audit(
                "duplicate",
                "events",
                record["event_id"],
                f"Locação {record['title']} duplicada a partir de {source_event_id}.",
                before=source_event,
                after=record,
            )
            flash(f"Locação duplicada com sucesso para {record['event_date']}. Revise rota, OS e cobrança antes de executar.", "success")
        else:
            record_audit("save", "events", record["event_id"], f"Evento {record['title']} salvo.", before=before, after=record)
            flash(f"Evento {record['title']} salvo com sucesso.", "success")
        warnings = event_completion_warnings(record)
        if warnings:
            flash_action_warning(
                "Aviso: evento salvo com pendências",
                f"Evento salvo, mas revise: {', '.join(warnings)}. Essas pendências podem bloquear rota, OS/PDF ou cobrança.",
                next_step="Abra o evento, complete os dados faltantes e salve novamente.",
                target_href=f"#event-{record['event_id']}",
                target_tab="events-tab",
                action="Corrigir evento",
            )
    except Exception as exc:  # noqa: BLE001
        flash_action_error(exc, "event")
    return redirect(url_for("index"))


@app.route("/events/<event_id>/recurrence-status", methods=["POST"])
@require_permission("events.edit")
def update_event_recurrence_status(event_id: str):
    events = load_events()
    target = next((event for event in events if clean_text(event.get("event_id")) == event_id), None)
    if not target:
        flash_action_error(ValueError(f"Evento {event_id} não encontrado. Atualize a tela e selecione um evento existente."), "event")
        return redirect(url_for("index"))
    before = dict(target)
    new_status = clean_text(request.form.get("recurrence_status"), "ativo") or "ativo"
    if new_status not in RECURRENCE_STATUS_OPTIONS:
        flash_action_error(ValueError("Status de recorrência inválido. Escolha ativo, pausado ou encerrado antes de salvar."), "event")
        return redirect(url_for("index"))
    target["recurrence_status"] = new_status
    target["next_occurrence_date"] = next_recurrence_date(target) if new_status == "ativo" else ""
    save_events(events)
    record_audit("recurrence_status", "events", event_id, f"Recorrência atualizada para {new_status}.", before=before, after=target)
    flash(f"Recorrência do evento {event_id} atualizada para {new_status}.", "success")
    return redirect(url_for("index"))


@app.route("/events/<event_id>/generate-next-recurrence", methods=["POST"])
@require_permission("events.create")
def generate_next_recurrence(event_id: str):
    events = load_events()
    source = next((event for event in events if clean_text(event.get("event_id")) == event_id), None)
    if not source:
        flash_action_error(ValueError(f"Evento {event_id} não encontrado. Atualize a tela e selecione um evento existente."), "event")
        return redirect(url_for("index"))
    if clean_text(source.get("recurrence_enabled")) != "true" or clean_text(source.get("recurrence_status"), "ativo") != "ativo":
        flash_action_error(ValueError("Este evento não possui recorrência ativa. Só é possível gerar próxima ocorrência de eventos recorrentes ativos."), "event")
        return redirect(url_for("index"))
    next_date = clean_text(source.get("next_occurrence_date")) or next_recurrence_date(source)
    if not next_date:
        flash_action_error(ValueError("Não foi encontrada próxima ocorrência válida para gerar. Revise a frequência, a data inicial e o prazo final da recorrência."), "event")
        return redirect(url_for("index"))
    duplicate = next(
        (
            event for event in events
            if clean_text(event.get("recurrence_parent_event_id")) == event_id and clean_text(event.get("event_date")) == next_date
        ),
        None,
    )
    if duplicate:
        flash_action_error(ValueError("A próxima ocorrência já foi gerada anteriormente. O sistema bloqueou a duplicidade para evitar dois eventos iguais na agenda."), "event")
        return redirect(url_for("index"))
    occurrence = {
        **source,
        "event_id": next_numeric_id(events, "EVT", "event_id"),
        "event_date": next_date,
        "event_end_date": parse_date(next_date).fromordinal(parse_date(next_date).toordinal() + event_duration_days(source)).isoformat(),
        "status": "confirmado",
        "last_route_generated_at": "",
        "recurrence_parent_event_id": event_id,
        "recurrence_generated": "true",
        "title": clean_text(source.get("title")),
    }
    occurrence["next_occurrence_date"] = ""
    occurrence["recurrence_enabled"] = ""
    validate_event_links(occurrence, clients=load_clients(), vehicles=load_vehicles_registry(), existing_events=events)
    events.append(occurrence)
    source["next_occurrence_date"] = next_recurrence_date(source, parse_date(next_date))
    save_events(events)
    record_audit("generate_recurrence", "events", occurrence["event_id"], f"Recorrência gerada a partir de {event_id}.", after=occurrence)
    flash(f"Próxima recorrência de {source.get('title')} gerada para {next_date}.", "success")
    return redirect(url_for("index"))


@app.route("/events/<event_id>/delete", methods=["POST"])
@require_permission("events.edit")
def delete_event(event_id: str):
    current_events = load_events()
    before = next((item for item in current_events if clean_text(item.get("event_id")) == clean_text(event_id)), None)
    events, deleted = delete_item(current_events, "event_id", event_id)
    if deleted:
        save_events(events)
        record_audit("delete", "events", event_id, f"Evento {event_id} removido.", before=before)
        flash(f"Evento {event_id} removido com sucesso.", "success")
    else:
        flash_action_error(ValueError(f"Evento {event_id} não encontrado. Atualize a tela e selecione um evento existente."), "event")
    return redirect(url_for("index"))


@app.route("/events/<event_id>/status", methods=["POST"])
@require_permission("events.close")
def update_event_status(event_id: str):
    events = load_events()
    target = next((event for event in events if event.get("event_id") == event_id), None)
    if not target:
        flash_action_error(ValueError(f"Evento {event_id} não encontrado. Atualize a tela e selecione um evento existente."), "event")
        return redirect(url_for("index"))
    before = dict(target)

    new_status = normalize_event_status(request.form.get("status"), normalize_event_status(target.get("status"), "rascunho"))
    if new_status == "concluido":
        clients = load_clients()
        inventory = build_inventory_view(clients, load_route_data(), load_field_confirmations())
        linked_client_ids = set(target.get("client_ids") or [])
        linked_equipment = [
            item for item in inventory
            if clean_text(item.get("linked_client_id")) in linked_client_ids and item.get("status") in {"em_rota", "instalado", "retirada_pendente"}
        ]
        if linked_equipment:
            flash_action_error(ValueError("Não é possível finalizar o evento enquanto houver equipamento em rota, instalado ou com retirada pendente. Confirme o retorno dos equipamentos antes de encerrar."), "event")
            return redirect(url_for("index"))
    target["status"] = new_status
    save_events(events)
    record_audit("status", "events", event_id, f"Status atualizado para {new_status}.", before=before, after=target)
    flash(f"Status do evento {event_id} atualizado para {event_status_label(target['status'])}.", "success")
    return redirect(url_for("index"))


@app.route("/validate-operation", methods=["POST"])
@require_permission("operations.validate")
def validate_operation():
    all_clients = load_clients()
    all_vehicles = load_vehicles_registry()
    selected_event_id = clean_text(request.form.get("event_id"))
    selected_event = next((event for event in load_events() if event.get("event_id") == selected_event_id), None) if selected_event_id else None
    clients_snapshot = all_clients if not selected_event else [client for client in all_clients if client.get("client_id") in selected_event.get("client_ids", [])]
    vehicles_snapshot = all_vehicles if not selected_event else [vehicle for vehicle in all_vehicles if vehicle.get("vehicle_id") in selected_event.get("vehicle_ids", [])]
    validation_payload = validate_operation_scope(
        selected_event=selected_event,
        clients_snapshot=clients_snapshot,
        vehicles_snapshot=vehicles_snapshot,
        route_data=load_route_data(),
    )
    save_operation_validation(validation_payload)
    record_audit("validate", "operations", selected_event_id, "Validação operacional executada.", after=validation_payload)
    if validation_payload.get("is_routable"):
        flash("Validação operacional concluída: operação apta para roteirização.", "success")
    else:
        flash_action_error(ValueError("Validação operacional encontrou bloqueios. Revise o painel de elegibilidade antes de gerar rota, OS ou PDF."), "route")
    return redirect(url_for("index"))


@app.route("/geocode", methods=["POST"])
@require_permission("clients.edit")
def geocode():
    try:
        address = clean_text(request.form.get("address"))
        if not address:
            raise ValueError("Informe um endereco para buscar latitude e longitude.")
        return jsonify({"ok": True, **geocode_address(address)})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": friendly_error_text(exc, "client")}), 400


@app.route("/preview/<path:filename>", methods=["GET"])
@require_permission("routes.view")
def preview_file(filename: str):
    return send_from_directory(PREVIEW_DIR, filename, as_attachment=False)


@app.route("/uploads/assets/<path:filename>", methods=["GET"])
@require_permission("dashboard.view")
def uploaded_asset(filename: str):
    return send_from_directory(UPLOADS_DIR / "assets", filename, as_attachment=False)


if __name__ == "__main__":
    app.run(
        debug=FLASK_DEBUG_ENABLED and not IS_PRODUCTION,
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
    )
