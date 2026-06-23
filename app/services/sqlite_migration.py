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
        "indexed": {
            "id": "id",
            "plate": "plate",
            "plate_normalized": "plate_normalized",
            "renavam": "renavam",
            "renavam_normalized": "renavam_normalized",
            "chassis": "chassis",
            "chassis_normalized": "chassis_normalized",
            "brand": "brand",
            "model": "model",
            "version": "version",
            "manufacture_year": "manufacture_year",
            "model_year": "model_year",
            "vehicle_type": "vehicle_type",
            "fuel_type": "fuel_type",
            "current_mileage": "current_mileage",
            "legal_owner_company": "legal_owner_company",
            "operating_company": "operating_company",
            "cost_center": "cost_center",
            "acquisition_date": "acquisition_date",
            "acquisition_value": "acquisition_value",
            "usual_driver_id": "usual_driver_id",
            "status": "status",
            "tracker_installed": "tracker_installed",
            "camera_installed": "camera_installed",
            "notes": "notes",
            "created_at": "created_at",
            "updated_at": "updated_at",
            "deleted_at": "deleted_at",
        },
    },
    "fleet_documents.json": {
        "entity": "documentos_frota",
        "table": "fleet_documents",
        "id_fields": ("id", "document_id"),
        "label_fields": ("document_type_label", "document_type", "number"),
        "indexed": {
            "id": "id",
            "vehicle_id": "vehicle_id",
            "document_type": "document_type",
            "number": "document_number",
            "issued_at": "issued_at",
            "expires_at": "expires_at",
            "issue_date": "issue_date",
            "expiration_date": "expiration_date",
            "file_path": "file_path",
            "status": "status",
            "responsible": "responsible",
            "responsible_user_id": "responsible_user_id",
            "notes": "notes",
            "created_at": "created_at",
            "updated_at": "updated_at",
            "deleted_at": "deleted_at",
        },
    },
    "fleet_service_orders.json": {
        "entity": "ordens_servico_frota",
        "table": "fleet_service_orders",
        "id_fields": ("id",),
        "label_fields": ("order_number", "reported_problem"),
        "indexed": {
            "vehicle_id": "vehicle_id",
            "order_number": "order_number",
            "maintenance_type": "maintenance_type",
            "maintenance_plan_id": "maintenance_plan_id",
            "status": "status",
            "priority": "priority",
            "reported_problem": "reported_problem",
            "diagnosis": "diagnosis",
            "services_performed": "services_performed",
            "opening_date": "opening_date",
            "expected_completion_date": "expected_completion_date",
            "completion_date": "completion_date",
            "entry_mileage": "entry_mileage",
            "exit_mileage": "exit_mileage",
            "supplier_id": "supplier_id",
            "supplier_name": "supplier_name",
            "internal_responsible_user_id": "internal_responsible_user_id",
            "driver_id": "driver_id",
            "labor_cost": "labor_cost",
            "parts_cost": "parts_cost",
            "additional_cost": "additional_cost",
            "discount": "discount",
            "total_cost": "total_cost",
            "total_override_justification": "total_override_justification",
            "downtime_hours": "downtime_hours",
            "warranty_expiration_date": "warranty_expiration_date",
            "next_service_date": "next_service_date",
            "next_service_mileage": "next_service_mileage",
            "notes": "notes",
            "created_by": "created_by",
            "created_at": "created_at",
            "updated_at": "updated_at",
            "deleted_at": "deleted_at",
        },
    },
    "fleet_service_order_items.json": {
        "entity": "itens_ordens_servico_frota",
        "table": "fleet_service_order_items",
        "id_fields": ("id",),
        "label_fields": ("description", "id"),
        "indexed": {
            "service_order_id": "service_order_id",
            "item_type": "item_type",
            "description": "description",
            "quantity": "quantity",
            "unit": "unit",
            "unit_cost": "unit_cost",
            "total_cost": "total_cost",
            "inventory_item_id": "inventory_item_id",
            "supplier_id": "supplier_id",
            "warranty_days": "warranty_days",
            "notes": "notes",
            "created_at": "created_at",
            "updated_at": "updated_at",
            "deleted_at": "deleted_at",
        },
    },
    "vehicle_maintenance_plans.json": {
        "entity": "planos_manutencao_veiculos",
        "table": "vehicle_maintenance_plans",
        "id_fields": ("id",),
        "label_fields": ("title", "category"),
        "indexed": {
            "vehicle_id": "vehicle_id",
            "title": "title",
            "category": "category",
            "description": "description",
            "interval_mileage": "interval_mileage",
            "interval_days": "interval_days",
            "warning_mileage": "warning_mileage",
            "warning_days": "warning_days",
            "last_service_date": "last_service_date",
            "last_service_mileage": "last_service_mileage",
            "next_service_date": "next_service_date",
            "next_service_mileage": "next_service_mileage",
            "priority": "priority",
            "is_active": "is_active",
            "instructions": "instructions",
            "created_at": "created_at",
            "updated_at": "updated_at",
            "deleted_at": "deleted_at",
        },
    },
    "fleet_maintenance_attachments.json": {
        "entity": "anexos_manutencao_frota",
        "table": "fleet_maintenance_attachments",
        "id_fields": ("id",),
        "label_fields": ("original_name", "attachment_type"),
        "indexed": {
            "service_order_id": "service_order_id",
            "vehicle_id": "vehicle_id",
            "attachment_type": "attachment_type",
            "original_name": "original_name",
            "file_path": "file_path",
            "content_type": "content_type",
            "size_bytes": "size_bytes",
            "notes": "notes",
            "uploaded_by": "uploaded_by",
            "created_at": "created_at",
            "deleted_at": "deleted_at",
        },
    },
    "fleet_inventory_reservations.json": {
        "entity": "reservas_estoque_frota",
        "table": "fleet_inventory_reservations",
        "id_fields": ("id",),
        "label_fields": ("inventory_item_id", "id"),
        "indexed": {
            "service_order_id": "service_order_id",
            "service_order_item_id": "service_order_item_id",
            "inventory_item_id": "inventory_item_id",
            "quantity": "quantity",
            "status": "status",
            "reserved_by": "reserved_by",
            "reserved_at": "reserved_at",
            "consumed_by": "consumed_by",
            "consumed_at": "consumed_at",
            "released_by": "released_by",
            "released_at": "released_at",
            "warehouse_movement_id": "warehouse_movement_id",
            "created_at": "created_at",
            "updated_at": "updated_at",
        },
    },
    "fleet_checklist_templates.json": {
        "entity": "modelos_checklist_frota", "table": "fleet_checklist_templates", "id_fields": ("id",), "label_fields": ("name", "id"),
        "indexed": {"logical_id": "logical_id", "name": "name", "description": "description", "checklist_type": "checklist_type", "vehicle_type": "vehicle_type", "is_active": "is_active", "version": "version", "supersedes_template_id": "supersedes_template_id", "created_by": "created_by", "created_at": "created_at", "updated_at": "updated_at", "deleted_at": "deleted_at"},
    },
    "fleet_checklist_template_items.json": {
        "entity": "itens_modelos_checklist_frota", "table": "fleet_checklist_template_items", "id_fields": ("id",), "label_fields": ("title", "id"),
        "indexed": {"template_id": "template_id", "category": "category", "title": "title", "description": "description", "display_order": "display_order", "response_type": "response_type", "selection_options_json": "selection_options_json", "is_required": "is_required", "is_critical": "is_critical", "requires_photo": "requires_photo", "requires_note_on_failure": "requires_note_on_failure", "creates_occurrence_on_failure": "creates_occurrence_on_failure", "blocks_vehicle_on_failure": "blocks_vehicle_on_failure", "created_at": "created_at", "updated_at": "updated_at", "deleted_at": "deleted_at"},
    },
    "fleet_checklists.json": {
        "entity": "checklists_frota", "table": "fleet_checklists", "id_fields": ("id",), "label_fields": ("id", "checklist_type"),
        "indexed": {"template_id": "template_id", "template_version": "template_version", "checklist_type": "checklist_type", "vehicle_id": "vehicle_id", "driver_id": "driver_id", "route_id": "route_id", "operation_id": "operation_id", "service_order_id": "service_order_id", "status": "status", "started_at": "started_at", "completed_at": "completed_at", "start_mileage": "start_mileage", "end_mileage": "end_mileage", "distance_travelled": "distance_travelled", "fuel_level": "fuel_level", "general_status": "general_status", "location_text": "location_text", "latitude": "latitude", "longitude": "longitude", "responsible_user_id": "responsible_user_id", "signature_name": "signature_name", "confirmation_hash": "confirmation_hash", "notes": "notes", "created_at": "created_at", "updated_at": "updated_at", "deleted_at": "deleted_at"},
    },
    "fleet_checklist_responses.json": {
        "entity": "respostas_checklists_frota", "table": "fleet_checklist_responses", "id_fields": ("id",), "label_fields": ("item_title_snapshot", "id"),
        "indexed": {"checklist_id": "checklist_id", "template_item_id": "template_item_id", "item_title_snapshot": "item_title_snapshot", "category_snapshot": "category_snapshot", "response_value": "response_value", "response_status": "response_status", "note": "note", "is_critical_snapshot": "is_critical_snapshot", "created_at": "created_at", "updated_at": "updated_at", "deleted_at": "deleted_at"},
    },
    "fleet_checklist_evidence.json": {
        "entity": "evidencias_checklists_frota", "table": "fleet_checklist_evidence", "id_fields": ("id",), "label_fields": ("original_name", "evidence_type"),
        "indexed": {"checklist_id": "checklist_id", "response_id": "response_id", "template_item_id": "template_item_id", "evidence_type": "evidence_type", "original_name": "original_name", "file_path": "file_path", "content_type": "content_type", "size_bytes": "size_bytes", "sha256": "sha256", "uploaded_by": "uploaded_by", "created_at": "created_at", "deleted_at": "deleted_at"},
    },
    "fleet_occurrences.json": {
        "entity": "ocorrencias_frota", "table": "fleet_occurrences", "id_fields": ("id",), "label_fields": ("occurrence_number", "title"),
        "indexed": {"occurrence_number": "occurrence_number", "vehicle_id": "vehicle_id", "driver_id": "driver_id", "route_id": "route_id", "operation_id": "operation_id", "checklist_id": "checklist_id", "service_order_id": "service_order_id", "occurrence_type": "occurrence_type", "severity": "severity", "status": "status", "title": "title", "description": "description", "occurrence_date": "occurrence_date", "reported_at": "reported_at", "location": "location", "responsible_user_id": "responsible_user_id", "assigned_user_id": "assigned_user_id", "resolution": "resolution", "resolved_at": "resolved_at", "resolved_by": "resolved_by", "created_at": "created_at", "updated_at": "updated_at", "deleted_at": "deleted_at"},
    },
    "vehicle_operational_blocks.json": {
        "entity": "bloqueios_operacionais_veiculos", "table": "vehicle_operational_blocks", "id_fields": ("id",), "label_fields": ("reason", "id"),
        "indexed": {"vehicle_id": "vehicle_id", "occurrence_id": "occurrence_id", "checklist_id": "checklist_id", "service_order_id": "service_order_id", "block_type": "block_type", "reason": "reason", "severity": "severity", "blocked_at": "blocked_at", "blocked_by": "blocked_by", "status": "status", "released_at": "released_at", "released_by": "released_by", "release_reason": "release_reason", "resolution_confirmed": "resolution_confirmed", "created_at": "created_at", "updated_at": "updated_at", "deleted_at": "deleted_at"},
    },
    "fleet_vehicle_assignments.json": {
        "entity": "entregas_veiculos_frota", "table": "fleet_vehicle_assignments", "id_fields": ("id",), "label_fields": ("vehicle_id", "driver_id"),
        "indexed": {"vehicle_id": "vehicle_id", "driver_id": "driver_id", "route_id": "route_id", "operation_id": "operation_id", "departure_checklist_id": "departure_checklist_id", "return_checklist_id": "return_checklist_id", "delivered_by": "delivered_by", "received_by_driver": "received_by_driver", "delivered_at": "delivered_at", "expected_return_at": "expected_return_at", "returned_at": "returned_at", "returned_by_driver": "returned_by_driver", "received_return_by": "received_return_by", "start_mileage": "start_mileage", "end_mileage": "end_mileage", "start_fuel_level": "start_fuel_level", "end_fuel_level": "end_fuel_level", "status": "status", "override_justification": "override_justification", "created_at": "created_at", "updated_at": "updated_at", "deleted_at": "deleted_at"},
    },
    "fleet_driver_authorizations.json": {
        "entity": "autorizacoes_motoristas_frota", "table": "fleet_driver_authorizations", "id_fields": ("id",), "label_fields": ("user_id", "employee_id"),
        "indexed": {"user_id": "user_id", "employee_id": "employee_id", "authorized_vehicle_ids_json": "authorized_vehicle_ids_json", "authorized_vehicle_types_json": "authorized_vehicle_types_json", "is_usual_driver": "is_usual_driver", "status": "status", "created_by": "created_by", "created_at": "created_at", "updated_at": "updated_at", "deleted_at": "deleted_at"},
    },
    "fleet_traffic_infractions.json": {
        "entity": "multas_frota", "table": "fleet_traffic_infractions", "id_fields": ("id",), "label_fields": ("internal_number", "infraction_notice_number"),
        "indexed": {"internal_number": "internal_number", "vehicle_id": "vehicle_id", "driver_id": "driver_id", "route_id": "route_id", "operation_id": "operation_id", "issuing_authority": "issuing_authority", "infraction_notice_number": "infraction_notice_number", "infraction_date": "infraction_date", "vehicle_plate_snapshot": "vehicle_plate_snapshot", "notification_type": "notification_type", "status": "status", "decision_status": "decision_status", "payment_status": "payment_status", "driver_identification_status": "driver_identification_status", "nic_risk_status": "nic_risk_status", "assigned_to": "assigned_to", "original_infraction_id": "original_infraction_id", "created_at": "created_at", "updated_at": "updated_at", "deleted_at": "deleted_at"},
    },
    "fleet_infraction_deadlines.json": {
        "entity": "prazos_multas_frota", "table": "fleet_infraction_deadlines", "id_fields": ("id",), "label_fields": ("deadline_type", "id"),
        "indexed": {"infraction_id": "infraction_id", "deadline_type": "deadline_type", "official_deadline": "official_deadline", "internal_deadline": "internal_deadline", "status": "status", "responsible_user_id": "responsible_user_id", "completed_at": "completed_at", "deleted_at": "deleted_at"},
    },
    "fleet_infraction_driver_identifications.json": {
        "entity": "identificacoes_condutor_multas", "table": "fleet_infraction_driver_identifications", "id_fields": ("id",), "label_fields": ("confirmed_driver_id", "suggested_driver_id"),
        "indexed": {"infraction_id": "infraction_id", "suggested_driver_id": "suggested_driver_id", "confirmed_driver_id": "confirmed_driver_id", "confidence": "confidence", "status": "status", "confirmed_by": "confirmed_by", "confirmed_at": "confirmed_at", "deleted_at": "deleted_at"},
    },
    "fleet_infraction_document_templates.json": {
        "entity": "modelos_documentos_multas", "table": "fleet_infraction_document_templates", "id_fields": ("id",), "label_fields": ("name", "issuing_authority"),
        "indexed": {"issuing_authority": "issuing_authority", "name": "name", "is_active": "is_active", "deleted_at": "deleted_at"},
    },
    "fleet_infraction_document_template_items.json": {
        "entity": "itens_modelos_documentos_multas", "table": "fleet_infraction_document_template_items", "id_fields": ("id",), "label_fields": ("document_type", "id"),
        "indexed": {"template_id": "template_id", "document_type": "document_type", "is_required": "is_required", "display_order": "display_order", "deleted_at": "deleted_at"},
    },
    "fleet_infraction_documents.json": {
        "entity": "documentos_multas_frota", "table": "fleet_infraction_documents", "id_fields": ("id",), "label_fields": ("document_type", "id"),
        "indexed": {"infraction_id": "infraction_id", "document_type": "document_type", "status": "status", "file_path": "file_path", "is_sensitive": "is_sensitive", "deleted_at": "deleted_at"},
    },
    "fleet_infraction_proceedings.json": {
        "entity": "processos_multas_frota", "table": "fleet_infraction_proceedings", "id_fields": ("id",), "label_fields": ("proceeding_type", "id"),
        "indexed": {"infraction_id": "infraction_id", "proceeding_type": "proceeding_type", "status": "status", "responsible_user_id": "responsible_user_id", "official_deadline": "official_deadline", "internal_deadline": "internal_deadline", "protocol_number": "protocol_number", "deleted_at": "deleted_at"},
    },
    "fleet_infraction_protocols.json": {
        "entity": "protocolos_multas_frota", "table": "fleet_infraction_protocols", "id_fields": ("id",), "label_fields": ("protocol_number", "protocol_channel"),
        "indexed": {"infraction_id": "infraction_id", "proceeding_id": "proceeding_id", "protocol_number": "protocol_number", "protocol_date": "protocol_date", "protocol_channel": "protocol_channel", "proof_path": "proof_path", "deleted_at": "deleted_at"},
    },
    "fleet_infraction_payments.json": {
        "entity": "pagamentos_multas_frota", "table": "fleet_infraction_payments", "id_fields": ("id",), "label_fields": ("infraction_id", "id"),
        "indexed": {"infraction_id": "infraction_id", "financial_entry_id": "financial_entry_id", "due_date": "due_date", "paid_amount": "paid_amount", "payment_date": "payment_date", "status": "status", "receipt_path": "receipt_path", "deleted_at": "deleted_at"},
    },
    "fleet_infraction_attachments.json": {
        "entity": "anexos_multas_frota", "table": "fleet_infraction_attachments", "id_fields": ("id",), "label_fields": ("original_name", "category"),
        "indexed": {"infraction_id": "infraction_id", "proceeding_id": "proceeding_id", "category": "category", "file_path": "file_path", "sha256": "sha256", "is_sensitive": "is_sensitive", "deleted_at": "deleted_at"},
    },
    "fleet_infraction_decisions.json": {
        "entity": "decisoes_multas_frota", "table": "fleet_infraction_decisions", "id_fields": ("id",), "label_fields": ("decision", "id"),
        "indexed": {"infraction_id": "infraction_id", "decision": "decision", "responsible_user_id": "responsible_user_id", "decided_at": "decided_at", "deleted_at": "deleted_at"},
    },
    "fleet_infraction_audit_logs.json": {
        "entity": "auditoria_multas_frota", "table": "fleet_infraction_audit_logs", "id_fields": ("id",), "label_fields": ("action", "id"),
        "indexed": {"infraction_id": "infraction_id", "user_id": "user_id", "action": "action", "justification": "justification", "created_at": "created_at"},
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
        if target_column in {
            "amount", "amount_received", "revenue_total", "expense_total", "profit_total",
            "acquisition_value", "labor_cost", "parts_cost", "additional_cost", "discount",
            "total_cost", "downtime_hours", "quantity", "unit_cost", "latitude", "longitude",
        }:
            value = numeric_value(value)
            if value is None and target_column in {"acquisition_value", "labor_cost", "parts_cost", "additional_cost", "discount", "total_cost", "downtime_hours", "unit_cost"}:
                value = 0.0
        elif target_column in {
            "manufacture_year", "model_year", "current_mileage", "entry_mileage", "exit_mileage",
            "next_service_mileage", "interval_mileage", "interval_days", "warning_mileage",
            "warning_days", "last_service_mileage", "warranty_days", "size_bytes", "version",
            "display_order", "template_version", "start_mileage", "end_mileage", "distance_travelled",
        }:
            numeric = numeric_value(value)
            value = int(numeric) if numeric is not None else (0 if target_column in {"current_mileage", "warranty_days", "size_bytes"} else None)
        elif target_column in {
            "tracker_installed", "camera_installed", "is_active", "is_required", "is_critical",
            "requires_photo", "requires_note_on_failure", "creates_occurrence_on_failure",
            "blocks_vehicle_on_failure", "is_critical_snapshot", "resolution_confirmed", "is_usual_driver",
        }:
            value = int(str(value if value is not None else "").strip().lower() in {"1", "true", "yes", "sim", "on"})
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
