from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Mapping, Sequence

from app.repositories.sqlite_repository import connect, initialize_database, json_dumps, payload_hash


CHECKLIST_TYPES = {
    "saida": "Saída",
    "retorno": "Retorno",
    "inspecao_periodica": "Inspeção periódica",
    "entrega_motorista": "Entrega para motorista",
    "devolucao_motorista": "Devolução pelo motorista",
    "pre_manutencao": "Pré-manutenção",
    "pos_manutencao": "Pós-manutenção",
}
CHECKLIST_STATUSES = {
    "rascunho": "Rascunho", "em_preenchimento": "Em preenchimento", "concluido": "Concluído",
    "concluido_com_ressalvas": "Concluído com ressalvas", "reprovado": "Reprovado", "cancelado": "Cancelado",
}
RESPONSE_TYPES = {
    "conformidade": "Conforme / atenção / não conforme / não aplicável",
    "sim_nao": "Sim / não", "texto": "Texto", "numero": "Número", "foto": "Foto",
    "selecao": "Seleção", "confirmacao": "Assinatura ou confirmação",
}
RESPONSE_STATUSES = {"conforme", "atencao", "nao_conforme", "nao_aplicavel", "sim", "nao"}
CHECKLIST_CATEGORIES = {
    "identificacao_veiculo": "Identificação do veículo", "documentacao": "Documentação",
    "quilometragem": "Quilometragem", "combustivel": "Combustível", "pneus": "Pneus",
    "estepe": "Estepe", "rodas": "Rodas", "freios": "Freios", "direcao": "Direção",
    "suspensao": "Suspensão", "iluminacao": "Iluminação", "sinalizacao": "Sinalização",
    "limpadores": "Limpadores", "retrovisores": "Retrovisores", "vidros": "Vidros",
    "buzina": "Buzina", "oleo_motor": "Óleo do motor", "liquido_arrefecimento": "Líquido de arrefecimento",
    "vazamentos": "Vazamentos", "bateria": "Bateria", "painel_alertas": "Painel e alertas",
    "equipamentos_obrigatorios": "Equipamentos obrigatórios", "extintor": "Extintor, quando aplicável",
    "triangulo": "Triângulo", "macaco": "Macaco", "chave_roda": "Chave de roda",
    "camera": "Câmera", "rastreador": "Rastreador", "cabine": "Cabine",
    "carroceria": "Carroceria", "bau": "Baú", "engate": "Engate", "reboque": "Reboque",
    "implemento": "Implemento", "avarias_externas": "Avarias externas", "limpeza": "Limpeza",
    "materiais_transportados": "Materiais transportados", "observacoes_gerais": "Observações gerais",
}
OCCURRENCE_TYPES = {
    "falha_mecanica": "Falha mecânica", "falha_eletrica": "Falha elétrica", "pneu": "Pneu",
    "avaria": "Avaria", "colisao": "Colisão", "acidente": "Acidente", "vazamento": "Vazamento",
    "equipamento_obrigatorio_ausente": "Equipamento obrigatório ausente", "documento_ausente": "Documento ausente",
    "material_ausente": "Material ausente", "problema_limpeza": "Problema de limpeza", "combustivel": "Combustível",
    "camera": "Câmera", "rastreador": "Rastreador", "conduta_operacional": "Conduta operacional",
    "possivel_infracao_transito": "Possível infração de trânsito", "outro": "Outro",
}
OCCURRENCE_SEVERITIES = {"informativa": "Informativa", "baixa": "Baixa", "media": "Média", "alta": "Alta", "critica": "Crítica"}
OCCURRENCE_STATUSES = {
    "aberta": "Aberta", "em_analise": "Em análise", "encaminhada_manutencao": "Encaminhada para manutenção",
    "aguardando_responsavel": "Aguardando responsável", "em_tratamento": "Em tratamento",
    "resolvida": "Resolvida", "cancelada": "Cancelada",
}
BLOCK_TYPES = {
    "manutencao": "Manutenção", "seguranca": "Segurança", "documentacao": "Documentação",
    "avaria": "Avaria", "ocorrencia": "Ocorrência", "decisao_administrativa": "Decisão administrativa", "outro": "Outro",
}
BLOCK_STATUSES = {"ativo", "aguardando_avaliacao"}
DEPARTURE_TYPES = {"saida", "entrega_motorista"}
RETURN_TYPES = {"retorno", "devolucao_motorista"}
FINAL_CHECKLIST_STATUSES = {"concluido", "concluido_com_ressalvas", "reprovado", "cancelado"}


