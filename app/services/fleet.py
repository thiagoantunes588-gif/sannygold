from __future__ import annotations

import re
from datetime import date, datetime
from typing import Mapping, Sequence


VEHICLE_STATUSES = {
    "disponivel": "Disponível",
    "em_operacao": "Em operação",
    "em_manutencao": "Em manutenção",
    "bloqueado": "Bloqueado",
    "parado": "Parado",
    "vendido": "Vendido",
    "baixado": "Baixado",
}

VEHICLE_STATUS_ALIASES = {
    "": "disponivel",
    "disponivel": "disponivel",
    "disponível": "disponivel",
    "em operação": "em_operacao",
    "em_operacao": "em_operacao",
    "em rota": "em_operacao",
    "em_rota": "em_operacao",
    "manutencao": "em_manutencao",
    "manutenção": "em_manutencao",
    "em manutenção": "em_manutencao",
    "em_manutencao": "em_manutencao",
    "indisponivel": "bloqueado",
    "indisponível": "bloqueado",
    "bloqueado": "bloqueado",
    "parado": "parado",
    "vendido": "vendido",
    "baixado": "baixado",
}

DOCUMENT_TYPES = {
    "crlv_e": "CRLV-e",
    "licenciamento": "Licenciamento",
    "seguro": "Seguro",
    "apolice": "Apólice",
    "vistoria": "Vistoria",
    "tacografo": "Tacógrafo",
    "rastreamento": "Contrato de rastreamento",
    "nota_fiscal_aquisicao": "Nota fiscal de aquisição",
    "procuracao": "Procuração",
    "recall": "Recall",
    "restricao": "Restrição",
    "outro": "Outro",
}

DOCUMENT_STATUSES = {
    "ativo": "Ativo",
    "pendente": "Pendente",
    "substituido": "Substituído",
    "cancelado": "Cancelado",
}

DEFAULT_DOCUMENT_ALERT_DAYS = [90, 60, 30, 15, 7]
IDENTIFIER_RE = re.compile(r"[^A-Z0-9]")
BLOCKED_VEHICLE_STATUSES = {"bloqueado", "em_manutencao", "parado"}
SENSITIVE_VEHICLE_DOCUMENT_FIELDS = {
    "renavam",
    "chassis",
    "insurer",
    "insurance_policy_number",
    "insurance_expiry",
}


def clean_text(value, fallback: str = "") -> str:
    text = str(value if value is not None else "").strip()
    return text or fallback


def normalize_identifier(value) -> str:
    return IDENTIFIER_RE.sub("", clean_text(value).upper())


def normalize_vehicle_status(value, fallback: str = "disponivel") -> str:
    normalized = VEHICLE_STATUS_ALIASES.get(clean_text(value).lower(), "")
    if normalized in VEHICLE_STATUSES:
        return normalized
    fallback_status = VEHICLE_STATUS_ALIASES.get(clean_text(fallback).lower(), "disponivel")
    return fallback_status if fallback_status in VEHICLE_STATUSES else "disponivel"


def required_vehicle_change_permissions(before: Mapping | None, after: Mapping) -> set[str]:
    current = dict(before or {})
    updated = dict(after)
    required: set[str] = set()

    if current and as_int(current.get("current_mileage"), 0) != as_int(updated.get("current_mileage"), 0):
        required.add("fleet.mileage.edit")

    previous_status = normalize_vehicle_status(current.get("status")) if current else ""
    next_status = normalize_vehicle_status(updated.get("status"))
    if previous_status != next_status:
        if previous_status in {"vendido", "baixado"} or next_status in {"vendido", "baixado"}:
            required.add("fleet.admin")
        elif next_status in BLOCKED_VEHICLE_STATUSES:
            required.add("fleet.vehicle.block")
        elif previous_status in BLOCKED_VEHICLE_STATUSES and next_status in {"disponivel", "em_operacao"}:
            required.add("fleet.vehicle.release")

    if clean_text(current.get("deleted_at")) != clean_text(updated.get("deleted_at")):
        required.add("fleet.admin")

    for field in SENSITIVE_VEHICLE_DOCUMENT_FIELDS:
        previous = clean_text(current.get(field))
        next_value = clean_text(updated.get(field))
        if previous != next_value:
            required.add("fleet.documents.view")

    previous_value = as_float(current.get("acquisition_value"), 0.0)
    next_value = as_float(updated.get("acquisition_value"), 0.0)
    if previous_value != next_value:
        required.add("fleet.values.view")

    return required


def vehicle_status_label(value) -> str:
    status = normalize_vehicle_status(value)
    return VEHICLE_STATUSES.get(status, status.replace("_", " ").title())


