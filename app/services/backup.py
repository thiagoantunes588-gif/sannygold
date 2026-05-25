from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4


@dataclass(frozen=True)
class BackupConfig:
    backups_dir: Path
    data_dir: Path
    storage_root: Path
    important_data_paths: tuple[Path, ...]
    retention_limit: int
    load_settings: Callable[[], dict]
    save_settings: Callable[[dict], None]
    now_iso: Callable[[], str]
    record_audit: Callable[..., None]
    clean_text: Callable[..., str]
    format_datetime_br: Callable[[str | None], str]


def list_backup_files(config: BackupConfig) -> list[Path]:
    config.backups_dir.mkdir(parents=True, exist_ok=True)
    files = [path for path in config.backups_dir.glob("sannygold-data-backup-*.zip") if path.is_file()]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def backup_file_created_at(path: Path | None) -> str:
    if not path:
        return ""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return ""


def prune_old_backups(config: BackupConfig, *, keep: int | None = None) -> list[str]:
    deleted: list[str] = []
    keep_count = config.retention_limit if keep is None else keep
    for path in list_backup_files(config)[keep_count:]:
        try:
            path.unlink()
            deleted.append(path.name)
        except OSError:
            continue
    return deleted


def write_data_backup_archive(config: BackupConfig, target, *, generated_at: str, trigger: str) -> dict:
    included: list[str] = []
    missing: list[str] = []
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in config.important_data_paths:
            if path.exists() and path.is_file():
                archive.write(path, arcname=f"data/{path.name}")
                included.append(f"data/{path.name}")
            else:
                missing.append(path.name)
        manifest = {
            "generated_at": generated_at,
            "trigger": trigger,
            "storage_root": str(config.storage_root),
            "data_dir": str(config.data_dir),
            "retention_keep": config.retention_limit,
            "included_files": included,
            "missing_files": missing,
        }
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return {"included_files": included, "missing_files": missing}


def create_data_backup(config: BackupConfig, *, trigger: str = "manual", audit_action: str | None = "create") -> dict:
    config.backups_dir.mkdir(parents=True, exist_ok=True)
    generated_at = config.now_iso()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = f"sannygold-data-backup-{timestamp}-{uuid4().hex[:8]}.zip"
    backup_path = config.backups_dir / backup_name
    temp_path = config.backups_dir / f".{backup_name}.tmp"
    payload = write_data_backup_archive(config, temp_path, generated_at=generated_at, trigger=trigger)
    temp_path.replace(backup_path)
    deleted = prune_old_backups(config)
    settings = config.load_settings()
    settings["last_backup_at"] = generated_at
    settings["last_backup_file"] = backup_name
    settings["last_backup_warnings"] = payload["missing_files"]
    config.save_settings(settings)
    result = {
        "path": backup_path,
        "filename": backup_name,
        "created_at": generated_at,
        "included_files": payload["included_files"],
        "missing_files": payload["missing_files"],
        "deleted_files": deleted,
        "size_bytes": backup_path.stat().st_size,
    }
    if audit_action:
        detail = f"Backup {trigger} gerado em {backup_name}."
        if payload["missing_files"]:
            detail += f" Arquivos ausentes: {', '.join(payload['missing_files'])}."
        config.record_audit(audit_action, "backup", backup_name, detail, after={key: value for key, value in result.items() if key != "path"})
    return result


def restore_data_backup(config: BackupConfig, backup_path: Path) -> dict:
    backup_path = Path(backup_path)
    backups_dir = config.backups_dir.resolve()
    if not backup_path.exists() or not backup_path.is_file() or backup_path.parent.resolve() != backups_dir:
        raise ValueError("Backup inválido para restauração.")

    data_dir = config.data_dir.resolve()
    restored: list[str] = []
    skipped: list[str] = []
    config.data_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(backup_path) as archive:
        for info in archive.infolist():
            if info.is_dir() or info.filename == "manifest.json":
                continue
            relative = Path(info.filename)
            if len(relative.parts) != 2 or relative.parts[0] != "data":
                skipped.append(info.filename)
                continue
            destination = (config.data_dir / relative.name).resolve()
            if destination.parent != data_dir:
                skipped.append(info.filename)
                continue
            destination.write_bytes(archive.read(info))
            restored.append(f"data/{relative.name}")
    return {
        "filename": backup_path.name,
        "restored_files": restored,
        "skipped_files": skipped,
        "restored_at": config.now_iso(),
    }


def build_backup_status(config: BackupConfig, settings: dict | None = None) -> dict:
    settings = settings or config.load_settings()
    files = list_backup_files(config)
    latest = files[0] if files else None
    latest_created_at = backup_file_created_at(latest)
    last_backup_at = config.clean_text(settings.get("last_backup_at")) or latest_created_at
    latest_name = latest.name if latest else config.clean_text(settings.get("last_backup_file"))
    return {
        "count": len(files),
        "last_backup_at": last_backup_at,
        "last_backup_label": config.format_datetime_br(last_backup_at),
        "latest_filename": latest_name,
        "latest_path": str(latest) if latest else "",
        "latest_size_bytes": latest.stat().st_size if latest else 0,
        "retention_limit": config.retention_limit,
        "backup_dir": str(config.backups_dir),
        "warnings": settings.get("last_backup_warnings") if isinstance(settings.get("last_backup_warnings"), list) else [],
        "has_latest": bool(latest and latest.exists()),
    }
