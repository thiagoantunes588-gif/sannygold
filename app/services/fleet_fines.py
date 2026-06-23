from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Mapping, Sequence


NOTIFICATION_TYPES = {
    "autuacao": "Notificação de autuação", "penalidade": "Notificação de penalidade",
    "nic": "Multa NIC", "resultado": "Comunicação de resultado", "cobranca": "Cobrança", "outra": "Outra",
}
JURISDICTIONS = {
    "municipal": "Municipal", "estadual": "Estadual", "federal": "Federal", "detran": "Detran",
    "der": "DER", "dnit": "DNIT", "prf": "PRF", "delegado": "Concessionária ou órgão delegado", "outro": "Outro",
}
INFRACTION_STATUSES = {
    "recebida": "Recebida", "em_conferencia": "Em conferência",
    "aguardando_identificacao": "Aguardando identificação do motorista", "aguardando_documentos": "Aguardando documentos",
    "aguardando_decisao": "Aguardando decisão", "indicacao_em_preparacao": "Indicação em preparação",
    "indicacao_protocolada": "Indicação protocolada", "defesa_em_preparacao": "Defesa em preparação",
    "defesa_protocolada": "Defesa protocolada", "jari_em_preparacao": "Recurso JARI em preparação",
    "jari_protocolado": "Recurso JARI protocolado", "segunda_instancia": "Recurso em segunda instância",
    "aguardando_julgamento": "Aguardando julgamento", "deferida": "Deferida", "indeferida": "Indeferida",
    "aguardando_pagamento": "Aguardando pagamento", "paga": "Paga", "cancelada": "Cancelada",
    "encerrada": "Encerrada", "prazo_perdido": "Prazo perdido",
}
IDENTIFICATION_STATUSES = {
    "nao_analisada": "Não analisada", "motorista_sugerido": "Motorista sugerido",
    "aguardando_confirmacao": "Aguardando confirmação", "confirmado_internamente": "Confirmado internamente",
    "documentos_pendentes": "Documentos pendentes", "assinatura_pendente": "Assinatura pendente",
    "pronto_protocolo": "Pronto para protocolo", "protocolado": "Protocolado", "aceito": "Aceito pelo órgão",
    "recusado": "Recusado pelo órgão", "nao_identificado": "Não identificado", "prazo_perdido": "Prazo perdido",
    "nao_aplicavel": "Não aplicável",
}
NIC_STATUSES = {
    "nao_aplicavel": "Não aplicável", "sem_risco": "Sem risco", "atencao": "Em atenção", "alto_risco": "Alto risco",
    "prazo_vencido": "Prazo vencido", "nic_recebida": "NIC recebida", "nic_paga": "NIC paga",
    "nic_contestada": "NIC contestada", "encerrada": "Encerrada",
}
DEADLINE_TYPES = {
    "driver_identification": "Indicação do condutor", "preliminary_defense": "Defesa prévia", "payment": "Pagamento",
    "first_appeal": "Recurso em primeira instância", "second_appeal": "Recurso em segunda instância",
    "signature": "Coleta de assinatura", "management_approval": "Aprovação da direção", "protocol": "Protocolo",
}
PROCEEDING_TYPES = {
    "driver_identification": "Indicação de condutor", "preliminary_defense": "Defesa prévia", "jari": "Recurso JARI",
    "second_instance": "Recurso em segunda instância", "suspensive_effect": "Pedido de efeito suspensivo",
    "refund": "Pedido de restituição", "other": "Outro",
}
PROCEEDING_STATUSES = {
    "nao_iniciado": "Não iniciado", "em_preparacao": "Em preparação", "aguardando_documentos": "Aguardando documentos",
    "aguardando_assinatura": "Aguardando assinatura", "aguardando_aprovacao": "Aguardando aprovação",
    "pronto_protocolo": "Pronto para protocolo", "protocolado": "Protocolado", "recebido": "Recebido pelo órgão",
    "em_julgamento": "Em julgamento", "deferido": "Deferido", "indeferido": "Indeferido",
    "arquivado": "Arquivado", "prazo_perdido": "Prazo perdido", "cancelado": "Cancelado",
}
DOCUMENT_STATUSES = {key: label for key, label in (
    ("nao_solicitado", "Não solicitado"), ("pendente", "Pendente"), ("recebido", "Recebido"),
    ("invalido", "Inválido"), ("corrigir", "Corrigir"), ("aprovado", "Aprovado"), ("protocolado", "Protocolado"),
)}
DECISIONS = {
    "identify_pay": "Indicar motorista e pagar", "identify_defend": "Indicar motorista e apresentar defesa",
    "recognize_pay": "Reconhecer infração e pagar", "preliminary_defense": "Apresentar defesa prévia",
    "jari": "Apresentar recurso à JARI", "second_instance": "Apresentar recurso em segunda instância",
    "await_documents": "Aguardar documentação", "no_appeal": "Não recorrer", "pending": "Decisão ainda não tomada",
}
SENSITIVE_DOCUMENT_TYPES = {"cnh_motorista", "cpf", "assinatura_motorista", "assinatura_representante", "documento_pessoal"}
DEFAULT_ALERT_DAYS = [15, 10, 7, 5, 3, 1, 0]


