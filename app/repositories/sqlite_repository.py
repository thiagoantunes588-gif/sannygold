from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime
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
    "fleet_documents": "document_id",
    "fleet_service_orders": "id",
    "fleet_service_order_items": "id",
    "vehicle_maintenance_plans": "id",
    "fleet_maintenance_attachments": "id",
    "fleet_inventory_reservations": "id",
    "fleet_checklist_templates": "id",
    "fleet_checklist_template_items": "id",
    "fleet_checklists": "id",
    "fleet_checklist_responses": "id",
    "fleet_checklist_evidence": "id",
    "fleet_occurrences": "id",
    "vehicle_operational_blocks": "id",
    "fleet_vehicle_assignments": "id",
    "fleet_driver_authorizations": "id",
    "fleet_traffic_infractions": "id",
    "fleet_infraction_deadlines": "id",
    "fleet_infraction_driver_identifications": "id",
    "fleet_infraction_document_templates": "id",
    "fleet_infraction_document_template_items": "id",
    "fleet_infraction_documents": "id",
    "fleet_infraction_proceedings": "id",
    "fleet_infraction_protocols": "id",
    "fleet_infraction_payments": "id",
    "fleet_infraction_attachments": "id",
    "fleet_infraction_decisions": "id",
    "fleet_infraction_audit_logs": "id",
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
        apply_fleet_phase1_schema(connection)
        apply_fleet_foundation_schema(connection)
        apply_fleet_maintenance_schema(connection)
        apply_fleet_checklist_schema(connection)
        apply_fleet_fines_schema(connection)


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    table = validate_identifier(table)
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def apply_fleet_phase1_schema(connection: sqlite3.Connection) -> None:
    migration_id = "20260619_01_fleet_phase1"
    columns = table_columns(connection, "vehicles")
    additions = {
        "plate_normalized": "TEXT NOT NULL DEFAULT ''",
        "renavam_normalized": "TEXT NOT NULL DEFAULT ''",
        "chassis_normalized": "TEXT NOT NULL DEFAULT ''",
        "status": "TEXT NOT NULL DEFAULT 'disponivel'",
        "deleted_at": "TEXT NOT NULL DEFAULT ''",
    }
    for column, definition in additions.items():
        if column not in columns:
            connection.execute(f"ALTER TABLE vehicles ADD COLUMN {column} {definition}")

    rows = connection.execute(
        "SELECT vehicle_id, payload_json FROM vehicles"
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        plate = re.sub(r"[^A-Z0-9]", "", str(payload.get("plate") or "").upper())
        renavam = re.sub(r"[^A-Z0-9]", "", str(payload.get("renavam") or "").upper())
        chassis = re.sub(
            r"[^A-Z0-9]",
            "",
            str(payload.get("chassis") or payload.get("chassi") or "").upper(),
        )
        status = str(payload.get("status") or "disponivel").strip() or "disponivel"
        deleted_at = str(payload.get("deleted_at") or "").strip()
        connection.execute(
            """
            UPDATE vehicles
               SET plate_normalized = ?,
                   renavam_normalized = ?,
                   chassis_normalized = ?,
                   status = ?,
                   deleted_at = ?
             WHERE vehicle_id = ?
            """,
            (plate, renavam, chassis, status, deleted_at, row["vehicle_id"]),
        )

    index_results = {}
    for index_name, column in (
        ("uq_vehicles_plate", "plate_normalized"),
        ("uq_vehicles_renavam", "renavam_normalized"),
        ("uq_vehicles_chassis", "chassis_normalized"),
    ):
        try:
            connection.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON vehicles({column}) WHERE {column} <> ''"
            )
            index_results[index_name] = "applied"
        except sqlite3.IntegrityError:
            index_results[index_name] = "skipped_existing_duplicates"
    connection.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (id, applied_at, details_json)
        VALUES (?, datetime('now'), ?)
        """,
        (
            migration_id,
            json.dumps(
                {
                    "module": "fleet",
                    "phase": 1,
                    "unique_indexes": index_results,
                    "rollback": "Restore the pre-migration snapshot created by scripts/migrate_fleet_phase1.py.",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        ),
    )


FLEET_FOUNDATION_MIGRATIONS = (
    "20260620_01_fleet_vehicle_entity",
    "20260620_02_fleet_vehicle_documents",
    "20260620_03_fleet_vehicle_mileage",
    "20260620_04_fleet_vehicle_audit_logs",
)

FLEET_MAINTENANCE_MIGRATIONS = (
    "20260621_01_fleet_service_orders",
    "20260621_02_fleet_service_order_items",
    "20260621_03_vehicle_maintenance_plans",
    "20260621_04_fleet_maintenance_attachments",
    "20260621_05_fleet_inventory_reservations",
)

FLEET_CHECKLIST_MIGRATIONS = (
    "20260621_11_fleet_checklist_templates",
    "20260621_12_fleet_checklist_template_items",
    "20260621_13_fleet_checklists",
    "20260621_14_fleet_checklist_responses",
    "20260621_15_fleet_checklist_evidence",
    "20260621_16_fleet_occurrences",
    "20260621_17_vehicle_operational_blocks",
    "20260621_18_fleet_vehicle_assignments",
    "20260621_19_fleet_driver_authorizations",
)

FLEET_FINES_MIGRATIONS = (
    "20260621_20_fleet_traffic_infractions",
    "20260621_21_fleet_infraction_deadlines",
    "20260621_22_fleet_infraction_driver_identifications",
    "20260621_23_fleet_infraction_document_templates",
    "20260621_24_fleet_infraction_document_template_items",
    "20260621_25_fleet_infraction_documents",
    "20260621_26_fleet_infraction_proceedings",
    "20260621_27_fleet_infraction_protocols",
    "20260621_28_fleet_infraction_payments",
    "20260621_29_fleet_infraction_attachments",
    "20260621_30_fleet_infraction_decisions",
    "20260621_31_fleet_infraction_audit_logs",
)


def _payload_from_row(value: str | None) -> dict:
    try:
        payload = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _text(value) -> str:
    return str(value or "").strip()


def _integer(value, fallback: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return fallback


def _number(value, fallback: float = 0.0) -> float:
    try:
        return round(float(str(value).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return fallback


def _boolean(value) -> int:
    return int(_text(value).lower() in {"1", "true", "yes", "sim", "on"})


def _record_schema_migration(connection: sqlite3.Connection, migration_id: str, details: dict) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (id, applied_at, details_json)
        VALUES (?, ?, ?)
        """,
        (
            migration_id,
            datetime.now().isoformat(timespec="seconds"),
            json.dumps(details, ensure_ascii=False, sort_keys=True),
        ),
    )


