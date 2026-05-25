from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.repositories.sqlite_repository import SQLiteRepository, initialize_database


LIST_SOURCES = {
    "clients.json": {
        "entity": "clientes",
        "table": "clients",
        "id_fields": ("client_id", "id"),
        "label_fields": ("customer_name", "nome"),
        "indexed": {"customer_name": "customer_name", "phone": "phone"},
    },
    "events.json": {
        "entity": "eventos",
        "table": "events",
        "id_fields": ("event_id", "id"),
        "label_fields": ("title", "event_title"),
        "indexed": {"title": "title", "event_date": "event_date", "status": "status"},
    },
    "equipment.json": {
        "entity": "equipamentos",
        "table": "equipment",
        "id_fields": ("equipment_id", "id"),
        "label_fields": ("equipment_type", "name"),
        "indexed": {"equipment_type": "equipment_type", "status": "status"},
    },
    "vehicles.json": {
        "entity": "veiculos",
        "table": "vehicles",
        "id_fields": ("vehicle_id", "id"),
        "label_fields": ("plate", "vehicle_id"),
        "indexed": {"plate": "plate", "vehicle_type": "vehicle_type"},
    },
    "users.json": {
        "entity": "usuarios",
        "table": "users",
        "id_fields": ("id", "user_id", "email"),
        "label_fields": ("nome", "email"),
        "indexed": {"email": "email", "nome": "nome", "role": "role", "status": "status"},
    },
    "audit_log.json": {
        "entity": "auditoria",
        "table": "audit_log",
        "id_fields": ("id",),
        "label_fields": ("detail", "action"),
        "indexed": {"created_at": "created_at", "user_email": "user_email", "action": "action", "module": "module", "target_id": "target_id"},
    },
    "financial_receivables.json": {
        "entity": "financeiro_recebimentos",
        "table": "financial_receivables",
        "id_fields": ("id", "receivable_id"),
        "label_fields": ("client_name", "event_title"),
        "indexed": {
            "client_id": "client_id",
            "client_name": "client_name",
            "event_id": "event_id",
            "amount": "amount",
            "amount_received": "amount_received",
            "due_date": "due_date",
            "status": "status",
        },
    },
    "financial_entries.json": {
        "entity": "financeiro_lancamentos",
        "table": "financial_entries",
        "id_fields": ("id", "entry_id"),
        "label_fields": ("description", "category"),
        "indexed": {"entry_type": "entry_type", "category": "category", "amount": "amount", "entry_date": "entry_date"},
    },
    "financial_closeouts.json": {
        "entity": "financeiro_fechamentos",
        "table": "financial_closeouts",
        "id_fields": ("id", "period"),
        "label_fields": ("period",),
        "indexed": {"period": "period", "revenue_total": "revenue_total", "expense_total": "expense_total", "profit_total": "profit_total"},
    },
}

GENERIC_LIST_SOURCES = {
    "contracts.json": "contratos",
    "quotes.json": "orcamentos",
    "service_log.json": "servicos_registrados",
    "attachments.json": "anexos",
    "route_history.json": "historico_rotas",
    "warehouse_items.json": "almoxarifado_itens",
    "warehouse_movements.json": "almoxarifado_movimentos",
    "field_confirmations.json": "confirmacoes_operacionais",
    "help_knowledge_base.json": "base_ajuda",
    "help_unanswered_questions.json": "duvidas_sem_resposta",
    "help_support_tickets.json": "chamados_suporte",
}

DOCUMENT_SOURCES = {
    "settings.json": "configuracoes",
    "operation_validation.json": "validacao_operacional",
    "forecast_audit.json": "auditoria_previsao",
    "help_metrics.json": "metricas_ajuda",
}

ALL_JSON_SOURCES = set(LIST_SOURCES) | set(GENERIC_LIST_SOURCES) | set(DOCUMENT_SOURCES)


