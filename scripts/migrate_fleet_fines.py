from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.fleet_fines_migration import apply_fleet_fines, list_snapshots, rollback_fleet_fines, validate_fleet_fines


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrations do módulo de multas da Frota")
    parser.add_argument("action", choices=("dry-run", "apply", "validate", "rollback", "snapshots"))
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--backups-dir", type=Path, default=ROOT / "backups")
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    db_path = args.db_path or args.data_dir / "sannygold.db"
    if args.action == "dry-run":
        result = apply_fleet_fines(data_dir=args.data_dir, db_path=db_path, backups_dir=args.backups_dir, dry_run=True)
    elif args.action == "apply":
        result = apply_fleet_fines(data_dir=args.data_dir, db_path=db_path, backups_dir=args.backups_dir)
    elif args.action == "validate":
        result = validate_fleet_fines(db_path)
    elif args.action == "rollback":
        result = rollback_fleet_fines(data_dir=args.data_dir, backups_dir=args.backups_dir, snapshot_dir=args.snapshot)
    else:
        result = {"snapshots": [str(path) for path in list_snapshots(args.backups_dir)]}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