def clean_text(value, fallback: str = "") -> str:
    text = str(value if value is not None else "").strip()
    return text or fallback


def as_float(value, fallback: float = 0.0) -> float:
    try:
        return round(float(str(value or "0").replace(".", "").replace(",", ".") if "," in str(value or "") else str(value or "0")), 2)
    except (TypeError, ValueError):
        return fallback


def as_int(value, fallback: int = 0) -> int:
    try:
        return int(float(str(value or fallback).replace(",", ".")))
    except (TypeError, ValueError):
        return fallback


def as_bool(value) -> bool:
    return clean_text(value).lower() in {"1", "true", "yes", "sim", "on"}


def normalize_plate(value) -> str:
    return re.sub(r"[^A-Z0-9]", "", clean_text(value).upper())


def next_id(records: Sequence[Mapping], prefix: str) -> str:
    numbers = []
    for record in records:
        match = re.search(r"(\d+)$", clean_text(record.get("id")))
        if match:
            numbers.append(int(match.group(1)))
    return f"{prefix}-{max(numbers, default=0) + 1:06d}"


def next_internal_number(records: Sequence[Mapping], when: str) -> str:
    year = int(clean_text(when)[:4] or date.today().year)
    pattern = re.compile(rf"^MULTA-{year}-(\d{{6}})$")
    used = [int(match.group(1)) for item in records if (match := pattern.match(clean_text(item.get("internal_number"))))]
    return f"MULTA-{year}-{max(used, default=0) + 1:06d}"


def natural_key(record: Mapping) -> tuple[str, str, str, str]:
    return (
        clean_text(record.get("issuing_authority")).casefold(),
        re.sub(r"[^A-Z0-9]", "", clean_text(record.get("infraction_notice_number")).upper()),
        normalize_plate(record.get("vehicle_plate_snapshot")), clean_text(record.get("infraction_date"))[:10],
    )


def exact_duplicate(candidate: Mapping, records: Sequence[Mapping]) -> dict | None:
    key = natural_key(candidate)
    return next((item for item in records if not clean_text(item.get("deleted_at")) and clean_text(item.get("id")) != clean_text(candidate.get("id")) and natural_key(item) == key), None)


def possible_duplicate(candidate: Mapping, records: Sequence[Mapping]) -> dict | None:
    authority, notice, plate, _when = natural_key(candidate)
    return next((item for item in records if not clean_text(item.get("deleted_at")) and clean_text(item.get("id")) != clean_text(candidate.get("id"))
                 and natural_key(item)[:3] == (authority, notice, plate)), None)


