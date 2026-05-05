from __future__ import annotations

import csv
import importlib.util
import io
import json
import os
import secrets
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for
from werkzeug.datastructures import MultiDict
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from app.executive import build_executive_dashboard
from app.security import DEFAULT_SECRET_KEY, build_security_posture, password_change_required, password_policy_issues


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BASE_DIR / "scripts" / "plan_routes.py"
DEFAULT_STORAGE_ROOT = Path("/tmp/rotaflow") if os.environ.get("VERCEL") else BASE_DIR
STORAGE_ROOT = Path(os.environ.get("ROTAFLOW_STORAGE_DIR", str(DEFAULT_STORAGE_ROOT)))
DATA_DIR = STORAGE_ROOT / "data"
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
UPLOADS_DIR = STORAGE_ROOT / "uploads"
PREVIEW_DIR = STORAGE_ROOT / "preview"
ROUTE_JSON_PATH = PREVIEW_DIR / "route-plan-mobile.json"
ROUTE_PDF_PATH = PREVIEW_DIR / "route-plan.pdf"
USER_MANUAL_PDF_PATH = BASE_DIR / "output" / "pdf" / "sannygold-manual-rapido-equipe.pdf"
APP_VERSION = os.environ.get("SANNYGOLD_APP_VERSION", "v1.0.0")
DEPLOY_TARGET = "vercel" if os.environ.get("VERCEL") else ("render" if os.environ.get("RENDER") else "local")
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
}
RECURRENCE_STATUS_OPTIONS = {"ativo", "pausado", "encerrado"}
RECURRENCE_FREQUENCIES = {"semanal", "quinzenal", "mensal", "personalizada"}
CLIENT_BILLING_MODELS = {"mensal", "avulso", "orcamento"}
CLIENT_CLEANING_FREQUENCIES = {"semanal", "quinzenal", "mensal", "sob_demanda", "nao_aplica"}
CLIENT_SERVICE_PROFILES = {"limpeza_semanal", "instalacao", "retirada", "evento_avulso", "apoio"}
EVENT_STATUS_FLOW = [
    {"key": "orcamento", "label": "Orçamento", "description": "Pedido recebido ou proposta em montagem."},
    {"key": "confirmado", "label": "Confirmado", "description": "Cliente aprovou e a operação pode ser preparada."},
    {"key": "em_preparacao", "label": "Em preparação", "description": "Equipamentos, equipe, rota e financeiro em conferência."},
    {"key": "em_andamento", "label": "Em andamento", "description": "Entrega, instalação, permanência ou atendimento em execução."},
    {"key": "finalizado", "label": "Finalizado", "description": "Operação concluída, aguardando conferência final ou pagamento."},
    {"key": "pago", "label": "Pago", "description": "Fechamento recebido e registrado."},
    {"key": "cancelado", "label": "Cancelado", "description": "Evento cancelado ou sem continuidade."},
]
EVENT_STATUS_LABELS = {item["key"]: item["label"] for item in EVENT_STATUS_FLOW}
EVENT_STATUS_OPTIONS = set(EVENT_STATUS_LABELS)
EVENT_STATUS_ALIASES = {
    "novo": "orcamento",
    "planejado": "confirmado",
    "em_execucao": "em_andamento",
    "em rota": "em_andamento",
}
ACTIVE_EVENT_STATUSES = {"orcamento", "confirmado", "em_preparacao", "em_andamento", "planejado", "em_execucao"}

app = Flask(__name__)
SECRET_KEY_CONFIGURED = bool(os.environ.get("SANNYGOLD_SECRET_KEY"))
app.config["SECRET_KEY"] = os.environ.get("SANNYGOLD_SECRET_KEY") or secrets.token_urlsafe(32)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)


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


def ensure_storage_dirs() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
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


def normalize_event_status(value: str | None, fallback: str = "confirmado") -> str:
    status = clean_text(value, fallback).lower().replace(" ", "_")
    status = EVENT_STATUS_ALIASES.get(status, status)
    return status if status in EVENT_STATUS_OPTIONS else fallback


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
    extension = Path(uploaded.filename).suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise ValueError("Envie uma imagem JPG, PNG, WEBP ou GIF.")
    safe_name = secure_filename(uploaded.filename) or f"foto{extension}"
    destination_dir = UPLOADS_DIR / "assets"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}-{safe_name}"
    uploaded.save(destination)
    return url_for("uploaded_asset", filename=destination.name)


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
        raise ValueError("Informe um valor a receber maior que zero.")
    status = clean_text(form.get("status"), "aguardando").lower()
    if status not in {"aguardando", "parcial", "pago", "vencido"}:
        raise ValueError("Status de recebimento inválido.")
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
        raise ValueError("Tipo de lançamento financeiro inválido.")
    amount = parse_decimal(form.get("amount"))
    if amount <= 0:
        raise ValueError("Informe um valor de lançamento maior que zero.")
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
        raise ValueError("Informe nome e telefone para o orçamento.")
    if quantity <= 0:
        raise ValueError("Quantidade do orçamento deve ser maior que zero.")
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


def record_audit(action: str, module: str, target_id: str = "", detail: str = "", before=None, after=None) -> None:
    user = current_user()
    items = load_audit_log()
    entry = {
        "id": next_numeric_id(items, "AUD", "id"),
        "created_at": now_iso(),
        "action": clean_text(action),
        "module": clean_text(module),
        "target_id": clean_text(target_id),
        "detail": clean_text(detail),
        "user_id": clean_text(user.get("id")),
        "user_name": clean_text(user.get("nome")),
        "user_email": clean_text(user.get("email")),
        "user_role": clean_text(user.get("role")),
    }
    if before is not None:
        entry["before"] = before
    if after is not None:
        entry["after"] = after
    items.append(entry)
    save_audit_log(items)


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


def load_users() -> list[dict]:
    return load_json_list(USERS_PATH)


def save_users(users: list[dict]) -> None:
    save_json_list(USERS_PATH, sort_by_label(users, "nome", "email"))


def create_user_record(form, existing_users: list[dict]) -> dict:
    user_id = clean_text(form.get("user_id")) or next_numeric_id(existing_users, "USR", "id")
    current = next((user for user in existing_users if clean_text(user.get("id")) == user_id), {})
    nome = clean_text(form.get("nome"))
    email = clean_text(form.get("email")).lower()
    role = clean_text(form.get("role"), "leitura") or "leitura"
    status = clean_text(form.get("status"), "ativo") or "ativo"
    password = form.get("password", "")
    if not nome:
        raise ValueError("Informe o nome do usuário.")
    if not email:
        raise ValueError("Informe o email do usuário.")
    if role not in ROLES or role == "guest":
        raise ValueError("Role inválida para usuário interno.")
    if status not in {"ativo", "inativo"}:
        raise ValueError("Status inválido.")
    if not current and not password:
        raise ValueError("Informe uma senha inicial para o usuário.")
    issues = password_policy_issues(password, [nome, email]) if password else []
    if issues:
        raise ValueError(issues[0])
    duplicate = next((user for user in existing_users if clean_text(user.get("email")).lower() == email and clean_text(user.get("id")) != user_id), None)
    if duplicate:
        raise ValueError("Já existe usuário com este email.")
    now = now_iso()
    return {
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
        flash("Sessão expirada. Entre novamente para continuar.", "warning")
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
                if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
                    return jsonify({"ok": False, "error": "Acesso não autorizado."}), 401
                flash("Acesso restrito. Entre na conta para continuar.", "warning")
                return redirect(url_for("index", auth="required"))
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


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
        "last_closeout_at": data.get("last_closeout_at", ""),
    }