@dataclass
class MigrationOptions:
    data_dir: Path
    db_path: Path
    report_path: Path | None = None
    dry_run: bool = False
    include_backups: bool = True


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_json_file(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def clean_text(value) -> str:
    return str(value or "").strip()


def first_value(record: dict, fields: tuple[str, ...]) -> str:
    for field in fields:
        text = clean_text(record.get(field))
        if text:
            return text
    return ""


def synthetic_id(source_name: str, index: int) -> str:
    return f"{Path(source_name).stem}:{index + 1}"


def numeric_value(value) -> float | None:
    if value in ("", None):
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def indexed_values(record: dict, mapping: dict[str, str]) -> dict:
    values = {}
    for source_field, target_column in mapping.items():
        value = record.get(source_field)
        if target_column in {"amount", "amount_received", "revenue_total", "expense_total", "profit_total"}:
            value = numeric_value(value)
        else:
            value = clean_text(value)
        values[target_column] = value
    return values


def record_label(record: dict, fields: tuple[str, ...]) -> str:
    return first_value(record, fields) or first_value(record, ("id", "client_id", "event_id", "equipment_id", "vehicle_id", "email"))


def add_report_item(report: dict, *, entity: str, source_file: str, record_id: str | None, status: str, message: str) -> None:
    report["items"].append(
        {
            "entity": entity,
            "source_file": source_file,
            "record_id": record_id,
            "status": status,
            "message": message,
        }
    )
    if status == "importado":
        report["summary"]["imported"] += 1
    elif status == "ignorado":
        report["summary"]["ignored"] += 1
    else:
        report["summary"]["errors"] += 1


def migrate_core_list(repository: SQLiteRepository, report: dict, source_path: Path, config: dict, records: list, migrated_at: str, dry_run: bool) -> None:
    entity = config["entity"]
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            add_report_item(report, entity=entity, source_file=source_path.name, record_id=None, status="ignorado", message=f"Item {index + 1} não é objeto JSON.")
            continue
        record_id = first_value(record, config["id_fields"]) or synthetic_id(source_path.name, index)
        message = "Importado."
        if record_id.startswith(f"{source_path.stem}:"):
            message = "Importado com ID sintético; revisar chave antes de ativar escrita SQLite."
        if not dry_run:
            repository.upsert_core_record(
                config["table"],
                record_id,
                indexed_values(record, config["indexed"]),
                record,
                source_file=source_path.name,
                migrated_at=migrated_at,
            )
        add_report_item(report, entity=entity, source_file=source_path.name, record_id=record_id, status="importado", message=message)


def migrate_generic_list(repository: SQLiteRepository, report: dict, source_path: Path, entity: str, records: list, migrated_at: str, dry_run: bool) -> None:
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            add_report_item(report, entity=entity, source_file=source_path.name, record_id=None, status="ignorado", message=f"Item {index + 1} não é objeto JSON.")
            continue
        record_id = first_value(record, ("id", "client_id", "event_id", "equipment_id", "vehicle_id", "created_at")) or synthetic_id(source_path.name, index)
        if not dry_run:
            repository.upsert_json_record(
                entity=entity,
                record_id=record_id,
                record_label=record_label(record, ("title", "name", "customer_name", "client_name", "description")),
                source_file=source_path.name,
                payload=record,
                migrated_at=migrated_at,
            )
        add_report_item(report, entity=entity, source_file=source_path.name, record_id=record_id, status="importado", message="Importado.")


def migrate_document(repository: SQLiteRepository, report: dict, source_path: Path, entity: str, payload: dict, migrated_at: str, dry_run: bool) -> None:
    if not dry_run:
        repository.upsert_json_document(entity=entity, source_file=source_path.name, payload=payload, migrated_at=migrated_at)
    add_report_item(report, entity=entity, source_file=source_path.name, record_id=entity, status="importado", message="Documento importado.")


def migrate_backup_files(repository: SQLiteRepository, report: dict, data_dir: Path, migrated_at: str, dry_run: bool) -> None:
    backups_dir = data_dir.parent / "backups"
    if not backups_dir.exists():
        add_report_item(report, entity="backups", source_file="backups/", record_id=None, status="ignorado", message="Pasta de backups não existe.")
        return
    backup_files = sorted(backups_dir.glob("sannygold-data-backup-*.zip"))
    if not backup_files:
        add_report_item(report, entity="backups", source_file="backups/", record_id=None, status="ignorado", message="Nenhum backup encontrado.")
        return
    for backup in backup_files:
        stat = backup.stat()
        payload = {"filename": backup.name, "path": str(backup), "size_bytes": stat.st_size}
        if not dry_run:
            repository.upsert_backup_file(
                filename=backup.name,
                path=str(backup),
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                payload=payload,
                migrated_at=migrated_at,
            )
        add_report_item(report, entity="backups", source_file="backups/", record_id=backup.name, status="importado", message="Metadados do backup importados.")


def migrate_json_to_sqlite(options: MigrationOptions) -> dict:
    data_dir = options.data_dir
    db_path = options.db_path
    migrated_at = now_iso()
    run_id = f"MIG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    report = {
        "run_id": run_id,
        "started_at": migrated_at,
        "finished_at": "",
        "data_dir": str(data_dir),
        "db_path": str(db_path),
        "dry_run": options.dry_run,
        "summary": {"imported": 0, "ignored": 0, "errors": 0},
        "sources": [],
        "items": [],
    }
    repository = SQLiteRepository(db_path)
    if not options.dry_run:
        initialize_database(db_path)

    for source_name in sorted(ALL_JSON_SOURCES):
        source_path = data_dir / source_name
        source_report = {"file": source_name, "exists": source_path.exists(), "type": "", "entity": ""}
        report["sources"].append(source_report)
        if not source_path.exists():
            add_report_item(report, entity=source_path.stem, source_file=source_name, record_id=None, status="ignorado", message="Arquivo ausente.")
            continue
        try:
            payload = load_json_file(source_path)
        except Exception as exc:  # noqa: BLE001
            add_report_item(report, entity=source_path.stem, source_file=source_name, record_id=None, status="erro", message=f"JSON inválido: {exc}")
            continue
        source_report["type"] = type(payload).__name__
        if source_name in LIST_SOURCES:
            config = LIST_SOURCES[source_name]
            source_report["entity"] = config["entity"]
            if not isinstance(payload, list):
                add_report_item(report, entity=config["entity"], source_file=source_name, record_id=None, status="erro", message="Esperado array/lista JSON.")
                continue
            migrate_core_list(repository, report, source_path, config, payload, migrated_at, options.dry_run)
        elif source_name in GENERIC_LIST_SOURCES:
            entity = GENERIC_LIST_SOURCES[source_name]
            source_report["entity"] = entity
            if not isinstance(payload, list):
                add_report_item(report, entity=entity, source_file=source_name, record_id=None, status="erro", message="Esperado array/lista JSON.")
                continue
            migrate_generic_list(repository, report, source_path, entity, payload, migrated_at, options.dry_run)
        else:
            entity = DOCUMENT_SOURCES[source_name]
            source_report["entity"] = entity
            if not isinstance(payload, dict):
                add_report_item(report, entity=entity, source_file=source_name, record_id=None, status="erro", message="Esperado objeto/dicionário JSON.")
                continue
            migrate_document(repository, report, source_path, entity, payload, migrated_at, options.dry_run)

    if options.include_backups:
        migrate_backup_files(repository, report, data_dir, migrated_at, options.dry_run)

    report["finished_at"] = now_iso()
    status = "ok" if report["summary"]["errors"] == 0 else "com_erros"
    if not options.dry_run:
        run_payload = {
            "id": run_id,
            "started_at": migrated_at,
            "finished_at": report["finished_at"],
            "source_data_dir": str(data_dir),
            "database_path": str(db_path),
            "status": status,
            "imported_count": report["summary"]["imported"],
            "ignored_count": report["summary"]["ignored"],
            "error_count": report["summary"]["errors"],
            "report": report,
        }
        repository.record_migration_run(run_payload)
        for item in report["items"]:
            repository.record_migration_item(run_id, item)
    if options.report_path:
        options.report_path.parent.mkdir(parents=True, exist_ok=True)
        options.report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report