def clean_text(value, fallback: str = "") -> str:
    text = str(value if value is not None else "").strip()
    return text or fallback


def as_bool(value) -> bool:
    return clean_text(value).lower() in {"1", "true", "yes", "sim", "on"}


def as_int(value, fallback: int | None = 0) -> int | None:
    try:
        return int(float(str(value).replace(",", ".")))
    except (TypeError, ValueError):
        return fallback


def as_float(value, fallback: float | None = None) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return fallback


def next_id(records: Sequence[Mapping], prefix: str) -> str:
    used = []
    for record in records:
        match = re.search(r"(\d+)$", clean_text(record.get("id")))
        if match:
            used.append(int(match.group(1)))
    return f"{prefix}-{max(used, default=0) + 1:06d}"


def next_occurrence_number(records: Sequence[Mapping], when: str) -> str:
    year = date.fromisoformat(when[:10]).year
    pattern = re.compile(rf"^OC-FROTA-{year}-(\d{{6}})$")
    used = [int(match.group(1)) for record in records if (match := pattern.match(clean_text(record.get("occurrence_number"))))]
    return f"OC-FROTA-{year}-{max(used, default=0) + 1:06d}"


def _choice(value, choices: Mapping[str, str], label: str, fallback: str = "") -> str:
    normalized = clean_text(value, fallback).lower().replace(" ", "_").replace("-", "_")
    aliases = {"saída": "saida", "retorno": "retorno", "inspeção_periódica": "inspecao_periodica", "média": "media", "crítica": "critica", "não_conforme": "nao_conforme", "não_aplicável": "nao_aplicavel"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in choices:
        raise ValueError(f"{label} inválido.")
    return normalized


def template_matches_vehicle(template: Mapping, vehicle: Mapping) -> bool:
    expected = clean_text(template.get("vehicle_type"), "geral").lower()
    actual = clean_text(vehicle.get("vehicle_type"), "geral").lower()
    return expected in {"", "geral", "todos"} or expected == actual


def build_template_version(form: Mapping, *, templates: list[dict], user_id: str, now: str) -> tuple[dict, dict | None]:
    source_id = clean_text(form.get("template_id") or form.get("id"))
    source = next((item for item in templates if clean_text(item.get("id")) == source_id), None) if source_id else None
    name = clean_text(form.get("name") or (source or {}).get("name"))
    if not name:
        raise ValueError("Informe o nome do modelo.")
    checklist_type = _choice(form.get("checklist_type") or (source or {}).get("checklist_type"), CHECKLIST_TYPES, "Tipo de checklist", "saida")
    logical_id = clean_text((source or {}).get("logical_id")) or next_id(templates, "TPLLOG")
    version = max([as_int(item.get("version"), 0) or 0 for item in templates if clean_text(item.get("logical_id")) == logical_id], default=0) + 1
    template = {
        "id": next_id(templates, "TPL"), "logical_id": logical_id, "name": name,
        "description": clean_text(form.get("description") or (source or {}).get("description")),
        "checklist_type": checklist_type, "vehicle_type": clean_text(form.get("vehicle_type") or (source or {}).get("vehicle_type"), "geral"),
        "is_active": True, "version": version, "supersedes_template_id": clean_text((source or {}).get("id")),
        "created_by": user_id, "created_at": now, "updated_at": now, "deleted_at": "",
    }
    previous = {**source, "is_active": False, "updated_at": now} if source else None
    return template, previous


def build_template_item(form: Mapping, *, template_id: str, items: list[dict], now: str) -> dict:
    category = clean_text(form.get("category"))
    if category not in CHECKLIST_CATEGORIES:
        raise ValueError("Categoria de checklist inválida.")
    title = clean_text(form.get("title"))
    if not title:
        raise ValueError("Informe o título do item.")
    response_type = _choice(form.get("response_type"), RESPONSE_TYPES, "Tipo de resposta", "conformidade")
    options = [clean_text(item) for item in clean_text(form.get("selection_options")).split("|") if clean_text(item)]
    if response_type == "selecao" and not options:
        raise ValueError("Informe opções separadas por | para o tipo seleção.")
    return {
        "id": next_id(items, "TPLI"), "template_id": template_id, "category": category,
        "title": title, "description": clean_text(form.get("description")),
        "display_order": max(as_int(form.get("display_order"), len(items) + 1) or 0, 0),
        "response_type": response_type, "selection_options": options,
        "selection_options_json": json.dumps(options, ensure_ascii=False),
        "is_required": as_bool(form.get("is_required")), "is_critical": as_bool(form.get("is_critical")),
        "requires_photo": as_bool(form.get("requires_photo")),
        "requires_note_on_failure": as_bool(form.get("requires_note_on_failure")),
        "creates_occurrence_on_failure": as_bool(form.get("creates_occurrence_on_failure")),
        "blocks_vehicle_on_failure": as_bool(form.get("blocks_vehicle_on_failure")),
        "created_at": now, "updated_at": now, "deleted_at": "",
    }


def clone_template_items(items: Sequence[Mapping], *, source_template_id: str, target_template_id: str, now: str, omit_item_id: str = "") -> list[dict]:
    cloned = []
    for item in items:
        if clean_text(item.get("template_id")) != source_template_id or clean_text(item.get("deleted_at")) or clean_text(item.get("id")) == omit_item_id:
            continue
        clone_key = f"{target_template_id}:{item.get('id')}"
        cloned.append({**dict(item), "id": f"TPLI-{hashlib.sha256(clone_key.encode()).hexdigest()[:16].upper()}", "source_item_id": clean_text(item.get("id")), "template_id": target_template_id, "created_at": now, "updated_at": now, "deleted_at": ""})
    return cloned


def build_checklist_draft(form: Mapping, *, template: Mapping, vehicle: Mapping, checklists: list[dict], user_id: str, now: str) -> dict:
    if not template_matches_vehicle(template, vehicle):
        raise ValueError("O modelo não é compatível com o tipo deste veículo.")
    checklist_type = clean_text(template.get("checklist_type"))
    driver_id = clean_text(form.get("driver_id"))
    if checklist_type in DEPARTURE_TYPES | RETURN_TYPES and not driver_id:
        raise ValueError("Selecione o motorista responsável.")
    latitude = as_float(form.get("latitude"))
    longitude = as_float(form.get("longitude"))
    if (latitude is None) != (longitude is None):
        raise ValueError("Informe latitude e longitude juntas ou deixe ambas vazias.")
    return {
        "id": next_id(checklists, "CHK"), "template_id": clean_text(template.get("id")),
        "template_version": as_int(template.get("version"), 1), "checklist_type": checklist_type,
        "vehicle_id": clean_text(vehicle.get("vehicle_id") or vehicle.get("id")), "driver_id": driver_id,
        "route_id": clean_text(form.get("route_id")), "operation_id": clean_text(form.get("operation_id")),
        "service_order_id": clean_text(form.get("service_order_id")), "status": "rascunho",
        "started_at": now, "completed_at": "", "start_mileage": as_int(form.get("start_mileage"), None),
        "end_mileage": as_int(form.get("end_mileage"), None), "distance_travelled": None,
        "fuel_level": clean_text(form.get("fuel_level")), "general_status": "rascunho",
        "location_text": clean_text(form.get("location_text")), "latitude": latitude, "longitude": longitude,
        "responsible_user_id": user_id, "signature_name": "", "confirmation_hash": "",
        "notes": clean_text(form.get("notes")), "created_at": now, "updated_at": now, "deleted_at": "",
    }


def build_checklist_responses(form: Mapping, *, checklist: Mapping, template_items: Sequence[Mapping], existing: Sequence[Mapping], now: str) -> list[dict]:
    responses = [dict(item) for item in existing if clean_text(item.get("checklist_id")) != clean_text(checklist.get("id"))]
    old_map = {clean_text(item.get("template_item_id")): item for item in existing if clean_text(item.get("checklist_id")) == clean_text(checklist.get("id"))}
    for item in template_items:
        if clean_text(item.get("template_id")) != clean_text(checklist.get("template_id")) or clean_text(item.get("deleted_at")):
            continue
        item_id = clean_text(item.get("id"))
        previous = old_map.get(item_id, {})
        value = clean_text(form.get(f"response_{item_id}"), clean_text(previous.get("response_value")))
        status = clean_text(form.get(f"status_{item_id}"), clean_text(previous.get("response_status")))
        if clean_text(item.get("response_type")) == "conformidade" and value in RESPONSE_STATUSES:
            status = value
        elif clean_text(item.get("response_type")) == "sim_nao" and value in {"sim", "nao"}:
            status = value
        response = {
            "id": clean_text(previous.get("id")) or next_id(responses, "CHKR"),
            "checklist_id": clean_text(checklist.get("id")), "template_item_id": item_id,
            "item_title_snapshot": clean_text(item.get("title")), "category_snapshot": clean_text(item.get("category")),
            "response_value": value, "response_status": status,
            "note": clean_text(form.get(f"note_{item_id}"), clean_text(previous.get("note"))),
            "is_critical_snapshot": as_bool(item.get("is_critical")),
            "created_at": clean_text(previous.get("created_at")) or now, "updated_at": now, "deleted_at": "",
        }
        responses.append(response)
    return responses


def validate_checklist_completion(checklist: Mapping, responses: Sequence[Mapping], template_items: Sequence[Mapping], evidence: Sequence[Mapping], *, signature_name: str) -> dict:
    response_map = {clean_text(item.get("template_item_id")): item for item in responses if clean_text(item.get("checklist_id")) == clean_text(checklist.get("id")) and not clean_text(item.get("deleted_at"))}
    evidence_items = [item for item in evidence if clean_text(item.get("checklist_id")) == clean_text(checklist.get("id")) and not clean_text(item.get("deleted_at"))]
    errors, warnings, failures = [], [], []
    for item in template_items:
        if clean_text(item.get("template_id")) != clean_text(checklist.get("template_id")) or clean_text(item.get("deleted_at")):
            continue
        item_id = clean_text(item.get("id"))
        response = response_map.get(item_id, {})
        value = clean_text(response.get("response_value"))
        status = clean_text(response.get("response_status"))
        note = clean_text(response.get("note"))
        failed = status in {"atencao", "nao_conforme", "nao"}
        has_photo = any(clean_text(file.get("template_item_id")) == item_id for file in evidence_items)
        if as_bool(item.get("is_required")) and not value and not status and not (clean_text(item.get("response_type")) == "foto" and has_photo):
            errors.append(f"Item obrigatório sem resposta: {item.get('title')}")
        if as_bool(item.get("requires_photo")) and not has_photo:
            errors.append(f"Foto obrigatória ausente: {item.get('title')}")
        if failed and (status == "nao_conforme" or as_bool(item.get("requires_note_on_failure"))) and not note:
            errors.append(f"Observação obrigatória na falha: {item.get('title')}")
        if failed:
            failures.append({"item": dict(item), "response": dict(response), "critical": as_bool(item.get("is_critical")) and status in {"nao_conforme", "nao"}})
            if status == "atencao":
                warnings.append(clean_text(item.get("title")))
    if not clean_text(signature_name):
        errors.append("Informe o nome para confirmação da conclusão.")
    if errors:
        raise ValueError(" ".join(errors))
    critical = [item for item in failures if item["critical"]]
    if critical:
        final_status, general_status = "reprovado", "critico"
    elif failures:
        final_status, general_status = "concluido_com_ressalvas", "atencao"
    else:
        final_status, general_status = "concluido", "conforme"
    confirmation_payload = {
        "checklist_id": checklist.get("id"), "template_id": checklist.get("template_id"),
        "template_version": checklist.get("template_version"), "vehicle_id": checklist.get("vehicle_id"),
        "signature_name": clean_text(signature_name),
        "responses": sorted([{"item": item.get("template_item_id"), "value": item.get("response_value"), "status": item.get("response_status"), "note": item.get("note")} for item in response_map.values()], key=lambda item: clean_text(item.get("item"))),
    }
    return {"status": final_status, "general_status": general_status, "failures": failures, "critical_failures": critical, "warnings": warnings, "confirmation_hash": hashlib.sha256(json_dumps(confirmation_payload).encode("utf-8")).hexdigest()}


def build_occurrences_from_failures(checklist: Mapping, failures: Sequence[Mapping], existing: list[dict], *, user_id: str, now: str) -> list[dict]:
    created = []
    occurrence_date = now[:10]
    for failure in failures:
        item, response = failure["item"], failure["response"]
        if not (as_bool(item.get("creates_occurrence_on_failure")) or clean_text(response.get("response_status")) in {"nao_conforme", "nao"}):
            continue
        if any(clean_text(record.get("checklist_id")) == clean_text(checklist.get("id")) and clean_text(record.get("source_template_item_id")) == clean_text(item.get("id")) and not clean_text(record.get("deleted_at")) for record in existing + created):
            continue
        severity = "critica" if failure.get("critical") else "media" if clean_text(response.get("response_status")) in {"nao_conforme", "nao"} else "baixa"
        category = clean_text(item.get("category"))
        occurrence_type = {"pneus": "pneu", "documentacao": "documento_ausente", "vazamentos": "vazamento", "limpeza": "problema_limpeza", "camera": "camera", "rastreador": "rastreador", "avarias_externas": "avaria", "combustivel": "combustivel"}.get(category, "outro")
        pool = existing + created
        created.append({
            "id": next_id(pool, "OCC"), "occurrence_number": next_occurrence_number(pool, occurrence_date),
            "vehicle_id": clean_text(checklist.get("vehicle_id")), "driver_id": clean_text(checklist.get("driver_id")),
            "route_id": clean_text(checklist.get("route_id")), "operation_id": clean_text(checklist.get("operation_id")),
            "checklist_id": clean_text(checklist.get("id")), "service_order_id": clean_text(checklist.get("service_order_id")),
            "source_template_item_id": clean_text(item.get("id")), "occurrence_type": occurrence_type,
            "severity": severity, "status": "aberta", "title": clean_text(item.get("title")),
            "description": clean_text(response.get("note"), f"Falha registrada no checklist {checklist.get('id')}."),
            "occurrence_date": occurrence_date, "reported_at": now, "location": clean_text(checklist.get("location_text")),
            "responsible_user_id": user_id, "assigned_user_id": "", "resolution": "", "resolved_at": "", "resolved_by": "",
            "created_at": now, "updated_at": now, "deleted_at": "",
        })
    return created


def build_blocks_from_failures(checklist: Mapping, failures: Sequence[Mapping], occurrences: Sequence[Mapping], existing: list[dict], *, user_id: str, now: str) -> list[dict]:
    blocks = []
    for failure in failures:
        item, response = failure["item"], failure["response"]
        if not (failure.get("critical") or as_bool(item.get("blocks_vehicle_on_failure"))):
            continue
        occurrence = next((record for record in occurrences if clean_text(record.get("source_template_item_id")) == clean_text(item.get("id"))), {})
        blocks.append({
            "id": next_id(existing + blocks, "BLK"), "vehicle_id": clean_text(checklist.get("vehicle_id")),
            "occurrence_id": clean_text(occurrence.get("id")), "checklist_id": clean_text(checklist.get("id")),
            "service_order_id": clean_text(checklist.get("service_order_id")),
            "block_type": "seguranca" if failure.get("critical") else "ocorrencia",
            "reason": f"{clean_text(item.get('title'))}: {clean_text(response.get('note'))}",
            "severity": "critica" if failure.get("critical") else "alta", "blocked_at": now, "blocked_by": user_id,
            "status": "ativo", "released_at": "", "released_by": "", "release_reason": "",
            "resolution_confirmed": False, "created_at": now, "updated_at": now, "deleted_at": "",
        })
    return blocks


def active_blocks_for_vehicle(blocks: Sequence[Mapping], vehicle_id: str, *, exclude_id: str = "") -> list[dict]:
    return [dict(item) for item in blocks if clean_text(item.get("vehicle_id")) == vehicle_id and clean_text(item.get("id")) != exclude_id and clean_text(item.get("status")) in BLOCK_STATUSES and not clean_text(item.get("deleted_at"))]


def build_vehicle_assignment(checklist: Mapping, assignments: list[dict], *, user_id: str, now: str, override_reason: str = "") -> dict:
    vehicle_id = clean_text(checklist.get("vehicle_id"))
    open_assignment = next((item for item in assignments if clean_text(item.get("vehicle_id")) == vehicle_id and clean_text(item.get("status")) == "entregue" and not clean_text(item.get("deleted_at"))), None)
    if open_assignment and not clean_text(override_reason):
        raise ValueError("O veículo já possui uma entrega aberta. É necessária autorização administrativa com justificativa.")
    mileage = as_int(checklist.get("start_mileage"), None)
    if mileage is None:
        raise ValueError("Informe a quilometragem de saída.")
    if not clean_text(checklist.get("driver_id")):
        raise ValueError("Selecione o motorista responsável pela entrega.")
    return {
        "id": next_id(assignments, "ENT"), "vehicle_id": vehicle_id, "driver_id": clean_text(checklist.get("driver_id")),
        "route_id": clean_text(checklist.get("route_id")), "operation_id": clean_text(checklist.get("operation_id")),
        "departure_checklist_id": clean_text(checklist.get("id")), "return_checklist_id": "",
        "delivered_by": user_id, "received_by_driver": clean_text(checklist.get("driver_id")), "delivered_at": now,
        "expected_return_at": clean_text(checklist.get("expected_return_at")), "returned_at": "",
        "returned_by_driver": "", "received_return_by": "", "start_mileage": mileage, "end_mileage": None,
        "start_fuel_level": clean_text(checklist.get("fuel_level")), "end_fuel_level": "", "status": "entregue",
        "override_justification": clean_text(override_reason), "created_at": now, "updated_at": now, "deleted_at": "",
    }


def close_vehicle_assignment(checklist: Mapping, assignments: list[dict], *, user_id: str, now: str) -> dict:
    assignment = next((item for item in assignments if clean_text(item.get("vehicle_id")) == clean_text(checklist.get("vehicle_id")) and clean_text(item.get("status")) == "entregue" and not clean_text(item.get("deleted_at"))), None)
    if not assignment:
        raise ValueError("Não existe entrega aberta para este veículo.")
    if clean_text(assignment.get("driver_id")) != clean_text(checklist.get("driver_id")):
        raise ValueError("O motorista da devolução não corresponde ao responsável atual.")
    end_mileage = as_int(checklist.get("end_mileage"), None)
    if end_mileage is None or end_mileage < (as_int(assignment.get("start_mileage"), 0) or 0):
        raise ValueError("A quilometragem de retorno não pode ser inferior à saída.")
    return {**assignment, "return_checklist_id": clean_text(checklist.get("id")), "returned_at": now, "returned_by_driver": clean_text(checklist.get("driver_id")), "received_return_by": user_id, "end_mileage": end_mileage, "end_fuel_level": clean_text(checklist.get("fuel_level")), "status": "devolvido", "updated_at": now}


def driver_authorized(user_id: str, vehicle: Mapping, authorizations: Sequence[Mapping]) -> bool:
    for auth in authorizations:
        if clean_text(auth.get("user_id")) != user_id or clean_text(auth.get("status")) != "ativo" or clean_text(auth.get("deleted_at")):
            continue
        vehicle_ids = auth.get("authorized_vehicle_ids") if isinstance(auth.get("authorized_vehicle_ids"), list) else []
        vehicle_types = auth.get("authorized_vehicle_types") if isinstance(auth.get("authorized_vehicle_types"), list) else []
        if not vehicle_ids and not vehicle_types:
            return True
        if clean_text(vehicle.get("vehicle_id")) in vehicle_ids or clean_text(vehicle.get("vehicle_type")) in vehicle_types:
            return True
    return False


def release_block_allowed(*, block: Mapping, blocks: Sequence[Mapping], occurrences: Sequence[Mapping], service_orders: Sequence[Mapping], documents: Sequence[Mapping]) -> tuple[bool, list[str]]:
    vehicle_id, reasons = clean_text(block.get("vehicle_id")), []
    if active_blocks_for_vehicle(blocks, vehicle_id, exclude_id=clean_text(block.get("id"))):
        reasons.append("Existe outro bloqueio operacional ativo.")
    if any(clean_text(item.get("vehicle_id")) == vehicle_id and clean_text(item.get("severity")) == "critica" and clean_text(item.get("status")) not in {"resolvida", "cancelada"} and not clean_text(item.get("deleted_at")) for item in occurrences):
        reasons.append("Existe ocorrência crítica aberta.")
    if any(clean_text(item.get("vehicle_id")) == vehicle_id and clean_text(item.get("priority")) == "critica" and clean_text(item.get("status")) not in {"concluida", "cancelada"} and not clean_text(item.get("deleted_at")) for item in service_orders):
        reasons.append("Existe ordem crítica em andamento.")
    today = date.today().isoformat()
    if any(clean_text(item.get("vehicle_id")) == vehicle_id and as_bool(item.get("blocks_vehicle_on_expiry")) and clean_text(item.get("expires_at") or item.get("expiration_date")) and clean_text(item.get("expires_at") or item.get("expiration_date")) < today and clean_text(item.get("status"), "ativo") == "ativo" and not clean_text(item.get("deleted_at")) for item in documents):
        reasons.append("Existe documento obrigatório vencido.")
    return not reasons, reasons


def route_departure_status(*, vehicle_id: str, route_id: str, operation_id: str, checklists: Sequence[Mapping], blocks: Sequence[Mapping], assignments: Sequence[Mapping], required: bool) -> dict:
    active_blocks = active_blocks_for_vehicle(blocks, vehicle_id)
    critical = any(clean_text(item.get("severity")) == "critica" for item in active_blocks)
    if active_blocks:
        return {"allowed": False, "critical": critical, "reason": clean_text(active_blocks[0].get("reason")), "code": "vehicle_blocked"}
    matching_checklists = [
        item for item in checklists
        if clean_text(item.get("vehicle_id")) == vehicle_id
        and clean_text(item.get("checklist_type")) in DEPARTURE_TYPES
        and clean_text(item.get("status")) in {"concluido", "concluido_com_ressalvas"}
        and (not route_id or clean_text(item.get("route_id")) == route_id)
        and (not operation_id or clean_text(item.get("operation_id")) == operation_id)
        and not clean_text(item.get("deleted_at"))
    ]
    open_assignment = next((item for item in assignments if clean_text(item.get("vehicle_id")) == vehicle_id and clean_text(item.get("status")) == "entregue" and not clean_text(item.get("deleted_at"))), None)
    if open_assignment:
        assignment_matches = any(clean_text(item.get("id")) == clean_text(open_assignment.get("departure_checklist_id")) for item in matching_checklists)
        if not assignment_matches:
            return {"allowed": False, "critical": False, "reason": "Existe entrega anterior ainda aberta.", "code": "assignment_open"}
    if not required:
        return {"allowed": True, "critical": False, "reason": "Checklist não exigido pela configuração.", "code": "not_required"}
    completed = bool(matching_checklists)
    return {"allowed": completed, "critical": False, "reason": "Checklist de saída pendente." if not completed else "Checklist de saída concluído.", "code": "checklist_pending" if not completed else "ready"}


def evidence_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _upsert_payload(connection: sqlite3.Connection, table: str, record: Mapping, fields: Sequence[str], source_file: str) -> None:
    payload = dict(record)
    columns = {field: payload.get(field) for field in fields}
    columns.update({"source_file": source_file, "payload_json": json_dumps(payload), "payload_hash": payload_hash(payload), "migrated_at": datetime.now().isoformat(timespec="seconds")})
    names = list(columns)
    assignments = ", ".join(f"{name}=excluded.{name}" for name in names if name != "id")
    connection.execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)}) ON CONFLICT(id) DO UPDATE SET {assignments}", [columns[name] for name in names])


