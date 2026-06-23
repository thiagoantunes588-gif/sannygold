from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Mapping, Sequence


MAINTENANCE_TYPES = {
    "preventiva": "Preventiva",
    "corretiva": "Corretiva",
    "revisao_programada": "Revisão programada",
    "pneus": "Pneus",
    "eletrica": "Elétrica",
    "mecanica": "Mecânica",
    "freios": "Freios",
    "suspensao": "Suspensão",
    "motor": "Motor",
    "transmissao": "Transmissão",
    "arrefecimento": "Arrefecimento",
    "funilaria": "Funilaria",
    "rastreador": "Rastreador",
    "camera": "Câmera",
    "documentacao": "Documentação",
    "outros": "Outros",
}

SERVICE_ORDER_STATUSES = {
    "aberta": "Aberta",
    "aguardando_diagnostico": "Aguardando diagnóstico",
    "aguardando_aprovacao": "Aguardando aprovação",
    "aprovada": "Aprovada",
    "aguardando_pecas": "Aguardando peças",
    "em_execucao": "Em execução",
    "concluida": "Concluída",
    "cancelada": "Cancelada",
}

SERVICE_ORDER_PRIORITIES = {
    "baixa": "Baixa",
    "normal": "Normal",
    "alta": "Alta",
    "critica": "Crítica",
}

SERVICE_ORDER_ITEM_TYPES = {
    "peca": "Peça",
    "material": "Material",
    "servico": "Serviço",
    "mao_de_obra": "Mão de obra",
    "taxa": "Taxa",
    "outros": "Outros",
}

MAINTENANCE_PLAN_CATEGORIES = {
    "oleo_motor": "Óleo do motor",
    "filtro_oleo": "Filtro de óleo",
    "filtro_combustivel": "Filtro de combustível",
    "filtro_ar": "Filtro de ar",
    "sistema_freios": "Sistema de freios",
    "pneus": "Pneus",
    "alinhamento": "Alinhamento",
    "balanceamento": "Balanceamento",
    "correias": "Correias",
    "bateria": "Bateria",
    "suspensao": "Suspensão",
    "arrefecimento": "Arrefecimento",
    "transmissao": "Transmissão",
    "tacografo": "Tacógrafo",
    "revisao_geral": "Revisão geral",
    "outros": "Outros",
}

ATTACHMENT_TYPES = {
    "orcamento": "Orçamento",
    "nota_fiscal": "Nota fiscal",
    "recibo": "Recibo",
    "laudo": "Laudo",
    "foto_antes": "Foto antes do serviço",
    "foto_depois": "Foto depois do serviço",
    "video": "Vídeo curto",
    "garantia": "Garantia",
    "comprovante_pagamento": "Comprovante de pagamento",
    "outros": "Outros",
}

TERMINAL_ORDER_STATUSES = {"concluida", "cancelada"}
RESERVATION_ORDER_STATUSES = {"aprovada", "aguardando_pecas", "em_execucao"}
EDITABLE_ORDER_STATUSES = {"aberta", "aguardando_diagnostico", "aguardando_aprovacao"}
DEFAULT_MAINTENANCE_ALERT_DAYS = [90, 60, 30, 15, 7]


def clean_text(value, fallback: str = "") -> str:
    value = str(value if value is not None else "").strip()
    return value or fallback


def as_number(value, fallback: float = 0.0) -> float:
    try:
        return round(float(str(value).strip().replace(",", ".")), 2)
    except (TypeError, ValueError):
        return fallback


def as_integer(value, fallback: int = 0) -> int:
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return fallback


def as_bool(value) -> bool:
    return clean_text(value).lower() in {"1", "true", "sim", "yes", "on"}


def parse_iso_date(value, label: str, *, required: bool = False) -> str:
    text = clean_text(value)
    if not text:
        if required:
            raise ValueError(f"Informe {label}.")
        return ""
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label.capitalize()} inválida.") from exc
    return text


def next_record_id(records: Sequence[Mapping], prefix: str) -> str:
    used = []
    for record in records:
        match = re.search(r"(\d+)$", clean_text(record.get("id")))
        if match:
            used.append(int(match.group(1)))
    return f"{prefix}-{max(used, default=0) + 1:06d}"


def next_order_number(orders: Sequence[Mapping], opening_date: str) -> str:
    year = date.fromisoformat(opening_date).year
    pattern = re.compile(rf"^OS-FROTA-{year}-(\d{{6}})$")
    used = [int(match.group(1)) for order in orders if (match := pattern.match(clean_text(order.get("order_number"))))]
    return f"OS-FROTA-{year}-{max(used, default=0) + 1:06d}"


