from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.repositories.sqlite_repository import (
    FLEET_FOUNDATION_MIGRATIONS,
    connect,
    initialize_database,
    table_columns,
)
from app.services.fleet import normalize_vehicle_record
from app.services.fleet_migration import find_duplicate_vehicle_identifiers


MIGRATION_GROUP_ID = "20260620_fleet_foundation"
SNAPSHOT_FILES = ("vehicles.json", "fleet_documents.json", "sannygold.db")
REQUIRED_VEHICLE_COLUMNS = {
    "id",
    "vehicle_id",
    "plate",
    "renavam",
    "chassis",
    "brand",
    "model",
    "version",
    "manufacture_year",
    "model_year",
    "vehicle_type",
    "fuel_type",
    "current_mileage",
    "legal_owner_company",
    "operating_company",
    "cost_center",
    "acquisition_date",
    "acquisition_value",
    "usual_driver_id",
    "status",
    "tracker_installed",
    "camera_installed",
    "notes",
    "created_at",
    "updated_at",
    "deleted_at",
}
REQUIRED_DOCUMENT_COLUMNS = {
    "id",
    "document_id",
    "vehicle_id",
    "document_type",
    "document_number",
    "issue_date",
    "expiration_date",
    "file_path",
    "status",
    "responsible_user_id",
    "notes",
    "created_at",
    "updated_at",
    "deleted_at",
}


def read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def create_snapshot(data_dir: Path, backups_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot_dir = backups_dir / "migrations" / f"{MIGRATION_GROUP_ID}-{timestamp}"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    present_files = []
    for filename in SNAPSHOT_FILES:
        source = data_dir / filename
        if source.exists():
            shutil.copy2(source, snapshot_dir / filename)
            present_files.append(filename)
    write_json(
        snapshot_dir / "manifest.json",
        {
            "migration_group_id": MIGRATION_GROUP_ID,
            "migration_ids": list(FLEET_FOUNDATION_MIGRATIONS),
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "data_dir": str(data_dir),
            "present_files": present_files,
        },
    )
    return snapshot_dir


def _readonly_database_summary(db_path: Path) -> dict:
    if not db_path.exists():
        return {
            "exists": False,
            "vehicle_columns": [],
            "document_columns": [],
            "tables": [],
            "applied_migrations": [],
        }
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        tables = sorted(
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        )
        vehicle_columns = (
            sorted(str(row[1]) for row in connection.execute("PRAGMA table_info(vehicles)"))
            if "vehicles" in tables
            else []
        )
        document_columns = (
            sorted(str(row[1]) for row in connection.execute("PRAGMA table_info(fleet_documents)"))
            if "fleet_documents" in tables
            else []
        )
        applied = (
            sorted(
                str(row[0])
                for row in connection.execute(
                    "SELECT id FROM schema_migrations WHERE id IN (?, ?, ?, ?)",
                    FLEET_FOUNDATION_MIGRATIONS,
                )
            )
            if "schema_migrations" in tables
            else []
        )
    return {
        "exists": True,
        "vehicle_columns": vehicle_columns,
        "document_columns": document_columns,
        "tables": tables,
        "applied_migrations": applied,
    }


def preflight_fleet_foundation(
    *,
    data_dir: Path,
    db_path: Path,
    hq_lat: float,
    hq_lng: float,
) -> dict:
    vehicles_payload = read_json(data_dir / "vehicles.json", [])
    if not isinstance(vehicles_payload, list):
        raise ValueError("vehicles.json precisa conter uma lista.")
    normalized = [
        normalize_vehicle_record(item, hq_lat=hq_lat, hq_lng=hq_lng)
        for item in vehicles_payload
        if isinstance(item, dict)
    ]
    duplicates = find_duplicate_vehicle_identifiers(normalized)
    duplicate_count = sum(len(items) for items in duplicates.values())
    database = _readonly_database_summary(db_path)
    return {
        "migration_group_id": MIGRATION_GROUP_ID,
        "migration_ids": list(FLEET_FOUNDATION_MIGRATIONS),
        "can_apply": duplicate_count == 0,
        "vehicles_found": len(vehicles_payload),
        "vehicles_normalized": len(normalized),
        "duplicate_identifiers": duplicates,
        "database": database,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def validate_fleet_foundation(db_path: Path) -> dict:
    with connect(db_path) as connection:
        vehicle_columns = table_columns(connection, "vehicles")
        document_columns = table_columns(connection, "fleet_documents")
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        applied = {
            str(row[0])
            for row in connection.execute(
                "SELECT id FROM schema_migrations WHERE id IN (?, ?, ?, ?)",
                FLEET_FOUNDATION_MIGRATIONS,
            )
        }
        missing_vehicle_columns = sorted(REQUIRED_VEHICLE_COLUMNS - vehicle_columns)
        missing_document_columns = sorted(REQUIRED_DOCUMENT_COLUMNS - document_columns)
        missing_tables = sorted({"vehicle_mileage", "vehicle_audit_logs"} - tables)
        missing_migrations = sorted(set(FLEET_FOUNDATION_MIGRATIONS) - applied)
        indexes = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        }
        required_indexes = {
            "uq_vehicles_plate",
            "uq_vehicles_renavam",
            "uq_vehicles_chassis",
            "idx_vehicle_mileage_vehicle_date",
            "idx_vehicle_audit_vehicle_created",
        }
        missing_indexes = sorted(required_indexes - indexes)
        counts = {
            "vehicles": int(connection.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]),
            "documents": int(connection.execute("SELECT COUNT(*) FROM fleet_documents").fetchone()[0]),
            "mileage": int(connection.execute("SELECT COUNT(*) FROM vehicle_mileage").fetchone()[0]),
            "audit_logs": int(connection.execute("SELECT COUNT(*) FROM vehicle_audit_logs").fetchone()[0]),
        }
    ok = not any(
        (missing_vehicle_columns, missing_document_columns, missing_tables, missing_migrations, missing_indexes)
    )
    return {
        "ok": ok,
        "missing_vehicle_columns": missing_vehicle_columns,
        "missing_document_columns": missing_document_columns,
        "missing_tables": missing_tables,
        "missing_migrations": missing_migrations,
        "missing_indexes": missing_indexes,
        "counts": counts,
    }


