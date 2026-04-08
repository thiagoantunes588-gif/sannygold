from __future__ import annotations

import csv
import importlib.util
import io
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET

from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BASE_DIR / "scripts" / "plan_routes.py"
DEFAULT_STORAGE_ROOT = Path("/tmp/rotaflow") if os.environ.get("VERCEL") else BASE_DIR
STORAGE_ROOT = Path(os.environ.get("ROTAFLOW_STORAGE_DIR", str(DEFAULT_STORAGE_ROOT)))
DATA_DIR = STORAGE_ROOT / "data"
CLIENTS_PATH = DATA_DIR / "clients.json"
VEHICLES_PATH = DATA_DIR / "vehicles.json"
EQUIPMENT_PATH = DATA_DIR / "equipment.json"
ROUTE_HISTORY_PATH = DATA_DIR / "route_history.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
EVENTS_PATH = DATA_DIR / "events.json"
FIELD_CONFIRMATIONS_PATH = DATA_DIR / "field_confirmations.json"
OPERATION_VALIDATION_PATH = DATA_DIR / "operation_validation.json"
FORECAST_AUDIT_PATH = DATA_DIR / "forecast_audit.json"
UPLOADS_DIR = STORAGE_ROOT / "uploads"
PREVIEW_DIR = STORAGE_ROOT / "preview"
ROUTE_JSON_PATH = PREVIEW_DIR / "route-plan-mobile.json"
ROUTE_PDF_PATH = PREVIEW_DIR / "route-plan.pdf"
HQ_ADDRESS = "Estrada Bento Pestana, 932 - Baldeador, Niterói - RJ"
HQ_LAT = -22.8753396
HQ_LNG = -43.068074
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

app = Flask(__name__)
app.config["SECRET_KEY"] = "rotaflow-local-dev"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


def ensure_storage_dirs() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path in (CLIENTS_PATH, VEHICLES_PATH, EQUIPMENT_PATH, ROUTE_HISTORY_PATH, EVENTS_PATH, FIELD_CONFIRMATIONS_PATH):
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")
    if not SETTINGS_PATH.exists():
        SETTINGS_PATH.write_text(json.dumps({"cost_per_km": 0.0}, indent=2) + "\n", encoding="utf-8")
    if not OPERATION_VALIDATION_PATH.exists():
        OPERATION_VALIDATION_PATH.write_text(json.dumps({}, indent=2) + "\n", encoding="utf-8")
    if not FORECAST_AUDIT_PATH.exists():
        FORECAST_AUDIT_PATH.write_text(json.dumps({}, indent=2) + "\n", encoding="utf-8")


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


def load_settings() -> dict:
    ensure_storage_dirs()
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return {
        "cost_per_km": float(data.get("cost_per_km") or 0.0),
    }


def save_settings(settings: dict) -> None:
    ensure_storage_dirs()
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def upsert_item(items: list[dict], record: dict, key: str) -> list[dict]:
    by_key = {item[key]: item for item in items if item.get(key)}
    by_key[record[key]] = record
    return list(by_key.values())


def delete_item(items: list[dict], key: str, value: str) -> tuple[list[dict], bool]:
    filtered = [item for item in items if item.get(key) != value]
    return filtered, len(filtered) != len(items)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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


def pending_reason_label(code: str) -> str:
    return PENDING_REASON_LABELS.get(code, code.replace("_", " "))


def event_is_active(event: dict) -> bool:
    return clean_text(event.get("status")) in {"planejado", "em_execucao"}


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
            "status": clean_text(event.get("status")),
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
            "cpf_cnpj": form.get("cpf_cnpj"),
            "email": form.get("email"),
            "address": form.get("client_address"),
            "lat": form.get("client_lat"),
            "lng": form.get("client_lng"),
            "client_type": form.get("client_type"),
            "equipment_type": form.get("equipment_type"),
            "equipment_quantity": form.get("equipment_quantity"),
            "equipment_number": form.get("equipment_number"),
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
        "cpf_cnpj": clean_text(values.get("cpf_cnpj")),
        "email": clean_text(values.get("email")),
        "address": address,
        "lat": float(lat),
        "lng": float(lng),
        "client_type": clean_text(values.get("client_type"), "fixo") or "fixo",
        "equipment_type": linked_equipment.get("equipment_type") if linked_equipment else clean_text(values.get("equipment_type"), "Banheiro Luxo"),
        "equipment_quantity": quantity,
        "equipment_number": equipment_number,
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
        "checklist_motorista",
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
        "status": clean_text(form.get("status"), "planejado") or "planejado",
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
        "start_lat": float(clean_text(form.get("start_lat"), str(HQ_LAT)) or HQ_LAT),
        "start_lng": float(clean_text(form.get("start_lng"), str(HQ_LNG)) or HQ_LNG),
        "capacity": capacity,
        "max_stops": max_stops,
        "max_minutes": max_minutes,
    }


