#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parents[1]
RESTORE_ROOTS = ("data", "uploads", "preview")
BACKUP_APP_NAME = "SannyGold"
BACKUP_FORMAT = "sannygold-data-backup-v1"


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(project_root: Path, message: str) -> None:
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "restore.log").open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp()}] {message}\n")


def read_env_file(project_root: Path) -> dict[str, str]:
    env_path = project_root / ".env.local"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def safe_port(value: str | int | None, default: int = 5007) -> int:
    try:
        port = int(str(value or default).strip())
    except (TypeError, ValueError):
        return default
    return port if 1 <= port <= 65535 else default


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def launcher_lock_is_active(project_root: Path) -> bool:
    lock_path = project_root / "logs" / "launcher.lock"
    if not lock_path.exists():
        return False
    for raw_line in lock_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw_line.startswith("pid="):
            continue
        try:
            return process_is_running(int(raw_line.split("=", 1)[1].strip()))
        except ValueError:
            return False
    return False


def healthcheck_is_active(project_root: Path) -> bool:
    env = read_env_file(project_root)
    port = safe_port(os.environ.get("PORT") or env.get("PORT"))
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def system_is_running(project_root: Path) -> bool:
    return launcher_lock_is_active(project_root) or healthcheck_is_active(project_root)


def validate_backup_zip(backup_path: Path) -> list[str]:
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
            normalized = PurePosixPath(name.replace("\\", "/"))
            if normalized.is_absolute() or ".." in normalized.parts or any(part.endswith(":") for part in normalized.parts):
                raise ValueError(f"Backup inválido: caminho inseguro no ZIP ({name}).")
        return names


def extract_to_temp(backup_path: Path, names: list[str]) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="sannygold-restore-"))
    with zipfile.ZipFile(backup_path) as archive:
        for name in names:
            archive.extract(name, temp_dir)
    return temp_dir


def create_safety_backup(project_root: Path) -> Path:
    backups_dir = project_root / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backups_dir / f"sannygold-pre-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as archive:
        manifest = {
            "app": BACKUP_APP_NAME,
            "backup_format": BACKUP_FORMAT,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "trigger": "pre_restore_cli",
            "included_roots": [],
        }
        for root_name in RESTORE_ROOTS:
            source = project_root / root_name
            if not source.exists() or not source.is_dir():
                continue
            manifest["included_roots"].append(root_name)
            for path in sorted(source.rglob("*")):
                if path.is_file():
                    archive.write(path, f"{root_name}/{path.relative_to(source).as_posix()}")
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return backup_path


def replace_tree(project_root: Path, extracted_root: Path, root_name: str, replaced_root: Path) -> list[str]:
    source = extracted_root / root_name
    if not source.exists() or not source.is_dir():
        return []
    target = project_root / root_name
    replaced_root.mkdir(parents=True, exist_ok=True)
    if target.exists():
        archived_target = replaced_root / root_name
        if archived_target.exists():
            shutil.rmtree(archived_target)
        shutil.move(str(target), str(archived_target))
    shutil.copytree(source, target)
    return [path.relative_to(source).as_posix() for path in sorted(source.rglob("*")) if path.is_file()]


def restore_backup(backup_path: Path, *, project_root: Path = BASE_DIR, skip_running_check: bool = False) -> dict:
    project_root = project_root.resolve()
    backup_path = backup_path.expanduser().resolve()
    log(project_root, f"Restauração solicitada: {backup_path}")
    if not skip_running_check and system_is_running(project_root):
        raise RuntimeError("O sistema parece estar rodando. Feche o launcher/servidor antes de restaurar.")

    names = validate_backup_zip(backup_path)
    extracted_root = extract_to_temp(backup_path, names)
    safety_backup = create_safety_backup(project_root)
    replaced_root = project_root / "tmp" / f"restore-replaced-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    restored: dict[str, list[str]] = {}
    try:
        for root_name in RESTORE_ROOTS:
            restored_files = replace_tree(project_root, extracted_root, root_name, replaced_root)
            if restored_files:
                restored[root_name] = restored_files
    finally:
        shutil.rmtree(extracted_root, ignore_errors=True)

    result = {
        "backup": str(backup_path),
        "safety_backup": str(safety_backup),
        "replaced_previous_state": str(replaced_root),
        "restored_roots": sorted(restored.keys()),
        "restored_file_count": sum(len(files) for files in restored.values()),
    }
    log(project_root, "Restauração concluída: " + json.dumps(result, ensure_ascii=False))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Restaura um backup .zip do Sistema SannyGold com backup preventivo.")
    parser.add_argument("backup_zip", help="Caminho do arquivo .zip de backup.")
    parser.add_argument("--project-root", default=str(BASE_DIR), help="Raiz do projeto SannyGold.")
    parser.add_argument("--skip-running-check", action="store_true", help="Uso restrito a testes: ignora checagem de servidor ativo.")
    args = parser.parse_args()

    try:
        result = restore_backup(
            Path(args.backup_zip),
            project_root=Path(args.project_root),
            skip_running_check=args.skip_running_check,
        )
    except Exception as exc:  # noqa: BLE001
        log(Path(args.project_root), f"Falha na restauração: {exc}")
        print(f"Falha na restauração: {exc}", file=sys.stderr)
        return 1

    print("Restauração concluída.")
    print(f"Backup restaurado: {result['backup']}")
    print(f"Backup preventivo criado: {result['safety_backup']}")
    print(f"Estado anterior movido para: {result['replaced_previous_state']}")
    print(f"Pastas restauradas: {', '.join(result['restored_roots'])}")
    print(f"Arquivos restaurados: {result['restored_file_count']}")
    print(f"Log: {Path(args.project_root) / 'logs' / 'restore.log'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