def as_bool(value) -> bool:
    return clean_text(value).lower() in {"1", "true", "yes", "sim", "on"}


def as_int(value, fallback: int = 0, *, minimum: int | None = None) -> int:
    try:
        parsed = int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        parsed = fallback
    if minimum is not None:
        parsed = max(parsed, minimum)
    return parsed


def as_float(value, fallback: float = 0.0, *, minimum: float | None = None) -> float:
    try:
        parsed = round(float(str(value).replace(",", ".")), 2)
    except (TypeError, ValueError):
        parsed = fallback
    if minimum is not None:
        parsed = max(parsed, minimum)
    return parsed


def normalize_alert_days(value) -> list[int]:
    if isinstance(value, str):
        candidates = re.split(r"[,;\s]+", value)
    elif isinstance(value, Sequence):
        candidates = value
    else:
        candidates = DEFAULT_DOCUMENT_ALERT_DAYS
    days = sorted(
        {
            as_int(item)
            for item in candidates
            if clean_text(item) and 1 <= as_int(item) <= 365
        },
        reverse=True,
    )
    return days or list(DEFAULT_DOCUMENT_ALERT_DAYS)


def _pick(form: Mapping, current: Mapping, key: str, fallback=""):
    if key in form:
        if hasattr(form, "getlist"):
            values = form.getlist(key)
            if values:
                return values[-1]
        return form.get(key)
    return current.get(key, fallback)


def _validate_date(value, label: str) -> str:
    text = clean_text(value)
    if not text:
        return ""
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label} inválida. Use uma data válida.") from exc
    return text


def _validate_year(value, label: str) -> int | str:
    text = clean_text(value)
    if not text:
        return ""
    year = as_int(text)
    if year < 1900 or year > date.today().year + 1:
        raise ValueError(f"{label} inválido. Informe um ano entre 1900 e {date.today().year + 1}.")
    return year


def normalize_vehicle_record(record: Mapping, *, hq_lat: float, hq_lng: float) -> dict:
    status = normalize_vehicle_status(record.get("status"))
    plate = normalize_identifier(record.get("plate"))
    renavam = normalize_identifier(record.get("renavam"))
    chassis = normalize_identifier(record.get("chassis") or record.get("chassi"))
    photos = record.get("photos") if isinstance(record.get("photos"), list) else []
    photo_url = clean_text(record.get("photo_url"))
    if photo_url and photo_url not in photos:
        photos = [photo_url, *photos]
    driver = clean_text(record.get("habitual_driver") or record.get("driver"))
    vehicle_id = clean_text(record.get("id") or record.get("vehicle_id"))
    legal_owner = clean_text(record.get("legal_owner_company") or record.get("legal_owner"))
    return {
        **dict(record),
        "id": vehicle_id,
        "vehicle_id": vehicle_id,
        "plate": plate,
        "plate_normalized": plate,
        "renavam": renavam,
        "renavam_normalized": renavam,
        "chassis": chassis,
        "chassi": chassis,
        "chassis_normalized": chassis,
        "vehicle_type": clean_text(record.get("vehicle_type"), "Van"),
        "brand": clean_text(record.get("brand")),
        "model": clean_text(record.get("model")),
        "version": clean_text(record.get("version")),
        "manufacture_year": record.get("manufacture_year", ""),
        "model_year": record.get("model_year", ""),
        "fuel_type": clean_text(record.get("fuel_type")),
        "current_mileage": as_int(record.get("current_mileage"), 0, minimum=0),
        "legal_owner": legal_owner,
        "legal_owner_company": legal_owner,
        "operating_company": clean_text(record.get("operating_company")),
        "operating_unit": clean_text(record.get("operating_unit")),
        "cost_center": clean_text(record.get("cost_center")),
        "acquisition_date": clean_text(record.get("acquisition_date")),
        "acquisition_value": as_float(record.get("acquisition_value"), 0.0, minimum=0.0),
        "habitual_driver": driver,
        "driver": driver,
        "usual_driver_id": clean_text(record.get("usual_driver_id")),
        "tracker_installed": as_bool(record.get("tracker_installed")),
        "camera_installed": as_bool(record.get("camera_installed")),
        "insurer": clean_text(record.get("insurer")),
        "insurance_policy_number": clean_text(record.get("insurance_policy_number")),
        "insurance_expiry": clean_text(record.get("insurance_expiry")),
        "status": status,
        "status_label": vehicle_status_label(status),
        "photo_url": photo_url or (photos[0] if photos else ""),
        "photos": list(dict.fromkeys(clean_text(item) for item in photos if clean_text(item))),
        "notes": clean_text(record.get("notes")),
        "start_lat": as_float(record.get("start_lat"), hq_lat),
        "start_lng": as_float(record.get("start_lng"), hq_lng),
        "capacity": as_int(record.get("capacity"), 1, minimum=1),
        "max_stops": as_int(record.get("max_stops"), 999, minimum=1),
        "max_minutes": as_int(record.get("max_minutes"), 600, minimum=1),
        "created_at": clean_text(record.get("created_at")),
        "updated_at": clean_text(record.get("updated_at")),
        "deleted_at": clean_text(record.get("deleted_at")),
        "deleted_by": clean_text(record.get("deleted_by")),
    }


