from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Callable
from uuid import uuid4

EXCLUDED_BACKUP_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "backups",
    "node_modules",
    "output",
    "tmp",
}
EXCLUDED_BACKUP_SUFFIXES = {".pyc", ".pyo", ".tmp", ".temp", ".part", ".download"}
BACKUP_APP_NAME = "SannyGold"
BACKUP_FORMAT = "sannygold-data-backup-v1"
RESTORE_ROOTS = ("data", "uploads", "preview")
SAFE_RUNTIME_CONFIG_KEYS = (
    "SANNYGOLD_ENV",
    "ROTAFLOW_STORAGE_DIR",
    "SANNYGOLD_SQLITE_PATH",
    "SANNYGOLD_STORAGE_BACKEND",
    "SANNYGOLD_SQLITE_MIRROR_JSON",
    "DROPBOX_BACKUP_DIR",
    "SANNYGOLD_BACKUP_COPY_DIR",
    "SANNYGOLD_BACKUP_RETENTION_LIMIT",
    "SANNYGOLD_DROPBOX_BACKUP_RETENTION_LIMIT",
    "PORT",
    "FLASK_HOST",
    "FLASK_DEBUG",
    "SANNYGOLD_SESSION_COOKIE_SECURE",
    "SANNYGOLD_CSRF_DISABLED",
)


@dataclass(frozen=True)
class BackupConfig:
    backups_dir: Path
    data_dir: Path
    storage_root: Path
    important_data_paths: tuple[Path, ...]
    include_directories: tuple[tuple[Path, str], ...]
    retention_limit: int
    backup_copy_dir: Path | None
    load_settings: Callable[[], dict]
    save_settings: Callable[[dict], None]
    now_iso: Callable[[], str]
    record_audit: Callable[..., None]
    clean_text: Callable[..., str]
    format_datetime_br: Callable[[str | None], str]
    external_retention_limit: int | None = None


def list_backup_files(config: BackupConfig) -> list[Path]:
    return list_backup_files_in_dir(config.backups_dir)


