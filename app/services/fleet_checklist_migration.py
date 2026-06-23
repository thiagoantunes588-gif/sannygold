from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from app.repositories.sqlite_repository import FLEET_CHECKLIST_MIGRATIONS, connect, initialize_database
from app.services.sqlite_store import save_dict_to_sqlite, save_list_to_sqlite


MIGRATION_GROUP_ID = "20260621_fleet_checklists"
JSON_FILES = (
    "fleet_checklist_templates.json",
    "fleet_checklist_template_items.json",
    "fleet_checklists.json",
    "fleet_checklist_responses.json",
    "fleet_checklist_evidence.json",
    "fleet_occurrences.json",
    "vehicle_operational_blocks.json",
    "fleet_vehicle_assignments.json",
    "fleet_driver_authorizations.json",
)
SNAPSHOT_FILES = (*JSON_FILES, "vehicles.json", "users.json", "settings.json", "sannygold.db")
REQUIRED_TABLES = {
    "fleet_checklist_templates", "fleet_checklist_template_items", "fleet_checklists",
    "fleet_checklist_responses", "fleet_checklist_evidence", "fleet_occurrences",
    "vehicle_operational_blocks", "fleet_vehicle_assignments", "fleet_driver_authorizations",
}
REQUIRED_INDEXES = {
    "idx_fleet_checklist_templates_active", "idx_fleet_checklist_template_items_template",
    "idx_fleet_checklists_vehicle_status", "idx_fleet_checklists_route",
    "idx_fleet_checklist_responses_checklist", "idx_fleet_checklist_evidence_checklist",
    "uq_fleet_occurrence_number", "idx_fleet_occurrences_vehicle_status",
    "idx_vehicle_operational_blocks_active", "uq_fleet_vehicle_assignment_open",
    "idx_fleet_vehicle_assignments_driver", "idx_fleet_driver_authorizations_user",
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


def _seed_templates(data_dir: Path) -> None:
    templates_path = data_dir / "fleet_checklist_templates.json"
    items_path = data_dir / "fleet_checklist_template_items.json"
    templates = read_json(templates_path, [])
    items = read_json(items_path, [])
    if templates or items:
        return
    now = datetime.now().isoformat(timespec="seconds")
    base_templates = (
        ("TPL-SAIDA-001", "LOG-SAIDA-PADRAO", "Checklist de saída padrão", "saida"),
        ("TPL-RETORNO-001", "LOG-RETORNO-PADRAO", "Checklist de retorno padrão", "retorno"),
    )
    templates = [
        {
            "id": template_id, "logical_id": logical_id, "name": name,
            "description": "Modelo inicial configurável. Revise os itens conforme o manual e o tipo do veículo.",
            "checklist_type": checklist_type, "vehicle_type": "geral", "is_active": True,
            "version": 1, "supersedes_template_id": "", "created_by": "migration",
            "created_at": now, "updated_at": now, "deleted_at": "",
        }
        for template_id, logical_id, name, checklist_type in base_templates
    ]
    seed_items = (
        ("identificacao_veiculo", "Identificação e placa conferidas", True, False, False),
        ("documentacao", "Documentação disponível", True, True, True),
        ("quilometragem", "Hodômetro registrado", True, False, True),
        ("pneus", "Pneus e estepe em condição segura", True, True, True),
        ("freios", "Freios sem anormalidade aparente", True, True, True),
        ("iluminacao", "Iluminação e sinalização funcionando", True, True, True),
        ("equipamentos_obrigatorios", "Equipamentos obrigatórios presentes", True, True, True),
        ("avarias_externas", "Avarias externas registradas", False, False, True),
    )
    items = []
    for template_id, _logical_id, _name, _type in base_templates:
        for position, (category, title, required, critical, photo) in enumerate(seed_items, start=1):
            items.append({
                "id": f"ITM-{template_id}-{position:02d}", "template_id": template_id,
                "category": category, "title": title, "description": "",
                "display_order": position, "response_type": "conformidade",
                "selection_options": [], "selection_options_json": "[]", "is_required": required,
                "is_critical": critical, "requires_photo": photo and category in {"quilometragem", "avarias_externas"},
                "requires_note_on_failure": True, "creates_occurrence_on_failure": True,
                "blocks_vehicle_on_failure": critical, "created_at": now, "updated_at": now,
                "deleted_at": "",
            })
    write_json(templates_path, templates)
    write_json(items_path, items)


def preflight_fleet_checklists(*, data_dir: Path, db_path: Path) -> dict:
    invalid_files, counts = [], {}
    for filename in JSON_FILES:
        payload = read_json(data_dir / filename, [])
        if (data_dir / filename).exists() and not isinstance(payload, list):
            invalid_files.append(filename)
        counts[filename] = len(payload) if isinstance(payload, list) else 0
    tables, applied = [], []
    if db_path.exists():
        uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            tables = sorted(str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'"))
            if "schema_migrations" in tables:
                placeholders = ",".join("?" for _ in FLEET_CHECKLIST_MIGRATIONS)
                applied = sorted(str(row[0]) for row in connection.execute(f"SELECT id FROM schema_migrations WHERE id IN ({placeholders})", FLEET_CHECKLIST_MIGRATIONS))
    return {
        "migration_group_id": MIGRATION_GROUP_ID, "migration_ids": list(FLEET_CHECKLIST_MIGRATIONS),
        "can_apply": not invalid_files, "invalid_files": invalid_files, "record_counts": counts,
        "database": {"exists": db_path.exists(), "tables": tables, "applied_migrations": applied},
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def create_snapshot(data_dir: Path, backups_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot = backups_dir / "migrations" / f"{MIGRATION_GROUP_ID}-{timestamp}"
    snapshot.mkdir(parents=True, exist_ok=False)
    present = []
    for filename in SNAPSHOT_FILES:
        source = data_dir / filename
        if source.exists():
            shutil.copy2(source, snapshot / filename)
            present.append(filename)
    write_json(snapshot / "manifest.json", {
        "migration_group_id": MIGRATION_GROUP_ID, "migration_ids": list(FLEET_CHECKLIST_MIGRATIONS),
        "created_at": datetime.now().isoformat(timespec="seconds"), "data_dir": str(data_dir),
        "present_files": present,
    })
    return snapshot


def validate_fleet_checklists(db_path: Path) -> dict:
    with connect(db_path) as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        placeholders = ",".join("?" for _ in FLEET_CHECKLIST_MIGRATIONS)
        applied = {str(row[0]) for row in connection.execute(f"SELECT id FROM schema_migrations WHERE id IN ({placeholders})", FLEET_CHECKLIST_MIGRATIONS)}
    missing_tables = sorted(REQUIRED_TABLES - tables)
    missing_indexes = sorted(REQUIRED_INDEXES - indexes)
    missing_migrations = sorted(set(FLEET_CHECKLIST_MIGRATIONS) - applied)
    return {"ok": not missing_tables and not missing_indexes and not missing_migrations, "missing_tables": missing_tables, "missing_indexes": missing_indexes, "missing_migrations": missing_migrations}


def apply_fleet_checklists(*, data_dir: Path, db_path: Path, backups_dir: Path, dry_run: bool = False) -> dict:
    preflight = preflight_fleet_checklists(data_dir=data_dir, db_path=db_path)
    if dry_run:
        return {**preflight, "dry_run": True, "snapshot_dir": ""}
    if not preflight["can_apply"]:
        raise ValueError("A migration não foi aplicada porque existem arquivos JSON inválidos.")
    snapshot = create_snapshot(data_dir, backups_dir)
    try:
        for filename in JSON_FILES:
            if not (data_dir / filename).exists():
                write_json(data_dir / filename, [])
        _seed_templates(data_dir)
        settings_path = data_dir / "settings.json"
        settings = read_json(settings_path, {})
        if not isinstance(settings, dict):
            settings = {}
        settings.setdefault("fleet_checklist_required_for_routes", True)
        settings.setdefault("fleet_checklist_route_exceptions_enabled", True)
        settings.setdefault("fleet_checklist_auto_draft", True)
        write_json(settings_path, settings)
        initialize_database(db_path)
        for filename in ("fleet_checklist_templates.json", "fleet_checklist_template_items.json"):
            if save_list_to_sqlite(db_path, data_dir / filename, read_json(data_dir / filename, [])) is not True:
                raise RuntimeError(f"Não foi possível importar {filename} para o SQLite.")
        if save_dict_to_sqlite(db_path, settings_path, settings) is not True:
            raise RuntimeError("Não foi possível atualizar as configurações no SQLite.")
        validation = validate_fleet_checklists(db_path)
        if not validation["ok"]:
            raise RuntimeError(f"Validação incompleta da Fase 3: {validation}")
        report = {**preflight, "dry_run": False, "snapshot_dir": str(snapshot), "applied_at": datetime.now().isoformat(timespec="seconds"), "validation": validation}
        write_json(snapshot / "apply-report.json", report)
        return report
    except Exception as exc:
        rollback = rollback_fleet_checklists(data_dir=data_dir, backups_dir=backups_dir, snapshot_dir=snapshot)
        write_json(snapshot / "failure-report.json", {"error": str(exc), "automatic_rollback": rollback, "failed_at": datetime.now().isoformat(timespec="seconds")})
        raise RuntimeError(f"Falha na migration da Fase 3. O snapshot {snapshot.name} foi restaurado.") from exc


def list_snapshots(backups_dir: Path) -> list[Path]:
    root = backups_dir / "migrations"
    if not root.exists():
        return []
    return sorted((path for path in root.glob(f"{MIGRATION_GROUP_ID}-*") if (path / "manifest.json").exists()), reverse=True)


def rollback_fleet_checklists(*, data_dir: Path, backups_dir: Path, snapshot_dir: Path | None = None) -> dict:
    selected = snapshot_dir or next(iter(list_snapshots(backups_dir)), None)
    if not selected or not selected.exists():
        raise FileNotFoundError("Nenhum snapshot da Fase 3 foi encontrado.")
    manifest = read_json(selected / "manifest.json", {})
    if manifest.get("migration_group_id") != MIGRATION_GROUP_ID:
        raise ValueError("O snapshot não pertence à Fase 3 da Frota.")
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