def build_infraction(form: Mapping, *, records: list[dict], vehicles: list[dict], user_id: str, now: str) -> dict:
    record_id = clean_text(form.get("id"))
    current = next((item for item in records if clean_text(item.get("id")) == record_id), {}) if record_id else {}
    vehicle_id = clean_text(form.get("vehicle_id") or current.get("vehicle_id"))
    vehicle = next((item for item in vehicles if clean_text(item.get("vehicle_id")) == vehicle_id and not clean_text(item.get("deleted_at"))), None)
    if not vehicle:
        raise ValueError("Selecione um veículo cadastrado na Frota.")
    issuing_authority = clean_text(form.get("issuing_authority") or current.get("issuing_authority"))
    notice = clean_text(form.get("infraction_notice_number") or current.get("infraction_notice_number"))
    infraction_date = clean_text(form.get("infraction_date") or current.get("infraction_date"))[:10]
    if not issuing_authority or not notice or not infraction_date:
        raise ValueError("Informe órgão autuador, número do auto e data da infração.")
    notification_type = clean_text(form.get("notification_type") or current.get("notification_type"), "autuacao")
    jurisdiction = clean_text(form.get("jurisdiction_type") or current.get("jurisdiction_type"), "outro")
    if notification_type not in NOTIFICATION_TYPES or jurisdiction not in JURISDICTIONS:
        raise ValueError("Tipo de notificação ou jurisdição inválida.")
    original_infraction_id = clean_text(form.get("original_infraction_id") or current.get("original_infraction_id"))
    if notification_type == "nic" and not original_infraction_id:
        raise ValueError("Uma multa NIC deve estar vinculada à infração original.")
    plate = normalize_plate(vehicle.get("plate"))
    record = {
        **current, "id": record_id or next_id(records, "FINF"),
        "internal_number": clean_text(current.get("internal_number")) or next_internal_number(records, infraction_date),
        "vehicle_id": vehicle_id, "legal_owner_company_id": clean_text(form.get("legal_owner_company_id") or vehicle.get("legal_owner_company")),
        "operating_company_id": clean_text(form.get("operating_company_id") or vehicle.get("operating_company")),
        "driver_id": clean_text(form.get("driver_id") or current.get("driver_id")), "route_id": clean_text(form.get("route_id") or current.get("route_id")),
        "operation_id": clean_text(form.get("operation_id") or current.get("operation_id")), "client_id": clean_text(form.get("client_id") or current.get("client_id")),
        "occurrence_id": clean_text(form.get("occurrence_id") or current.get("occurrence_id")), "issuing_authority": issuing_authority,
        "authority_code": clean_text(form.get("authority_code") or current.get("authority_code")), "jurisdiction_type": jurisdiction,
        "infraction_notice_number": notice, "renainf_number": clean_text(form.get("renainf_number") or current.get("renainf_number")),
        "infraction_code": clean_text(form.get("infraction_code") or current.get("infraction_code")),
        "infraction_description": clean_text(form.get("infraction_description") or current.get("infraction_description")),
        "infraction_date": infraction_date, "infraction_time": clean_text(form.get("infraction_time") or current.get("infraction_time")),
        "location": clean_text(form.get("location") or current.get("location")), "city": clean_text(form.get("city") or current.get("city")),
        "state": clean_text(form.get("state") or current.get("state")).upper()[:2], "vehicle_plate_snapshot": plate,
        "vehicle_renavam_snapshot": clean_text(vehicle.get("renavam")), "notification_type": notification_type,
        "notification_received_date": clean_text(form.get("notification_received_date") or current.get("notification_received_date")),
        "notification_method": clean_text(form.get("notification_method") or current.get("notification_method")),
        "notice_issue_date": clean_text(form.get("notice_issue_date") or current.get("notice_issue_date")),
        "original_amount": as_float(form.get("original_amount") if form.get("original_amount") is not None else current.get("original_amount")),
        "discounted_amount": as_float(form.get("discounted_amount") if form.get("discounted_amount") is not None else current.get("discounted_amount")),
        "final_amount": as_float(form.get("final_amount") if form.get("final_amount") is not None else current.get("final_amount")),
        "points": as_int(form.get("points") if form.get("points") is not None else current.get("points")),
        "severity": clean_text(form.get("severity") or current.get("severity"), "media"),
        "status": clean_text(form.get("status") or current.get("status"), "recebida"),
        "decision_status": clean_text(current.get("decision_status"), "pending"), "payment_status": clean_text(current.get("payment_status"), "pendente"),
        "driver_identification_status": clean_text(current.get("driver_identification_status"), "nao_analisada"),
        "nic_risk_status": clean_text(current.get("nic_risk_status"), "nao_aplicavel"),
        "financial_responsibility": clean_text(form.get("financial_responsibility") or current.get("financial_responsibility"), "em_analise"),
        "company_notes": clean_text(form.get("company_notes") or current.get("company_notes")),
        "confidential_notes": clean_text(form.get("confidential_notes") or current.get("confidential_notes")),
        "created_by": clean_text(current.get("created_by")) or user_id, "assigned_to": clean_text(form.get("assigned_to") or current.get("assigned_to")),
        "original_infraction_id": original_infraction_id, "nic_infraction_id": clean_text(current.get("nic_infraction_id")),
        "nic_amount": as_float(form.get("nic_amount") or current.get("nic_amount")), "nic_notice_date": clean_text(form.get("nic_notice_date") or current.get("nic_notice_date")),
        "nic_payment_deadline": clean_text(form.get("nic_payment_deadline") or current.get("nic_payment_deadline")), "nic_status": clean_text(current.get("nic_status")),
        "driver_identification_required": as_bool(form.get("driver_identification_required") or current.get("driver_identification_required")),
        "released_to_driver_at": clean_text(current.get("released_to_driver_at")), "duplicate_review_status": clean_text(current.get("duplicate_review_status")),
        "duplicate_of_id": clean_text(current.get("duplicate_of_id")), "created_at": clean_text(current.get("created_at")) or now,
        "updated_at": now, "deleted_at": clean_text(current.get("deleted_at")),
    }
    duplicate = exact_duplicate(record, records)
    if duplicate:
        raise ValueError(f"Duplicidade bloqueada: já existe {duplicate.get('internal_number')} para o mesmo órgão, auto, placa e data.")
    duplicate = possible_duplicate(record, records)
    if duplicate:
        if not as_bool(form.get("duplicate_review_confirmed")) or not clean_text(form.get("duplicate_review_notes")):
            raise ValueError(f"Possível duplicidade com {duplicate.get('internal_number')}. Revise e informe a justificativa antes de salvar.")
        record.update({"duplicate_review_status": "revisado", "duplicate_of_id": clean_text(duplicate.get("id")), "duplicate_review_notes": clean_text(form.get("duplicate_review_notes")), "duplicate_reviewed_by": user_id, "duplicate_reviewed_at": now})
    return record