def apply_fleet_foundation(
    *,
    data_dir: Path,
    db_path: Path,
    backups_dir: Path,
    hq_lat: float,
    hq_lng: float,
    dry_run: bool = False,
) -> dict:
    preflight = preflight_fleet_foundation(
        data_dir=data_dir,
        db_path=db_path,
        hq_lat=hq_lat,
        hq_lng=hq_lng,
    )
    if dry_run:
        return {**preflight, "dry_run": True, "snapshot_dir": ""}
    if not preflight["can_apply"]:
        raise ValueError(
            "A migration nao foi aplicada porque existem placas, Renavam ou chassis duplicados. "
            "Execute --dry-run e corrija os conflitos antes de continuar."
        )

    snapshot_dir = create_snapshot(data_dir, backups_dir)
    try:
        initialize_database(db_path)
        validation = validate_fleet_foundation(db_path)
        if not validation["ok"]:
            raise RuntimeError(f"Validacao incompleta da fundacao da Frota: {validation}")
        report = {
            **preflight,
            "dry_run": False,
            "snapshot_dir": str(snapshot_dir),
            "applied_at": datetime.now().isoformat(timespec="seconds"),
            "validation": validation,
        }
        write_json(snapshot_dir / "apply-report.json", report)
        return report
    except Exception as exc:
        rollback = rollback_fleet_foundation(
            data_dir=data_dir,
            backups_dir=backups_dir,
            snapshot_dir=snapshot_dir,
        )
        write_json(
            snapshot_dir / "failure-report.json",
            {
                "migration_group_id": MIGRATION_GROUP_ID,
                "failed_at": datetime.now().isoformat(timespec="seconds"),
                "error": str(exc),
                "automatic_rollback": rollback,
            },
        )
        raise RuntimeError(
            f"Falha na migration da fundacao da Frota. O snapshot {snapshot_dir.name} foi restaurado."
        ) from exc


def list_snapshots(backups_dir: Path) -> list[Path]:
    root = backups_dir / "migrations"
    if not root.exists():
        return []
    return sorted(
        (
            path
            for path in root.glob(f"{MIGRATION_GROUP_ID}-*")
            if path.is_dir() and (path / "manifest.json").exists()
        ),
        reverse=True,
    )


def rollback_fleet_foundation(
    *,
    data_dir: Path,
    backups_dir: Path,
    snapshot_dir: Path | None = None,
) -> dict:
    selected = snapshot_dir or next(iter(list_snapshots(backups_dir)), None)
    if not selected or not selected.exists():
        raise FileNotFoundError("Nenhum snapshot da fundacao da Frota foi encontrado.")
    manifest = read_json(selected / "manifest.json", {})
    if manifest.get("migration_group_id") != MIGRATION_GROUP_ID:
        raise ValueError("O snapshot selecionado nao pertence a fundacao da Frota.")
    present_files = set(manifest.get("present_files") or [])
    restored = []
    removed = []
    for filename in SNAPSHOT_FILES:
        target = data_dir / filename
        snapshot_file = selected / filename
        if filename in present_files and snapshot_file.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snapshot_file, target)
            restored.append(filename)
        elif target.exists():
            target.unlink()
            removed.append(filename)
    report = {
        "migration_group_id": MIGRATION_GROUP_ID,
        "snapshot_dir": str(selected),
        "rolled_back_at": datetime.now().isoformat(timespec="seconds"),
        "restored_files": restored,
        "removed_files": removed,
    }
    write_json(selected / "rollback-report.json", report)
    return report