def normalize_choice(value, choices: Mapping[str, str], label: str, fallback: str = "") -> str:
    normalized = clean_text(value, fallback).lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "revisão_programada": "revisao_programada",
        "elétrica": "eletrica",
        "mecânica": "mecanica",
        "suspensão": "suspensao",
        "transmissão": "transmissao",
        "documentação": "documentacao",
        "aguardando_diagnóstico": "aguardando_diagnostico",
        "aguardando_aprovação": "aguardando_aprovacao",
        "aguardando_peças": "aguardando_pecas",
        "em_execução": "em_execucao",
        "concluída": "concluida",
        "crítica": "critica",
        "peça": "peca",
        "mão_de_obra": "mao_de_obra",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in choices:
        raise ValueError(f"{label} inválido.")
    return normalized


def build_service_order(
    form: Mapping,
    *,
    orders: list[dict],
    vehicles: list[dict],
    user_id: str,
    now: str,
) -> dict:
    order_id = clean_text(form.get("id") or form.get("service_order_id"))
    current = next((item for item in orders if clean_text(item.get("id")) == order_id), {}) if order_id else {}
    if current and clean_text(current.get("status")) in TERMINAL_ORDER_STATUSES:
        raise ValueError("Ordens concluídas ou canceladas não podem ser editadas. Registre uma revisão complementar.")

    vehicle_id = clean_text(form.get("vehicle_id") or current.get("vehicle_id"))
    vehicle = next(
        (item for item in vehicles if clean_text(item.get("vehicle_id") or item.get("id")) == vehicle_id and not clean_text(item.get("deleted_at"))),
        None,
    )
    if not vehicle:
        raise ValueError("Selecione um veículo ativo.")
    opening_date = parse_iso_date(form.get("opening_date") or current.get("opening_date") or now[:10], "a data de abertura", required=True)
    expected_completion = parse_iso_date(form.get("expected_completion_date") or current.get("expected_completion_date"), "a previsão de conclusão")
    reported_problem = clean_text(form.get("reported_problem") or current.get("reported_problem"))
    if not reported_problem:
        raise ValueError("Descreva o problema relatado ou a manutenção preventiva solicitada.")
    entry_mileage = as_integer(form.get("entry_mileage", current.get("entry_mileage", vehicle.get("current_mileage", 0))), -1)
    if entry_mileage < 0:
        raise ValueError("A quilometragem de entrada não pode ser negativa.")

    order_number = clean_text(current.get("order_number")) or next_order_number(orders, opening_date)
    if any(clean_text(item.get("order_number")) == order_number and clean_text(item.get("id")) != order_id for item in orders):
        raise ValueError(f"A numeração {order_number} já existe.")
    created_at = clean_text(current.get("created_at")) or now
    return {
        **current,
        "id": order_id or next_record_id(orders, "OSF"),
        "vehicle_id": vehicle_id,
        "order_number": order_number,
        "maintenance_type": normalize_choice(form.get("maintenance_type") or current.get("maintenance_type"), MAINTENANCE_TYPES, "Tipo de manutenção", "corretiva"),
        "maintenance_plan_id": clean_text(form.get("maintenance_plan_id") or current.get("maintenance_plan_id")),
        "status": clean_text(current.get("status"), "aberta"),
        "priority": normalize_choice(form.get("priority") or current.get("priority"), SERVICE_ORDER_PRIORITIES, "Prioridade", "normal"),
        "reported_problem": reported_problem,
        "diagnosis": clean_text(form.get("diagnosis") or current.get("diagnosis")),
        "services_performed": clean_text(current.get("services_performed")),
        "opening_date": opening_date,
        "expected_completion_date": expected_completion,
        "completion_date": clean_text(current.get("completion_date")),
        "entry_mileage": entry_mileage,
        "exit_mileage": current.get("exit_mileage"),
        "supplier_id": clean_text(form.get("supplier_id") or current.get("supplier_id")),
        "supplier_name": clean_text(form.get("supplier_name") or current.get("supplier_name")),
        "internal_responsible_user_id": clean_text(form.get("internal_responsible_user_id") or current.get("internal_responsible_user_id")),
        "driver_id": clean_text(form.get("driver_id") or current.get("driver_id")),
        "labor_cost": max(as_number(current.get("labor_cost")), 0),
        "parts_cost": max(as_number(current.get("parts_cost")), 0),
        "additional_cost": max(as_number(current.get("additional_cost")), 0),
        "discount": max(as_number(form.get("discount", current.get("discount", 0))), 0),
        "total_cost": max(as_number(current.get("total_cost")), 0),
        "total_override_justification": clean_text(current.get("total_override_justification")),
        "downtime_hours": max(as_number(current.get("downtime_hours")), 0),
        "warranty_expiration_date": parse_iso_date(form.get("warranty_expiration_date") or current.get("warranty_expiration_date"), "o vencimento da garantia"),
        "next_service_date": parse_iso_date(form.get("next_service_date") or current.get("next_service_date"), "a próxima manutenção"),
        "next_service_mileage": max(as_integer(form.get("next_service_mileage", current.get("next_service_mileage", 0))), 0) or None,
        "notes": clean_text(form.get("notes") or current.get("notes")),
        "created_by": clean_text(current.get("created_by")) or user_id,
        "created_at": created_at,
        "updated_at": now,
        "deleted_at": clean_text(current.get("deleted_at")),
    }