def build_deadlines(form: Mapping, *, infraction_id: str, existing: list[dict], user_id: str, now: str) -> list[dict]:
    output = list(existing)
    for field, deadline_type in (
        ("driver_identification_deadline", "driver_identification"), ("preliminary_defense_deadline", "preliminary_defense"),
        ("payment_deadline", "payment"), ("first_appeal_deadline", "first_appeal"), ("second_appeal_deadline", "second_appeal"),
    ):
        official = clean_text(form.get(field))
        if not official:
            continue
        current = next((item for item in output if clean_text(item.get("infraction_id")) == infraction_id and clean_text(item.get("deadline_type")) == deadline_type and not clean_text(item.get("deleted_at"))), {})
        record = {**current, "id": clean_text(current.get("id")) or next_id(output, "FDL"), "infraction_id": infraction_id,
                  "deadline_type": deadline_type, "official_deadline": official, "internal_deadline": clean_text(form.get(f"{field}_internal")),
                  "source": clean_text(form.get(f"{field}_source"), "notificacao_recebida"), "checked_by": user_id,
                  "checked_at": now, "notes": clean_text(form.get(f"{field}_notes")), "status": clean_text(current.get("status"), "aberto"),
                  "responsible_user_id": clean_text(form.get("assigned_to")), "completed_at": clean_text(current.get("completed_at")),
                  "created_at": clean_text(current.get("created_at")) or now, "updated_at": now, "deleted_at": ""}
        output = [record if clean_text(item.get("id")) == clean_text(record.get("id")) else item for item in output]
        if not current:
            output.append(record)
    return output


def classify_deadline(deadline: Mapping, today: date | None = None) -> dict:
    today = today or date.today()
    raw = clean_text(deadline.get("internal_deadline") or deadline.get("official_deadline"))[:10]
    if clean_text(deadline.get("completed_at")) or clean_text(deadline.get("status")) == "concluido":
        return {"classification": "concluido", "days": None, "priority": 99}
    try:
        days = (date.fromisoformat(raw) - today).days
    except ValueError:
        return {"classification": "sem_data", "days": None, "priority": 98}
    if days < 0:
        return {"classification": "vencido", "days": days, "priority": 0}
    if days == 0:
        return {"classification": "vence_hoje", "days": 0, "priority": 1}
    if days <= 3:
        return {"classification": "urgente", "days": days, "priority": 2}
    if days <= 7:
        return {"classification": "atencao", "days": days, "priority": 3}
    if days <= 15:
        return {"classification": "preventivo", "days": days, "priority": 4}
    return {"classification": "em_dia", "days": days, "priority": 5}


