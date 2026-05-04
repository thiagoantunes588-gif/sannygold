from __future__ import annotations

from collections import defaultdict


def _round2(value: float) -> float:
    return round(float(value or 0.0), 2)


def _margin_pct(profit: float, revenue: float) -> float:
    return _round2((profit / revenue) * 100) if revenue else 0.0


def build_executive_dashboard(
    *,
    clients: list[dict],
    events: list[dict],
    route_history: list[dict],
    financial_management: dict,
    future_dashboard: dict,
    security_posture: dict,
) -> dict:
    active_events = [event for event in events if str(event.get("status") or "") in {"planejado", "em_execucao"}]
    recurring_events = [event for event in events if str(event.get("recurrence_status") or "ativo") == "ativo"]
    overdue_amount = _round2(sum(float(item.get("amount") or 0.0) for item in financial_management.get("receivables_overdue") or []))
    soon_amount = _round2(sum(float(item.get("amount") or 0.0) for item in financial_management.get("receivables_due_soon") or []))
    projected_balance = _round2(financial_management.get("projected_balance") or 0.0)
    expected_in = _round2(financial_management.get("expected_in") or 0.0)

    top_clients_map: dict[str, dict] = defaultdict(lambda: {"client_name": "Cliente", "revenue": 0.0, "profit": 0.0, "events": 0})
    for item in route_history:
        seen_clients: set[str] = set()
        for client in item.get("financial_clients") or []:
            key = str(client.get("client_id") or client.get("client_name") or "cliente")
            bucket = top_clients_map[key]
            bucket["client_name"] = str(client.get("client_name") or bucket["client_name"])
            bucket["revenue"] += float(client.get("revenue") or 0.0)
            bucket["profit"] += float(client.get("profit") or 0.0)
            if key not in seen_clients:
                bucket["events"] += 1
                seen_clients.add(key)

    top_clients = sorted(top_clients_map.values(), key=lambda item: item["revenue"], reverse=True)[:5]
    for item in top_clients:
        item["revenue"] = _round2(item["revenue"])
        item["profit"] = _round2(item["profit"])
        item["margin_pct"] = _margin_pct(item["profit"], item["revenue"])

    priorities = []
    if overdue_amount > 0:
        priorities.append({"level": "danger", "title": "Cobrança atrasada", "detail": f"Há {overdue_amount:.2f} em valores vencidos para tratar."})
    if projected_balance < 0:
        priorities.append({"level": "danger", "title": "Saldo projetado negativo", "detail": "A operação projetada está consumindo mais caixa do que recebe no período."})
    if (future_dashboard.get("alerts") or []):
        priorities.append({"level": "warning", "title": "Capacidade futura sob pressão", "detail": f"{len(future_dashboard.get('alerts') or [])} alerta(s) foram gerados na agenda futura."})
    if security_posture.get("critical_count") or security_posture.get("attention_count"):
        priorities.append({"level": "warning", "title": "Governança requer atenção", "detail": "Há pendências de segurança ou operação administrativa no sistema."})
    if not priorities:
        priorities.append({"level": "ready", "title": "Painel executivo estável", "detail": "Não há alertas executivos relevantes no momento."})

    return {
        "headline": {
            "clients": len(clients),
            "active_events": len(active_events),
            "recurring_events": len(recurring_events),
            "projected_balance": projected_balance,
            "expected_in": expected_in,
            "overdue_amount": overdue_amount,
            "due_soon_amount": soon_amount,
        },
        "priorities": priorities[:4],
        "top_clients": top_clients,
        "pipeline": {
            "planned": sum(1 for event in events if str(event.get("status") or "") == "planejado"),
            "in_progress": sum(1 for event in events if str(event.get("status") or "") == "em_execucao"),
            "finished": sum(1 for event in events if str(event.get("status") or "") == "finalizado"),
        },
        "governance": {
            "security_attention": security_posture.get("attention_count") or 0,
            "security_critical": security_posture.get("critical_count") or 0,
            "password_rotation_pending": security_posture.get("password_rotation_pending") or 0,
        },
    }
