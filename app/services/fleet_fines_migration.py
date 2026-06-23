from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.repositories.sqlite_repository import FLEET_FINES_MIGRATIONS, connect, initialize_database
from app.services.fleet_fines import DEFAULT_ALERT_DAYS
from app.services.sqlite_store import save_dict_to_sqlite


MIGRATION_GROUP_ID = "20260621_fleet_fines"
JSON_FILES = (
    "fleet_traffic_infractions.json", "fleet_infraction_deadlines.json", "fleet_infraction_driver_identifications.json",
    "fleet_infraction_document_templates.json", "fleet_infraction_document_template_items.json", "fleet_infraction_documents.json",
    "fleet_infraction_proceedings.json", "fleet_infraction_protocols.json", "fleet_infraction_payments.json",
    "fleet_infraction_attachments.json", "fleet_infraction_decisions.json", "fleet_infraction_audit_logs.json",
)
SNAPSHOT_FILES = (*JSON_FILES, "settings.json", "financial_entries.json", "sannygold.db")
REQUIRED_TABLES = {
    "fleet_traffic_infractions", "fleet_infraction_deadlines", "fleet_infraction_driver_identifications",
    "fleet_infraction_document_templates", "fleet_infraction_document_template_items", "fleet_infraction_documents",
    "fleet_infraction_proceedings", "fleet_infraction_protocols", "fleet_infraction_payments",
    "fleet_infraction_attachments", "fleet_infraction_decisions", "fleet_infraction_audit_logs",
}
REQUIRED_INDEXES = {
    "uq_fleet_infraction_natural_key", "idx_fleet_infractions_vehicle_status", "idx_fleet_infractions_driver",
    "idx_fleet_infraction_deadlines_priority", "idx_fleet_infraction_identification", "idx_fleet_infraction_documents",
    "idx_fleet_infraction_proceedings", "idx_fleet_infraction_protocols", "uq_fleet_infraction_payment_financial_entry",
    "idx_fleet_infraction_attachments", "idx_fleet_infraction_decisions", "idx_fleet_infraction_audit",
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


def preflight_fleet_fines(*, data_dir: Path, db_path: Path) -> dict:
    invalid, counts = [], {}
    for filename in JSON_FILES:
        payload = read_json(data_dir / filename, [])
        if (data_dir / filename).exists() and not isinstance(payload, list):
            invalid.append(filename)
        counts[filename] = len(payload) if isinstance(payload, list) else 0
    applied = []
    if db_path.exists():
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "schema_migrations" in tables:
                placeholders = ",".join("?" for _ in FLEET_FINES_MIGRATIONS)
                applied = [str(row[0]) for row in connection.execute(f"SELECT id FROM schema_migrations WHERE id IN ({placeholders})", FLEET_FINES_MIGRATIONS)]
    return {"migration_group_id": MIGRATION_GROUP_ID, "migration_ids": list(FLEET_FINES_MIGRATIONS), "can_apply": not invalid,
            "invalid_files": invalid, "record_counts": counts, "applied_migrations": sorted(applied),
            "checked_at": datetime.now().isoformat(timespec="seconds")}


def create_snapshot(data_dir: Path, backups_dir: Path) -> Path:
    target = backups_dir / "migrations" / f"{MIGRATION_GROUP_ID}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    target.mkdir(parents=True, exist_ok=False)
    present = []
    for filename in SNAPSHOT_FILES:
        source = data_dir / filename
        if source.exists():
            shutil.copy2(source, target / filename)
            present.append(filename)
    write_json(target / "manifest.json", {"migration_group_id": MIGRATION_GROUP_ID, "migration_ids": list(FLEET_FINES_MIGRATIONS),
                                          "created_at": datetime.now().isoformat(timespec="seconds"), "present_files": present})
    return target


def validate_fleet_fines(db_path: Path) -> dict:
    with connect(db_path) as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        placeholders = ",".join("?" for _ in FLEET_FINES_MIGRATIONS)
        applied = {str(row[0]) for row in connection.execute(f"SELECT id FROM schema_migrations WHERE id IN ({placeholders})", FLEET_FINES_MIGRATIONS)}
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]
    missing_tables, missing_indexes = sorted(REQUIRED_TABLES - tables), sorted(REQUIRED_INDEXES - indexes)
    missing_migrations = sorted(set(FLEET_FINES_MIGRATIONS) - applied)
    return {"ok": not missing_tables and not missing_indexes and not missing_migrations and integrity == "ok" and not foreign_keys,
            "missing_tables": missing_tables, "missing_indexes": missing_indexes, "missing_migrations": missing_migrations,
            "integrity": integrity, "foreign_key_errors": foreign_keys}


def apply_fleet_fines(*, data_dir: Path, db_path: Path, backups_dir: Path, dry_run: bool = False) -> dict:
    preflight = preflight_fleet_fines(data_dir=data_dir, db_path=db_path)
    if dry_run:
        return {**preflight, "dry_run": True, "snapshot_dir": ""}
    if not preflight["can_apply"]:
        raise ValueError("A migration não foi aplicada porque existem arquivos JSON inválidos.")
    snapshot = create_snapshot(data_dir, backups_dir)
    try:
        for filename in JSON_FILES:
            path = data_dir / filename
            if not path.exists():
                write_json(path, [])
        settings_path = data_dir / "settings.json"
        settings = read_json(settings_path, {})
        if not isinstance(settings, dict):
            settings = {}
        settings.setdefault("fleet_fines_alert_days", DEFAULT_ALERT_DAYS)
        settings.setdefault("fleet_fines_official_links", {})
        write_json(settings_path, settings)
        initialize_database(db_path)
        if save_dict_to_sqlite(db_path, settings_path, settings) is not True:
            raise RuntimeError("Não foi possível atualizar as configurações no SQLite.")
        validation = validate_fleet_fines(db_path)
        if not validation["ok"]:
            raise RuntimeError(f"Validação incompleta das migrations de multas: {validation}")
        report = {**preflight, "dry_run": False, "snapshot_dir": str(snapshot), "applied_at": datetime.now().isoformat(timespec="seconds"), "validation": validation}
        write_json(snapshot / "apply-report.json", report)
        return report
    except Exception as exc:
        rollback_fleet_fines(data_dir=data_dir, backups_dir=backups_dir, snapshot_dir=snapshot)
        raise RuntimeError(f"Falha na migration de multas. O snapshot {snapshot.name} foi restaurado.") from exc


def list_snapshots(backups_dir: Path) -> list[Path]:
    root = backups_dir / "migrations"
    return sorted((path for path in root.glob(f"{MIGRATION_GROUP_ID}-*") if (path / "manifest.json").exists()), reverse=True) if root.exists() else []


def rollback_fleet_fines(*, data_dir: Path, backups_dir: Path, snapshot_dir: Path | None = None) -> dict:
    selected = snapshot_dir or next(iter(list_snapshots(backups_dir)), None)
    if not selected or not selected.exists():
        raise FileNotFoundError("Nenhum snapshot das multas foi encontrado.")
    manifest = read_json(selected / "manifest.json", {})
    if manifest.get("migration_group_id") != MIGRATION_GROUP_ID:
        raise ValueError("O snapshot não pertence ao módulo de multas.")
    present, restored, removed = set(manifest.get("present_files") or []), [], []
    for filename in SNAPSHOT_FILES:
        target, source = data_dir / filename, selected / filename
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