def complete_checklist_transaction(*, db_path: Path, checklist: dict, responses: Sequence[Mapping], vehicle: dict, mileage: int | None, mileage_source: str, user_id: str, correction_allowed: bool, correction_justification: str) -> dict:
    initialize_database(db_path)
    vehicle_id = clean_text(checklist.get("vehicle_id"))
    now = clean_text(checklist.get("completed_at")) or datetime.now().isoformat(timespec="seconds")
    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute("SELECT current_mileage, payload_json FROM vehicles WHERE vehicle_id = ?", (vehicle_id,)).fetchone()
        if not row:
            raise ValueError("Veículo não encontrado no SQLite.")
        current = int(row["current_mileage"] or 0)
        last_row = connection.execute("SELECT MAX(mileage) FROM vehicle_mileage WHERE vehicle_id = ?", (vehicle_id,)).fetchone()
        last = max(current, int(last_row[0] or 0))
        if mileage is not None and mileage < last:
            if not correction_allowed:
                raise PermissionError("A quilometragem não pode regredir.")
            if len(clean_text(correction_justification)) < 10:
                raise ValueError("Informe justificativa administrativa para corrigir a quilometragem.")
        checklist_fields = (
            "id", "template_id", "template_version", "checklist_type", "vehicle_id", "driver_id", "route_id", "operation_id", "service_order_id", "status", "started_at", "completed_at", "start_mileage", "end_mileage", "distance_travelled", "fuel_level", "general_status", "location_text", "latitude", "longitude", "responsible_user_id", "signature_name", "confirmation_hash", "notes", "created_at", "updated_at", "deleted_at",
        )
        response_fields = (
            "id", "checklist_id", "template_item_id", "item_title_snapshot", "category_snapshot", "response_value", "response_status", "note", "is_critical_snapshot", "created_at", "updated_at", "deleted_at",
        )
        _upsert_payload(connection, "fleet_checklists", checklist, checklist_fields, "fleet_checklists.json")
        for response in responses:
            if clean_text(response.get("checklist_id")) == clean_text(checklist.get("id")):
                _upsert_payload(connection, "fleet_checklist_responses", response, response_fields, "fleet_checklist_responses.json")
        updated_vehicle = dict(vehicle)
        if mileage is not None:
            updated_vehicle["current_mileage"] = mileage
            updated_vehicle["updated_at"] = now
            vehicle_payload = json_dumps(updated_vehicle)
            connection.execute("UPDATE vehicles SET current_mileage = ?, updated_at = ?, payload_json = ?, payload_hash = ?, migrated_at = ? WHERE vehicle_id = ?", (mileage, now, vehicle_payload, payload_hash(updated_vehicle), now, vehicle_id))
            mileage_key = f"{checklist.get('id')}:{mileage_source}"
            mileage_id = f"KM-{hashlib.sha256(mileage_key.encode()).hexdigest()[:24].upper()}"
            connection.execute("INSERT INTO vehicle_mileage (id, vehicle_id, mileage, record_date, source, user_id, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET mileage=excluded.mileage, notes=excluded.notes", (mileage_id, vehicle_id, mileage, now[:10], mileage_source, user_id, f"Checklist {checklist.get('id')}. {clean_text(correction_justification)}", now))
        audit_key = f"{checklist.get('id')}:complete"
        audit_id = f"VAU-{hashlib.sha256(audit_key.encode()).hexdigest()[:24].upper()}"
        connection.execute("INSERT INTO vehicle_audit_logs (id, vehicle_id, user_id, action, previous_data, new_data, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET new_data=excluded.new_data, created_at=excluded.created_at", (audit_id, vehicle_id, user_id, "complete_checklist", json.dumps({"current_mileage": current}, ensure_ascii=False), json.dumps({"checklist": checklist, "current_mileage": mileage if mileage is not None else current}, ensure_ascii=False), now))
    return {"vehicle": updated_vehicle, "previous_mileage": current, "mileage": mileage, "audit_id": audit_id}


