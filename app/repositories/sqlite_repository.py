from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_STORAGE_ROOT = Path(os.environ.get("ROTAFLOW_STORAGE_DIR", str(BASE_DIR)))
DEFAULT_DB_PATH = Path(os.environ.get("SANNYGOLD_SQLITE_PATH", str(DEFAULT_STORAGE_ROOT / "data" / "sannygold.db")))
SCHEMA_PATH = BASE_DIR / "app" / "db" / "schema.sql"

CORE_TABLES = {
    "clients": "client_id",
    "events": "event_id",
    "equipment": "equipment_id",
    "vehicles": "vehicle_id",
    "users": "user_id",
    "audit_log": "audit_id",
    "financial_receivables": "receivable_id",
    "financial_entries": "entry_id",
    "financial_closeouts": "closeout_id",
}
IDENTIFIER_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(json_dumps(payload).encode("utf-8")).hexdigest()


def connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db_path: Path | str = DEFAULT_DB_PATH, schema_path: Path | str = SCHEMA_PATH) -> None:
    schema = Path(schema_path).read_text(encoding="utf-8")
    with connect(db_path) as connection:
        connection.executescript(schema)


def validate_identifier(value: str) -> str:
    if not IDENTIFIER_PATTERN.match(value):
        raise ValueError(f"Identificador SQL inválido: {value}")
    return value


class SQLiteRepository:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        initialize_database(self.db_path)

    def upsert_core_record(
        self,
        table: str,
        record_id: str,
        indexed_fields: dict[str, Any],
        payload: dict,
        *,
        source_file: str,
        migrated_at: str,
    ) -> None:
        if table not in CORE_TABLES:
            raise ValueError(f"Tabela principal não permitida: {table}")
        id_column = CORE_TABLES[table]
        columns = {
            id_column: record_id,
            **indexed_fields,
            "source_file": source_file,
            "payload_json": json_dumps(payload),
            "payload_hash": payload_hash(payload),
            "migrated_at": migrated_at,
        }
        self._upsert(table, id_column, columns)

    def upsert_json_record(
        self,
        *,
        entity: str,
        record_id: str,
        record_label: str,
        source_file: str,
        payload: dict,
        migrated_at: str,
    ) -> None:
        columns = {
            "entity": entity,
            "record_id": record_id,
            "record_label": record_label,
            "source_file": source_file,
            "payload_json": json_dumps(payload),
            "payload_hash": payload_hash(payload),
            "migrated_at": migrated_at,
        }
        self._upsert("json_records", "entity, record_id", columns)

    def upsert_json_document(self, *, entity: str, source_file: str, payload: dict, migrated_at: str) -> None:
        columns = {
            "entity": entity,
            "source_file": source_file,
            "payload_json": json_dumps(payload),
            "payload_hash": payload_hash(payload),
            "migrated_at": migrated_at,
        }
        self._upsert("json_documents", "entity", columns)

    def upsert_backup_file(self, *, filename: str, path: str, size_bytes: int, modified_at: str, payload: dict, migrated_at: str) -> None:
        columns = {
            "filename": filename,
            "path": path,
            "size_bytes": size_bytes,
            "modified_at": modified_at,
            "payload_json": json_dumps(payload),
            "migrated_at": migrated_at,
        }
        self._upsert("backup_files", "filename", columns)

    def record_migration_run(self, run: dict) -> None:
        columns = {
            "id": run["id"],
            "started_at": run["started_at"],
            "finished_at": run.get("finished_at"),
            "source_data_dir": run["source_data_dir"],
            "database_path": run["database_path"],
            "status": run["status"],
            "imported_count": int(run.get("imported_count") or 0),
            "ignored_count": int(run.get("ignored_count") or 0),
            "error_count": int(run.get("error_count") or 0),
            "report_json": json_dumps(run.get("report") or {}),
        }
        self._upsert("migration_runs", "id", columns)

    def record_migration_item(self, run_id: str, item: dict) -> None:
        columns = {
            "run_id": run_id,
            "entity": item.get("entity", ""),
            "source_file": item.get("source_file", ""),
            "record_id": item.get("record_id"),
            "status": item.get("status", ""),
            "message": item.get("message", ""),
        }
        column_names = list(columns)
        placeholders = ", ".join("?" for _ in column_names)
        with connect(self.db_path) as connection:
            connection.execute(
                f"INSERT INTO migration_items ({', '.join(column_names)}) VALUES ({placeholders})",
                [columns[column] for column in column_names],
            )

    def count_rows(self, table: str) -> int:
        table = validate_identifier(table)
        with connect(self.db_path) as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def _upsert(self, table: str, conflict_target: str, columns: dict[str, Any]) -> None:
        table = validate_identifier(table)
        for column in columns:
            validate_identifier(column)
        conflict_columns = [validate_identifier(column.strip()) for column in conflict_target.split(",")]
        column_names = list(columns)
        placeholders = ", ".join("?" for _ in column_names)
        assignments = ", ".join(
            f"{column}=excluded.{column}"
            for column in column_names
            if column not in conflict_columns
        )
        sql = (
            f"INSERT INTO {table} ({', '.join(column_names)}) VALUES ({placeholders}) "
            f"ON CONFLICT({', '.join(conflict_columns)}) DO UPDATE SET {assignments}"
        )
        with connect(self.db_path) as connection:
            connection.execute(sql, [columns[column] for column in column_names])