def suggest_driver(infraction: Mapping, *, assignments: list[dict], checklists: list[dict], vehicles: list[dict]) -> dict:
    vehicle_id, moment = clean_text(infraction.get("vehicle_id")), f"{clean_text(infraction.get('infraction_date'))}T{clean_text(infraction.get('infraction_time'), '12:00')}"
    candidates: list[dict] = []
    for item in assignments:
        if clean_text(item.get("vehicle_id")) != vehicle_id or clean_text(item.get("deleted_at")):
            continue
        start, end = clean_text(item.get("delivered_at")), clean_text(item.get("returned_at")) or "9999-12-31T23:59"
        if start and start <= moment <= end:
            candidates.append({"driver_id": clean_text(item.get("driver_id")), "confidence": "alta", "score": 100,
                               "evidence": [f"Entrega {item.get('id')} cobria o horário da infração"], "period_start": start, "period_end": clean_text(item.get("returned_at")),
                               "route_id": clean_text(item.get("route_id")), "operation_id": clean_text(item.get("operation_id"))})
    for item in checklists:
        if clean_text(item.get("vehicle_id")) == vehicle_id and clean_text(item.get("started_at"))[:10] == moment[:10] and clean_text(item.get("driver_id")):
            candidates.append({"driver_id": clean_text(item.get("driver_id")), "confidence": "media", "score": 70,
                               "evidence": [f"Checklist {item.get('id')} registrado na data"], "period_start": clean_text(item.get("started_at")),
                               "period_end": clean_text(item.get("completed_at")), "route_id": clean_text(item.get("route_id")), "operation_id": clean_text(item.get("operation_id"))})
    vehicle = next((item for item in vehicles if clean_text(item.get("vehicle_id")) == vehicle_id), {})
    if clean_text(vehicle.get("usual_driver_id")):
        candidates.append({"driver_id": clean_text(vehicle.get("usual_driver_id")), "confidence": "baixa", "score": 30,
                           "evidence": ["Motorista habitual do cadastro do veículo"], "period_start": "", "period_end": "", "route_id": "", "operation_id": ""})
    if not candidates:
        return {"driver_id": "", "confidence": "nenhuma", "score": 0, "evidence": ["Nenhum vínculo operacional encontrado"]}
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[0]


def build_identification(infraction: Mapping, suggestion: Mapping, *, existing: list[dict], now: str) -> dict:
    current = next((item for item in existing if clean_text(item.get("infraction_id")) == clean_text(infraction.get("id")) and not clean_text(item.get("deleted_at"))), {})
    return {**current, "id": clean_text(current.get("id")) or next_id(existing, "FID"), "infraction_id": clean_text(infraction.get("id")),
            "suggested_driver_id": clean_text(suggestion.get("driver_id")), "confirmed_driver_id": clean_text(current.get("confirmed_driver_id")),
            "confidence": clean_text(suggestion.get("confidence")), "confidence_score": as_int(suggestion.get("score")),
            "evidence": list(suggestion.get("evidence") or []), "period_start": clean_text(suggestion.get("period_start")),
            "period_end": clean_text(suggestion.get("period_end")), "route_id": clean_text(suggestion.get("route_id")),
            "operation_id": clean_text(suggestion.get("operation_id")), "status": "motorista_sugerido" if clean_text(suggestion.get("driver_id")) else "nao_identificado",
            "created_at": clean_text(current.get("created_at")) or now, "updated_at": now, "deleted_at": ""}


def confirm_identification(identification: Mapping, *, driver_id: str, user_id: str, now: str, notes: str = "", disagreement: str = "") -> dict:
    driver_id = clean_text(driver_id)
    if not driver_id:
        raise ValueError("Selecione o motorista após revisar as evidências.")
    if driver_id == user_id:
        raise PermissionError("O motorista não pode confirmar sozinho a própria identificação.")
    return {**identification, "confirmed_driver_id": driver_id, "status": "confirmado_internamente", "confirmed_by": user_id,
            "confirmed_at": now, "confirmation_notes": clean_text(notes), "disagreement": clean_text(disagreement), "updated_at": now}