def build_vehicle_record(
    form: Mapping,
    *,
    existing_vehicles: list[dict],
    now: str,
    hq_lat: float,
    hq_lng: float,
    generated_id: str,
    uploaded_photos: list[str] | None = None,
) -> dict:
    vehicle_id = clean_text(form.get("vehicle_id")) or generated_id
    current = next(
        (item for item in existing_vehicles if clean_text(item.get("vehicle_id")) == vehicle_id),
        {},
    )
    if not vehicle_id:
        raise ValueError("Informe o ID do veículo.")

    plate = normalize_identifier(_pick(form, current, "plate"))
    if not plate:
        raise ValueError("Informe a placa do veículo.")
    renavam = normalize_identifier(_pick(form, current, "renavam"))
    chassis = normalize_identifier(_pick(form, current, "chassis", current.get("chassi", "")))

    duplicate_fields = (
        ("plate", plate, "placa"),
        ("renavam", renavam, "Renavam"),
        ("chassis", chassis, "chassi"),
    )
    for field, normalized_value, label in duplicate_fields:
        if not normalized_value:
            continue
        normalized_key = f"{field}_normalized"
        for vehicle in existing_vehicles:
            if clean_text(vehicle.get("vehicle_id")) == vehicle_id:
                continue
            other_value = normalize_identifier(vehicle.get(normalized_key) or vehicle.get(field) or vehicle.get("chassi"))
            if other_value == normalized_value:
                raise ValueError(f"Já existe outro veículo com {label} {normalized_value}.")

    capacity = as_int(_pick(form, current, "capacity", 1), minimum=1)
    max_stops = as_int(_pick(form, current, "max_stops", 999), minimum=1)
    max_minutes = as_int(_pick(form, current, "max_minutes", 600), minimum=1)
    current_mileage = as_int(_pick(form, current, "current_mileage", 0), minimum=0)
    acquisition_value = as_float(_pick(form, current, "acquisition_value", 0), minimum=0)
    photos = current.get("photos") if isinstance(current.get("photos"), list) else []
    photos = [*photos, *(uploaded_photos or [])]
    external_photo = clean_text(_pick(form, current, "photo_url"))
    if external_photo:
        photos.append(external_photo)
    photos = list(dict.fromkeys(clean_text(item) for item in photos if clean_text(item)))
    status = normalize_vehicle_status(_pick(form, current, "status", "disponivel"))
    habitual_driver = clean_text(_pick(form, current, "habitual_driver", current.get("driver", "")))

    return normalize_vehicle_record(
        {
            **current,
            "vehicle_id": vehicle_id,
            "plate": plate,
            "renavam": renavam,
            "chassis": chassis,
            "brand": clean_text(_pick(form, current, "brand")),
            "model": clean_text(_pick(form, current, "model")),
            "version": clean_text(_pick(form, current, "version")),
            "manufacture_year": _validate_year(_pick(form, current, "manufacture_year"), "Ano de fabricação"),
            "model_year": _validate_year(_pick(form, current, "model_year"), "Ano do modelo"),
            "vehicle_type": clean_text(_pick(form, current, "vehicle_type", "Van"), "Van"),
            "fuel_type": clean_text(_pick(form, current, "fuel_type")),
            "current_mileage": current_mileage,
            "legal_owner": clean_text(_pick(form, current, "legal_owner")),
            "legal_owner_company": clean_text(
                _pick(form, current, "legal_owner_company", _pick(form, current, "legal_owner"))
            ),
            "operating_company": clean_text(_pick(form, current, "operating_company")),
            "operating_unit": clean_text(_pick(form, current, "operating_unit")),
            "cost_center": clean_text(_pick(form, current, "cost_center")),
            "acquisition_date": _validate_date(_pick(form, current, "acquisition_date"), "Data de aquisição"),
            "acquisition_value": acquisition_value,
            "habitual_driver": habitual_driver,
            "driver": habitual_driver,
            "usual_driver_id": clean_text(_pick(form, current, "usual_driver_id")),
            "tracker_installed": as_bool(_pick(form, current, "tracker_installed")),
            "camera_installed": as_bool(_pick(form, current, "camera_installed")),
            "insurer": clean_text(_pick(form, current, "insurer")),
            "insurance_policy_number": clean_text(_pick(form, current, "insurance_policy_number")),
            "insurance_expiry": _validate_date(_pick(form, current, "insurance_expiry"), "Vencimento do seguro"),
            "status": status,
            "photo_url": photos[0] if photos else "",
            "photos": photos,
            "notes": clean_text(_pick(form, current, "notes")),
            "start_lat": as_float(_pick(form, current, "start_lat", hq_lat), hq_lat),
            "start_lng": as_float(_pick(form, current, "start_lng", hq_lng), hq_lng),
            "capacity": capacity,
            "max_stops": max_stops,
            "max_minutes": max_minutes,
            "created_at": clean_text(current.get("created_at")) or now,
            "updated_at": now,
            "deleted_at": "",
            "deleted_by": "",
        },
        hq_lat=hq_lat,
        hq_lng=hq_lng,
    )