def build_service_order_item(
    form: Mapping,
    *,
    items: list[dict],
    order: Mapping,
    warehouse_items: list[dict],
    now: str,
) -> dict:
    if clean_text(order.get("status")) not in EDITABLE_ORDER_STATUSES:
        raise ValueError("Itens só podem ser alterados antes da aprovação da ordem.")
    item_id = clean_text(form.get("id") or form.get("item_id"))
    current = next((item for item in items if clean_text(item.get("id")) == item_id), {}) if item_id else {}
    item_type = normalize_choice(form.get("item_type") or current.get("item_type"), SERVICE_ORDER_ITEM_TYPES, "Tipo de item", "peca")
    inventory_item_id = clean_text(form.get("inventory_item_id") or current.get("inventory_item_id"))
    inventory_item = next((item for item in warehouse_items if clean_text(item.get("id")) == inventory_item_id), None) if inventory_item_id else None
    if inventory_item_id and not inventory_item:
        raise ValueError("O produto selecionado não existe no almoxarifado.")
    if inventory_item_id and any(
        clean_text(item.get("service_order_id")) == clean_text(order.get("id"))
        and clean_text(item.get("inventory_item_id")) == inventory_item_id
        and clean_text(item.get("id")) != item_id
        and not clean_text(item.get("deleted_at"))
        for item in items
    ):
        raise ValueError("Este produto já foi incluído na ordem. Ajuste a quantidade do item existente.")
    description = clean_text(form.get("description") or current.get("description") or (inventory_item or {}).get("name"))
    if not description:
        raise ValueError("Informe a descrição do item ou serviço.")
    quantity = as_number(form.get("quantity", current.get("quantity", 0)), -1)
    unit_cost = as_number(form.get("unit_cost", current.get("unit_cost", 0)), -1)
    if quantity <= 0:
        raise ValueError("A quantidade deve ser maior que zero.")
    if unit_cost < 0:
        raise ValueError("O custo unitário não pode ser negativo.")
    warranty_days = as_integer(form.get("warranty_days", current.get("warranty_days", 0)), -1)
    if warranty_days < 0:
        raise ValueError("A garantia não pode ter dias negativos.")
    return {
        **current,
        "id": item_id or next_record_id(items, "OSI"),
        "service_order_id": clean_text(order.get("id")),
        "item_type": item_type,
        "description": description,
        "quantity": quantity,
        "unit": clean_text(form.get("unit") or current.get("unit") or (inventory_item or {}).get("unit"), "un"),
        "unit_cost": unit_cost,
        "total_cost": round(quantity * unit_cost, 2),
        "inventory_item_id": inventory_item_id,
        "supplier_id": clean_text(form.get("supplier_id") or current.get("supplier_id")),
        "warranty_days": warranty_days,
        "notes": clean_text(form.get("notes") or current.get("notes")),
        "created_at": clean_text(current.get("created_at")) or now,
        "updated_at": now,
        "deleted_at": clean_text(current.get("deleted_at")),
    }


def calculate_order_costs(
    order: Mapping,
    items: Sequence[Mapping],
    *,
    manual_total=None,
    override_justification: str = "",
    can_override: bool = False,
) -> dict:
    active = [item for item in items if clean_text(item.get("service_order_id")) == clean_text(order.get("id")) and not clean_text(item.get("deleted_at"))]
    parts_cost = round(sum(as_number(item.get("total_cost")) for item in active if clean_text(item.get("item_type")) in {"peca", "material"}), 2)
    labor_cost = round(sum(as_number(item.get("total_cost")) for item in active if clean_text(item.get("item_type")) == "mao_de_obra"), 2)
    additional_cost = round(sum(as_number(item.get("total_cost")) for item in active if clean_text(item.get("item_type")) in {"servico", "taxa", "outros"}), 2)
    discount = max(as_number(order.get("discount")), 0)
    calculated = max(round(parts_cost + labor_cost + additional_cost - discount, 2), 0)
    justification = clean_text(override_justification or order.get("total_override_justification"))
    total = calculated
    if clean_text(manual_total) and as_number(manual_total, calculated) != calculated:
        if not can_override:
            raise PermissionError("Somente administrador pode substituir o total calculado.")
        if len(justification) < 10:
            raise ValueError("Informe uma justificativa administrativa com pelo menos 10 caracteres.")
        total = as_number(manual_total, -1)
        if total < 0:
            raise ValueError("O valor final não pode ser negativo.")
    else:
        justification = ""
    return {
        **dict(order),
        "parts_cost": parts_cost,
        "labor_cost": labor_cost,
        "additional_cost": additional_cost,
        "discount": discount,
        "total_cost": total,
        "calculated_total_cost": calculated,
        "total_override_justification": justification,
    }