def apply_fleet_foundation_schema(connection: sqlite3.Connection) -> None:
    applied = {
        str(row[0])
        for row in connection.execute(
            "SELECT id FROM schema_migrations WHERE id IN (?, ?, ?, ?)",
            FLEET_FOUNDATION_MIGRATIONS,
        )
    }

    vehicle_columns = table_columns(connection, "vehicles")
    vehicle_additions = {
        "id": "TEXT",
        "renavam": "TEXT",
        "chassis": "TEXT",
        "brand": "TEXT",
        "model": "TEXT",
        "version": "TEXT",
        "manufacture_year": "INTEGER",
        "model_year": "INTEGER",
        "fuel_type": "TEXT",
        "current_mileage": "INTEGER NOT NULL DEFAULT 0 CHECK (current_mileage >= 0)",
        "legal_owner_company": "TEXT",
        "operating_company": "TEXT",
        "cost_center": "TEXT",
        "acquisition_date": "TEXT",
        "acquisition_value": "REAL NOT NULL DEFAULT 0 CHECK (acquisition_value >= 0)",
        "usual_driver_id": "TEXT",
        "tracker_installed": "INTEGER NOT NULL DEFAULT 0 CHECK (tracker_installed IN (0, 1))",
        "camera_installed": "INTEGER NOT NULL DEFAULT 0 CHECK (camera_installed IN (0, 1))",
        "notes": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
        "deleted_at": "TEXT NOT NULL DEFAULT ''",
    }
    for column, definition in vehicle_additions.items():
        if column not in vehicle_columns:
            connection.execute(f"ALTER TABLE vehicles ADD COLUMN {column} {definition}")

    vehicle_rows = connection.execute(
        "SELECT vehicle_id, payload_json, migrated_at FROM vehicles"
    ).fetchall()
    for row in vehicle_rows:
        payload = _payload_from_row(row["payload_json"])
        connection.execute(
            """
            UPDATE vehicles
               SET id = ?, plate = ?, renavam = ?, chassis = ?, brand = ?, model = ?, version = ?,
                   manufacture_year = ?, model_year = ?, vehicle_type = ?, fuel_type = ?, current_mileage = ?,
                   legal_owner_company = ?, operating_company = ?, cost_center = ?, acquisition_date = ?,
                   acquisition_value = ?, usual_driver_id = ?, status = ?, tracker_installed = ?,
                   camera_installed = ?, notes = ?, created_at = ?, updated_at = ?, deleted_at = ?
             WHERE vehicle_id = ?
            """,
            (
                _text(payload.get("id") or payload.get("vehicle_id") or row["vehicle_id"]),
                _text(payload.get("plate")),
                _text(payload.get("renavam")),
                _text(payload.get("chassis") or payload.get("chassi")),
                _text(payload.get("brand")),
                _text(payload.get("model")),
                _text(payload.get("version")),
                _integer(payload.get("manufacture_year"), 0) or None,
                _integer(payload.get("model_year"), 0) or None,
                _text(payload.get("vehicle_type")),
                _text(payload.get("fuel_type")),
                max(_integer(payload.get("current_mileage"), 0), 0),
                _text(payload.get("legal_owner_company") or payload.get("legal_owner")),
                _text(payload.get("operating_company")),
                _text(payload.get("cost_center")),
                _text(payload.get("acquisition_date")),
                max(_number(payload.get("acquisition_value"), 0.0), 0.0),
                _text(payload.get("usual_driver_id")),
                _text(payload.get("status")) or "disponivel",
                _boolean(payload.get("tracker_installed")),
                _boolean(payload.get("camera_installed")),
                _text(payload.get("notes")),
                _text(payload.get("created_at")) or _text(row["migrated_at"]),
                _text(payload.get("updated_at")) or _text(row["migrated_at"]),
                _text(payload.get("deleted_at")),
                row["vehicle_id"],
            ),
        )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicles_entity_id ON vehicles(id) WHERE id IS NOT NULL AND id <> ''"
    )
    if FLEET_FOUNDATION_MIGRATIONS[0] not in applied:
        _record_schema_migration(
            connection,
            FLEET_FOUNDATION_MIGRATIONS[0],
            {"module": "fleet", "entity": "Vehicle", "strategy": "additive_columns_and_backfill"},
        )

    document_columns = table_columns(connection, "fleet_documents")
    document_additions = {
        "id": "TEXT",
        "issue_date": "TEXT",
        "expiration_date": "TEXT",
        "file_path": "TEXT",
        "responsible_user_id": "TEXT",
        "notes": "TEXT",
        "created_at": "TEXT",
        "updated_at": "TEXT",
        "deleted_at": "TEXT NOT NULL DEFAULT ''",
    }
    for column, definition in document_additions.items():
        if column not in document_columns:
            connection.execute(f"ALTER TABLE fleet_documents ADD COLUMN {column} {definition}")

    document_rows = connection.execute(
        "SELECT document_id, payload_json, migrated_at FROM fleet_documents"
    ).fetchall()
    for row in document_rows:
        payload = _payload_from_row(row["payload_json"])
        connection.execute(
            """
            UPDATE fleet_documents
               SET id = ?, vehicle_id = ?, document_type = ?, document_number = ?,
                   issue_date = ?, expiration_date = ?, file_path = ?, status = ?,
                   responsible_user_id = ?, notes = ?, created_at = ?, updated_at = ?, deleted_at = ?
             WHERE document_id = ?
            """,
            (
                _text(payload.get("id") or payload.get("document_id") or row["document_id"]),
                _text(payload.get("vehicle_id")),
                _text(payload.get("document_type")),
                _text(payload.get("document_number") or payload.get("number")),
                _text(payload.get("issue_date") or payload.get("issued_at")),
                _text(payload.get("expiration_date") or payload.get("expires_at")),
                _text(payload.get("file_path") or payload.get("file_url")),
                _text(payload.get("status")) or "ativo",
                _text(payload.get("responsible_user_id")),
                _text(payload.get("notes")),
                _text(payload.get("created_at")) or _text(row["migrated_at"]),
                _text(payload.get("updated_at")) or _text(row["migrated_at"]),
                _text(payload.get("deleted_at")),
                row["document_id"],
            ),
        )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fleet_documents_entity_id ON fleet_documents(id) WHERE id IS NOT NULL AND id <> ''"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_fleet_documents_expiration_date ON fleet_documents(expiration_date)"
    )
    if FLEET_FOUNDATION_MIGRATIONS[1] not in applied:
        _record_schema_migration(
            connection,
            FLEET_FOUNDATION_MIGRATIONS[1],
            {"module": "fleet", "entity": "VehicleDocument", "strategy": "additive_columns_and_backfill"},
        )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS vehicle_mileage (
            id TEXT PRIMARY KEY,
            vehicle_id TEXT NOT NULL,
            mileage INTEGER NOT NULL CHECK (mileage >= 0),
            record_date TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual',
            user_id TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicle_mileage_vehicle_date ON vehicle_mileage(vehicle_id, record_date DESC)"
    )
    if FLEET_FOUNDATION_MIGRATIONS[2] not in applied:
        for row in vehicle_rows:
            payload = _payload_from_row(row["payload_json"])
            created_at = _text(payload.get("updated_at") or payload.get("created_at") or row["migrated_at"])
            record_date = created_at[:10] if len(created_at) >= 10 else datetime.now().date().isoformat()
            connection.execute(
                """
                INSERT OR IGNORE INTO vehicle_mileage
                    (id, vehicle_id, mileage, record_date, source, user_id, notes, created_at)
                VALUES (?, ?, ?, ?, 'migration_initial', NULL, ?, ?)
                """,
                (
                    f"MIL-{row['vehicle_id']}-INITIAL",
                    row["vehicle_id"],
                    max(_integer(payload.get("current_mileage"), 0), 0),
                    record_date,
                    "Marco inicial criado pela migration da Frota.",
                    created_at or datetime.now().isoformat(timespec="seconds"),
                ),
            )
        _record_schema_migration(
            connection,
            FLEET_FOUNDATION_MIGRATIONS[2],
            {"module": "fleet", "entity": "VehicleMileage", "strategy": "create_table_and_initial_snapshot"},
        )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS vehicle_audit_logs (
            id TEXT PRIMARY KEY,
            vehicle_id TEXT NOT NULL,
            user_id TEXT,
            action TEXT NOT NULL,
            previous_data TEXT,
            new_data TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id) ON UPDATE CASCADE ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_vehicle_audit_vehicle_created ON vehicle_audit_logs(vehicle_id, created_at DESC)"
    )
    if FLEET_FOUNDATION_MIGRATIONS[3] not in applied:
        for row in vehicle_rows:
            payload = _payload_from_row(row["payload_json"])
            created_at = _text(payload.get("created_at") or row["migrated_at"]) or datetime.now().isoformat(timespec="seconds")
            connection.execute(
                """
                INSERT OR IGNORE INTO vehicle_audit_logs
                    (id, vehicle_id, user_id, action, previous_data, new_data, created_at)
                VALUES (?, ?, NULL, 'migration_initial', NULL, ?, ?)
                """,
                (
                    f"VAUD-{row['vehicle_id']}-INITIAL",
                    row["vehicle_id"],
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    created_at,
                ),
            )
        _record_schema_migration(
            connection,
            FLEET_FOUNDATION_MIGRATIONS[3],
            {"module": "fleet", "entity": "VehicleAuditLog", "strategy": "create_table_and_initial_log"},
        )