def compute_nic_risk(infraction: Mapping, deadlines: list[dict], *, today: date | None = None) -> str:
    if not clean_text(infraction.get("legal_owner_company_id")) or not as_bool(infraction.get("driver_identification_required")):
        return "nao_aplicavel"
    if clean_text(infraction.get("driver_identification_status")) in {"protocolado", "aceito", "nao_aplicavel"}:
        return "sem_risco"
    target = next((item for item in deadlines if clean_text(item.get("infraction_id")) == clean_text(infraction.get("id")) and clean_text(item.get("deadline_type")) == "driver_identification" and not clean_text(item.get("deleted_at"))), None)
    if not target:
        return "atencao"
    info = classify_deadline(target, today=today)
    if info["classification"] == "vencido":
        return "prazo_vencido"
    if info["days"] is not None and info["days"] <= 3:
        return "alto_risco"
    if info["days"] is not None and info["days"] <= 10:
        return "atencao"
    return "sem_risco"


def build_proceeding(form: Mapping, *, infraction_id: str, records: list[dict], user_id: str, now: str) -> dict:
    proceeding_type, status = clean_text(form.get("proceeding_type")), clean_text(form.get("status"), "nao_iniciado")
    if proceeding_type not in PROCEEDING_TYPES or status not in PROCEEDING_STATUSES:
        raise ValueError("Tipo ou status do processo inválido.")
    return {"id": next_id(records, "FPR"), "infraction_id": infraction_id, "proceeding_type": proceeding_type, "status": status,
            "responsible_user_id": clean_text(form.get("responsible_user_id"), user_id), "legal_responsible": clean_text(form.get("legal_responsible")),
            "preparation_started_at": clean_text(form.get("preparation_started_at"), now), "internal_deadline": clean_text(form.get("internal_deadline")),
            "official_deadline": clean_text(form.get("official_deadline")), "protocol_date": "", "protocol_number": "", "protocol_channel": "",
            "decision_date": "", "decision_result": "", "decision_reason": "", "next_action": clean_text(form.get("next_action")),
            "next_deadline": clean_text(form.get("next_deadline")), "notes": clean_text(form.get("notes")), "created_at": now, "updated_at": now, "deleted_at": ""}


def build_decision(form: Mapping, *, infraction_id: str, records: list[dict], user_id: str, now: str) -> dict:
    decision = clean_text(form.get("decision"), "pending")
    if decision not in DECISIONS:
        raise ValueError("Decisão inválida.")
    if decision in {"identify_pay", "recognize_pay", "no_appeal"} and as_bool(form.get("discount_requires_waiver")) and not as_bool(form.get("waiver_warning_acknowledged")):
        raise ValueError("Confirme que o desconto pode implicar renúncia de defesa ou recurso antes de registrar a decisão.")
    justification = clean_text(form.get("justification"))
    if not justification:
        raise ValueError("Informe a justificativa da decisão humana.")
    return {"id": next_id(records, "FDE"), "infraction_id": infraction_id, "decision": decision, "responsible_user_id": user_id,
            "decided_at": now, "justification": justification, "original_amount": as_float(form.get("original_amount")),
            "discount_available": as_float(form.get("discount_available")), "estimated_missed_deadline_cost": as_float(form.get("estimated_missed_deadline_cost")),
            "points_impact": as_int(form.get("points_impact")), "nic_risk": clean_text(form.get("nic_risk")),
            "documents_available": clean_text(form.get("documents_available")), "discount_requires_waiver": as_bool(form.get("discount_requires_waiver")),
            "waiver_warning_acknowledged": as_bool(form.get("waiver_warning_acknowledged")), "created_at": now, "updated_at": now, "deleted_at": ""}