def normalize_document_record(record: Mapping) -> dict:
    document_id = clean_text(record.get("id") or record.get("document_id"))
    issue_date = clean_text(record.get("issue_date") or record.get("issued_at"))
    expiration_date = clean_text(record.get("expiration_date") or record.get("expires_at"))
    file_path = clean_text(record.get("file_path") or record.get("file_url"))
    document_number = clean_text(record.get("document_number") or record.get("number"))
    return {
        **dict(record),
        "id": document_id,
        "document_id": document_id,
        "number": document_number,
        "document_number": document_number,
        "issued_at": issue_date,
        "issue_date": issue_date,
        "expires_at": expiration_date,
        "expiration_date": expiration_date,
        "file_url": file_path,
        "file_path": file_path,
        "responsible_user_id": clean_text(record.get("responsible_user_id")),
        "notes": clean_text(record.get("notes")),
        "created_at": clean_text(record.get("created_at")),
        "updated_at": clean_text(record.get("updated_at")),
        "deleted_at": clean_text(record.get("deleted_at")),
    }


def build_document_record(
    form: Mapping,
    *,
    existing_documents: list[dict],
    vehicles: list[dict],
    now: str,
    generated_id: str,
    uploaded_file_url: str = "",
) -> dict:
    document_id = clean_text(form.get("document_id")) or generated_id
    current = next(
        (item for item in existing_documents if clean_text(item.get("id")) == document_id),
        {},
    )
    vehicle_id = clean_text(_pick(form, current, "vehicle_id"))
    vehicle = next(
        (item for item in vehicles if clean_text(item.get("vehicle_id")) == vehicle_id and not clean_text(item.get("deleted_at"))),
        None,
    )
    if not vehicle:
        raise ValueError("Selecione um veículo ativo para o documento.")

    document_type = clean_text(_pick(form, current, "document_type"))
    if document_type not in DOCUMENT_TYPES:
        raise ValueError("Selecione um tipo de documento válido.")
    custom_type = clean_text(_pick(form, current, "custom_type"))
    if document_type == "outro" and not custom_type:
        raise ValueError("Informe o nome do documento configurável.")
    status = clean_text(_pick(form, current, "status", "ativo")).lower()
    if status not in DOCUMENT_STATUSES:
        raise ValueError("Selecione um status de documento válido.")
    file_url = uploaded_file_url or clean_text(_pick(form, current, "file_url"))
    if not file_url:
        raise ValueError("Anexe um arquivo ao documento.")
    issued_at = _validate_date(_pick(form, current, "issued_at"), "Data de emissão")
    expires_at = _validate_date(_pick(form, current, "expires_at"), "Data de vencimento")
    if issued_at and expires_at and expires_at < issued_at:
        raise ValueError("O vencimento do documento não pode ser anterior à emissão.")

    return normalize_document_record({
        **current,
        "id": document_id,
        "document_id": document_id,
        "vehicle_id": vehicle_id,
        "vehicle_plate": clean_text(vehicle.get("plate")),
        "document_type": document_type,
        "document_type_label": custom_type or DOCUMENT_TYPES[document_type],
        "custom_type": custom_type,
        "number": clean_text(_pick(form, current, "number")),
        "document_number": clean_text(_pick(form, current, "document_number", _pick(form, current, "number"))),
        "issued_at": issued_at,
        "issue_date": issued_at,
        "expires_at": expires_at,
        "expiration_date": expires_at,
        "file_url": file_url,
        "file_path": file_url,
        "responsible": clean_text(_pick(form, current, "responsible")),
        "responsible_user_id": clean_text(_pick(form, current, "responsible_user_id")),
        "status": status,
        "notes": clean_text(_pick(form, current, "notes")),
        "created_at": clean_text(current.get("created_at")) or now,
        "updated_at": now,
        "deleted_at": "",
        "deleted_by": "",
    })