def apply_fleet_maintenance_schema(connection: sqlite3.Connection) -> None:
    table_map = (
        (FLEET_MAINTENANCE_MIGRATIONS[0], "FleetServiceOrder", "fleet_service_orders"),
        (FLEET_MAINTENANCE_MIGRATIONS[1], "FleetServiceOrderItem", "fleet_service_order_items"),
        (FLEET_MAINTENANCE_MIGRATIONS[2], "VehicleMaintenancePlan", "vehicle_maintenance_plans"),
        (FLEET_MAINTENANCE_MIGRATIONS[3], "FleetMaintenanceAttachment", "fleet_maintenance_attachments"),
        (FLEET_MAINTENANCE_MIGRATIONS[4], "FleetInventoryReservation", "fleet_inventory_reservations"),
    )
    existing_tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    for migration_id, entity, table in table_map:
        if table not in existing_tables:
            raise RuntimeError(f"A tabela obrigatoria {table} nao foi criada pelo schema.")
        _record_schema_migration(
            connection,
            migration_id,
            {
                "module": "fleet",
                "phase": 2,
                "entity": entity,
                "table": table,
                "strategy": "additive_create_table",
            },
        )


def apply_fleet_checklist_schema(connection: sqlite3.Connection) -> None:
    table_map = (
        (FLEET_CHECKLIST_MIGRATIONS[0], "FleetChecklistTemplate", "fleet_checklist_templates"),
        (FLEET_CHECKLIST_MIGRATIONS[1], "FleetChecklistTemplateItem", "fleet_checklist_template_items"),
        (FLEET_CHECKLIST_MIGRATIONS[2], "FleetChecklist", "fleet_checklists"),
        (FLEET_CHECKLIST_MIGRATIONS[3], "FleetChecklistResponse", "fleet_checklist_responses"),
        (FLEET_CHECKLIST_MIGRATIONS[4], "FleetChecklistEvidence", "fleet_checklist_evidence"),
        (FLEET_CHECKLIST_MIGRATIONS[5], "FleetOccurrence", "fleet_occurrences"),
        (FLEET_CHECKLIST_MIGRATIONS[6], "VehicleOperationalBlock", "vehicle_operational_blocks"),
        (FLEET_CHECKLIST_MIGRATIONS[7], "FleetVehicleAssignment", "fleet_vehicle_assignments"),
        (FLEET_CHECKLIST_MIGRATIONS[8], "FleetDriverAuthorization", "fleet_driver_authorizations"),
    )
    existing_tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    for migration_id, entity, table in table_map:
        if table not in existing_tables:
            raise RuntimeError(f"A tabela obrigatoria {table} nao foi criada pelo schema.")
        _record_schema_migration(
            connection,
            migration_id,
            {
                "module": "fleet",
                "phase": 3,
                "entity": entity,
                "table": table,
                "strategy": "additive_create_table",
            },
        )


