#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.services.fleet_foundation_migration import (  # noqa: E402
    apply_fleet_foundation,
    rollback_fleet_foundation,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Aplica ou reverte a fundacao da Frota com snapshot local."
    )
    parser.add_argument("action", choices=("apply", "rollback"))
    parser.add_argument("--data-dir", default=str(BASE_DIR / "data"))
    parser.add_argument("--db", default=str(BASE_DIR / "data" / "sannygold.db"))
    parser.add_argument("--backups-dir", default=str(BASE_DIR / "backups"))
    parser.add_argument("--snapshot", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--hq-lat", type=float, default=-22.8753396)
    parser.add_argument("--hq-lng", type=float, default=-43.068074)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = Path(args.data_dir).expanduser().resolve()
    backups_dir = Path(args.backups_dir).expanduser().resolve()
    if args.action == "apply":
        report = apply_fleet_foundation(
            data_dir=data_dir,
            db_path=Path(args.db).expanduser().resolve(),
            backups_dir=backups_dir,
            hq_lat=args.hq_lat,
            hq_lng=args.hq_lng,
            dry_run=args.dry_run,
        )
    else:
        if args.dry_run:
            raise ValueError("--dry-run so e aceito com apply.")
        report = rollback_fleet_foundation(
            data_dir=data_dir,
            backups_dir=backups_dir,
            snapshot_dir=Path(args.snapshot).expanduser().resolve() if args.snapshot else None,
        )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