def list_backup_files_in_dir(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    files = [path for path in directory.glob("sannygold-data-backup-*.zip") if path.is_file()]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def list_existing_backup_files(directory: Path) -> list[Path]:
    if not directory.exists() or not directory.is_dir():
        return []
    files = [path for path in directory.glob("sannygold-data-backup-*.zip") if path.is_file()]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def backup_file_created_at(path: Path | None) -> str:
    if not path:
        return ""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return ""


def prune_old_backups(config: BackupConfig, *, keep: int | None = None) -> list[str]:
    return prune_old_backups_in_dir(config.backups_dir, keep=config.retention_limit if keep is None else keep)


def prune_old_backups_in_dir(directory: Path, *, keep: int) -> list[str]:
    deleted: list[str] = []
    for path in list_backup_files_in_dir(directory)[keep:]:
        try:
            path.unlink()
            deleted.append(path.name)
        except OSError:
            continue
    return deleted


def path_is_inside(path: Path, parent: Path) -> bool:
    try:
        path_resolved = path.expanduser().resolve()
        parent_resolved = parent.expanduser().resolve()
        return path_resolved == parent_resolved or parent_resolved in path_resolved.parents
    except OSError:
        return False


def dropbox_root_from_backup_dir(path: Path | None) -> Path | None:
    if not path:
        return None
    expanded = path.expanduser()
    candidates = [expanded, *expanded.parents]
    for candidate in candidates:
        if candidate.name.lower() == "dropbox":
            return candidate
    return expanded


def directory_is_writable(directory: Path) -> bool:
    if not directory.exists() or not directory.is_dir():
        return False
    try:
        with tempfile.NamedTemporaryFile(prefix=".sannygold-write-test-", suffix=".tmp", dir=directory, delete=False) as handle:
            handle.write(b"ok")
            temp_path = Path(handle.name)
        temp_path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def diagnose_dropbox_backup(config: BackupConfig, settings: dict | None = None) -> dict:
    settings = settings or config.load_settings()
    local_files = list_backup_files(config)
    latest_local = local_files[0] if local_files else None
    latest_local_time = backup_file_created_at(latest_local)
    latest_local_size = latest_local.stat().st_size if latest_local else 0

    base_payload = {
        "configured": bool(config.backup_copy_dir),
        "enabled": bool(config.backup_copy_dir),
        "exists": False,
        "writable": False,
        "has_zip": False,
        "path": str(config.backup_copy_dir.expanduser()) if config.backup_copy_dir else "",
        "warning": "",
        "alerts": [],
        "latest_local_filename": latest_local.name if latest_local else config.clean_text(settings.get("last_backup_file")),
        "latest_local_path": str(latest_local) if latest_local else "",
        "latest_local_at": latest_local_time or config.clean_text(settings.get("last_backup_at")),
        "latest_local_size_bytes": latest_local_size,
        "latest_local_size_label": format_size_label(latest_local_size),
        "latest_copy_filename": config.clean_text(settings.get("last_backup_copy_file")),
        "latest_copy_path": config.clean_text(settings.get("last_backup_copy_path")),
        "latest_copy_at": "",
        "latest_copy_size_bytes": 0,
        "latest_copy_size_label": "",
        "time_difference_seconds": None,
    }
    if not config.backup_copy_dir:
        return {
            **base_payload,
            "status": "nao_configurado",
            "status_label": "Dropbox não configurado",
            "status_detail": "Configure DROPBOX_BACKUP_DIR para copiar backups para uma pasta Dropbox local.",
        }

    copy_dir = config.backup_copy_dir.expanduser()
    if path_is_inside(copy_dir, config.storage_root) or path_is_inside(copy_dir, config.backups_dir):
        warning = "A pasta Dropbox não pode ficar dentro da pasta ativa do sistema. Use uma pasta externa que receba apenas arquivos .zip."
        return {
            **base_payload,
            "status": "erro",
            "status_label": "Risco: banco ativo parece estar dentro do Dropbox",
            "status_detail": warning,
            "warning": warning,
            "alerts": [warning],
        }

    dropbox_root = dropbox_root_from_backup_dir(copy_dir)
    risk_paths = []
    if dropbox_root:
        uploads_path = next(
            (
                path
                for path, archive_name in config.include_directories
                if archive_name == "uploads" or path.name == "uploads"
            ),
            config.storage_root / "uploads",
        )
        checks = (
            ("data/", config.data_dir),
            ("uploads/", uploads_path),
            ("sannygold.db", next((path for path in config.important_data_paths if path.name == "sannygold.db"), config.data_dir / "sannygold.db")),
        )
        for label, path in checks:
            if path_is_inside(path, dropbox_root):
                risk_paths.append(label)
    if risk_paths:
        warning = "Risco: banco ativo parece estar dentro do Dropbox"
        detail = "Revise a configuração: " + ", ".join(risk_paths) + " não deve ficar no Dropbox."
        return {
            **base_payload,
            "status": "erro",
            "status_label": warning,
            "status_detail": detail,
            "warning": detail,
            "alerts": [warning, detail],
        }

    if not copy_dir.exists():
        warning = f"Pasta Dropbox não encontrada: {copy_dir} (Dropbox não encontrado)"
        return {
            **base_payload,
            "status": "aviso",
            "status_label": "Dropbox configurado, mas pasta não encontrada",
            "status_detail": "O backup local continuará funcionando. Crie a pasta ou ajuste DROPBOX_BACKUP_DIR.",
            "warning": warning,
            "alerts": [warning],
        }
    if not copy_dir.is_dir():
        warning = f"O caminho configurado para Dropbox não é uma pasta: {copy_dir}"
        return {
            **base_payload,
            "exists": True,
            "status": "erro",
            "status_label": "Caminho Dropbox inválido",
            "status_detail": "Ajuste DROPBOX_BACKUP_DIR para apontar para uma pasta.",
            "warning": warning,
            "alerts": [warning],
        }
    writable = directory_is_writable(copy_dir)
    if not writable:
        warning = f"Sem permissão para gravar no Dropbox: {copy_dir}"
        return {
            **base_payload,
            "exists": True,
            "status": "erro",
            "status_label": "Sem permissão para gravar no Dropbox",
            "status_detail": "O backup local continuará funcionando. Ajuste a permissão da pasta Dropbox.",
            "warning": warning,
            "alerts": [warning],
        }

    copy_files = list_existing_backup_files(copy_dir)
    latest_copy = copy_files[0] if copy_files else None
    latest_copy_time = backup_file_created_at(latest_copy)
    latest_copy_size = latest_copy.stat().st_size if latest_copy else 0
    time_difference_seconds = None
    if latest_local and latest_copy:
        try:
            time_difference_seconds = int(abs(latest_local.stat().st_mtime - latest_copy.stat().st_mtime))
        except OSError:
            time_difference_seconds = None

    if latest_copy:
        return {
            **base_payload,
            "exists": True,
            "writable": True,
            "has_zip": True,
            "status": "sucesso",
            "status_label": "Dropbox OK",
            "status_detail": f"Última cópia no Dropbox: {latest_copy.name}",
            "latest_copy_filename": latest_copy.name,
            "latest_copy_path": str(latest_copy),
            "latest_copy_at": latest_copy_time,
            "latest_copy_size_bytes": latest_copy_size,
            "latest_copy_size_label": format_size_label(latest_copy_size),
            "time_difference_seconds": time_difference_seconds,
        }
    return {
        **base_payload,
        "exists": True,
        "writable": True,
        "status": "sucesso",
        "status_label": "Dropbox configurado, mas sem backup ainda",
        "status_detail": "A pasta está pronta. Gere um backup para criar a primeira cópia .zip.",
    }


def external_backup_dir_status(config: BackupConfig) -> dict:
    return diagnose_dropbox_backup(config)


def test_external_backup_dir(config: BackupConfig) -> dict:
    status = external_backup_dir_status(config)
    if status.get("status") != "sucesso":
        return status
    copy_dir = config.backup_copy_dir.expanduser()
    if os.access(copy_dir, os.W_OK):
        return {
            **status,
            "status": "sucesso",
            "status_label": "Pasta Dropbox testada com sucesso",
            "status_detail": "O sistema encontrou a pasta e ela está liberada para receber backups .zip.",
        }
    warning = f"Sem permissão para gravar na pasta Dropbox: {copy_dir}"
    return {
        **status,
        "status": "erro",
        "status_label": "Sem permissão para gravar no Dropbox",
        "status_detail": "O backup local continuará funcionando. Ajuste a permissão da pasta Dropbox.",
        "warning": warning,
    }


def is_excluded_backup_path(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDED_BACKUP_DIR_NAMES:
        return True
    if path.name.startswith(".") and path.name != ".gitkeep":
        return True
    return path.suffix.lower() in EXCLUDED_BACKUP_SUFFIXES


def safe_archive_write(archive: zipfile.ZipFile, written: set[str], path: Path, arcname: str) -> bool:
    arcname = Path(arcname).as_posix()
    if arcname in written or is_excluded_backup_path(path):
        return False
    archive.write(path, arcname=arcname)
    written.add(arcname)
    return True


def safe_runtime_config_snapshot() -> dict:
    return {key: os.environ.get(key, "") for key in SAFE_RUNTIME_CONFIG_KEYS if os.environ.get(key)}


def backup_external_retention_limit(config: BackupConfig) -> int:
    return config.external_retention_limit or config.retention_limit


def write_data_backup_archive(config: BackupConfig, target, *, generated_at: str, trigger: str) -> dict:
    included: list[str] = []
    included_roots: list[str] = []
    missing: list[str] = []
    skipped: list[str] = []
    written: set[str] = set()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in config.important_data_paths:
            if path.exists() and path.is_file():
                arcname = f"data/{path.name}"
                if safe_archive_write(archive, written, path, arcname):
                    included.append(arcname)
            else:
                missing.append(path.name)
        for directory, arc_root in config.include_directories:
            if not directory.exists():
                missing.append(f"{arc_root}/")
                continue
            if not directory.is_dir():
                skipped.append(f"{arc_root}/")
                continue
            included_roots.append(arc_root)
            dir_marker = f"{arc_root}/"
            if dir_marker not in written:
                archive.writestr(dir_marker, "")
                written.add(dir_marker)
            for path in sorted(directory.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(directory).as_posix()
                arcname = f"{arc_root}/{relative}"
                if arcname in written:
                    continue
                if safe_archive_write(archive, written, path, arcname):
                    included.append(arcname)
                else:
                    skipped.append(arcname)
        backup_config_payload = {
            "app": BACKUP_APP_NAME,
            "backup_format": BACKUP_FORMAT,
            "storage_root": str(config.storage_root),
            "data_dir": str(config.data_dir),
            "backup_dir": str(config.backups_dir),
            "external_copy_enabled": bool(config.backup_copy_dir),
            "external_backup_dir": str(config.backup_copy_dir) if config.backup_copy_dir else "",
            "retention_keep": config.retention_limit,
            "external_retention_keep": backup_external_retention_limit(config),
            "included_roots": [arc_root for _, arc_root in config.include_directories],
            "excluded_dir_names": sorted(EXCLUDED_BACKUP_DIR_NAMES),
            "excluded_suffixes": sorted(EXCLUDED_BACKUP_SUFFIXES),
        }
        archive.writestr("config/backup-config.json", json.dumps(backup_config_payload, indent=2, ensure_ascii=False))
        written.add("config/backup-config.json")
        archive.writestr("config/runtime-config.json", json.dumps(safe_runtime_config_snapshot(), indent=2, ensure_ascii=False))
        written.add("config/runtime-config.json")
        manifest = {
            "app": BACKUP_APP_NAME,
            "backup_format": BACKUP_FORMAT,
            "generated_at": generated_at,
            "trigger": trigger,
            "storage_root": str(config.storage_root),
            "data_dir": str(config.data_dir),
            "retention_keep": config.retention_limit,
            "external_retention_keep": backup_external_retention_limit(config),
            "included_roots": sorted(set(included_roots)),
            "included_files": included,
            "missing_files": missing,
            "skipped_files": sorted(set(skipped)),
        }
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return {"included_files": included, "missing_files": missing, "skipped_files": sorted(set(skipped))}


def copy_backup_to_external_dir(config: BackupConfig, backup_path: Path) -> dict:
    if not config.backup_copy_dir:
        return external_copy_disabled()
    status = external_backup_dir_status(config)
    if status.get("status") != "sucesso":
        return {
            "enabled": True,
            "path": "",
            "filename": "",
            "warning": status.get("warning") or status.get("status_detail", ""),
            "deleted_files": [],
            "status": status.get("status"),
            "status_label": status.get("status_label"),
        }
    try:
        copy_dir = config.backup_copy_dir.expanduser()
        destination = copy_dir / backup_path.name
        shutil.copy2(backup_path, destination)
        deleted = prune_old_backups_in_dir(copy_dir, keep=backup_external_retention_limit(config))
        return {
            "enabled": True,
            "path": str(destination),
            "filename": destination.name,
            "warning": "",
            "deleted_files": deleted,
            "status": "sucesso",
            "status_label": "Copiado para Dropbox",
        }
    except OSError as exc:
        return {
            "enabled": True,
            "path": "",
            "filename": "",
            "warning": f"Não foi possível copiar o backup para a pasta Dropbox: {exc}",
            "deleted_files": [],
            "status": "erro",
            "status_label": "Erro ao copiar para Dropbox",
        }


def external_copy_disabled() -> dict:
    return {"enabled": False, "path": "", "filename": "", "warning": "", "deleted_files": []}


def create_data_backup(
    config: BackupConfig,
    *,
    trigger: str = "manual",
    audit_action: str | None = "create",
    copy_external: bool = False,
) -> dict:
    config.backups_dir.mkdir(parents=True, exist_ok=True)
    generated_at = config.now_iso()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_name = f"sannygold-data-backup-{timestamp}-{uuid4().hex[:8]}.zip"
    backup_path = config.backups_dir / backup_name
    temp_path = config.backups_dir / f".{backup_name}.tmp"
    payload = write_data_backup_archive(config, temp_path, generated_at=generated_at, trigger=trigger)
    temp_path.replace(backup_path)
    external_copy = copy_backup_to_external_dir(config, backup_path) if copy_external else external_copy_disabled()
    deleted = prune_old_backups(config)
    settings = config.load_settings()
    settings["last_backup_at"] = generated_at
    settings["last_backup_file"] = backup_name
    settings["last_backup_warnings"] = payload["missing_files"]
    settings["last_backup_skipped_files"] = payload["skipped_files"]
    settings["last_backup_copy_file"] = external_copy.get("filename", "")
    settings["last_backup_copy_path"] = external_copy.get("path", "")
    settings["last_backup_copy_warning"] = external_copy.get("warning", "")
    config.save_settings(settings)
    result = {
        "path": backup_path,
        "filename": backup_name,
        "created_at": generated_at,
        "included_files": payload["included_files"],
        "missing_files": payload["missing_files"],
        "skipped_files": payload["skipped_files"],
        "deleted_files": deleted,
        "external_copy": external_copy,
        "size_bytes": backup_path.stat().st_size,
    }
    if audit_action:
        detail = f"Backup {trigger} gerado em {backup_name}."
        if payload["missing_files"]:
            detail += f" Arquivos ausentes: {', '.join(payload['missing_files'])}."
        if copy_external and external_copy.get("warning"):
            detail += f" Aviso de cópia externa: {external_copy['warning']}."
        config.record_audit(audit_action, "backup", backup_name, detail, after={key: value for key, value in result.items() if key != "path"})
    if copy_external and external_copy.get("enabled"):
        if external_copy.get("path"):
            config.record_audit(
                "copy",
                "backup",
                backup_name,
                f"Backup copiado para Dropbox em {external_copy['path']}.",
                after={"copy_path": external_copy.get("path"), "source_file": str(backup_path)},
            )
        elif external_copy.get("warning"):
            config.record_audit(
                "copy_warning",
                "backup",
                backup_name,
                f"Cópia para Dropbox não concluída: {external_copy['warning']}",
                after={"warning": external_copy.get("warning"), "configured_path": str(config.backup_copy_dir or "")},
            )
    return result


def normalize_zip_member_name(name: str) -> PurePosixPath:
    return PurePosixPath(name.replace("\\", "/"))


def validate_backup_archive(backup_path: Path) -> dict:
    backup_path = Path(backup_path)
    if not backup_path.exists() or not backup_path.is_file():
        raise ValueError(f"Backup não encontrado: {backup_path}")
    if backup_path.suffix.lower() != ".zip":
        raise ValueError("O arquivo informado precisa ser um .zip.")
    with zipfile.ZipFile(backup_path) as archive:
        names = archive.namelist()
        if "manifest.json" not in names:
            raise ValueError("Backup inválido: manifest.json não encontrado.")
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Backup inválido: manifest.json não é JSON válido.") from exc
        if not isinstance(manifest, dict):
            raise ValueError("Backup inválido: manifest.json precisa ser um objeto JSON.")
        if manifest.get("app") != BACKUP_APP_NAME or manifest.get("backup_format") != BACKUP_FORMAT:
            raise ValueError("Backup inválido: o arquivo não foi identificado como backup SannyGold atual.")
        if not any(name == "data/" or name.startswith("data/") for name in names):
            raise ValueError("Backup inválido: pasta data/ não encontrada.")
        for name in names:
            normalized = normalize_zip_member_name(name)
            if normalized.is_absolute() or ".." in normalized.parts or any(part.endswith(":") for part in normalized.parts):
                raise ValueError(f"Backup inválido: caminho inseguro no ZIP ({name}).")
    return {
        "manifest": manifest,
        "names": names,
        "restorable_roots": sorted({normalize_zip_member_name(name).parts[0] for name in names if normalize_zip_member_name(name).parts and normalize_zip_member_name(name).parts[0] in RESTORE_ROOTS}),
    }


def extract_backup_to_temp(backup_path: Path) -> tuple[Path, dict]:
    validation = validate_backup_archive(backup_path)
    temp_dir = Path(tempfile.mkdtemp(prefix="sannygold-restore-test-"))
    try:
        with zipfile.ZipFile(backup_path) as archive:
            for name in validation["names"]:
                archive.extract(name, temp_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    return temp_dir, validation


def replace_allowed_restore_roots(config: BackupConfig, extracted_root: Path) -> tuple[list[str], list[str]]:
    allowed_roots = {
        "data": config.data_dir.resolve(),
        "preview": (config.storage_root / "preview").resolve(),
        "uploads": (config.storage_root / "uploads").resolve(),
    }
    restored: list[str] = []
    skipped: list[str] = []
    for root_name, target_root in allowed_roots.items():
        source_root = extracted_root / root_name
        if not source_root.exists():
            continue
        if not source_root.is_dir():
            skipped.append(root_name)
            continue
        for source in sorted(source_root.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(source_root)
            destination = (target_root / relative).resolve()
            if target_root not in destination.parents and destination != target_root:
                skipped.append(f"{root_name}/{relative.as_posix()}")
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            restored.append(f"{root_name}/{relative.as_posix()}")
    return restored, skipped


def restore_data_backup(config: BackupConfig, backup_path: Path) -> dict:
    backup_path = Path(backup_path)
    backups_dir = config.backups_dir.resolve()
    if not backup_path.exists() or not backup_path.is_file() or backup_path.parent.resolve() != backups_dir:
        raise ValueError("Backup inválido para restauração.")

    temp_dir, validation = extract_backup_to_temp(backup_path)
    try:
        restored, skipped = replace_allowed_restore_roots(config, temp_dir)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return {
        "filename": backup_path.name,
        "restored_files": restored,
        "skipped_files": skipped,
        "manifest": validation["manifest"],
        "restored_at": config.now_iso(),
    }


def test_restore_backup(config: BackupConfig, backup_path: Path) -> dict:
    backup_path = Path(backup_path)
    temp_dir, validation = extract_backup_to_temp(backup_path)
    try:
        restored_files = []
        for root_name in RESTORE_ROOTS:
            source_root = temp_dir / root_name
            if source_root.exists() and source_root.is_dir():
                restored_files.extend(f"{root_name}/{path.relative_to(source_root).as_posix()}" for path in sorted(source_root.rglob("*")) if path.is_file())
        return {
            "filename": backup_path.name,
            "tested_at": config.now_iso(),
            "temp_dir": str(temp_dir),
            "restorable_roots": validation["restorable_roots"],
            "restorable_file_count": len(restored_files),
            "manifest": validation["manifest"],
            "changed_real_data": False,
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def format_size_label(size_bytes: int) -> str:
    size = float(size_bytes or 0)
    for suffix in ("B", "KB", "MB", "GB"):
        if size < 1024 or suffix == "GB":
            return f"{size:.1f} {suffix}" if suffix != "B" else f"{int(size)} B"
        size /= 1024
    return f"{int(size_bytes)} B"


def build_backup_status(config: BackupConfig, settings: dict | None = None) -> dict:
    settings = settings or config.load_settings()
    files = list_backup_files(config)
    dropbox_status = diagnose_dropbox_backup(config, settings)
    copy_dir = config.backup_copy_dir.expanduser() if config.backup_copy_dir else None
    copy_files = list_existing_backup_files(copy_dir) if copy_dir else []
    latest = files[0] if files else None
    latest_copy = copy_files[0] if copy_files else None
    latest_created_at = backup_file_created_at(latest)
    last_backup_at = config.clean_text(settings.get("last_backup_at")) or latest_created_at
    latest_name = latest.name if latest else config.clean_text(settings.get("last_backup_file"))
    copy_warning = config.clean_text(settings.get("last_backup_copy_warning"))
    warnings = settings.get("last_backup_warnings") if isinstance(settings.get("last_backup_warnings"), list) else []
    skipped_files = settings.get("last_backup_skipped_files") if isinstance(settings.get("last_backup_skipped_files"), list) else []
    latest_size = latest.stat().st_size if latest else 0
    if not latest:
        status = "aviso"
        status_label = "Nenhum backup local encontrado"
        status_detail = "Gere um backup para proteger os dados."
    elif warnings or skipped_files:
        status = "aviso"
        status_label = "Backup local criado com aviso"
        status_detail = "O backup foi salvo, mas existe arquivo ausente ou ignorado. Revise os detalhes antes de depender dele."
    elif dropbox_status.get("configured") and (copy_warning or dropbox_status.get("status") != "sucesso"):
        status = "aviso"
        status_label = "Backup local em dia; Dropbox com aviso"
        status_detail = "O backup local está salvo. Corrija a pasta Dropbox para manter a cópia externa."
    else:
        status = "sucesso"
        status_label = "Backup local em dia"
        status_detail = "Backup local disponível em backups/." + (" Cópia Dropbox atualizada." if latest_copy else "")
    if copy_warning:
        dropbox_status = {
            **dropbox_status,
            "status": "aviso" if dropbox_status.get("status") != "erro" else "erro",
            "status_label": "Cópia Dropbox com aviso",
            "status_detail": copy_warning,
            "warning": copy_warning,
        }
    return {
        "count": len(files),
        "last_backup_at": last_backup_at,
        "last_backup_label": config.format_datetime_br(last_backup_at),
        "latest_filename": latest_name,
        "latest_path": str(latest) if latest else "",
        "latest_size_bytes": latest_size,
        "latest_size_label": format_size_label(latest_size),
        "retention_limit": config.retention_limit,
        "external_retention_limit": backup_external_retention_limit(config),
        "backup_dir": str(config.backups_dir),
        "backup_copy_dir": str(copy_dir) if copy_dir else "",
        "copy_count": len(copy_files),
        "latest_copy_filename": dropbox_status.get("latest_copy_filename") or (latest_copy.name if latest_copy else config.clean_text(settings.get("last_backup_copy_file"))),
        "latest_copy_path": dropbox_status.get("latest_copy_path") or (str(latest_copy) if latest_copy else config.clean_text(settings.get("last_backup_copy_path"))),
        "latest_copy_size_label": dropbox_status.get("latest_copy_size_label") or (format_size_label(latest_copy.stat().st_size) if latest_copy else ""),
        "latest_copy_at": dropbox_status.get("latest_copy_at", ""),
        "dropbox_time_difference_seconds": dropbox_status.get("time_difference_seconds"),
        "dropbox_writable": bool(dropbox_status.get("writable")),
        "dropbox_has_zip": bool(dropbox_status.get("has_zip")),
        "dropbox_alerts": dropbox_status.get("alerts", []),
        "has_latest_copy": bool(latest_copy and latest_copy.exists()),
        "copy_warning": copy_warning,
        "dropbox_configured": bool(dropbox_status.get("configured")),
        "dropbox_enabled": bool(dropbox_status.get("enabled")),
        "dropbox_status": dropbox_status.get("status"),
        "dropbox_status_label": dropbox_status.get("status_label"),
        "dropbox_status_detail": dropbox_status.get("status_detail"),
        "dropbox_warning": dropbox_status.get("warning", ""),
        "warnings": warnings,
        "skipped_files": skipped_files,
        "has_latest": bool(latest and latest.exists()),
        "status": status,
        "status_label": status_label,
        "status_detail": status_detail,
    }