def create_equipment_record(form) -> dict:
    equipment_items = load_equipment_registry()
    equipment_id = clean_text(form.get("equipment_id")) or next_numeric_id(equipment_items, "EQ", "equipment_id")
    equipment_type = clean_text(form.get("stock_equipment_type"), "Banheiro Luxo")
    if not equipment_id or not equipment_type:
        raise ValueError("Informe o ID e o tipo do equipamento.")
    status = normalize_equipment_status(form.get("status") or form.get("condition"))
    return {
        "equipment_id": equipment_id,
        "equipment_type": equipment_type,
        "condition": status,
        "status": status,
        "notes": clean_text(form.get("notes")),
        "returned_at": clean_text(form.get("returned_at")),
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
                f"Linha {index} invalida. Use: nome | endereco | latitude | longitude | tipo | equipamento | quantidade | equipamento_id | servico | prioridade | valor_servico | custo_equipe | custo_equipamento | janela_inicio | janela_fim | veiculo_travado | contato | cpf_cnpj | email"
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
                "cpf_cnpj": parts[17] if len(parts) > 17 else "",
                "email": parts[18] if len(parts) > 18 else "",
                "address": parts[1],
                "lat": float(parts[2]),
                "lng": float(parts[3]),
                "client_type": parts[4] if len(parts) > 4 else "fixo",
                "equipment_type": parts[5] if len(parts) > 5 else "Banheiro Luxo",
                "equipment_quantity": int(parts[6] if len(parts) > 6 else "1"),
                "equipment_number": parts[7] if len(parts) > 7 else "",
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
        "cpf_cnpj": "cpf_cnpj",
        "cpfcnpj": "cpf_cnpj",
        "email": "email",
        "e_mail": "email",
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
        "servico",
        "prioridade",
        "valor_servico",
        "custo_equipe",
        "custo_equipamento",
        "janela_inicial",
        "janela_final",
        "veiculo_travado",
        "contato",
        "cpf_cnpj",
        "email",
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
        "20",
        "3",
        "1200",
        "300",
        "150",
        "08:00",
        "18:00",
        "",
        "Marcos Silva",
        "00.000.000/0001-00",
        "contato@cliente.com",
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
    return {"lat": float(top["lat"]), "lng": float(top["lon"]), "display_name": top.get("display_name") or address}


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
    event_id: str = "",
    event_title: str = "",
    event_notes: str = "",
) -> dict:
    clients_by_id = {client.get("client_id"): client for client in clients if client.get("client_id")}
    generated_at = datetime.now().isoformat(timespec="seconds")
    normalized_operation_date = operation_date or datetime.now().date().isoformat()
    normalized_event_id = clean_text(event_id)
    normalized_event_title = clean_text(event_title)
    normalized_event_notes = clean_text(event_notes)

    payload["generated_at"] = generated_at
    payload["operation_date"] = normalized_operation_date
    payload["event_id"] = normalized_event_id
    payload["event_title"] = normalized_event_title
    payload["event_notes"] = normalized_event_notes

    for route in payload.get("routes", []):
        route["operation_date"] = normalized_operation_date
        route["event_id"] = normalized_event_id
        route["event_title"] = normalized_event_title
        route["event_notes"] = normalized_event_notes
        for stop in route.get("stops", []):
            client = clients_by_id.get(stop.get("delivery_id")) or {}
            stop["operation_date"] = normalized_operation_date
            stop["event_id"] = normalized_event_id
            stop["contact_name"] = clean_text(client.get("contact_name"))
            stop["cpf_cnpj"] = clean_text(client.get("cpf_cnpj"))
            stop["email"] = clean_text(client.get("email"))
            stop["window_start"] = clean_text(client.get("window_start"), "08:00") or "08:00"
            stop["window_end"] = clean_text(client.get("window_end"), "18:00") or "18:00"
            stop["operation_notes"] = normalized_event_notes

    for item in payload.get("unassigned", []):
        client = clients_by_id.get(item.get("delivery_id")) or {}
        item["operation_date"] = normalized_operation_date
        item["event_id"] = normalized_event_id
        item["contact_name"] = clean_text(client.get("contact_name"))
        item["cpf_cnpj"] = clean_text(client.get("cpf_cnpj"))
        item["email"] = clean_text(client.get("email"))
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
            target["status"] = "em_execucao"
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
            mobile_stop["cpf_cnpj"] = full_stop.get("cpf_cnpj", "")
            mobile_stop["email"] = full_stop.get("email", "")
            mobile_stop["window_start"] = full_stop.get("window_start", "")
            mobile_stop["window_end"] = full_stop.get("window_end", "")
            mobile_stop["operation_date"] = full_stop.get("operation_date", "")
            mobile_stop["operation_notes"] = full_stop.get("operation_notes", "")
    mobile_payload["generated_at"] = payload.get("generated_at") or ""
    mobile_payload["operation_date"] = payload.get("operation_date") or ""
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
                    else "aguardando campo"
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
        return "retornado", "Retorno confirmado em campo"
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
        if clean_text(selected_event.get("status")) == "finalizado":
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
            reasons.append(build_pending_item(client, "sem_equipamento_disponivel", f"Equipamento {equipment_id} não existe no estoque."))
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
        "event_status": clean_text((selected_event or {}).get("status")) or "geral",
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
        status = clean_text(occurrence.get("status"))
        if status == "planejado":
            bucket["planned_count"] += 1
        elif status == "em_execucao":
            bucket["execution_count"] += 1
        elif status == "finalizado":
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
            findings.append({"severity": "alta", "title": "Equipamento ausente no estoque", "detail": f"{client.get('customer_name') or client.get('client_id')} aponta para {client.get('equipment_number')} sem cadastro."})
        if clean_text(client.get("locked_vehicle_id")) and client.get("locked_vehicle_id") not in vehicle_ids:
            findings.append({"severity": "media", "title": "Veículo travado inválido", "detail": f"{client.get('customer_name') or client.get('client_id')} está travado em {client.get('locked_vehicle_id')} não cadastrado."})
    for event in events:
        if not event.get("client_ids"):
            findings.append({"severity": "media", "title": "Evento sem clientes", "detail": f"{event.get('title') or event.get('event_id')} ainda não possui clientes vinculados."})
        if not event.get("vehicle_ids"):
            findings.append({"severity": "media", "title": "Evento sem veículos", "detail": f"{event.get('title') or event.get('event_id')} ainda não possui veículos vinculados."})
        if clean_text(event.get("status")) in {"em_execucao", "finalizado"} and any(not item.get("done") for item in event.get("checklist", [])):
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
        shortage_alert = "Nenhum equipamento cadastrado em estoque."

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