def build_protocol(form: Mapping, *, infraction_id: str, records: list[dict], user_id: str, now: str, proof_path: str = "") -> dict:
    protocol_date, channel = clean_text(form.get("protocol_date")), clean_text(form.get("protocol_channel"))
    override_reason = clean_text(form.get("proof_override_reason"))
    if not protocol_date or not channel:
        raise ValueError("Informe data e canal do protocolo.")
    if not proof_path and not (as_bool(form.get("proof_override_authorized")) and override_reason):
        raise ValueError("Anexe o comprovante do protocolo ou registre uma autorização com justificativa.")
    return {"id": next_id(records, "FPT"), "infraction_id": infraction_id, "proceeding_id": clean_text(form.get("proceeding_id")),
            "authority": clean_text(form.get("authority")), "protocol_channel": channel, "protocol_date": protocol_date,
            "protocol_time": clean_text(form.get("protocol_time")), "protocol_number": clean_text(form.get("protocol_number")),
            "responsible_user_id": user_id, "proof_path": proof_path, "proof_override_authorized": as_bool(form.get("proof_override_authorized")),
            "proof_override_reason": override_reason, "notes": clean_text(form.get("notes")), "expected_response_deadline": clean_text(form.get("expected_response_deadline")),
            "created_at": now, "updated_at": now, "deleted_at": ""}


def complete_deadline(deadline: Mapping, *, user_id: str, now: str, proof_path: str = "", justification: str = "") -> dict:
    if not proof_path and not clean_text(justification):
        raise ValueError("Para concluir o prazo, anexe um comprovante ou informe a justificativa.")
    return {**deadline, "status": "concluido", "completed_at": now, "completed_by": user_id,
            "completion_proof_path": proof_path, "completion_justification": clean_text(justification), "updated_at": now}


def missing_required_documents(template_items: Sequence[Mapping], documents: Sequence[Mapping]) -> list[str]:
    approved = {clean_text(item.get("document_type")) for item in documents if clean_text(item.get("status")) in {"recebido", "aprovado", "protocolado"} and not clean_text(item.get("deleted_at"))}
    return [clean_text(item.get("document_type")) for item in template_items if as_bool(item.get("is_required")) and not clean_text(item.get("deleted_at")) and clean_text(item.get("document_type")) not in approved]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dashboard(infractions: list[dict], deadlines: list[dict], payments: list[dict], proceedings: list[dict] | None = None) -> dict:
    active = [item for item in infractions if not clean_text(item.get("deleted_at"))]
    classified = []
    for item in deadlines:
        if clean_text(item.get("deleted_at")):
            continue
        classified.append({**item, **classify_deadline(item)})
    def grouped(field: str) -> list[dict]:
        counts: dict[str, int] = {}
        for item in active:
            label = clean_text(item.get(field), "Não informado")
            counts[label] = counts.get(label, 0) + 1
        return [{"label": label, "count": count} for label, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]

    resolved_days = []
    for item in active:
        if clean_text(item.get("status")) not in {"deferida", "indeferida", "paga", "cancelada", "encerrada"}:
            continue
        try:
            resolved_days.append((datetime.fromisoformat(clean_text(item.get("updated_at"))) - datetime.fromisoformat(clean_text(item.get("created_at")))).days)
        except ValueError:
            pass
    proceeding_items = [item for item in (proceedings or []) if not clean_text(item.get("deleted_at"))]
    return {
        "counts": {
            "new": sum(clean_text(item.get("status")) == "recebida" for item in active),
            "analysis": sum(clean_text(item.get("status")) in {"em_conferencia", "aguardando_decisao"} for item in active),
            "unidentified": sum(clean_text(item.get("driver_identification_status")) in {"nao_analisada", "nao_identificado", "motorista_sugerido"} for item in active),
            "nic_risk": sum(clean_text(item.get("nic_risk_status")) in {"atencao", "alto_risco", "prazo_vencido"} for item in active),
            "due_15": sum(item.get("days") is not None and 0 <= item["days"] <= 15 for item in classified),
            "due_7": sum(item.get("days") is not None and 0 <= item["days"] <= 7 for item in classified),
            "due_3": sum(item.get("days") is not None and 0 <= item["days"] <= 3 for item in classified),
            "overdue": sum(item.get("classification") == "vencido" for item in classified),
            "awaiting_payment": sum(clean_text(item.get("payment_status")) in {"pendente", "agendado", "vencido"} for item in active),
            "paid": sum(clean_text(item.get("payment_status")) == "pago" for item in active),
        },
        "amounts": {"original": round(sum(as_float(item.get("original_amount")) for item in active), 2),
                    "paid": round(sum(as_float(item.get("paid_amount")) for item in payments if clean_text(item.get("status")) == "pago"), 2),
                    "nic": round(sum(as_float(item.get("nic_amount")) for item in active), 2)},
        "deadlines": sorted(classified, key=lambda item: (item["priority"], clean_text(item.get("internal_deadline") or item.get("official_deadline"))))
        ,"reports": {
            "by_vehicle": grouped("vehicle_plate_snapshot"), "by_driver": grouped("driver_id"),
            "by_company": grouped("operating_company_id"), "by_operation": grouped("operation_id"),
            "by_client": grouped("client_id"), "by_authority": grouped("issuing_authority"),
            "by_type": grouped("infraction_code"),
            "repeat_drivers": [item for item in grouped("driver_id") if item["label"] != "Não informado" and item["count"] > 1],
            "missed_deadlines": sum(item.get("classification") == "vencido" for item in classified),
            "nic_count": sum(clean_text(item.get("notification_type")) == "nic" for item in active),
            "paid_amount": round(sum(as_float(item.get("paid_amount")) for item in payments if clean_text(item.get("status")) == "pago"), 2),
            "pending_amount": round(sum(as_float(item.get("original_amount")) for item in active if clean_text(item.get("payment_status")) in {"pendente", "agendado", "vencido"}), 2),
            "discounts": round(sum(as_float(item.get("discount_amount")) for item in payments), 2),
            "cancelled": sum(clean_text(item.get("status")) in {"cancelada", "deferida"} for item in active),
            "appeals_granted": sum(clean_text(item.get("status")) == "deferido" for item in proceeding_items),
            "appeals_denied": sum(clean_text(item.get("status")) == "indeferido" for item in proceeding_items),
            "average_resolution_days": round(sum(resolved_days) / len(resolved_days), 1) if resolved_days else 0,
        }
    }