def build_maintenance_plan(form: Mapping, *, plans: list[dict], vehicles: list[dict], now: str) -> dict:
    plan_id = clean_text(form.get("id") or form.get("plan_id"))
    current = next((item for item in plans if clean_text(item.get("id")) == plan_id), {}) if plan_id else {}
    vehicle_id = clean_text(form.get("vehicle_id") or current.get("vehicle_id"))
    if not any(clean_text(item.get("vehicle_id") or item.get("id")) == vehicle_id and not clean_text(item.get("deleted_at")) for item in vehicles):
        raise ValueError("Selecione um veículo ativo para o plano.")
    title = clean_text(form.get("title") or current.get("title"))
    if not title:
        raise ValueError("Informe o título do plano preventivo.")
    interval_mileage = as_integer(form.get("interval_mileage", current.get("interval_mileage", 0)))
    interval_days = as_integer(form.get("interval_days", current.get("interval_days", 0)))
    if interval_mileage <= 0 and interval_days <= 0:
        raise ValueError("Informe ao menos um intervalo baseado no manual do veículo ou no plano interno.")
    warning_mileage = as_integer(form.get("warning_mileage", current.get("warning_mileage", 0)))
    warning_days = as_integer(form.get("warning_days", current.get("warning_days", 0)))
    if warning_mileage < 0 or warning_days < 0:
        raise ValueError("Os alertas não podem ser negativos.")
    if interval_mileage > 0 and warning_mileage >= interval_mileage:
        raise ValueError("O alerta de quilometragem deve ser menor que o intervalo.")
    if interval_days > 0 and warning_days >= interval_days:
        raise ValueError("O alerta de dias deve ser menor que o intervalo.")
    last_date = parse_iso_date(form.get("last_service_date") or current.get("last_service_date"), "a data do último serviço")
    last_mileage = max(as_integer(form.get("last_service_mileage", current.get("last_service_mileage", 0))), 0) or None
    next_date = parse_iso_date(form.get("next_service_date") or current.get("next_service_date"), "a data da próxima revisão")
    next_mileage = max(as_integer(form.get("next_service_mileage", current.get("next_service_mileage", 0))), 0) or None
    if last_date and interval_days > 0:
        next_date = (date.fromisoformat(last_date) + timedelta(days=interval_days)).isoformat()
    if last_mileage is not None and interval_mileage > 0:
        next_mileage = last_mileage + interval_mileage
    return {
        **current,
        "id": plan_id or next_record_id(plans, "PMP"),
        "vehicle_id": vehicle_id,
        "title": title,
        "category": normalize_choice(form.get("category") or current.get("category"), MAINTENANCE_PLAN_CATEGORIES, "Categoria", "outros"),
        "description": clean_text(form.get("description") or current.get("description")),
        "interval_mileage": interval_mileage or None,
        "interval_days": interval_days or None,
        "warning_mileage": warning_mileage,
        "warning_days": warning_days,
        "last_service_date": last_date,
        "last_service_mileage": last_mileage,
        "next_service_date": next_date,
        "next_service_mileage": next_mileage,
        "priority": normalize_choice(form.get("priority") or current.get("priority"), SERVICE_ORDER_PRIORITIES, "Prioridade", "normal"),
        "is_active": as_bool(form.get("is_active", current.get("is_active", True))),
        "instructions": clean_text(form.get("instructions") or current.get("instructions")),
        "created_at": clean_text(current.get("created_at")) or now,
        "updated_at": now,
        "deleted_at": clean_text(current.get("deleted_at")),
    }