def build_dashboard_context() -> dict:
    selected_financial_period = clean_text(request.args.get("financial_period"), "monthly") or "monthly"
    selected_agenda_period = clean_text(request.args.get("agenda_period"), "weekly") or "weekly"
    field_confirmations = load_field_confirmations()
    route_data = attach_field_confirmations(load_route_data(), field_confirmations)
    clients = load_clients()
    vehicles = load_vehicles_registry()
    events = load_events()
    inventory = build_inventory_view(clients, route_data, field_confirmations)
    route_history = load_route_history()
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
    financial_dashboard = build_financial_dashboard(route_data, route_history, selected_financial_period)
    future_dashboard = build_future_capacity_dashboard(events, clients, vehicles, inventory, route_history, selected_agenda_period)
    settings = load_settings()
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
        enriched_events.append(
            {
                **event,
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
        "clients": clients,
        "vehicles_registry": vehicles,
        "events": enriched_events,
        "equipment_registry": inventory,
        "available_equipment": [item for item in inventory if item["status"] == "disponivel"],
        "route_history": route_history[:10],
        "operational_dashboard": operational_dashboard,
        "operational_validations": validations,
        "pending_reasons": pending_reasons,
        "operation_validation": validation_payload,
        "financial_dashboard": financial_dashboard,
        "financial_period": selected_financial_period,
        "future_dashboard": future_dashboard,
        "agenda_period": selected_agenda_period,
        "forecast_audit": load_forecast_audit(),
        "inventory_counts": {
            "total": len(inventory),
            "available": sum(1 for item in inventory if item["status"] == "disponivel"),
            "in_route": sum(1 for item in inventory if item["status"] in {"carregado", "em_rota", "instalado", "retirada_pendente"}),
            "maintenance": sum(1 for item in inventory if item["status"] in {"manutencao", "indisponivel"}),
            "reserved": sum(1 for item in inventory if item["status"] == "reservado"),
        },
        "settings": settings,
        "hq": {
            "address": HQ_ADDRESS,
            "lat": HQ_LAT,
            "lng": HQ_LNG,
        },
    }


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", **build_dashboard_context())


@app.route("/generate", methods=["POST"])
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
        flash("Rotas geradas com sucesso. JSON e PDF atualizados em preview/.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    finally:
        for temp_path in (deliveries_temp_path, vehicles_temp_path):
            if temp_path and temp_path.exists():
                temp_path.unlink(missing_ok=True)
    return redirect(url_for("index"))


@app.route("/clients", methods=["POST"])
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
        save_clients(upsert_item(load_clients(), record, "client_id"))
        flash(f"Endereco de {record['customer_name']} salvo com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/clients/bulk", methods=["POST"])
def save_clients_bulk():
    try:
        records = parse_bulk_clients(clean_text(request.form.get("bulk_clients")))
        items = load_clients()
        for record in records:
            items = upsert_item(items, record, "client_id")
        validate_client_equipment_conflicts(items)
        save_clients(items)
        flash(f"{len(records)} enderecos adicionados em lote com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/clients/import-excel", methods=["POST"])
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
        flash(f"{len(records)} clientes importados da planilha com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    finally:
        if upload_path and upload_path.exists():
            upload_path.unlink(missing_ok=True)
    return redirect(url_for("index"))


@app.route("/clients/template.xlsx", methods=["GET"])
def download_clients_template():
    return send_file(
        io.BytesIO(build_clients_template_xlsx()),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="modelo-clientes-sannygold.xlsx",
    )


@app.route("/backup/system.zip", methods=["GET"])
def download_system_backup():
    return send_file(
        io.BytesIO(build_system_backup_bytes()),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"sannygold-backup-{datetime.now().date().isoformat()}.zip",
    )


@app.route("/clients/<client_id>/delete", methods=["POST"])
def delete_client(client_id: str):
    clients, deleted = delete_item(load_clients(), "client_id", client_id)
    if deleted:
        save_clients(clients)
        flash(f"Endereco {client_id} removido com sucesso.", "success")
    else:
        flash(f"Endereco {client_id} nao encontrado.", "danger")
    return redirect(url_for("index"))


@app.route("/vehicles", methods=["POST"])
def save_vehicle():
    try:
        record = create_vehicle_record(request.form)
        save_vehicles_registry(upsert_item(load_vehicles_registry(), record, "vehicle_id"))
        flash(f"Veiculo {record['vehicle_id']} salvo com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/vehicles/<vehicle_id>/delete", methods=["POST"])
def delete_vehicle(vehicle_id: str):
    vehicles, deleted = delete_item(load_vehicles_registry(), "vehicle_id", vehicle_id)
    if deleted:
        save_vehicles_registry(vehicles)
        flash(f"Veiculo {vehicle_id} removido com sucesso.", "success")
    else:
        flash(f"Veiculo {vehicle_id} nao encontrado.", "danger")
    return redirect(url_for("index"))


@app.route("/equipment", methods=["POST"])
def save_equipment():
    try:
        record = create_equipment_record(request.form)
        if normalize_equipment_status(record.get("status")) in BLOCKED_EQUIPMENT_STATUSES and clean_text(record.get("equipment_id")):
            linked_clients = [client for client in load_clients() if clean_text(client.get("equipment_number")) == clean_text(record.get("equipment_id"))]
            if linked_clients:
                raise ValueError("Não é possível marcar um item vinculado a cliente como manutenção/indisponível sem liberar o vínculo antes.")
        save_equipment_registry(upsert_item(load_equipment_registry(), record, "equipment_id"))
        flash(f"Equipamento {record['equipment_id']} salvo com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/equipment/<equipment_id>/delete", methods=["POST"])
def delete_equipment(equipment_id: str):
    items, deleted = delete_item(load_equipment_registry(), "equipment_id", equipment_id)
    if deleted:
        save_equipment_registry(items)
        flash(f"Equipamento {equipment_id} removido com sucesso.", "success")
    else:
        flash(f"Equipamento {equipment_id} nao encontrado.", "danger")
    return redirect(url_for("index"))


@app.route("/equipment/<equipment_id>/return", methods=["POST"])
def return_equipment_to_stock(equipment_id: str):
    items = load_equipment_registry()
    target = next((item for item in items if item.get("equipment_id") == equipment_id), None)
    if not target:
        flash(f"Equipamento {equipment_id} nao encontrado.", "danger")
        return redirect(url_for("index"))

    current_status = normalize_equipment_status(target.get("status") or target.get("condition"))
    if current_status not in {"instalado", "retirada_pendente", "retornado"}:
        flash("Retorno ao estoque só pode ser confirmado após o ciclo operacional concluir instalação/retirada.", "danger")
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
    flash(f"Equipamento {equipment_id} marcado como retornado ao estoque.", "success")
    return redirect(url_for("index"))


@app.route("/equipment/<equipment_id>/release", methods=["POST"])
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
    save_equipment_registry(items)
    flash(f"Equipamento {equipment_id} liberado para disponível.", "success")
    return redirect(url_for("index"))


@app.route("/field-confirmations", methods=["POST"])
def save_field_confirmation():
    route_data = load_route_data()
    if not route_data:
        flash("Gere uma rota antes de confirmar execução em campo.", "danger")
        return redirect(url_for("index"))

    client_id = clean_text(request.form.get("client_id"))
    equipment_id = clean_text(request.form.get("equipment_id"))
    vehicle_id = clean_text(request.form.get("vehicle_id"))
    action = clean_text(request.form.get("action"))
    if action not in {"arrival", "execution", "return"}:
        flash("Ação de campo inválida.", "danger")
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
    flash("Confirmação operacional registrada com sucesso.", "success")
    return redirect(url_for("index"))


@app.route("/settings/financial", methods=["POST"])
def save_financial_settings():
    try:
        save_settings({"cost_per_km": float(clean_text(request.form.get("cost_per_km"), "0") or 0)})
        flash("Configuracao financeira atualizada com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/events", methods=["POST"])
def save_event():
    try:
        record = create_event_record(request.form)
        validate_event_links(record, clients=load_clients(), vehicles=load_vehicles_registry(), existing_events=load_events())
        save_events(upsert_item(load_events(), record, "event_id"))
        flash(f"Evento {record['title']} salvo com sucesso.", "success")
    except Exception as exc:  # noqa: BLE001
        flash(str(exc), "danger")
    return redirect(url_for("index"))


@app.route("/events/<event_id>/recurrence-status", methods=["POST"])
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
    flash(f"Recorrência do evento {event_id} atualizada para {new_status}.", "success")
    return redirect(url_for("index"))


@app.route("/events/<event_id>/generate-next-recurrence", methods=["POST"])
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
    flash(f"Próxima recorrência de {source.get('title')} gerada para {next_date}.", "success")
    return redirect(url_for("index"))


@app.route("/events/<event_id>/delete", methods=["POST"])
def delete_event(event_id: str):
    events, deleted = delete_item(load_events(), "event_id", event_id)
    if deleted:
        save_events(events)
        flash(f"Evento {event_id} removido com sucesso.", "success")
    else:
        flash(f"Evento {event_id} nao encontrado.", "danger")
    return redirect(url_for("index"))


@app.route("/events/<event_id>/status", methods=["POST"])
def update_event_status(event_id: str):
    events = load_events()
    target = next((event for event in events if event.get("event_id") == event_id), None)
    if not target:
        flash(f"Evento {event_id} nao encontrado.", "danger")
        return redirect(url_for("index"))

    new_status = clean_text(request.form.get("status"), target.get("status") or "planejado")
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
    flash(f"Status do evento {event_id} atualizado para {target['status']}.", "success")
    return redirect(url_for("index"))


@app.route("/validate-operation", methods=["POST"])
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
    if validation_payload.get("is_routable"):
        flash("Validação operacional concluída: operação apta para roteirização.", "success")
    else:
        flash("Validação operacional encontrou bloqueios. Revise o painel de elegibilidade.", "danger")
    return redirect(url_for("index"))


@app.route("/geocode", methods=["POST"])
def geocode():
    try:
        address = clean_text(request.form.get("address"))
        if not address:
            raise ValueError("Informe um endereco para buscar latitude e longitude.")
        return jsonify({"ok": True, **geocode_address(address)})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/preview/<path:filename>", methods=["GET"])
def preview_file(filename: str):
    return send_from_directory(PREVIEW_DIR, filename, as_attachment=False)


if __name__ == "__main__":
    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        host=os.environ.get("FLASK_HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
    )
