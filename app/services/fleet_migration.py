from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from app.repositories.sqlite_repository import initialize_database
from app.services.fleet import (
    DEFAULT_DOCUMENT_ALERT_DAYS,
    normalize_alert_days,
    normalize_vehicle_record,
)
from app.services.sqlite_store import save_dict_to_sqlite, save_list_to_sqlite


MIGRATION_ID = "20260619_01_fleet_phase1"
MIGRATED_FILES = ("vehicles.json", "fleet_documents.json", "settings.json", "sannygold.db")


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
    snapshot_dir = backups_dir / "migrations" / f"{MIGRATION_ID}-{timestamp}"
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    present_files = []
    for filename in MIGRATED_FILES:
        source = data_dir / filename
        if source.exists():
            shutil.copy2(source, snapshot_dir / filename)
            present_files.append(filename)
    write_json(
        snapshot_dir / "manifest.json",
        {
            "migration_id": MIGRATION_ID,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "data_dir": str(data_dir),
            "present_files": present_files,
        },
    )
    return snapshot_dir


def find_duplicate_vehicle_identifiers(vehicles: list[dict]) -> dict[str, list[dict]]:
    duplicates: dict[str, list[dict]] = {}
    for field in ("plate_normalized", "renavam_normalized", "chassis_normalized"):
        grouped: dict[str, list[str]] = {}
        for vehicle in vehicles:
            value = str(vehicle.get(field) or "").strip()
            if not value:
                continue
            grouped.setdefault(value, []).append(str(vehicle.get("vehicle_id") or "").strip())
        duplicates[field] = [
            {"value": value, "vehicle_ids": vehicle_ids}
            for value, vehicle_ids in sorted(grouped.items())
            if len(vehicle_ids) > 1
        ]
    return duplicates


def apply_fleet_phase1(
    *,
    data_dir: Path,
    db_path: Path,
    backups_dir: Path,
    hq_lat: float,
    hq_lng: float,
    dry_run: bool = False,
) -> dict:
    vehicles_path = data_dir / "vehicles.json"
    documents_path = data_dir / "fleet_documents.json"
    settings_path = data_dir / "settings.json"
    vehicles = read_json(vehicles_path, [])
    documents = read_json(documents_path, [])
    settings = read_json(settings_path, {})
    if not isinstance(vehicles, list):
        raise ValueError("vehicles.json precisa conter uma lista.")
    if not isinstance(documents, list):
        documents = []
    if not isinstance(settings, dict):
        settings = {}

    migrated_at = datetime.now().isoformat(timespec="seconds")
    normalized_vehicles = []
    for vehicle in vehicles:
        if not isinstance(vehicle, dict):
            continue
        normalized = normalize_vehicle_record(vehicle, hq_lat=hq_lat, hq_lng=hq_lng)
        normalized["created_at"] = normalized.get("created_at") or migrated_at
        normalized["updated_at"] = normalized.get("updated_at") or migrated_at
        normalized_vehicles.append(normalized)
    settings["fleet_document_alert_days"] = normalize_alert_days(
        settings.get("fleet_document_alert_days") or DEFAULT_DOCUMENT_ALERT_DAYS
    )
    duplicate_identifiers = find_duplicate_vehicle_identifiers(normalized_vehicles)
    duplicate_count = sum(len(items) for items in duplicate_identifiers.values())

    report = {
        "migration_id": MIGRATION_ID,
        "dry_run": dry_run,
        "can_apply": duplicate_count == 0,
        "vehicles_found": len(vehicles),
        "vehicles_normalized": len(normalized_vehicles),
        "documents_found": len(documents),
        "alert_days": settings["fleet_document_alert_days"],
        "duplicate_identifiers": duplicate_identifiers,
        "snapshot_dir": "",
        "applied_at": migrated_at,
    }
    if dry_run:
        return report
    if duplicate_count:
        raise ValueError(
            "A migration não foi aplicada porque existem placas, Renavam ou chassis duplicados. "
            "Execute com --dry-run e corrija os identificadores informados no relatório."
        )

    snapshot_dir = create_snapshot(data_dir, backups_dir)
    report["snapshot_dir"] = str(snapshot_dir)
    try:
        write_json(vehicles_path, normalized_vehicles)
        write_json(documents_path, documents)
        write_json(settings_path, settings)
        initialize_database(db_path)
        if not save_list_to_sqlite(db_path, vehicles_path, normalized_vehicles):
            raise RuntimeError("Não foi possível gravar veículos no SQLite.")
        if not save_list_to_sqlite(db_path, documents_path, documents):
            raise RuntimeError("Não foi possível gravar documentos da frota no SQLite.")
        if not save_dict_to_sqlite(db_path, settings_path, settings):
            raise RuntimeError("Não foi possível gravar configurações da frota no SQLite.")
        write_json(snapshot_dir / "apply-report.json", report)
    except Exception as exc:
        rollback_report = rollback_fleet_phase1(
            data_dir=data_dir,
            backups_dir=backups_dir,
            snapshot_dir=snapshot_dir,
        )
        write_json(
            snapshot_dir / "failure-report.json",
            {
                "migration_id": MIGRATION_ID,
                "failed_at": datetime.now().isoformat(timespec="seconds"),
                "error": str(exc),
                "automatic_rollback": rollback_report,
            },
        )
        raise RuntimeError(
            f"Falha ao aplicar a migration da Frota. O snapshot {snapshot_dir.name} foi restaurado automaticamente."
        ) from exc
    return report


def list_snapshots(backups_dir: Path) -> list[Path]:
    root = backups_dir / "migrations"
    if not root.exists():
        return []
    return sorted(
        (
            path
            for path in root.glob(f"{MIGRATION_ID}-*")
            if path.is_dir() and (path / "manifest.json").exists()
        ),
        reverse=True,
    )


def rollback_fleet_phase1(*, data_dir: Path, backups_dir: Path, snapshot_dir: Path | None = None) -> dict:
    selected = snapshot_dir or next(iter(list_snapshots(backups_dir)), None)
    if not selected or not selected.exists():
        raise FileNotFoundError("Nenhum snapshot da migration da Frota foi encontrado.")
    manifest = read_json(selected / "manifest.json", {})
    if manifest.get("migration_id") != MIGRATION_ID:
        raise ValueError("O snapshot selecionado não pertence à migration da Frota Fase 1.")
    present_files = set(manifest.get("present_files") or [])
    restored = []
    removed = []
    for filename in MIGRATED_FILES:
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
        "migration_id": MIGRATION_ID,
        "snapshot_dir": str(selected),
        "rolled_back_at": datetime.now().isoformat(timespec="seconds"),
        "restored_files": restored,
        "removed_files": removed,
    }
    write_json(selected / "rollback-report.json", report)
    return report
