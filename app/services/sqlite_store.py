from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.repositories.sqlite_repository import SQLiteRepository, connect, initialize_database
from app.services.sqlite_migration import DOCUMENT_SOURCES, GENERIC_LIST_SOURCES, LIST_SOURCES, synthetic_id


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def decode_payload(value: str | None, fallback: Any):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _source_name(path: Path) -> str:
    return Path(path).name


def initialize_sqlite_store(db_path: Path) -> None:
    initialize_database(db_path)


def load_list_from_sqlite(db_path: Path, source_path: Path) -> list[dict] | None:
    source_name = _source_name(source_path)
    if source_name in LIST_SOURCES:
        table = LIST_SOURCES[source_name]["table"]
        sql = f"SELECT payload_json FROM {table} WHERE source_file = ? ORDER BY rowid"
        params = (source_name,)
    elif source_name in GENERIC_LIST_SOURCES:
        sql = "SELECT payload_json FROM json_records WHERE entity = ? AND source_file = ? ORDER BY rowid"
        params = (GENERIC_LIST_SOURCES[source_name], source_name)
    else:
        return None
    try:
        initialize_sqlite_store(db_path)
        with connect(db_path) as connection:
            return [
                payload
                for payload in (decode_payload(row[0], None) for row in connection.execute(sql, params))
                if isinstance(payload, dict)
            ]
    except Exception:  # noqa: BLE001
        return None


def load_dict_from_sqlite(db_path: Path, source_path: Path) -> dict | None:
    source_name = _source_name(source_path)
    entity = DOCUMENT_SOURCES.get(source_name)
    if not entity:
        return None
    try:
        initialize_sqlite_store(db_path)
        with connect(db_path) as connection:
            row = connection.execute(
                "SELECT payload_json FROM json_documents WHERE entity = ? AND source_file = ?",
                (entity, source_name),
            ).fetchone()
        payload = decode_payload(row[0], {}) if row else {}
        return payload if isinstance(payload, dict) else {}
    except Exception:  # noqa: BLE001
        return None


def save_list_to_sqlite(db_path: Path, source_path: Path, items: list[dict]) -> bool | None:
    source_name = _source_name(source_path)
    migrated_at = now_iso()
    repository = SQLiteRepository(db_path)
    try:
        initialize_sqlite_store(db_path)
        with connect(db_path) as connection:
            if source_name in LIST_SOURCES:
                table = LIST_SOURCES[source_name]["table"]
                connection.execute(f"DELETE FROM {table} WHERE source_file = ?", (source_name,))
            elif source_name in GENERIC_LIST_SOURCES:
                connection.execute(
                    "DELETE FROM json_records WHERE entity = ? AND source_file = ?",
                    (GENERIC_LIST_SOURCES[source_name], source_name),
                )
            else:
                return None
            if source_name in LIST_SOURCES:
                config = LIST_SOURCES[source_name]
                for index, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    record_id = _first_value(item, config["id_fields"]) or synthetic_id(source_name, index)
                    repository.upsert_core_record(
                        config["table"],
                        record_id,
                        _indexed_values(item, config["indexed"]),
                        item,
                        source_file=source_name,
                        migrated_at=migrated_at,
                        connection=connection,
                    )
            else:
                entity = GENERIC_LIST_SOURCES[source_name]
                for index, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    record_id = _first_value(item, ("id", "client_id", "event_id", "equipment_id", "vehicle_id", "created_at")) or synthetic_id(source_name, index)
                    repository.upsert_json_record(
                        entity=entity,
                        record_id=record_id,
                        record_label=_record_label(item),
                        source_file=source_name,
                        payload=item,
                        migrated_at=migrated_at,
                        connection=connection,
                    )
        return True
    except Exception:  # noqa: BLE001
        return False


def save_dict_to_sqlite(db_path: Path, source_path: Path, payload: dict) -> bool | None:
    source_name = _source_name(source_path)
    entity = DOCUMENT_SOURCES.get(source_name)
    if not entity:
        return None
    try:
        initialize_sqlite_store(db_path)
        SQLiteRepository(db_path).upsert_json_document(
            entity=entity,
            source_file=source_name,
            payload=payload if isinstance(payload, dict) else {},
            migrated_at=now_iso(),
        )
        return True
    except Exception:  # noqa: BLE001
        return False


def _clean_text(value) -> str:
    return str(value or "").strip()


def _first_value(record: dict, fields: tuple[str, ...]) -> str:
    for field in fields:
        text = _clean_text(record.get(field))
        if text:
            return text
    return ""


def _numeric_value(value) -> float | None:
    if value in ("", None):
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _indexed_values(record: dict, mapping: dict[str, str]) -> dict:
    values = {}
    for source_field, target_column in mapping.items():
        value = record.get(source_field)
        if target_column in {
            "amount",
            "amount_received",
            "revenue_total",
            "expense_total",
            "profit_total",
            "labor_cost",
            "parts_cost",
            "additional_cost",
            "discount",
            "total_cost",
            "downtime_hours",
            "paid_amount",
            "quantity",
            "unit_cost",
            "latitude",
            "longitude",
        }:
            value = _numeric_value(value)
        elif target_column == "acquisition_value":
            value = _numeric_value(value) or 0.0
        elif target_column in {
            "manufacture_year",
            "model_year",
            "current_mileage",
            "entry_mileage",
            "exit_mileage",
            "next_service_mileage",
            "interval_mileage",
            "interval_days",
            "warning_mileage",
            "warning_days",
            "last_service_mileage",
            "warranty_days",
            "size_bytes",
            "version",
            "display_order",
            "template_version",
            "start_mileage",
            "end_mileage",
            "distance_travelled",
        }:
            numeric = _numeric_value(value)
            value = int(numeric) if numeric is not None else (0 if target_column in {"current_mileage", "warranty_days", "size_bytes"} else None)
        elif target_column in {
            "tracker_installed", "camera_installed", "is_active", "is_required", "is_critical",
            "requires_photo", "requires_note_on_failure", "creates_occurrence_on_failure",
            "blocks_vehicle_on_failure", "is_critical_snapshot", "resolution_confirmed", "is_usual_driver",
            "is_sensitive",
        }:
            value = int(str(value or "").strip().lower() in {"1", "true", "yes", "sim", "on"})
        else:
            value = _clean_text(value)
        values[target_column] = value
    return values


def _record_label(record: dict) -> str:
    return _first_value(record, ("title", "name", "customer_name", "client_name", "description", "id", "created_at"))
