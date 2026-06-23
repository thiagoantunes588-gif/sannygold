#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.main import build_backup_status, create_data_backup, ensure_storage_dirs


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera backup local compactado dos dados da SannyGold.")
    parser.add_argument("--trigger", default="manual_cli", help="Origem registrada no manifest do backup.")
    parser.add_argument("--if-older-hours", type=int, default=0, help="Gera apenas se o último backup for mais antigo que este limite.")
    parser.add_argument("--quiet", action="store_true", help="Mostra somente erros.")
    args = parser.parse_args()

    ensure_storage_dirs()
    status = build_backup_status()
    last_backup = parse_iso_datetime(status.get("last_backup_at"))
    if args.if_older_hours and last_backup:
        threshold = datetime.now() - timedelta(hours=args.if_older_hours)
        if last_backup >= threshold:
            if not args.quiet:
                print(f"Backup recente encontrado: {status.get('latest_filename') or status.get('last_backup_label')}")
            return 0

    backup = create_data_backup(trigger=args.trigger, audit_action="automatic")
    if not args.quiet:
        print(f"Backup criado: {backup['path']}")
        external_copy = backup.get("external_copy") or {}
        if external_copy.get("path"):
            print(f"Cópia externa: {external_copy['path']}")
        elif external_copy.get("warning"):
            print(external_copy["warning"])
        if backup.get("missing_files"):
            print("Arquivos ausentes: " + ", ".join(backup["missing_files"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
