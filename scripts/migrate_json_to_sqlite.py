#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.repositories.sqlite_repository import DEFAULT_DB_PATH  # noqa: E402
from app.services.sqlite_migration import MigrationOptions, migrate_json_to_sqlite  # noqa: E402


def default_report_path(data_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return data_dir / "migration_reports" / f"sqlite-migration-{timestamp}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migra dados JSON da SannyGold para SQLite sem apagar os JSON originais.")
    parser.add_argument("--data-dir", default=str(BASE_DIR / "data"), help="Pasta com os arquivos JSON atuais.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Caminho do banco SQLite a criar/atualizar.")
    parser.add_argument("--report", default="", help="Caminho do relatorio JSON. Padrao: data/migration_reports/...")
    parser.add_argument("--dry-run", action="store_true", help="Valida e gera relatorio sem escrever no SQLite.")
    parser.add_argument("--no-backups", action="store_true", help="Nao importar metadados da pasta backups/.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = Path(args.data_dir)
    db_path = Path(args.db)
    report_path = Path(args.report) if args.report else default_report_path(data_dir)
    report = migrate_json_to_sqlite(
        MigrationOptions(
            data_dir=data_dir,
            db_path=db_path,
            report_path=report_path,
            dry_run=args.dry_run,
            include_backups=not args.no_backups,
        )
    )
    summary = report["summary"]
    print(f"Banco SQLite: {db_path}")
    print(f"Relatorio: {report_path}")
    print(f"Importados: {summary['imported']}")
    print(f"Ignorados: {summary['ignored']}")
    print(f"Erros: {summary['errors']}")
    if args.dry_run:
        print("Dry-run: nenhum dado foi gravado no SQLite.")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