def build_operational_dashboard(*, checklists: Sequence[Mapping], occurrences: Sequence[Mapping], blocks: Sequence[Mapping], assignments: Sequence[Mapping], vehicles: Sequence[Mapping], today: str | None = None) -> dict:
    today = today or date.today().isoformat()
    active_checklists = [item for item in checklists if not clean_text(item.get("deleted_at"))]
    open_occurrences = [item for item in occurrences if clean_text(item.get("status")) not in {"resolvida", "cancelada"} and not clean_text(item.get("deleted_at"))]
    active_blocks = [item for item in blocks if clean_text(item.get("status")) in BLOCK_STATUSES and not clean_text(item.get("deleted_at"))]
    open_assignments = [item for item in assignments if clean_text(item.get("status")) == "entregue" and not clean_text(item.get("deleted_at"))]
    notifications = []
    for item in active_checklists:
        if clean_text(item.get("status")) == "reprovado":
            notifications.append({"level": "danger", "title": "Checklist reprovado", "detail": f"{item.get('vehicle_id')} · {item.get('id')}"})
    for item in active_blocks:
        notifications.append({"level": "danger", "title": "Veículo bloqueado", "detail": f"{item.get('vehicle_id')} · {item.get('reason')}"})
        if clean_text(item.get("severity")) == "critica":
            notifications.append({"level": "warning", "title": "Ordem de serviço sugerida", "detail": f"Avalie a ocorrência do veículo {item.get('vehicle_id')} antes de abrir a ordem."})
    for item in blocks:
        if clean_text(item.get("status")) == "liberado" and clean_text(item.get("released_at"))[:10] == today and not clean_text(item.get("deleted_at")):
            notifications.append({"level": "success", "title": "Veículo liberado", "detail": f"{item.get('vehicle_id')} · {item.get('release_reason')}"})
    for item in open_occurrences:
        if clean_text(item.get("severity")) == "critica":
            notifications.append({"level": "danger", "title": "Ocorrência crítica", "detail": f"{item.get('occurrence_number')} · {item.get('title')}"})
    for item in open_assignments:
        notifications.append({"level": "warning", "title": "Checklist de retorno pendente", "detail": f"{item.get('vehicle_id')} · motorista {item.get('driver_id')}"})
        if clean_text(item.get("expected_return_at")) and clean_text(item.get("expected_return_at"))[:10] < today:
            notifications.append({"level": "warning", "title": "Retorno atrasado", "detail": f"{item.get('vehicle_id')} · motorista {item.get('driver_id')}"})
    return {
        "counts": {
            "departures_today": sum(1 for item in active_checklists if clean_text(item.get("checklist_type")) in DEPARTURE_TYPES and clean_text(item.get("completed_at"))[:10] == today),
            "pending_returns": len(open_assignments),
            "pending_checklists": sum(1 for item in active_checklists if clean_text(item.get("status")) in {"rascunho", "em_preenchimento"}),
            "failed_checklists": sum(1 for item in active_checklists if clean_text(item.get("status")) == "reprovado"),
            "blocked_vehicles": len({clean_text(item.get("vehicle_id")) for item in active_blocks}),
            "delivered_vehicles": len(open_assignments), "open_occurrences": len(open_occurrences),
            "critical_occurrences": sum(1 for item in open_occurrences if clean_text(item.get("severity")) == "critica"),
            "stale_mileage": sum(1 for item in vehicles if (as_int(item.get("current_mileage"), 0) or 0) <= 0),
        },
        "notifications": notifications[:20], "active_blocks": active_blocks, "open_assignments": open_assignments,
        "open_occurrences": open_occurrences, "recent_checklists": sorted(active_checklists, key=lambda item: clean_text(item.get("updated_at")), reverse=True)[:20],
    }