def maintenance_plan_status(plan: Mapping, *, current_mileage: int, today: date | None = None, has_open_order: bool = False) -> dict:
    today = today or date.today()
    if has_open_order:
        return {"status": "em_manutencao", "label": "Em manutenção", "due_by": "ordem", "days_remaining": None, "mileage_remaining": None}
    next_date = clean_text(plan.get("next_service_date"))
    next_mileage = as_integer(plan.get("next_service_mileage"), 0) or None
    days_remaining = (date.fromisoformat(next_date) - today).days if next_date else None
    mileage_remaining = next_mileage - current_mileage if next_mileage is not None else None
    due_candidates = []
    if days_remaining is not None:
        due_candidates.append((days_remaining <= 0, days_remaining, "data"))
    if mileage_remaining is not None:
        due_candidates.append((mileage_remaining <= 0, mileage_remaining, "quilometragem"))
    if any(item[0] for item in due_candidates):
        due_by = next((item[2] for item in due_candidates if item[0]), "data")
        return {"status": "vencido", "label": "Vencido", "due_by": due_by, "days_remaining": days_remaining, "mileage_remaining": mileage_remaining}
    warning_days = as_integer(plan.get("warning_days"), 0)
    warning_mileage = as_integer(plan.get("warning_mileage"), 0)
    critical_date = days_remaining is not None and warning_days > 0 and days_remaining <= max(1, warning_days // 2)
    critical_mileage = mileage_remaining is not None and warning_mileage > 0 and mileage_remaining <= max(1, warning_mileage // 2)
    warning_date = days_remaining is not None and warning_days > 0 and days_remaining <= warning_days
    warning_mileage_reached = mileage_remaining is not None and warning_mileage > 0 and mileage_remaining <= warning_mileage
    if critical_date or critical_mileage:
        status = "proximo_vencimento"
        label = "Próximo do vencimento"
    elif warning_date or warning_mileage_reached:
        status = "atencao"
        label = "Atenção"
    elif not next_date and next_mileage is None and (plan.get("last_service_date") or plan.get("last_service_mileage") is not None):
        status = "concluido"
        label = "Concluído"
    else:
        status = "em_dia"
        label = "Em dia"
    due_by = "data" if days_remaining is not None and (mileage_remaining is None or days_remaining <= mileage_remaining) else "quilometragem"
    return {"status": status, "label": label, "due_by": due_by, "days_remaining": days_remaining, "mileage_remaining": mileage_remaining}


def update_plan_after_service(plan: Mapping, *, service_date: str, mileage: int, now: str) -> dict:
    interval_days = as_integer(plan.get("interval_days"), 0)
    interval_mileage = as_integer(plan.get("interval_mileage"), 0)
    return {
        **dict(plan),
        "last_service_date": service_date,
        "last_service_mileage": mileage,
        "next_service_date": (date.fromisoformat(service_date) + timedelta(days=interval_days)).isoformat() if interval_days > 0 else "",
        "next_service_mileage": mileage + interval_mileage if interval_mileage > 0 else None,
        "updated_at": now,
    }


def available_inventory_quantity(item_id: str, warehouse_items: Sequence[Mapping], reservations: Sequence[Mapping], *, exclude_order_id: str = "") -> float:
    item = next((record for record in warehouse_items if clean_text(record.get("id")) == item_id), {})
    physical = as_number(item.get("quantity_current"))
    reserved = sum(
        as_number(record.get("quantity"))
        for record in reservations
        if clean_text(record.get("inventory_item_id")) == item_id
        and clean_text(record.get("status")) == "reservada"
        and clean_text(record.get("service_order_id")) != exclude_order_id
    )
    return round(physical - reserved, 2)


def _warehouse_movement(movements: Sequence[Mapping], *, order: Mapping, item: Mapping, inventory: Mapping, user: Mapping, now: str, movement_type: str, quantity_changed: float, previous_balance: float, final_balance: float) -> dict:
    return {
        "id": next_record_id(movements, "MOV"),
        "item_id": clean_text(inventory.get("id")),
        "item_name": clean_text(inventory.get("name")),
        "movement_type": movement_type,
        "quantity_changed": quantity_changed,
        "reserved_quantity": as_number(item.get("quantity")),
        "previous_balance": previous_balance,
        "final_balance": final_balance,
        "observation": f"{clean_text(order.get('order_number'))} - {clean_text(order.get('reported_problem'))}",
        "vehicle_id": clean_text(order.get("vehicle_id")),
        "service_order_id": clean_text(order.get("id")),
        "service_order_number": clean_text(order.get("order_number")),
        "user_id": clean_text(user.get("id")),
        "user_name": clean_text(user.get("nome")),
        "user_email": clean_text(user.get("email")),
        "created_at": now,
    }


def reserve_inventory(order: Mapping, items: Sequence[Mapping], warehouse_items: Sequence[Mapping], reservations: Sequence[Mapping], movements: Sequence[Mapping], *, user: Mapping, now: str) -> tuple[list[dict], list[dict]]:
    updated_reservations = [dict(item) for item in reservations]
    updated_movements = [dict(item) for item in movements]
    order_items = [item for item in items if clean_text(item.get("service_order_id")) == clean_text(order.get("id")) and clean_text(item.get("inventory_item_id")) and not clean_text(item.get("deleted_at"))]
    seen: set[str] = set()
    for order_item in order_items:
        inventory_id = clean_text(order_item.get("inventory_item_id"))
        if inventory_id in seen:
            raise ValueError("A ordem possui produto duplicado do almoxarifado.")
        seen.add(inventory_id)
        existing = next((record for record in updated_reservations if clean_text(record.get("service_order_item_id")) == clean_text(order_item.get("id")) and clean_text(record.get("status")) == "reservada"), None)
        if existing:
            continue
        available = available_inventory_quantity(inventory_id, warehouse_items, updated_reservations, exclude_order_id=clean_text(order.get("id")))
        quantity = as_number(order_item.get("quantity"))
        if available < quantity:
            raise ValueError(f"Estoque disponível insuficiente para {clean_text(order_item.get('description'))}: disponível {available}.")
        inventory = next((record for record in warehouse_items if clean_text(record.get("id")) == inventory_id), None)
        if not inventory:
            raise ValueError("Produto da ordem não encontrado no almoxarifado.")
        reservation = {
            "id": next_record_id(updated_reservations, "RES"),
            "service_order_id": clean_text(order.get("id")),
            "service_order_item_id": clean_text(order_item.get("id")),
            "inventory_item_id": inventory_id,
            "quantity": quantity,
            "status": "reservada",
            "reserved_by": clean_text(user.get("id")),
            "reserved_at": now,
            "consumed_by": "",
            "consumed_at": "",
            "released_by": "",
            "released_at": "",
            "warehouse_movement_id": "",
            "created_at": now,
            "updated_at": now,
        }
        movement = _warehouse_movement(updated_movements, order=order, item=order_item, inventory=inventory, user=user, now=now, movement_type="reserva frota", quantity_changed=0, previous_balance=as_number(inventory.get("quantity_current")), final_balance=as_number(inventory.get("quantity_current")))
        reservation["warehouse_movement_id"] = movement["id"]
        updated_reservations.append(reservation)
        updated_movements.append(movement)
    return updated_reservations, updated_movements


def release_inventory(order: Mapping, reservations: Sequence[Mapping], warehouse_items: Sequence[Mapping], movements: Sequence[Mapping], *, user: Mapping, now: str) -> tuple[list[dict], list[dict]]:
    updated = [dict(item) for item in reservations]
    updated_movements = [dict(item) for item in movements]
    for reservation in updated:
        if clean_text(reservation.get("service_order_id")) != clean_text(order.get("id")) or clean_text(reservation.get("status")) != "reservada":
            continue
        inventory = next((item for item in warehouse_items if clean_text(item.get("id")) == clean_text(reservation.get("inventory_item_id"))), {})
        pseudo_item = {"quantity": reservation.get("quantity"), "description": inventory.get("name")}
        movement = _warehouse_movement(updated_movements, order=order, item=pseudo_item, inventory=inventory, user=user, now=now, movement_type="liberacao reserva frota", quantity_changed=0, previous_balance=as_number(inventory.get("quantity_current")), final_balance=as_number(inventory.get("quantity_current")))
        reservation.update({"status": "liberada", "released_by": clean_text(user.get("id")), "released_at": now, "updated_at": now, "warehouse_movement_id": movement["id"]})
        updated_movements.append(movement)
    return updated, updated_movements


def consume_inventory(order: Mapping, reservations: Sequence[Mapping], warehouse_items: Sequence[Mapping], movements: Sequence[Mapping], *, user: Mapping, now: str, allow_negative: bool = False) -> tuple[list[dict], list[dict], list[dict]]:
    updated_reservations = [dict(item) for item in reservations]
    updated_items = [dict(item) for item in warehouse_items]
    updated_movements = [dict(item) for item in movements]
    for reservation in updated_reservations:
        if clean_text(reservation.get("service_order_id")) != clean_text(order.get("id")) or clean_text(reservation.get("status")) != "reservada":
            continue
        inventory = next((item for item in updated_items if clean_text(item.get("id")) == clean_text(reservation.get("inventory_item_id"))), None)
        if not inventory:
            raise ValueError("Produto reservado não encontrado no almoxarifado.")
        previous = as_number(inventory.get("quantity_current"))
        quantity = as_number(reservation.get("quantity"))
        final = round(previous - quantity, 2)
        if final < 0 and not allow_negative:
            raise ValueError(f"A baixa deixaria {clean_text(inventory.get('name'))} com estoque negativo.")
        inventory["quantity_current"] = final
        inventory["updated_at"] = now
        pseudo_item = {"quantity": quantity, "description": inventory.get("name")}
        movement = _warehouse_movement(updated_movements, order=order, item=pseudo_item, inventory=inventory, user=user, now=now, movement_type="saida frota", quantity_changed=quantity, previous_balance=previous, final_balance=final)
        reservation.update({"status": "consumida", "consumed_by": clean_text(user.get("id")), "consumed_at": now, "updated_at": now, "warehouse_movement_id": movement["id"]})
        updated_movements.append(movement)
    return updated_reservations, updated_items, updated_movements


def validate_completion(order: Mapping, *, services_performed: str, exit_mileage, current_mileage: int, allow_mileage_correction: bool, correction_justification: str) -> tuple[int, str]:
    services = clean_text(services_performed)
    if not services:
        raise ValueError("Descreva os serviços realizados antes de concluir.")
    mileage = as_integer(exit_mileage, -1)
    if mileage < 0:
        raise ValueError("Informe a quilometragem de saída.")
    minimum = max(as_integer(order.get("entry_mileage")), current_mileage)
    justification = clean_text(correction_justification)
    if mileage < minimum:
        if not allow_mileage_correction:
            raise PermissionError("A quilometragem não pode regredir sem correção administrativa autorizada.")
        if len(justification) < 10:
            raise ValueError("Informe uma justificativa para corrigir a quilometragem.")
    return mileage, justification


def downtime_hours(opening_date: str, completion_date: str) -> float:
    start = datetime.combine(date.fromisoformat(opening_date), datetime.min.time())
    end = datetime.combine(date.fromisoformat(completion_date), datetime.min.time())
    return max(round((end - start).total_seconds() / 3600, 2), 0)


def build_maintenance_dashboard(
    *,
    orders: Sequence[Mapping],
    items: Sequence[Mapping],
    plans: Sequence[Mapping],
    attachments: Sequence[Mapping],
    reservations: Sequence[Mapping],
    vehicles: Sequence[Mapping],
    warehouse_items: Sequence[Mapping],
    can_view_costs: bool,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    vehicle_map = {clean_text(item.get("vehicle_id") or item.get("id")): item for item in vehicles}
    enriched_orders = []
    for order in orders:
        if clean_text(order.get("deleted_at")):
            continue
        vehicle = vehicle_map.get(clean_text(order.get("vehicle_id")), {})
        order_items = [dict(item) for item in items if clean_text(item.get("service_order_id")) == clean_text(order.get("id")) and not clean_text(item.get("deleted_at"))]
        enriched = {
            **dict(order),
            "vehicle_plate": clean_text(vehicle.get("plate")),
            "vehicle_label": f"{clean_text(vehicle.get('plate'))} · {clean_text(vehicle.get('brand'))} {clean_text(vehicle.get('model'))}".strip(),
            "maintenance_type_label": MAINTENANCE_TYPES.get(clean_text(order.get("maintenance_type")), clean_text(order.get("maintenance_type"))),
            "status_label": SERVICE_ORDER_STATUSES.get(clean_text(order.get("status")), clean_text(order.get("status"))),
            "priority_label": SERVICE_ORDER_PRIORITIES.get(clean_text(order.get("priority")), clean_text(order.get("priority"))),
            "items": order_items,
            "attachments": [dict(item) for item in attachments if clean_text(item.get("service_order_id")) == clean_text(order.get("id")) and not clean_text(item.get("deleted_at"))],
            "reservations": [dict(item) for item in reservations if clean_text(item.get("service_order_id")) == clean_text(order.get("id"))],
        }
        if not can_view_costs:
            for key in ("labor_cost", "parts_cost", "additional_cost", "discount", "total_cost", "calculated_total_cost", "total_override_justification"):
                enriched.pop(key, None)
            for order_item in enriched["items"]:
                order_item.pop("unit_cost", None)
                order_item.pop("total_cost", None)
        enriched_orders.append(enriched)
    enriched_orders.sort(key=lambda item: (clean_text(item.get("opening_date")), clean_text(item.get("order_number"))), reverse=True)

    enriched_plans = []
    for plan in plans:
        if clean_text(plan.get("deleted_at")) or not as_bool(plan.get("is_active", True)):
            continue
        vehicle = vehicle_map.get(clean_text(plan.get("vehicle_id")), {})
        has_open = any(clean_text(order.get("maintenance_plan_id")) == clean_text(plan.get("id")) and clean_text(order.get("status")) not in TERMINAL_ORDER_STATUSES and not clean_text(order.get("deleted_at")) for order in orders)
        status = maintenance_plan_status(plan, current_mileage=as_integer(vehicle.get("current_mileage")), today=today, has_open_order=has_open)
        enriched_plans.append({**dict(plan), **status, "vehicle_plate": clean_text(vehicle.get("plate")), "category_label": MAINTENANCE_PLAN_CATEGORIES.get(clean_text(plan.get("category")), clean_text(plan.get("category")))})
    status_order = {"vencido": 0, "proximo_vencimento": 1, "atencao": 2, "em_manutencao": 3, "em_dia": 4, "concluido": 5}
    enriched_plans.sort(key=lambda item: (status_order.get(clean_text(item.get("status")), 9), clean_text(item.get("next_service_date")) or "9999-12-31"))

    active_orders = [item for item in enriched_orders if clean_text(item.get("status")) not in TERMINAL_ORDER_STATUSES]
    completed = [item for item in enriched_orders if clean_text(item.get("status")) == "concluida"]
    reports = {
        "maintenance_by_vehicle": _group_count(enriched_orders, "vehicle_plate"),
        "preventive_vs_corrective": _group_count(enriched_orders, "maintenance_type_label"),
        "blocked_vehicles": [dict(item) for item in vehicles if clean_text(item.get("status")) in {"bloqueado", "em_manutencao"}],
        "overdue_vehicles": [item for item in enriched_plans if item.get("status") == "vencido"],
        "parts_used": _group_item_quantity(items),
        "suppliers": _group_count(enriched_orders, "supplier_name"),
        "downtime_hours": round(sum(as_number(item.get("downtime_hours")) for item in completed), 2),
    }
    if can_view_costs:
        reports["total_cost"] = round(sum(as_number(item.get("total_cost")) for item in completed), 2)
        reports["cost_by_vehicle"] = _group_sum(completed, "vehicle_plate", "total_cost")
        monthly = [{**item, "cost_period": clean_text(item.get("completion_date") or item.get("opening_date"))[:7] or "Não informado"} for item in completed]
        reports["cost_by_period"] = _group_sum(monthly, "cost_period", "total_cost")
    return {
        "orders": enriched_orders,
        "active_orders": active_orders,
        "plans": enriched_plans,
        "warehouse_items": [dict(item) for item in warehouse_items if clean_text(item.get("status"), "ativo") == "ativo"],
        "counts": {
            "orders": len(enriched_orders),
            "active": len(active_orders),
            "critical": sum(1 for item in active_orders if clean_text(item.get("priority")) == "critica"),
            "completed": len(completed),
            "overdue_plans": sum(1 for item in enriched_plans if item.get("status") == "vencido"),
        },
        "reports": reports,
        "maintenance_types": MAINTENANCE_TYPES,
        "statuses": SERVICE_ORDER_STATUSES,
        "priorities": SERVICE_ORDER_PRIORITIES,
        "item_types": SERVICE_ORDER_ITEM_TYPES,
        "plan_categories": MAINTENANCE_PLAN_CATEGORIES,
        "attachment_types": ATTACHMENT_TYPES,
    }


def build_vehicle_history(*, vehicle_id: str, orders: Sequence[Mapping], mileage: Sequence[Mapping], documents: Sequence[Mapping], attachments: Sequence[Mapping], audit_logs: Sequence[Mapping]) -> list[dict]:
    events: list[dict] = []
    order_map = {clean_text(item.get("id")): item for item in orders}
    for item in orders:
        if clean_text(item.get("vehicle_id")) != vehicle_id:
            continue
        events.append({"date": clean_text(item.get("completion_date") or item.get("opening_date")), "type": "manutencao", "title": clean_text(item.get("order_number")), "detail": clean_text(item.get("reported_problem")), "user_id": clean_text(item.get("created_by")), "order_number": clean_text(item.get("order_number")), "maintenance_type": clean_text(item.get("maintenance_type"))})
    for item in mileage:
        if clean_text(item.get("vehicle_id")) == vehicle_id:
            events.append({"date": clean_text(item.get("record_date") or item.get("created_at"))[:10], "type": "quilometragem", "title": f"{as_integer(item.get('mileage'))} km", "detail": clean_text(item.get("source")), "user_id": clean_text(item.get("user_id")), "order_number": clean_text(item.get("service_order_number"))})
    for item in documents:
        if clean_text(item.get("vehicle_id")) == vehicle_id:
            events.append({"date": clean_text(item.get("created_at"))[:10], "type": "documento", "title": clean_text(item.get("document_type_label") or item.get("document_type")), "detail": clean_text(item.get("status")), "user_id": clean_text(item.get("responsible_user_id"))})
    for item in attachments:
        if clean_text(item.get("vehicle_id")) == vehicle_id and not clean_text(item.get("deleted_at")):
            order = order_map.get(clean_text(item.get("service_order_id")), {})
            events.append({"date": clean_text(item.get("created_at"))[:10], "type": "anexo", "title": clean_text(item.get("original_name")), "detail": clean_text(item.get("attachment_type")), "user_id": clean_text(item.get("uploaded_by")), "order_number": clean_text(order.get("order_number"))})
    for item in audit_logs:
        if clean_text(item.get("vehicle_id") or item.get("target_id")) == vehicle_id:
            events.append({"date": clean_text(item.get("created_at"))[:10], "type": clean_text(item.get("action"), "alteracao"), "title": clean_text(item.get("action"), "Alteração"), "detail": clean_text(item.get("detail")), "user_id": clean_text(item.get("user_id"))})
    return sorted(events, key=lambda item: clean_text(item.get("date")), reverse=True)


def _group_count(records: Sequence[Mapping], key: str) -> list[dict]:
    grouped: dict[str, int] = {}
    for record in records:
        label = clean_text(record.get(key), "Não informado")
        grouped[label] = grouped.get(label, 0) + 1
    return [{"label": label, "count": count} for label, count in sorted(grouped.items(), key=lambda item: (-item[1], item[0]))]


def _group_sum(records: Sequence[Mapping], key: str, value_key: str) -> list[dict]:
    grouped: dict[str, float] = {}
    for record in records:
        label = clean_text(record.get(key), "Não informado")
        grouped[label] = round(grouped.get(label, 0) + as_number(record.get(value_key)), 2)
    return [{"label": label, "value": value} for label, value in sorted(grouped.items(), key=lambda item: (-item[1], item[0]))]


def _group_item_quantity(items: Sequence[Mapping]) -> list[dict]:
    grouped: dict[str, float] = {}
    for item in items:
        if clean_text(item.get("item_type")) not in {"peca", "material"} or clean_text(item.get("deleted_at")):
            continue
        label = clean_text(item.get("description"), "Não informado")
        grouped[label] = round(grouped.get(label, 0) + as_number(item.get("quantity")), 2)
    return [{"label": label, "quantity": quantity} for label, quantity in sorted(grouped.items(), key=lambda item: (-item[1], item[0]))]
