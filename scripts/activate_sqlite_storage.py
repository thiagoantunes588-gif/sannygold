#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#") or "=" not in clean:
            continue
        key, value = clean.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def write_env_file(path: Path, values: dict[str, str]) -> None:
    preferred_order = [
        "SANNYGOLD_ENV",
        "SANNYGOLD_SECRET_KEY",
        "SANNYGOLD_ADMIN_EMAIL",
        "SANNYGOLD_ADMIN_PASSWORD",
        "SANNYGOLD_ADMIN_NAME",
        "ROTAFLOW_STORAGE_DIR",
        "SANNYGOLD_SQLITE_PATH",
        "SANNYGOLD_STORAGE_BACKEND",
        "SANNYGOLD_SQLITE_MIRROR_JSON",
        "DROPBOX_BACKUP_DIR",
        "FLASK_DEBUG",
        "SANNYGOLD_SESSION_COOKIE_SECURE",
        "SANNYGOLD_CSRF_DISABLED",
    ]
    keys = preferred_order + sorted(key for key in values if key not in preferred_order)
    lines = [f"{key}={shell_quote(values[key])}" for key in keys if key in values]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    env_path = BASE_DIR / ".env.local"
    values = parse_env_file(env_path)
    values.setdefault("SANNYGOLD_ENV", "local")
    values.setdefault("SANNYGOLD_ADMIN_EMAIL", "contato@sannygold.com")
    values.setdefault("SANNYGOLD_ADMIN_PASSWORD", "troque-esta-senha")
    values.setdefault("SANNYGOLD_ADMIN_NAME", "Administrador SannyGold")
    values.setdefault("FLASK_DEBUG", "0")
    values.setdefault("SANNYGOLD_SESSION_COOKIE_SECURE", "0")
    values.setdefault("SANNYGOLD_CSRF_DISABLED", "0")
    values["ROTAFLOW_STORAGE_DIR"] = str(BASE_DIR)
    values["SANNYGOLD_SQLITE_PATH"] = str(BASE_DIR / "data" / "sannygold.db")
    values["SANNYGOLD_STORAGE_BACKEND"] = "sqlite"
    values["SANNYGOLD_SQLITE_MIRROR_JSON"] = "1"
    values.setdefault("DROPBOX_BACKUP_DIR", values.pop("SANNYGOLD_BACKUP_COPY_DIR", str(Path.home() / "Dropbox" / "Sistema SannyGold" / "Backups")))
    write_env_file(env_path, values)

    os.environ.update(values)
    from app.services.sqlite_migration import MigrationOptions, migrate_json_to_sqlite

    report_path = BASE_DIR / "data" / "migration_reports" / f"sqlite-activation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    report = migrate_json_to_sqlite(
        MigrationOptions(
            data_dir=BASE_DIR / "data",
            db_path=Path(values["SANNYGOLD_SQLITE_PATH"]),
            report_path=report_path,
            include_backups=True,
        )
    )
    summary = report["summary"]
    print(f"SQLite ativo em: {values['SANNYGOLD_SQLITE_PATH']}")
    print(f"Relatório: {report_path}")
    print(f"Importados: {summary['imported']}")
    print(f"Ignorados: {summary['ignored']}")
    print(f"Erros: {summary['errors']}")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