def save_settings(settings: dict) -> None:
    ensure_storage_dirs()
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_system_status_snapshot() -> dict:
    ensure_storage_dirs()
    settings = load_settings()
    users = load_users()
    active_users = [user for user in users if clean_text(user.get("status")) == "ativo"]
    storage_ready = all(path.exists() for path in (DATA_DIR, PREVIEW_DIR, UPLOADS_DIR))
    health = {
        "ok": True,
        "storage_ready": storage_ready,
        "has_secret_key": SECRET_KEY_CONFIGURED,
        "has_recent_backup": bool(clean_text(settings.get("last_backup_at"))),
        "has_recent_closeout": bool(clean_text(settings.get("last_closeout_at"))),
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
    }
    operations = {
        "last_backup_at": clean_text(settings.get("last_backup_at")),
        "last_closeout_at": clean_text(settings.get("last_closeout_at")),
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
            "8. Registrar checklist de saída",
            checklist_marked,
            problem="Nenhum checklist de saída foi marcado em evento.",
            next_action="Editar um evento e marcar os itens conferidos antes da saída.",
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
        raise ValueError("Preencha ID, nome, endereco, latitude e longitude do cliente.")

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
        raise ValueError("Servico, prioridade e quantidade devem ser maiores que zero.")
    if hhmm_to_minutes(window_start) >= hhmm_to_minutes(window_end):
        raise ValueError("A janela do evento deve ter hora inicial menor que a final.")

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
                f"O equipamento {equipment_number} ja esta vinculado ao cliente {conflict.get('customer_name') or conflict.get('client_id')}."
            )
        if linked_equipment and normalize_equipment_status(linked_equipment.get("status") or linked_equipment.get("condition")) in BLOCKED_EQUIPMENT_STATUSES:
            raise ValueError(f"O equipamento {equipment_number} está {normalize_equipment_status(linked_equipment.get('status') or linked_equipment.get('condition'))} e não pode ser reservado.")

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
        raise ValueError("Informe nome e data inicial do evento.")
    start_date = parse_date(event_date)
    end_date = parse_date(event_end_date)
    if not start_date or not end_date:
        raise ValueError("Informe datas válidas para o evento.")
    if end_date < start_date:
        raise ValueError("A data final do evento não pode ser anterior à data inicial.")

    client_ids = request.form.getlist("event_client_ids")
    vehicle_ids = request.form.getlist("event_vehicle_ids")
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
        "status": normalize_event_status(form.get("status"), "confirmado"),
        "client_ids": client_ids,
        "vehicle_ids": vehicle_ids,
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
        raise ValueError("Informe o ID do veiculo.")

    capacity = int(clean_text(form.get("capacity"), "1"))
    max_stops = int(clean_text(form.get("max_stops"), "999"))
    max_minutes = int(clean_text(form.get("max_minutes"), "600"))
    if capacity <= 0 or max_stops <= 0 or max_minutes <= 0:
        raise ValueError("Capacidade, maximo de paradas e maximo de minutos devem ser maiores que zero.")

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
        raise ValueError("Informe o ID e o tipo do equipamento.")
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
        raise ValueError("Cole pelo menos uma linha para importacao em lote.")

    clients = load_clients()
    current_number = int("".join(ch for ch in next_numeric_id(clients, "CLI", "client_id") if ch.isdigit()) or "1")
    records: list[dict] = []

    for index, line in enumerate(lines, start=1):
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 4:
            raise ValueError(
                f"Linha {index} invalida. Use: nome | endereco | latitude | longitude | tipo | equipamento | quantidade | equipamento_id | servico | prioridade | valor_servico | custo_equipe | custo_equipamento | janela_inicio | janela_fim | veiculo_travado | contato | telefone | cpf_cnpj | email | nota | numero_nota"
            )
        window_start = parts[13] if len(parts) > 13 else "08:00"
        window_end = parts[14] if len(parts) > 14 else "18:00"
        if hhmm_to_minutes(window_start) >= hhmm_to_minutes(window_end):
            raise ValueError(f"Linha {index} invalida. A janela inicial deve ser menor que a final.")
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
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in (
            CLIENTS_PATH,
            VEHICLES_PATH,
            EQUIPMENT_PATH,
            EVENTS_PATH,
            ROUTE_HISTORY_PATH,
            SETTINGS_PATH,
            FIELD_CONFIRMATIONS_PATH,
            OPERATION_VALIDATION_PATH,
            FORECAST_AUDIT_PATH,
            AUDIT_LOG_PATH,
            WAREHOUSE_ITEMS_PATH,
            WAREHOUSE_MOVEMENTS_PATH,
        ):
            if path.exists():
                archive.write(path, arcname=f"data/{path.name}")
        if ROUTE_JSON_PATH.exists():
            archive.write(ROUTE_JSON_PATH, arcname="preview/route-plan-mobile.json")
        if ROUTE_PDF_PATH.exists():
            archive.write(ROUTE_PDF_PATH, arcname="preview/route-plan.pdf")
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
        raise ValueError("Endereco nao encontrado para geocodificacao.")
    top = payload[0]
    return {"lat": float(top["lat"]), "lng": float(top["lon"]), "display_name": top.get("display_name") or address, "provider": "openstreetmap", "place_id": ""}


def build_deliveries_csv_from_clients() -> Path:
    clients = load_clients()
    if not clients:
        raise ValueError("Cadastre pelo menos um endereco manual ou envie um CSV de entregas.")

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
        raise ValueError("Nenhum cliente vinculado ao evento selecionado.")

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
        raise ValueError("Cadastre pelo menos um veiculo manual ou envie um CSV de veiculos.")

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
        raise ValueError("Nenhum veiculo vinculado ao evento selecionado.")
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


def build_upload_path(original_name: str) -> Path:
    ensure_storage_dirs()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:8]
    safe_name = secure_filename(original_name) or "arquivo.csv"
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


