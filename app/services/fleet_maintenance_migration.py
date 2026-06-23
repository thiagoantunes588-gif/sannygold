from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.repositories.sqlite_repository import (
    FLEET_MAINTENANCE_MIGRATIONS,
    connect,
    initialize_database,
    table_columns,
)


MIGRATION_GROUP_ID = "20260621_fleet_maintenance"
JSON_FILES = (
    "fleet_service_orders.json",
    "fleet_service_order_items.json",
    "vehicle_maintenance_plans.json",
    "fleet_maintenance_attachments.json",
    "fleet_inventory_reservations.json",
)
SNAPSHOT_FILES = (*JSON_FILES, "vehicles.json", "warehouse_items.json", "warehouse_movements.json", "sannygold.db")
REQUIRED_TABLES = {
    "fleet_service_orders",
    "fleet_service_order_items",
    "vehicle_maintenance_plans",
    "fleet_maintenance_attachments",
    "fleet_inventory_reservations",
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


def preflight_fleet_maintenance(*, data_dir: Path, db_path: Path) -> dict:
    invalid_files = []
    counts = {}
    for filename in JSON_FILES:
        path = data_dir / filename
        payload = read_json(path, [])
        if path.exists() and not isinstance(payload, list):
            invalid_files.append(filename)
        counts[filename] = len(payload) if isinstance(payload, list) else 0
    duplicate_numbers = []
    orders = read_json(data_dir / "fleet_service_orders.json", [])
    if isinstance(orders, list):
        seen = set()
        for order in orders:
            number = str((order or {}).get("order_number") or "").strip()
            if number and number in seen:
                duplicate_numbers.append(number)
            seen.add(number)
    tables = []
    migrations = []
    if db_path.exists():
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            tables = sorted(str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'"))
            if "schema_migrations" in tables:
                placeholders = ",".join("?" for _ in FLEET_MAINTENANCE_MIGRATIONS)
                migrations = sorted(str(row[0]) for row in connection.execute(f"SELECT id FROM schema_migrations WHERE id IN ({placeholders})", FLEET_MAINTENANCE_MIGRATIONS))
    return {
        "migration_group_id": MIGRATION_GROUP_ID,
        "migration_ids": list(FLEET_MAINTENANCE_MIGRATIONS),
        "can_apply": not invalid_files and not duplicate_numbers,
        "invalid_files": invalid_files,
        "duplicate_order_numbers": sorted(set(duplicate_numbers)),
        "record_counts": counts,
        "database": {"exists": db_path.exists(), "tables": tables, "applied_migrations": migrations},
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


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
    write_json(snapshot_dir / "manifest.json", {
        "migration_group_id": MIGRATION_GROUP_ID,
        "migration_ids": list(FLEET_MAINTENANCE_MIGRATIONS),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "data_dir": str(data_dir),
        "present_files": present_files,
    })
    return snapshot_dir


def validate_fleet_maintenance(db_path: Path) -> dict:
    with connect(db_path) as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        placeholders = ",".join("?" for _ in FLEET_MAINTENANCE_MIGRATIONS)
        applied = {str(row[0]) for row in connection.execute(f"SELECT id FROM schema_migrations WHERE id IN ({placeholders})", FLEET_MAINTENANCE_MIGRATIONS)}
        indexes = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        required_indexes = {
            "uq_fleet_service_orders_number",
            "idx_fleet_service_orders_vehicle_status",
            "idx_fleet_service_order_items_order",
            "idx_vehicle_maintenance_plans_due",
            "idx_fleet_maintenance_attachments_order",
            "idx_fleet_inventory_reservations_item_status",
            "uq_fleet_inventory_reservation_active",
        }
        columns = {table: sorted(table_columns(connection, table)) for table in REQUIRED_TABLES if table in tables}
    missing_tables = sorted(REQUIRED_TABLES - tables)
    missing_migrations = sorted(set(FLEET_MAINTENANCE_MIGRATIONS) - applied)
    missing_indexes = sorted(required_indexes - indexes)
    return {
        "ok": not missing_tables and not missing_migrations and not missing_indexes,
        "missing_tables": missing_tables,
        "missing_migrations": missing_migrations,
        "missing_indexes": missing_indexes,
        "columns": columns,
    }


def apply_fleet_maintenance(*, data_dir: Path, db_path: Path, backups_dir: Path, dry_run: bool = False) -> dict:
    preflight = preflight_fleet_maintenance(data_dir=data_dir, db_path=db_path)
    if dry_run:
        return {**preflight, "dry_run": True, "snapshot_dir": ""}
    if not preflight["can_apply"]:
        raise ValueError("A migration não foi aplicada. Corrija arquivos inválidos ou números de ordem duplicados.")
    snapshot_dir = create_snapshot(data_dir, backups_dir)
    try:
        for filename in JSON_FILES:
            path = data_dir / filename
            if not path.exists():
                write_json(path, [])
        initialize_database(db_path)
        validation = validate_fleet_maintenance(db_path)
        if not validation["ok"]:
            raise RuntimeError(f"Validação incompleta da Fase 2 da Frota: {validation}")
        report = {**preflight, "dry_run": False, "snapshot_dir": str(snapshot_dir), "applied_at": datetime.now().isoformat(timespec="seconds"), "validation": validation}
        write_json(snapshot_dir / "apply-report.json", report)
        return report
    except Exception as exc:
        rollback = rollback_fleet_maintenance(data_dir=data_dir, backups_dir=backups_dir, snapshot_dir=snapshot_dir)
        write_json(snapshot_dir / "failure-report.json", {"migration_group_id": MIGRATION_GROUP_ID, "failed_at": datetime.now().isoformat(timespec="seconds"), "error": str(exc), "automatic_rollback": rollback})
        raise RuntimeError(f"Falha na migration da Fase 2. O snapshot {snapshot_dir.name} foi restaurado.") from exc


def list_snapshots(backups_dir: Path) -> list[Path]:
    root = backups_dir / "migrations"
    if not root.exists():
        return []
    return sorted((path for path in root.glob(f"{MIGRATION_GROUP_ID}-*") if path.is_dir() and (path / "manifest.json").exists()), reverse=True)


def rollback_fleet_maintenance(*, data_dir: Path, backups_dir: Path, snapshot_dir: Path | None = None) -> dict:
    selected = snapshot_dir or next(iter(list_snapshots(backups_dir)), None)
    if not selected or not selected.exists():
        raise FileNotFoundError("Nenhum snapshot da Fase 2 da Frota foi encontrado.")
    manifest = read_json(selected / "manifest.json", {})
    if manifest.get("migration_group_id") != MIGRATION_GROUP_ID:
        raise ValueError("O snapshot selecionado não pertence à Fase 2 da Frota.")
    present = set(manifest.get("present_files") or [])
    restored, removed = [], []
    for filename in SNAPSHOT_FILES:
        target = data_dir / filename
        source = selected / filename
        if filename in present and source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            restored.append(filename)
        elif target.exists():
            target.unlink()
            removed.append(filename)
    report = {"migration_group_id": MIGRATION_GROUP_ID, "snapshot_dir": str(selected), "rolled_back_at": datetime.now().isoformat(timespec="seconds"), "restored_files": restored, "removed_files": removed}
    write_json(selected / "rollback-report.json", report)
    return report
