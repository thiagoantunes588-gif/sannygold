#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.services.fleet_maintenance_migration import apply_fleet_maintenance, rollback_fleet_maintenance  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Aplica ou reverte a Fase 2 da Frota com snapshot local.")
    parser.add_argument("action", choices=("apply", "rollback"))
    parser.add_argument("--data-dir", default=str(BASE_DIR / "data"))
    parser.add_argument("--db", default=str(BASE_DIR / "data" / "sannygold.db"))
    parser.add_argument("--backups-dir", default=str(BASE_DIR / "backups"))
    parser.add_argument("--snapshot", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    data_dir = Path(args.data_dir).expanduser().resolve()
    backups_dir = Path(args.backups_dir).expanduser().resolve()
    if args.action == "apply":
        report = apply_fleet_maintenance(data_dir=data_dir, db_path=Path(args.db).expanduser().resolve(), backups_dir=backups_dir, dry_run=args.dry_run)
    else:
        if args.dry_run:
            raise ValueError("--dry-run só é aceito com apply.")
        report = rollback_fleet_maintenance(data_dir=data_dir, backups_dir=backups_dir, snapshot_dir=Path(args.snapshot).expanduser().resolve() if args.snapshot else None)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