def save_upload(field_name: str) -> Path:
    uploaded = request.files.get(field_name)
    if uploaded is None or uploaded.filename is None or not uploaded.filename.strip():
        raise ValueError(f"Envie o arquivo de {field_name}.")
    destination = build_upload_path(uploaded.filename)
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
    if linked_event and clean_text(linked_event.get("status")) == "finalizado" and linked_client:
        return "retirada_pendente", "Evento finalizado aguardando retirada"
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

    event_errors: list[dict] = []
    if selected_event:
        if not clean_text(selected_event.get("event_date")):
            event_errors.append({"reason_code": "evento_inapto", "reason_label": pending_reason_label("evento_inapto"), "reason": "Evento sem data válida."})
        if parse_date(clean_text(selected_event.get("event_end_date")) or clean_text(selected_event.get("event_date"))) is None:
            event_errors.append({"reason_code": "evento_inapto", "reason_label": pending_reason_label("evento_inapto"), "reason": "Evento sem data final válida."})
        elif parse_date(clean_text(selected_event.get("event_end_date")) or clean_text(selected_event.get("event_date"))) < parse_date(clean_text(selected_event.get("event_date"))):
            event_errors.append({"reason_code": "evento_inapto", "reason_label": pending_reason_label("evento_inapto"), "reason": "Período do evento inválido."})
        if normalize_event_status(selected_event.get("status")) in {"finalizado", "pago", "cancelado"}:
            event_errors.append({"reason_code": "evento_inapto", "reason_label": pending_reason_label("evento_inapto"), "reason": "Evento já está finalizado."})
        if not clients_snapshot or not vehicles_snapshot:
            event_errors.append({"reason_code": "evento_inapto", "reason_label": pending_reason_label("evento_inapto"), "reason": "Evento não possui clientes e veículos mínimos para roteirização."})

    vehicle_capacity_total = sum(int(vehicle.get("capacity") or 0) for vehicle in vehicles_snapshot)
    total_demand = sum(int(client.get("equipment_quantity") or 0) for client in clients_snapshot)
    if vehicles_snapshot and total_demand > vehicle_capacity_total:
        event_errors.append({"reason_code": "capacidade_excedida", "reason_label": pending_reason_label("capacidade_excedida"), "reason": "Demanda maior que a capacidade total da frota elegível."})

    pending_items: list[dict] = []
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
            if conflicts or equipment.get("status") in COMMITTED_EQUIPMENT_STATUSES:
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
        "is_routable": not event_errors and bool(eligible_clients) and bool(eligible_vehicle_ids),
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
        if status in {"orcamento", "confirmado", "em_preparacao"}:
            bucket["planned_count"] += 1
        elif status == "em_andamento":
            bucket["execution_count"] += 1
        elif status in {"finalizado", "pago"}:
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
        if normalize_event_status(event.get("status")) in {"em_andamento", "finalizado"} and any(not item.get("done") for item in event.get("checklist", [])):
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
        opening_detail = f"{len(blocking_warnings)} bloqueio(s) precisam ser resolvidos antes da saída."
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
    closeout_detail = "Feche o dia quando as confirmações operacionais e o backup estiverem em dia."
    if last_closeout_at and str(last_closeout_at).startswith(datetime.now().date().isoformat()):
        closeout_status = "ready"
        closeout_detail = "O fechamento diário já foi gerado hoje."
    elif last_backup_at:
        closeout_status = "attention"
        closeout_detail = "Faça o fechamento diário depois do backup e das confirmações finais."

    if opening_status == "block":
        next_action = {
            "title": "Corrigir bloqueios antes da saída",
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
            "title": "Concluir confirmações e fechamento",
            "detail": closeout_detail,
            "target_tab": "summary-tab",
            "target_href": "#central-day-panel",
            "action": "Finalizar dia",
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


def build_global_search_items(
    clients: list[dict],
    events: list[dict],
    vehicles: list[dict],
    equipment: list[dict],
    warehouse_dashboard: dict,
    receivables: list[dict] | None = None,
) -> list[dict]:
    items: list[dict] = []
    for client in clients:
        items.append({
            "module": "Clientes",
            "module_key": "clientes",
            "title": clean_text(client.get("customer_name")) or clean_text(client.get("client_id")),
            "detail": f"{client.get('client_id')} • {client.get('address')} • {client.get('phone') or 'sem telefone'}",
            "target_tab": "clients-tab",
            "target_href": f"#client-{clean_text(client.get('client_id'))}",
            "text": " ".join(str(client.get(field) or "") for field in ("client_id", "customer_name", "address", "phone", "equipment_number")),
        })
    for event in events:
        items.append({
            "module": "Eventos",
            "module_key": "eventos",
            "title": clean_text(event.get("title")) or clean_text(event.get("event_id")),
            "detail": f"{event.get('event_id')} • {event.get('event_date')} • {event.get('status')}",
            "target_tab": "events-tab",
            "target_href": f"#event-{clean_text(event.get('event_id'))}",
            "text": " ".join(str(event.get(field) or "") for field in ("event_id", "title", "status", "event_date")),
        })
    for vehicle in vehicles:
        items.append({
            "module": "Frota",
            "module_key": "frota",
            "title": clean_text(vehicle.get("vehicle_id")),
            "detail": f"{vehicle.get('vehicle_type')} • placa {vehicle.get('plate') or 'n/d'}",
            "target_tab": "fleet-tab",
            "target_href": f"#vehicle-{clean_text(vehicle.get('vehicle_id'))}",
            "text": " ".join(str(vehicle.get(field) or "") for field in ("vehicle_id", "vehicle_type", "plate", "model")),
        })
    for item in equipment:
        items.append({
            "module": "Equipamentos",
            "module_key": "equipamentos",
            "title": clean_text(item.get("equipment_id")),
            "detail": f"{item.get('equipment_type')} • placa {item.get('plate') or 'n/d'} • {item.get('status')}",
            "target_tab": "fleet-tab",
            "target_href": f"#equipment-{clean_text(item.get('equipment_id'))}",
            "text": " ".join(str(item.get(field) or "") for field in ("equipment_id", "equipment_type", "plate", "status", "linked_client_name", "notes")),
        })
    for item in warehouse_dashboard.get("items") or []:
        items.append({
            "module": "Almoxarifado",
            "module_key": "almoxarifado",
            "title": clean_text(item.get("name")),
            "detail": f"{item.get('category')} • {item.get('quantity_current')} {item.get('unit')} • {item.get('stock_status_label')}",
            "target_tab": "warehouse-tab",
            "target_href": "#warehouse-pane",
            "text": " ".join(str(item.get(field) or "") for field in ("id", "name", "category", "storage_location", "purchase_location")),
        })
    for receivable in receivables or []:
        items.append({
            "module": "Financeiro",
            "module_key": "financeiro",
            "title": clean_text(receivable.get("client_name")) or clean_text(receivable.get("id")),
            "detail": f"{receivable.get('id')} • NF {receivable.get('invoice_number') or 'n/d'} • {format_currency_br(receivable.get('amount'))}",
            "target_tab": "summary-tab",
            "target_href": "#receivables-panel",
            "text": " ".join(str(receivable.get(field) or "") for field in ("id", "client_name", "client_phone", "event_title", "service_type", "invoice_number", "payment_method", "status")),
        })
    return items[:80]


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
    process_statuses = [item["label"] for item in EVENT_STATUS_FLOW]
    workflow_tracks = [
        {
            "label": "Orçamento",
            "detail": "Pedido do cliente, modelo de serviço, quantidade, valor sugerido e retorno comercial.",
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
            "detail": "Tipo, placa quando for trailer, status, foto, manutenção, vínculo com cliente e histórico de uso.",
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
) -> dict[str, dict]:
    contracts_by_client = {clean_text(item.get("client_id")): item for item in contracts}
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
    result = {}
    for client in clients:
        client_id = clean_text(client.get("client_id"))
        cleanings = sorted(cleanings_by_client.get(client_id, []), key=lambda item: clean_text(item.get("service_date")), reverse=True)
        routes = sorted(routes_by_client.get(client_id, []), key=lambda item: clean_text(item.get("generated_at")), reverse=True)
        result[client_id] = {
            "contract": contracts_by_client.get(client_id, {}),
            "cleanings_count": len(cleanings),
            "last_cleaning": cleanings[0] if cleanings else {},
            "recent_cleanings": cleanings[:4],
            "recent_routes": routes[:4],
            "open_quotes": quotes_by_name.get(normalize_business_text(client.get("customer_name")), [])[:3],
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
) -> dict:
    today = datetime.now().date().isoformat()
    today_events = [
        item for item in events
        if clean_text(item.get("event_date")) <= today <= (clean_text(item.get("event_end_date")) or clean_text(item.get("event_date")))
    ]
    today_cleanings = [item for item in cleaning_agenda if clean_text(item.get("service_date")) == today]
    today_receivables = [
        item for item in financial_management.get("receivables_due_soon", [])
        if clean_text(item.get("due_date")) == today
    ]
    route_stops = sum(len(route.get("stops", []) or []) for route in (route_data or {}).get("routes", []) or [])
    returns_pending = [item for item in inventory if clean_text(item.get("status")) in {"instalado", "retirada_pendente"}]
    return {
        "today_events": today_events[:8],
        "today_cleanings": today_cleanings[:8],
        "today_receivables": today_receivables[:8],
        "route_stops": route_stops,
        "returns_pending": returns_pending[:8],
        "alerts": usability_alerts[:8],
        "next_actions": [
            {"label": "Cobrar vencidos", "count": len(financial_management.get("overdue", [])), "target": "financial-panel"},
            {"label": "Limpezas de hoje", "count": len(today_cleanings), "target": "contracts-quotes-panel"},
            {"label": "Retiradas pendentes", "count": len(returns_pending), "target": "fleet-pane"},
            {"label": "Paradas em rota", "count": route_stops, "target": "route-list"},
        ],
    }


def build_operational_kanban(quotes: list[dict], financial_management: dict, events: list[dict], inventory: list[dict]) -> list[dict]:
    columns = [
        {"key": "orcamento", "title": "Orçamento", "items": []},
        {"key": "pagamento", "title": "Aguardando pagamento", "items": []},
        {"key": "separar", "title": "Separar equipamento", "items": []},
        {"key": "rota", "title": "Em rota", "items": []},
        {"key": "instalado", "title": "Instalado", "items": []},
        {"key": "retirar", "title": "Retirar", "items": []},
        {"key": "finalizado", "title": "Finalizado", "items": []},
    ]
    by_key = {column["key"]: column for column in columns}
    for quote in quotes[:8]:
        by_key["orcamento"]["items"].append({"title": clean_text(quote.get("customer_name")), "detail": f"{quote.get('equipment_quantity')}x {quote.get('equipment_type')}", "badge": clean_text(quote.get("status"), "novo")})
    for receivable in financial_management.get("overdue", [])[:8]:
        by_key["pagamento"]["items"].append({"title": clean_text(receivable.get("client_name")), "detail": f"{format_currency_br(receivable.get('open_amount'))} vencido", "badge": f"{receivable.get('days_overdue')} dia(s)"})
    for event in events:
        status = clean_text(event.get("status"), "planejado")
        normalized_status = normalize_event_status(status)
        if normalized_status in {"orcamento", "confirmado", "em_preparacao"}:
            by_key["separar"]["items"].append({"title": clean_text(event.get("title")), "detail": clean_text(event.get("event_date")), "badge": f"{event.get('equipment_count', 0)} equip."})
        elif normalized_status == "em_andamento":
            by_key["rota"]["items"].append({"title": clean_text(event.get("title")), "detail": clean_text(event.get("event_date")), "badge": event_status_label(status)})
        elif normalized_status in {"finalizado", "pago"}:
            by_key["finalizado"]["items"].append({"title": clean_text(event.get("title")), "detail": clean_text(event.get("event_date")), "badge": event_status_label(status)})
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
        lines.append(
            f"- {client.get('customer_name') or client_id} | {client.get('address') or 'sem endereço'} | "
            f"{client.get('phone') or 'sem telefone'} | {client.get('equipment_quantity') or 1}x {client.get('equipment_type') or 'Equipamento'} | "
            f"{client.get('equipment_number') or 'sem ID'} | placa {equipment_item.get('plate') or 'n/d'}"
        )
    lines.append("")
    lines.append("Veículos:")
    for vehicle_id in event.get("vehicle_ids", []) or []:
        vehicle = vehicle_map.get(clean_text(vehicle_id), {})
        lines.append(f"- {vehicle_id} | {vehicle.get('vehicle_type') or 'veículo'} | placa {vehicle.get('plate') or 'n/d'}")
    return build_simple_text_pdf(f"SannyGold - Ordem de Serviço {event.get('event_id')}", lines)


def build_calendar_weeks(events: list[dict], horizon_days: int = 35) -> list[list[dict]]:
    today = datetime.now().date()
    start = today - timedelta(days=today.weekday())
    occurrences = expand_future_occurrences(events, horizon_days=horizon_days)
    by_date: dict[str, list[dict]] = {}
    for occurrence in occurrences:
        event_date = clean_text(occurrence.get("event_date"))
        if event_date:
            by_date.setdefault(event_date, []).append(occurrence)

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
        warnings.append({"level": "warning", "title": "Equipamentos vazios", "detail": "Cadastre equipamentos para controlar vínculo e retorno.", "target_tab": "fleet-tab", "target_href": "#fleet-pane", "action": "Abrir equipamentos"})
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
    open_events = [event for event in events if normalize_event_status(event.get("status")) not in {"finalizado", "pago", "cancelado"}]
    maintenance_items = [
        item for item in inventory
        if clean_text(item.get("status")) in {"manutencao", "indisponivel"}
        or clean_text(item.get("maintenance_reason"))
    ]
    inactive_users = [user for user in users if clean_text(user.get("status")) != "ativo"]
    items = [
        {
            "title": "Acessos e senhas",
            "detail": f"{security_posture.get('password_rotation_pending', 0)} troca(s) de senha pendente(s) e {len(inactive_users)} acesso(s) inativo(s).",
            "level": "warning" if security_posture.get("password_rotation_pending") else "ready",
        },
        {
            "title": "Cadastros de clientes",
            "detail": f"{len(incomplete_clients)} cliente(s) sem dados essenciais para operação.",
            "level": "warning" if incomplete_clients else "ready",
        },
        {
            "title": "Eventos em aberto",
            "detail": f"{len(open_events)} evento(s) ainda não finalizado(s).",
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
    future_dashboard = build_future_capacity_dashboard(events, clients, vehicles, inventory, route_history, selected_agenda_period)
    warehouse_dashboard = build_warehouse_dashboard()
    cleaning_agenda = build_cleaning_agenda(clients, service_log)
    usability_alerts = build_usability_alerts(clients, vehicles, inventory, contracts, cleaning_agenda, warehouse_dashboard)
    usability_home = build_usability_home(clients, events, vehicles, inventory, cleaning_agenda, warehouse_dashboard, usability_alerts)
    daily_command_center = build_daily_command_center(events, cleaning_agenda, financial_management, route_data, inventory, usability_alerts)
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
    )
    equipment_history = build_equipment_history(inventory, clients, route_history, service_log)
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
    can_view_finance = has_permission(user, "finance.view")
    settings = load_settings()
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
    recent_audit_log = load_audit_log()[:8]
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
        enriched_events.append(
            {
                **event,
                "checklist": checklist,
                "clients_count": len(linked_clients),
                "vehicles_count": len(linked_vehicles),
                "equipment_count": equipment_count,
                "financial_summary": latest_financial_by_event.get(clean_text(event.get("event_id")), {}),
                "event_period_label": event_period_label(event),
            }
        )
    return {
        "route_data": route_data,
        "has_pdf": ROUTE_PDF_PATH.exists(),
        "has_json": ROUTE_JSON_PATH.exists(),
        "last_backup_at": clean_text(settings.get("last_backup_at")),
        "last_backup_label": format_datetime_br(settings.get("last_backup_at")),
        "clients": clients,
        "vehicles_registry": vehicles,
        "events": enriched_events,
        "equipment_registry": inventory,
        "available_equipment": [item for item in inventory if item["status"] == "disponivel"],
        "route_history": route_history[:10],
        "operational_dashboard": operational_dashboard,
        "dispatch_today": dispatch_today,
        "daily_flow": daily_flow,
        "operational_validations": validations,
        "pending_reasons": pending_reasons,
        "operation_validation": validation_payload,
        "financial_dashboard": financial_dashboard,
        "financial_management": financial_management,
        "customer_history": build_customer_history(clients, events, route_history, field_confirmations),
        "calendar_weeks": build_calendar_weeks(events),
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
        "client_details": build_client_detail_index(clients, contracts, service_log, quotes, route_history),
        "usability_alerts": usability_alerts,
        "usability_home": usability_home,
        "daily_command_center": daily_command_center,
        "operational_kanban": operational_kanban,
        "general_improvements": general_improvements,
        "equipment_history": equipment_history,
        "contract_financial_dashboard": build_contract_financial_dashboard(contracts, service_log),
        "maintenance_preventive_dashboard": build_maintenance_preventive_dashboard(inventory, service_log),
        "mobile_sync_dashboard": mobile_sync_dashboard,
        "security_posture": security_posture,
        "security_technical_checklist": build_security_technical_checklist(security_posture, system_status),
        "homologation_checklist": homologation_checklist,
        "team_weekly_review": team_weekly_review,
        "system_status": system_status,
        "global_search_items": build_global_search_items(clients, events, vehicles, inventory, warehouse_dashboard, financial_receivables),
        "maintenance_items": [item for item in inventory if item.get("status") in {"manutencao", "indisponivel"} or item.get("maintenance_reason")],
        "can_view_finance": can_view_finance,
        "role_home_label": role_home_labels.get(clean_text(user.get("role")), role_home_labels["guest"]),
        "event_status_flow": EVENT_STATUS_FLOW,
        "event_status_labels": EVENT_STATUS_LABELS,
        "recent_shortcuts": recent_shortcuts,
        "recent_audit_log": recent_audit_log,
        "agenda_period": selected_agenda_period,
        "forecast_audit": load_forecast_audit(),
        "inventory_counts": {
            "total": len(inventory),
            "available": sum(1 for item in inventory if item["status"] == "disponivel"),
            "in_route": sum(1 for item in inventory if item["status"] in {"carregado", "em_rota", "instalado", "retirada_pendente"}),
            "maintenance": sum(1 for item in inventory if item["status"] in {"manutencao", "indisponivel"}),
            "reserved": sum(1 for item in inventory if item["status"] == "reservado"),
        },
        "equipment_family_counts": equipment_family_counts,
        "equipment_type_suggestions": EQUIPMENT_TYPE_SUGGESTIONS,
        "settings": settings,
        "current_user": user,
        "is_authenticated": user["role"] != "guest",
        "users": [sanitize_user(item) for item in users],
        "roles": sorted(ROLES),
        "role_labels": role_labels,
        "permission_catalog": sorted(
            {
                "clients.view",
                "clients.edit",
                "events.create",
                "events.close",
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


@app.route("/auth/login", methods=["POST"])
def login():
    email = clean_text(request.form.get("email")).lower()
    password = request.form.get("password", "")
    if not email or not password:
        flash("Informe email e senha para entrar.", "danger")
        return redirect(url_for("index"))

    user = find_user_by_email(email)
    if not user:
        flash("Usuário não encontrado.", "danger")
        return redirect(url_for("index"))
    if clean_text(user.get("status"), "inativo") != "ativo":
        flash("Usuário inativo. Peça a um administrador para reativar o acesso.", "danger")
        return redirect(url_for("index"))
    if not check_password_hash(clean_text(user.get("senha_hash")), password):
        flash("Senha incorreta.", "danger")
        return redirect(url_for("index"))

    session.clear()
    session.permanent = True
    session["user_id"] = clean_text(user.get("id"))
    session["login_at"] = now_iso()
    record_audit("login", "auth", clean_text(user.get("id")), "Login realizado.")
    if password_change_required(user):
        flash("Troca de senha pendente. Atualize a senha inicial antes de continuar operando em equipe.", "warning")
    flash("Login realizado com sucesso.", "success")
    return redirect(url_for("index"))


@app.route("/auth/logout", methods=["POST"])
def logout():
    record_audit("logout", "auth", clean_text(session.get("user_id")), "Logout manual.")
    session.clear()
    flash("Você saiu da conta. O sistema voltou ao modo visitante.", "success")
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
        flash(issues[0], "danger")
        return redirect(url_for("index"))
    if not user or not check_password_hash(clean_text(user.get("senha_hash")), current_password):
        flash("Senha atual incorreta.", "danger")
        return redirect(url_for("index"))

    user["senha_hash"] = generate_password_hash(new_password, method="pbkdf2:sha256")
    user["must_change_password"] = False
    user["updated_at"] = now_iso()
    save_users(users)
    record_audit("change_password", "auth", user_id, "Senha alterada pelo usuário.")
    flash("Senha atualizada com sucesso.", "success")
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
        flash(f"Usuário {record['email']} salvo com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


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
        flash(str(exc), "danger")
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
        flash(str(exc), "danger")
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
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/quick-rental", methods=["POST"])
@require_permission("clients.edit")
def save_quick_rental():
    try:
        form = request.form
        address = clean_text(form.get("address"))
        lat = clean_text(form.get("lat"))
        lng = clean_text(form.get("lng"))
        if address and (not lat or not lng):
            try:
                geo = geocode_address(address)
                lat = str(geo["lat"])
                lng = str(geo["lng"])
            except Exception:
                lat = str(HQ_LAT)
                lng = str(HQ_LNG)
        client_type = clean_text(form.get("client_type"), "avulso") or "avulso"
        billing_model = clean_text(form.get("billing_model"), "mensal" if client_type == "fixo" else "avulso")
        client_values = {
            "customer_name": clean_text(form.get("customer_name")),
            "contact_name": clean_text(form.get("contact_name")),
            "phone": clean_text(form.get("phone")),
            "address": address,
            "lat": lat,
            "lng": lng,
            "client_type": client_type,
            "equipment_type": clean_text(form.get("equipment_type"), "Banheiro Luxo") or "Banheiro Luxo",
            "equipment_quantity": clean_text(form.get("equipment_quantity"), "1") or "1",
            "billing_model": billing_model,
            "cleaning_frequency": clean_text(form.get("cleaning_frequency"), "semanal" if billing_model == "mensal" else "nao_aplica"),
            "service_profile": "limpeza_semanal" if billing_model == "mensal" else "evento_avulso",
            "default_service_minutes": clean_text(form.get("default_service_minutes"), "20") or "20",
            "default_priority": clean_text(form.get("default_priority"), "3") or "3",
            "window_start": clean_text(form.get("window_start"), "08:00") or "08:00",
            "window_end": clean_text(form.get("window_end"), "18:00") or "18:00",
            "service_value": clean_text(form.get("service_value"), "0") or "0",
            "team_cost": clean_text(form.get("team_cost"), "0") or "0",
            "equipment_cost": clean_text(form.get("equipment_cost"), "0") or "0",
            "invoice_status": clean_text(form.get("invoice_status"), "sem_nota") or "sem_nota",
        }
        clients = load_clients()
        client_record = create_client_record_from_values(client_values, existing_clients=clients)
        save_clients(upsert_item(clients, client_record, "client_id"))
        upsert_contract_from_client(client_record)

        event_date = clean_text(form.get("event_date")) or datetime.now().date().isoformat()
        event_form = MultiDict(
            {
                "title": clean_text(form.get("title")) or f"Locação - {client_record['customer_name']}",
                "event_category": "locacao",
                "event_date": event_date,
                "event_end_date": clean_text(form.get("event_end_date")) or event_date,
                "status": "planejado",
                "valor_servico": client_record["service_value"],
                "custo_equipe": client_record["team_cost"],
                "custo_por_equipamento": client_record["equipment_cost"],
                "notes": clean_text(form.get("notes")),
            }
        )
        event_form.setlist("client_ids", [client_record["client_id"]])
        event_record = create_event_record(event_form)
        save_events(upsert_item(load_events(), event_record, "event_id"))
        record_audit("quick_rental", "events", event_record["event_id"], f"Locação rápida criada para {client_record['customer_name']}.", after=event_record)
        flash(f"Locação criada: {client_record['customer_name']} entrou em clientes e no evento {event_record['event_id']}.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index", _anchor="summary-pane"))


@app.route("/portal/orcamento", methods=["POST"])
def public_quote_request():
    try:
        items = load_quotes()
        record = create_quote_record(request.form, items, source="portal")
        save_quotes(upsert_item(items, record, "id"))
        flash("Solicitação de orçamento recebida. A equipe SannyGold entrará em contato.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
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
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/warehouse/items.pdf", methods=["GET"])
@require_permission("warehouse.view")
def download_warehouse_pdf():
    return send_file(
        io.BytesIO(build_warehouse_pdf()),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"sannygold-almoxarifado-{datetime.now().date().isoformat()}.pdf",
    )


@app.route("/warehouse/low-stock.pdf", methods=["GET"])
@require_permission("warehouse.view")
def download_warehouse_low_stock_pdf():
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
        return "Relatório não encontrado.", 404
    if not has_permission(current_user(), permission):
        flash("Acesso restrito para este relatório.", "warning")
        return redirect(url_for("index", auth="required"))
    record_audit("download", "reports", module, f"Relatório PDF {title} baixado.")
    return send_file(
        io.BytesIO(payload),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"sannygold-{module}-{datetime.now().date().isoformat()}.pdf",
    )


@app.route("/exports/<module>.xlsx", methods=["GET"])
def download_module_xlsx(module: str):
    try:
        title, payload, permission = build_module_xlsx(module)
    except ValueError:
        return "Exportação não encontrada.", 404
    if not has_permission(current_user(), permission):
        flash("Acesso restrito para esta exportação.", "warning")
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
            raise ValueError("Operação bloqueada pela validação pré-rota. Revise o painel de elegibilidade antes de gerar.")

        if uploaded_deliveries and uploaded_deliveries.filename and uploaded_deliveries.filename.strip():
            deliveries_path = save_upload("deliveries_file")
        else:
            deliveries_temp_path = build_deliveries_csv_for_clients(clients_snapshot) if selected_event else build_deliveries_csv_from_clients()
            deliveries_path = deliveries_temp_path

        if uploaded_vehicles and uploaded_vehicles.filename and uploaded_vehicles.filename.strip():
            vehicles_path = save_upload("vehicles_file")
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
        flash(str(exc), "danger")
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
        flash(f"Endereco de {record['customer_name']} salvo com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
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
        flash(str(exc), "danger")
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
        upload_path = save_upload("excel_clients_file")
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
        flash(str(exc), "danger")
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


@app.route("/backup/system.zip", methods=["GET"])
@require_permission("settings.manage")
def download_system_backup():
    settings = load_settings()
    settings["last_backup_at"] = now_iso()
    save_settings(settings)
    record_audit("download", "backup", "system", "Backup completo baixado.")
    return send_file(
        io.BytesIO(build_system_backup_bytes()),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"sannygold-backup-{datetime.now().date().isoformat()}.zip",
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


@app.route("/clients/<client_id>/delete", methods=["POST"])
@require_permission("clients.edit")
def delete_client(client_id: str):
    clients, deleted = delete_item(load_clients(), "client_id", client_id)
    if deleted:
        save_clients(clients)
        record_audit("delete", "clients", client_id, f"Cliente {client_id} removido.")
        flash(f"Endereco {client_id} removido com sucesso.", "success")
    else:
        flash(f"Endereco {client_id} nao encontrado.", "danger")
    return redirect(url_for("index"))


@app.route("/vehicles", methods=["POST"])
@require_permission("fleet.edit")
def save_vehicle():
    try:
        record = create_vehicle_record(request.form)
        before = next((item for item in load_vehicles_registry() if clean_text(item.get("vehicle_id")) == clean_text(record.get("vehicle_id"))), None)
        save_vehicles_registry(upsert_item(load_vehicles_registry(), record, "vehicle_id"))
        record_audit("save", "fleet", record["vehicle_id"], f"Veículo {record['vehicle_id']} salvo.", before=before, after=record)
        flash(f"Veiculo {record['vehicle_id']} salvo com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/vehicles/<vehicle_id>/delete", methods=["POST"])
@require_permission("fleet.edit")
def delete_vehicle(vehicle_id: str):
    vehicles, deleted = delete_item(load_vehicles_registry(), "vehicle_id", vehicle_id)
    if deleted:
        save_vehicles_registry(vehicles)
        record_audit("delete", "fleet", vehicle_id, f"Veículo {vehicle_id} removido.")
        flash(f"Veiculo {vehicle_id} removido com sucesso.", "success")
    else:
        flash(f"Veiculo {vehicle_id} nao encontrado.", "danger")
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
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/equipment/<equipment_id>/delete", methods=["POST"])
@require_permission("inventory.edit")
def delete_equipment(equipment_id: str):
    items, deleted = delete_item(load_equipment_registry(), "equipment_id", equipment_id)
    if deleted:
        save_equipment_registry(items)
        record_audit("delete", "equipment", equipment_id, f"Equipamento {equipment_id} removido.")
        flash(f"Equipamento {equipment_id} removido com sucesso.", "success")
    else:
        flash(f"Equipamento {equipment_id} nao encontrado.", "danger")
    return redirect(url_for("index"))


@app.route("/equipment/<equipment_id>/maintenance", methods=["POST"])
@require_permission("inventory.edit")
def send_equipment_to_maintenance(equipment_id: str):
    items = load_equipment_registry()
    target = next((item for item in items if clean_text(item.get("equipment_id")) == equipment_id), None)
    if not target:
        flash(f"Equipamento {equipment_id} nao encontrado.", "danger")
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
    flash(f"Manutenção registrada para {equipment_id}.", "success")
    return redirect(url_for("index"))


@app.route("/equipment/<equipment_id>/return", methods=["POST"])
@require_permission("inventory.edit")
def return_equipment_to_stock(equipment_id: str):
    items = load_equipment_registry()
    target = next((item for item in items if item.get("equipment_id") == equipment_id), None)
    if not target:
        flash(f"Equipamento {equipment_id} nao encontrado.", "danger")
        return redirect(url_for("index"))

    current_status = normalize_equipment_status(target.get("status") or target.get("condition"))
    if current_status not in {"instalado", "retirada_pendente", "retornado"}:
        flash("Retorno do equipamento só pode ser confirmado após o ciclo operacional concluir instalação/retirada.", "danger")
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
    record_audit("return", "equipment", equipment_id, f"Equipamento {equipment_id} marcado como retornado.")
    flash(f"Equipamento {equipment_id} marcado como retornado.", "success")
    return redirect(url_for("index"))


@app.route("/equipment/<equipment_id>/release", methods=["POST"])
@require_permission("inventory.edit")
def release_equipment_to_available(equipment_id: str):
    items = load_equipment_registry()
    target = next((item for item in items if item.get("equipment_id") == equipment_id), None)
    if not target:
        flash(f"Equipamento {equipment_id} nao encontrado.", "danger")
        return redirect(url_for("index"))
    if normalize_equipment_status(target.get("status") or target.get("condition")) != "retornado":
        flash("Só é possível liberar para disponível após o item estar como retornado.", "danger")
        return redirect(url_for("index"))
    target["condition"] = "disponivel"
    target["status"] = "disponivel"
    target["maintenance_reason"] = ""
    target["maintenance_expected_release"] = ""
    save_equipment_registry(items)
    record_audit("release", "equipment", equipment_id, f"Equipamento {equipment_id} liberado para disponível.")
    flash(f"Equipamento {equipment_id} liberado para disponível.", "success")
    return redirect(url_for("index"))


@app.route("/field-confirmations", methods=["POST"])
@require_permission("operations.validate")
def save_field_confirmation():
    route_data = load_route_data()
    if not route_data:
        flash("Gere uma rota antes de confirmar execução.", "danger")
        return redirect(url_for("index"))

    client_id = clean_text(request.form.get("client_id"))
    equipment_id = clean_text(request.form.get("equipment_id"))
    vehicle_id = clean_text(request.form.get("vehicle_id"))
    action = clean_text(request.form.get("action"))
    if action not in {"arrival", "execution", "return"}:
        flash("Ação operacional inválida.", "danger")
        return redirect(url_for("index"))

    current_route = next((route for route in route_data.get("routes", []) if clean_text(route.get("vehicle_id")) == vehicle_id), None)
    current_stop = next((stop for stop in (current_route or {}).get("stops", []) if clean_text(stop.get("delivery_id")) == client_id), None)
    if not current_route or not current_stop:
        flash("Parada operacional não encontrada para confirmação.", "danger")
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
    flash("Confirmação operacional registrada com sucesso.", "success")
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
        flash("Configuracao financeira atualizada com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
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
        flash("Modelos de orçamento atualizados.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
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
        flash("Anexo salvo.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index", _anchor="attachments-panel"))


@app.route("/events/<event_id>/service-order.pdf", methods=["GET"])
@require_permission("operations.view")
def download_service_order(event_id: str):
    event = next((item for item in load_events() if clean_text(item.get("event_id")) == clean_text(event_id)), None)
    if not event:
        flash("Evento não encontrado para gerar OS.", "danger")
        return redirect(url_for("index"))
    payload = build_service_order_pdf(event, load_clients(), load_vehicles_registry(), load_equipment_registry())
    record_audit("download", "events", event_id, "Ordem de serviço baixada.")
    return send_file(
        io.BytesIO(payload),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"sannygold-os-{event_id}.pdf",
    )


@app.route("/financial/receivables", methods=["POST"])
@require_permission("finance.payments")
def save_financial_receivable():
    try:
        items = load_financial_receivables()
        record = create_financial_receivable_record(request.form, items)
        before = next((item for item in items if clean_text(item.get("id")) == clean_text(record.get("id"))), None)
        save_financial_receivables(upsert_item(items, record, "id"))
        record_audit("save", "finance", record["id"], "Conta a receber salva.", before=before, after=record)
        flash("Conta a receber salva.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/financial/receivables/generate-monthly", methods=["POST"])
@require_permission("finance.payments")
def generate_monthly_receivables():
    try:
        period = clean_text(request.form.get("period")) or datetime.now().date().isoformat()[:7]
        due_day = int(clean_text(request.form.get("due_day"), "10") or 10)
        created = generate_monthly_contract_receivables(period, due_day)
        record_audit("generate", "finance", period, f"{len(created)} cobrança(s) mensal(is) gerada(s).")
        flash(f"{len(created)} cobrança(s) mensal(is) gerada(s) para {period}.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/financial/receivables/<receivable_id>/payment", methods=["POST"])
@require_permission("finance.payments")
def update_receivable_payment(receivable_id: str):
    try:
        items = load_financial_receivables()
        target = next((item for item in items if clean_text(item.get("id")) == clean_text(receivable_id)), None)
        if not target:
            raise ValueError("Conta a receber não encontrada.")
        before = dict(target)
        action = clean_text(request.form.get("action"), "paid")
        received_amount = parse_decimal(request.form.get("amount_received"), parse_decimal(target.get("amount")))
        target["amount_received"] = min(received_amount, parse_decimal(target.get("amount")))
        target["received_date"] = clean_text(request.form.get("received_date")) or datetime.now().date().isoformat()
        target["payment_method"] = clean_text(request.form.get("payment_method")) or clean_text(target.get("payment_method")) or "pix"
        if action == "partial" and target["amount_received"] < parse_decimal(target.get("amount")):
            target["status"] = "parcial"
        else:
            target["amount_received"] = parse_decimal(target.get("amount"))
            target["status"] = "pago"
        target["collection_status"] = "pagamento_registrado"
        target["updated_at"] = now_iso()
        save_financial_receivables(items)
        record_audit("payment", "finance", receivable_id, "Pagamento registrado.", before=before, after=target)
        flash("Pagamento registrado.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/financial/receivables/<receivable_id>/receipt.pdf", methods=["GET"])
@require_permission("finance.export")
def download_receivable_receipt(receivable_id: str):
    target = next((item for item in load_financial_receivables() if clean_text(item.get("id")) == clean_text(receivable_id)), None)
    if not target:
        flash("Conta a receber não encontrada.", "danger")
        return redirect(url_for("index"))
    record_audit("download", "finance", receivable_id, "Recibo financeiro baixado.")
    return send_file(
        io.BytesIO(build_receipt_pdf(target)),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"sannygold-recibo-{receivable_id}.pdf",
    )


@app.route("/financial/entries", methods=["POST"])
@require_permission("finance.edit")
def save_financial_entry():
    try:
        items = load_financial_entries()
        record = create_financial_entry_record(request.form, items)
        before = next((item for item in items if clean_text(item.get("id")) == clean_text(record.get("id"))), None)
        save_financial_entries(upsert_item(items, record, "id"))
        record_audit("save", "finance", record["id"], "Lançamento financeiro salvo.", before=before, after=record)
        flash("Lançamento financeiro salvo.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/financial/monthly-closeouts", methods=["POST"])
@require_permission("finance.close")
def save_financial_monthly_closeout():
    try:
        period = clean_text(request.form.get("period")) or datetime.now().date().isoformat()[:7]
        record = build_monthly_closeout(period, request.form.get("notes", ""))
        record_audit("close", "finance", period, f"Fechamento financeiro de {period} gerado.", after=record)
        flash(f"Fechamento financeiro de {period} gerado.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/financial/monthly-closeouts/<period>.pdf", methods=["GET"])
@require_permission("finance.export")
def download_financial_monthly_closeout_pdf(period: str):
    try:
        payload = build_monthly_closeout_pdf(period)
    except Exception as exc:  # noqa: BLE001
        return str(exc), 404
    record_audit("download", "finance", period, f"PDF do fechamento financeiro {period} baixado.")
    return send_file(
        io.BytesIO(payload),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"sannygold-fechamento-financeiro-{period}.pdf",
    )


@app.route("/events", methods=["POST"])
@require_permission("events.create")
def save_event():
    try:
        record = create_event_record(request.form)
        validate_event_links(record, clients=load_clients(), vehicles=load_vehicles_registry(), existing_events=load_events())
        before = next((item for item in load_events() if clean_text(item.get("event_id")) == clean_text(record.get("event_id"))), None)
        save_events(upsert_item(load_events(), record, "event_id"))
        record_audit("save", "events", record["event_id"], f"Evento {record['title']} salvo.", before=before, after=record)
        flash(f"Evento {record['title']} salvo com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/events/<event_id>/recurrence-status", methods=["POST"])
@require_permission("events.edit")
def update_event_recurrence_status(event_id: str):
    events = load_events()
    target = next((event for event in events if clean_text(event.get("event_id")) == event_id), None)
    if not target:
        flash(f"Evento {event_id} nao encontrado.", "danger")
        return redirect(url_for("index"))
    new_status = clean_text(request.form.get("recurrence_status"), "ativo") or "ativo"
    if new_status not in RECURRENCE_STATUS_OPTIONS:
        flash("Status de recorrência inválido.", "danger")
        return redirect(url_for("index"))
    target["recurrence_status"] = new_status
    target["next_occurrence_date"] = next_recurrence_date(target) if new_status == "ativo" else ""
    save_events(events)
    record_audit("recurrence_status", "events", event_id, f"Recorrência atualizada para {new_status}.")
    flash(f"Recorrência do evento {event_id} atualizada para {new_status}.", "success")
    return redirect(url_for("index"))


@app.route("/events/<event_id>/generate-next-recurrence", methods=["POST"])
@require_permission("events.create")
def generate_next_recurrence(event_id: str):
    events = load_events()
    source = next((event for event in events if clean_text(event.get("event_id")) == event_id), None)
    if not source:
        flash(f"Evento {event_id} nao encontrado.", "danger")
        return redirect(url_for("index"))
    if clean_text(source.get("recurrence_enabled")) != "true" or clean_text(source.get("recurrence_status"), "ativo") != "ativo":
        flash("Este evento não possui recorrência ativa.", "danger")
        return redirect(url_for("index"))
    next_date = clean_text(source.get("next_occurrence_date")) or next_recurrence_date(source)
    if not next_date:
        flash("Não foi encontrada próxima ocorrência válida para gerar.", "danger")
        return redirect(url_for("index"))
    duplicate = next(
        (
            event for event in events
            if clean_text(event.get("recurrence_parent_event_id")) == event_id and clean_text(event.get("event_date")) == next_date
        ),
        None,
    )
    if duplicate:
        flash("A próxima ocorrência já foi gerada anteriormente.", "danger")
        return redirect(url_for("index"))
    occurrence = {
        **source,
        "event_id": next_numeric_id(events, "EVT", "event_id"),
        "event_date": next_date,
        "event_end_date": parse_date(next_date).fromordinal(parse_date(next_date).toordinal() + event_duration_days(source)).isoformat(),
        "status": "planejado",
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
    events, deleted = delete_item(load_events(), "event_id", event_id)
    if deleted:
        save_events(events)
        record_audit("delete", "events", event_id, f"Evento {event_id} removido.")
        flash(f"Evento {event_id} removido com sucesso.", "success")
    else:
        flash(f"Evento {event_id} nao encontrado.", "danger")
    return redirect(url_for("index"))


@app.route("/events/<event_id>/status", methods=["POST"])
@require_permission("events.close")
def update_event_status(event_id: str):
    events = load_events()
    target = next((event for event in events if event.get("event_id") == event_id), None)
    if not target:
        flash(f"Evento {event_id} nao encontrado.", "danger")
        return redirect(url_for("index"))

    new_status = normalize_event_status(request.form.get("status"), normalize_event_status(target.get("status"), "confirmado"))
    if new_status == "finalizado":
        clients = load_clients()
        inventory = build_inventory_view(clients, load_route_data(), load_field_confirmations())
        linked_client_ids = set(target.get("client_ids") or [])
        linked_equipment = [
            item for item in inventory
            if clean_text(item.get("linked_client_id")) in linked_client_ids and item.get("status") in {"em_rota", "instalado", "retirada_pendente"}
        ]
        if linked_equipment:
            flash("Não é possível finalizar o evento enquanto houver equipamento em rota, instalado ou com retirada pendente.", "danger")
            return redirect(url_for("index"))
    target["status"] = new_status
    save_events(events)
    record_audit("status", "events", event_id, f"Status atualizado para {new_status}.")
    flash(f"Status do evento {event_id} atualizado para {target['status']}.", "success")
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
        flash("Validação operacional encontrou bloqueios. Revise o painel de elegibilidade.", "danger")
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
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/preview/<path:filename>", methods=["GET"])
@require_permission("routes.view")
def preview_file(filename: str):
    return send_from_directory(PREVIEW_DIR, filename, as_attachment=False)


@app.route("/manual/sannygold-equipe.pdf", methods=["GET"])
@require_permission("dashboard.view")
def download_user_manual():
    if not USER_MANUAL_PDF_PATH.exists():
        flash("Manual ainda não foi gerado.", "danger")
        return redirect(url_for("index"))
    return send_file(
        io.BytesIO(USER_MANUAL_PDF_PATH.read_bytes()),
        mimetype="application/pdf",
        as_attachment=False,
        download_name="sannygold-manual-rapido-equipe.pdf",
    )


@app.route("/uploads/assets/<path:filename>", methods=["GET"])
def uploaded_asset(filename: str):
    return send_from_directory(UPLOADS_DIR / "assets", filename, as_attachment=False)


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
    )