def import_mapping(row: Mapping) -> dict:
    aliases = {
        "placa": "plate", "renavam": "renavam", "numero_do_auto": "infraction_notice_number", "numero_auto": "infraction_notice_number",
        "orgao": "issuing_authority", "codigo": "infraction_code", "descricao": "infraction_description", "data": "infraction_date",
        "hora": "infraction_time", "local": "location", "valor": "original_amount", "pontos": "points",
        "prazo_de_indicacao": "driver_identification_deadline", "prazo_de_defesa": "preliminary_defense_deadline",
        "prazo_de_pagamento": "payment_deadline", "motorista": "driver_name", "status": "status", "observacoes": "company_notes",
    }
    return {aliases.get(key, key): value for key, value in row.items() if aliases.get(key, key)}


def financial_link_note(infraction_id: str) -> str:
    return f"Vínculo único com infração {clean_text(infraction_id)}."


def find_linked_financial_entry(entries: Sequence[Mapping], infraction_id: str) -> Mapping | None:
    note = financial_link_note(infraction_id)
    return next((item for item in entries if clean_text(item.get("notes")) == note), None)


def driver_can_view_infraction(infraction: Mapping, user_id: str) -> bool:
    return clean_text(infraction.get("driver_id")) == clean_text(user_id) and bool(clean_text(infraction.get("released_to_driver_at")))


def attachment_access_allowed(attachment: Mapping, infraction: Mapping, *, user_id: str, role: str, can_view_sensitive: bool) -> bool:
    if clean_text(role) == "leitura" and not driver_can_view_infraction(infraction, user_id):
        return False
    if as_bool(attachment.get("is_sensitive")) and not can_view_sensitive:
        return False
    return True


def build_audit_log(*, log_id: str, infraction_id: str, user_id: str, action: str, before, after, justification: str, created_at: str) -> dict:
    return {"id": log_id, "infraction_id": clean_text(infraction_id), "user_id": clean_text(user_id), "action": clean_text(action),
            "previous_data": before, "new_data": after, "justification": clean_text(justification), "created_at": clean_text(created_at)}


def soft_delete(record: Mapping, *, now: str) -> dict:
    return {**record, "deleted_at": clean_text(now), "updated_at": clean_text(now)}