def apply_fleet_fines_schema(connection: sqlite3.Connection) -> None:
    entities = (
        "FleetTrafficInfraction", "FleetInfractionDeadline", "FleetInfractionDriverIdentification",
        "FleetInfractionDocumentTemplate", "FleetInfractionDocumentTemplateItem", "FleetInfractionDocument",
        "FleetInfractionProceeding", "FleetInfractionProtocol", "FleetInfractionPayment",
        "FleetInfractionAttachment", "FleetInfractionDecision", "FleetInfractionAuditLog",
    )
    tables = (
        "fleet_traffic_infractions", "fleet_infraction_deadlines", "fleet_infraction_driver_identifications",
        "fleet_infraction_document_templates", "fleet_infraction_document_template_items", "fleet_infraction_documents",
        "fleet_infraction_proceedings", "fleet_infraction_protocols", "fleet_infraction_payments",
        "fleet_infraction_attachments", "fleet_infraction_decisions", "fleet_infraction_audit_logs",
    )
    existing = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    for migration_id, entity, table in zip(FLEET_FINES_MIGRATIONS, entities, tables):
        if table not in existing:
            raise RuntimeError(f"A tabela obrigatoria {table} nao foi criada pelo schema.")
        _record_schema_migration(connection, migration_id, {
            "module": "fleet_fines", "entity": entity, "table": table,
            "strategy": "additive_create_table", "rollback": "restore_pre_migration_snapshot",
        })


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
        connection: sqlite3.Connection | None = None,
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
        self._upsert(table, id_column, columns, connection=connection)

    def upsert_json_record(
        self,
        *,
        entity: str,
        record_id: str,
        record_label: str,
        source_file: str,
        payload: dict,
        migrated_at: str,
        connection: sqlite3.Connection | None = None,
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
        self._upsert("json_records", "entity, record_id", columns, connection=connection)

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

    def _upsert(
        self,
        table: str,
        conflict_target: str,
        columns: dict[str, Any],
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
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
        values = [columns[column] for column in column_names]
        if connection is not None:
            connection.execute(sql, values)
            return
        with connect(self.db_path) as managed_connection:
            managed_connection.execute(sql, values)