def document_status_view(document: Mapping, alert_days: list[int], *, today: date | None = None) -> dict:
    reference = today or date.today()
    deleted = bool(clean_text(document.get("deleted_at")))
    expires_at = clean_text(document.get("expires_at"))
    days_until_expiry = None
    if expires_at:
        try:
            days_until_expiry = (date.fromisoformat(expires_at) - reference).days
        except ValueError:
            days_until_expiry = None
    base_status = clean_text(document.get("status"), "ativo")
    if deleted:
        effective_status = "arquivado"
        effective_label = "Arquivado"
    elif base_status in {"cancelado", "substituido"}:
        effective_status = base_status
        effective_label = DOCUMENT_STATUSES[base_status]
    elif days_until_expiry is not None and days_until_expiry < 0:
        effective_status = "vencido"
        effective_label = "Vencido"
    elif days_until_expiry is not None and days_until_expiry <= max(alert_days):
        effective_status = "proximo_vencimento"
        effective_label = "Próximo do vencimento"
    else:
        effective_status = base_status
        effective_label = DOCUMENT_STATUSES.get(base_status, base_status.title())
    alert_level = next((days for days in sorted(alert_days) if days_until_expiry is not None and days_until_expiry <= days), None)
    return {
        **dict(document),
        "effective_status": effective_status,
        "effective_status_label": effective_label,
        "days_until_expiry": days_until_expiry,
        "alert_level": alert_level,
    }


def vehicle_view(vehicle: Mapping, *, can_view_documents: bool, can_view_values: bool) -> dict:
    item = dict(vehicle)
    if not can_view_documents:
        for key in (
            "renavam",
            "renavam_normalized",
            "chassis",
            "chassi",
            "chassis_normalized",
            "insurer",
            "insurance_policy_number",
            "insurance_expiry",
        ):
            item[key] = ""
        item["sensitive_data_restricted"] = True
    if not can_view_values:
        item["acquisition_value"] = None
        item["values_restricted"] = True
    return item


def build_fleet_phase1_view(
    *,
    vehicles: list[dict],
    documents: list[dict],
    alert_days: list[int],
    can_view_documents: bool,
    can_view_values: bool,
) -> dict:
    normalized_alerts = normalize_alert_days(alert_days)
    active_vehicles = [item for item in vehicles if not clean_text(item.get("deleted_at"))]
    archived_vehicles = [item for item in vehicles if clean_text(item.get("deleted_at"))]
    document_views = [
        document_status_view(item, normalized_alerts)
        for item in documents
        if not clean_text(item.get("deleted_at"))
    ] if can_view_documents else []
    return {
        "vehicles": [
            vehicle_view(item, can_view_documents=can_view_documents, can_view_values=can_view_values)
            for item in active_vehicles
        ],
        "archived_vehicles": [
            vehicle_view(item, can_view_documents=can_view_documents, can_view_values=can_view_values)
            for item in archived_vehicles
        ],
        "documents": sorted(
            document_views,
            key=lambda item: (clean_text(item.get("expires_at")) or "9999-12-31", clean_text(item.get("vehicle_plate"))),
        ),
        "alert_days": normalized_alerts,
        "counts": {
            "total": len(active_vehicles),
            "available": sum(1 for item in active_vehicles if normalize_vehicle_status(item.get("status")) == "disponivel"),
            "operation": sum(1 for item in active_vehicles if normalize_vehicle_status(item.get("status")) == "em_operacao"),
            "blocked": sum(1 for item in active_vehicles if normalize_vehicle_status(item.get("status")) in {"bloqueado", "em_manutencao"}),
            "archived": len(archived_vehicles),
            "documents": len(document_views),
            "expired_documents": sum(1 for item in document_views if item["effective_status"] == "vencido"),
            "expiring_documents": sum(1 for item in document_views if item["effective_status"] == "proximo_vencimento"),
        },
        "vehicle_statuses": VEHICLE_STATUSES,
        "document_types": DOCUMENT_TYPES,
        "document_statuses": DOCUMENT_STATUSES,
    }
