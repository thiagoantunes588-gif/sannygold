from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

from flask import abort, flash, redirect, render_template, request, send_from_directory, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from app.services.fleet_maintenance import (
    ATTACHMENT_TYPES,
    SERVICE_ORDER_STATUSES,
    TERMINAL_ORDER_STATUSES,
    build_maintenance_dashboard,
    build_maintenance_plan,
    build_service_order,
    build_service_order_item,
    build_vehicle_history,
    calculate_order_costs,
    consume_inventory,
    downtime_hours,
    release_inventory,
    reserve_inventory,
    update_plan_after_service,
    validate_completion,
)


def register_fleet_routes(app, deps) -> None:
    def document_audit_payload(record):
        if not isinstance(record, dict):
            return record
        return {
            **record,
            "number": "[protegido]" if record.get("number") else "",
            "document_number": "[protegido]" if record.get("document_number") else "",
            "file_url": "[protegido]" if record.get("file_url") else "",
            "file_path": "[protegido]" if record.get("file_path") else "",
        }

    def enforce_permission(permission: str) -> None:
        if deps.has_permission(deps.current_user(), permission):
            return
        deps.record_audit(
            "access_denied",
            "permissions",
            permission,
            f"Tentativa de alteração da frota sem permissão para {permission}.",
            after={"permission": permission, "path": request.path, "method": request.method},
        )
        abort(403)

    def maintenance_redirect(order_id: str = "", vehicle_id: str = ""):
        query = {}
        if order_id:
            query["order"] = order_id
        if vehicle_id:
            query["vehicle"] = vehicle_id
        return redirect(url_for("fleet_maintenance_home", **query))

    def maintenance_state() -> dict:
        return {
            "orders": deps.load_fleet_service_orders(include_archived=True),
            "items": deps.load_fleet_service_order_items(include_archived=True),
            "plans": deps.load_vehicle_maintenance_plans(include_archived=True),
            "attachments": deps.load_fleet_maintenance_attachments(include_archived=True),
            "reservations": deps.load_fleet_inventory_reservations(),
            "vehicles": deps.load_vehicles_registry(include_archived=True),
            "warehouse_items": deps.load_warehouse_items(),
            "warehouse_movements": deps.load_warehouse_movements(),
        }

    def save_maintenance_state(state: dict, *keys: str) -> None:
        savers = {
            "orders": deps.save_fleet_service_orders,
            "items": deps.save_fleet_service_order_items,
            "plans": deps.save_vehicle_maintenance_plans,
            "attachments": deps.save_fleet_maintenance_attachments,
            "reservations": deps.save_fleet_inventory_reservations,
            "vehicles": deps.save_vehicles_registry,
            "warehouse_items": deps.save_warehouse_items,
            "warehouse_movements": deps.save_warehouse_movements,
        }
        for key in keys:
            savers[key](state[key])

    def state_order(state: dict, order_id: str) -> dict:
        order = next((item for item in state["orders"] if deps.clean_text(item.get("id")) == deps.clean_text(order_id) and not deps.clean_text(item.get("deleted_at"))), None)
        if not order:
            raise ValueError("Ordem de serviço não encontrada.")
        return order

    def state_vehicle(state: dict, vehicle_id: str) -> dict:
        vehicle = next((item for item in state["vehicles"] if deps.clean_text(item.get("vehicle_id")) == deps.clean_text(vehicle_id) and not deps.clean_text(item.get("deleted_at"))), None)
        if not vehicle:
            raise ValueError("Veículo não encontrado.")
        return vehicle

    def set_order(state: dict, order: dict) -> None:
        state["orders"] = deps.upsert_item(state["orders"], order, "id")

    def set_vehicle(state: dict, vehicle: dict) -> None:
        state["vehicles"] = deps.upsert_item(state["vehicles"], vehicle, "vehicle_id")

    def critical_open_orders(state: dict, vehicle_id: str, *, exclude_order_id: str = "") -> list[dict]:
        return [
            item for item in state["orders"]
            if deps.clean_text(item.get("vehicle_id")) == vehicle_id
            and deps.clean_text(item.get("id")) != exclude_order_id
            and deps.clean_text(item.get("priority")) == "critica"
            and deps.clean_text(item.get("status")) not in TERMINAL_ORDER_STATUSES
            and not deps.clean_text(item.get("deleted_at"))
        ]

    @app.route("/fleet", methods=["GET"])
    @deps.require_permission("fleet.view")
    def fleet_home():
        return redirect(url_for("index", _anchor="fleet-pane"))

    @app.route("/fleet/maintenance", methods=["GET"])
    @deps.require_permission("fleet.maintenance.view")
    def fleet_maintenance_home():
        state = maintenance_state()
        user = deps.current_user()
        can_view_costs = deps.has_permission(user, "fleet.maintenance.costs.view")
        dashboard = build_maintenance_dashboard(
            orders=state["orders"],
            items=state["items"],
            plans=state["plans"],
            attachments=state["attachments"],
            reservations=state["reservations"],
            vehicles=state["vehicles"],
            warehouse_items=state["warehouse_items"],
            can_view_costs=can_view_costs,
        )
        selected_order_id = deps.clean_text(request.args.get("order"))
        selected_order = next((item for item in dashboard["orders"] if deps.clean_text(item.get("id")) == selected_order_id), None)
        selected_vehicle_id = deps.clean_text(request.args.get("vehicle") or (selected_order or {}).get("vehicle_id"))
        history = build_vehicle_history(
            vehicle_id=selected_vehicle_id,
            orders=state["orders"],
            mileage=deps.load_vehicle_mileage_records(selected_vehicle_id) if selected_vehicle_id else [],
            documents=deps.load_fleet_documents(include_archived=True),
            attachments=state["attachments"],
            audit_logs=deps.load_vehicle_audit_records(selected_vehicle_id) if selected_vehicle_id else [],
        ) if selected_vehicle_id else []
        period_start = deps.clean_text(request.args.get("history_start"))
        period_end = deps.clean_text(request.args.get("history_end"))
        event_type = deps.clean_text(request.args.get("history_type"))
        history_user = deps.clean_text(request.args.get("history_user"))
        history_order = deps.clean_text(request.args.get("history_order"))
        maintenance_kind = deps.clean_text(request.args.get("history_maintenance_type"))
        history = [
            item for item in history
            if (not period_start or deps.clean_text(item.get("date")) >= period_start)
            and (not period_end or deps.clean_text(item.get("date")) <= period_end)
            and (not event_type or deps.clean_text(item.get("type")) == event_type)
            and (not history_user or deps.clean_text(item.get("user_id")) == history_user)
            and (not history_order or deps.clean_text(item.get("order_number")) == history_order)
            and (not maintenance_kind or deps.clean_text(item.get("maintenance_type")) == maintenance_kind)
        ]
        return render_template(
            "fleet_maintenance.html",
            current_user=user,
            dashboard=dashboard,
            vehicles=[item for item in state["vehicles"] if not deps.clean_text(item.get("deleted_at"))],
            users=[{"id": deps.clean_text(item.get("id")), "nome": deps.clean_text(item.get("nome"))} for item in deps.load_users() if deps.clean_text(item.get("status")) == "ativo"],
            today_iso=date.today().isoformat(),
            selected_order=selected_order,
            selected_vehicle_id=selected_vehicle_id,
            vehicle_history=history,
            can_view_costs=can_view_costs,
            can_manage_costs=deps.has_permission(user, "fleet.maintenance.costs.manage"),
            permissions={permission: deps.has_permission(user, permission) for permission in (
                "fleet.maintenance.create", "fleet.maintenance.edit", "fleet.maintenance.approve",
                "fleet.maintenance.execute", "fleet.maintenance.complete", "fleet.maintenance.cancel",
                "fleet.maintenance.release_vehicle", "fleet.maintenance.plans.manage",
                "fleet.maintenance.inventory.manage", "fleet.admin",
            )},
        )

    @app.route("/fleet/maintenance/orders", methods=["POST"])
    def save_fleet_service_order():
        state = maintenance_state()
        order_id = deps.clean_text(request.form.get("id") or request.form.get("service_order_id"))
        enforce_permission("fleet.maintenance.edit" if order_id else "fleet.maintenance.create")
        try:
            user = deps.current_user()
            before = next((item for item in state["orders"] if deps.clean_text(item.get("id")) == order_id), None)
            order = build_service_order(request.form, orders=state["orders"], vehicles=state["vehicles"], user_id=deps.clean_text(user.get("id")), now=deps.now_iso())
            order = calculate_order_costs(order, state["items"])
            set_order(state, order)
            if order["priority"] == "critica":
                vehicle = state_vehicle(state, order["vehicle_id"])
                vehicle = {**vehicle, "status": "bloqueado", "status_label": "Bloqueado", "maintenance_block_reason": f"{order['order_number']} - {order['reported_problem']}", "maintenance_blocked_at": deps.now_iso(), "maintenance_blocked_by": deps.clean_text(user.get("id")), "updated_at": deps.now_iso()}
                set_vehicle(state, vehicle)
                save_maintenance_state(state, "orders", "vehicles")
                deps.record_vehicle_maintenance_history(vehicle_id=order["vehicle_id"], mileage=None, record_date=order["opening_date"], source="ordem de serviço", user_id=deps.clean_text(user.get("id")), notes=order["order_number"], action="block", previous_data=before, new_data=vehicle)
            else:
                save_maintenance_state(state, "orders")
            deps.record_audit("save", "fleet_maintenance", order["id"], f"Ordem {order['order_number']} salva.", before=before, after=order)
            flash(f"Ordem {order['order_number']} salva com sucesso.", "success")
            return maintenance_redirect(order["id"])
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
            return maintenance_redirect(order_id)

    @app.route("/fleet/maintenance/orders/<order_id>/items", methods=["POST"])
    @deps.require_permission("fleet.maintenance.edit")
    def save_fleet_service_order_item(order_id: str):
        state = maintenance_state()
        try:
            order = state_order(state, order_id)
            payload = request.form.to_dict()
            if deps.clean_text(payload.get("inventory_item_id")):
                enforce_permission("fleet.maintenance.inventory.manage")
            if not deps.has_permission(deps.current_user(), "fleet.maintenance.costs.manage"):
                payload["unit_cost"] = "0"
            item = build_service_order_item(payload, items=state["items"], order=order, warehouse_items=state["warehouse_items"], now=deps.now_iso())
            state["items"] = deps.upsert_item(state["items"], item, "id")
            set_order(state, calculate_order_costs(order, state["items"]))
            save_maintenance_state(state, "items", "orders")
            deps.record_audit("save", "fleet_maintenance", order_id, f"Item {item['description']} salvo na ordem {order['order_number']}.", after=item)
            flash("Item da ordem salvo.", "success")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return maintenance_redirect(order_id)

    @app.route("/fleet/maintenance/orders/<order_id>/items/<item_id>/delete", methods=["POST"])
    @deps.require_permission("fleet.maintenance.edit")
    def delete_fleet_service_order_item(order_id: str, item_id: str):
        state = maintenance_state()
        try:
            order = state_order(state, order_id)
            if deps.clean_text(order.get("status")) not in {"aberta", "aguardando_diagnostico", "aguardando_aprovacao"}:
                raise ValueError("Itens não podem ser removidos depois da aprovação.")
            item = next((record for record in state["items"] if deps.clean_text(record.get("id")) == item_id and deps.clean_text(record.get("service_order_id")) == order_id), None)
            if not item:
                raise ValueError("Item não encontrado.")
            archived = {**item, "deleted_at": deps.now_iso(), "updated_at": deps.now_iso()}
            state["items"] = deps.upsert_item(state["items"], archived, "id")
            set_order(state, calculate_order_costs(order, state["items"]))
            save_maintenance_state(state, "items", "orders")
            deps.record_audit("delete", "fleet_maintenance", item_id, "Item da ordem arquivado por exclusão lógica.", before=item, after=archived)
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return maintenance_redirect(order_id)

    @app.route("/fleet/maintenance/orders/<order_id>/approve", methods=["POST"])
    @deps.require_permission("fleet.maintenance.approve")
    def approve_fleet_service_order(order_id: str):
        state = maintenance_state()
        try:
            user, now = deps.current_user(), deps.now_iso()
            order = state_order(state, order_id)
            if deps.clean_text(order.get("status")) in TERMINAL_ORDER_STATUSES:
                raise ValueError("Esta ordem não pode ser aprovada.")
            order = calculate_order_costs(order, state["items"], manual_total=request.form.get("manual_total"), override_justification=request.form.get("total_override_justification", ""), can_override=deps.has_permission(user, "fleet.maintenance.costs.manage"))
            reservations, movements = reserve_inventory(order, state["items"], state["warehouse_items"], state["reservations"], state["warehouse_movements"], user=user, now=now)
            order.update({"status": "aprovada", "approved_by": deps.clean_text(user.get("id")), "approved_at": now, "updated_at": now})
            state["reservations"], state["warehouse_movements"] = reservations, movements
            set_order(state, order)
            vehicle = state_vehicle(state, order["vehicle_id"])
            set_vehicle(state, {**vehicle, "status": "em_manutencao", "status_label": "Em manutenção", "maintenance_block_reason": f"{order['order_number']} aprovada", "updated_at": now})
            save_maintenance_state(state, "reservations", "warehouse_movements", "orders", "vehicles")
            deps.record_audit("approve", "fleet_maintenance", order_id, f"Ordem {order['order_number']} aprovada e peças reservadas.", after=order)
            flash("Ordem aprovada e estoque reservado.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "warehouse" if "estoque" in str(exc).lower() else "fleet")
        return maintenance_redirect(order_id)

    @app.route("/fleet/maintenance/orders/<order_id>/execute", methods=["POST"])
    @deps.require_permission("fleet.maintenance.execute")
    def execute_fleet_service_order(order_id: str):
        state = maintenance_state()
        try:
            user, now = deps.current_user(), deps.now_iso()
            order = state_order(state, order_id)
            if deps.clean_text(order.get("status")) not in {"aprovada", "aguardando_pecas", "em_execucao"}:
                raise ValueError("A ordem precisa estar aprovada antes da execução.")
            reservations, movements = reserve_inventory(order, state["items"], state["warehouse_items"], state["reservations"], state["warehouse_movements"], user=user, now=now)
            order.update({"status": "em_execucao", "execution_started_by": deps.clean_text(user.get("id")), "execution_started_at": deps.clean_text(order.get("execution_started_at")) or now, "diagnosis": deps.clean_text(request.form.get("diagnosis") or order.get("diagnosis")), "updated_at": now})
            state["reservations"], state["warehouse_movements"] = reservations, movements
            set_order(state, order)
            save_maintenance_state(state, "reservations", "warehouse_movements", "orders")
            deps.record_audit("execute", "fleet_maintenance", order_id, f"Execução da ordem {order['order_number']} iniciada.", after=order)
            flash("Execução iniciada.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return maintenance_redirect(order_id)

    @app.route("/fleet/maintenance/orders/<order_id>/complete", methods=["POST"])
    @deps.require_permission("fleet.maintenance.complete")
    def complete_fleet_service_order(order_id: str):
        state = maintenance_state()
        try:
            user, now = deps.current_user(), deps.now_iso()
            order = state_order(state, order_id)
            if deps.clean_text(order.get("status")) not in {"aprovada", "aguardando_pecas", "em_execucao"}:
                raise ValueError("A ordem precisa estar aprovada ou em execução para ser concluída.")
            vehicle = state_vehicle(state, order["vehicle_id"])
            exit_mileage, correction = validate_completion(order, services_performed=request.form.get("services_performed", ""), exit_mileage=request.form.get("exit_mileage"), current_mileage=int(vehicle.get("current_mileage") or 0), allow_mileage_correction=deps.has_permission(user, "fleet.admin"), correction_justification=request.form.get("mileage_correction_justification", ""))
            order = calculate_order_costs(order, state["items"], manual_total=request.form.get("manual_total"), override_justification=request.form.get("total_override_justification", ""), can_override=deps.has_permission(user, "fleet.maintenance.costs.manage"))
            reservations, movements = reserve_inventory(order, state["items"], state["warehouse_items"], state["reservations"], state["warehouse_movements"], user=user, now=now)
            reservations, warehouse_items, movements = consume_inventory(order, reservations, state["warehouse_items"], movements, user=user, now=now, allow_negative=deps.has_permission(user, "fleet.admin") and deps.clean_text(request.form.get("allow_negative")) == "true")
            completion_date = request.form.get("completion_date") or date.today().isoformat()
            date.fromisoformat(completion_date)
            order.update({"status": "concluida", "services_performed": deps.clean_text(request.form.get("services_performed")), "completion_date": completion_date, "exit_mileage": exit_mileage, "downtime_hours": downtime_hours(order["opening_date"], completion_date), "completed_by": deps.clean_text(user.get("id")), "completed_at": now, "mileage_correction_justification": correction, "updated_at": now})
            state["reservations"], state["warehouse_items"], state["warehouse_movements"] = reservations, warehouse_items, movements
            if deps.clean_text(order.get("maintenance_plan_id")):
                plan = next((item for item in state["plans"] if deps.clean_text(item.get("id")) == deps.clean_text(order.get("maintenance_plan_id")) and not deps.clean_text(item.get("deleted_at"))), None)
                if plan:
                    updated_plan = update_plan_after_service(plan, service_date=completion_date, mileage=exit_mileage, now=now)
                    state["plans"] = deps.upsert_item(state["plans"], updated_plan, "id")
                    order["next_service_date"] = updated_plan.get("next_service_date") or ""
                    order["next_service_mileage"] = updated_plan.get("next_service_mileage")
            before_vehicle = dict(vehicle)
            vehicle.update({"current_mileage": exit_mileage, "status": "em_manutencao", "status_label": "Em manutenção", "updated_at": now})
            if deps.clean_text(request.form.get("release_vehicle")) in {"1", "true", "on"}:
                enforce_permission("fleet.maintenance.release_vehicle")
                if critical_open_orders(state, order["vehicle_id"], exclude_order_id=order_id):
                    raise ValueError("O veículo possui outra ordem crítica aberta e não pode ser liberado.")
                vehicle.update({"status": "disponivel", "status_label": "Disponível", "maintenance_block_reason": "", "maintenance_released_at": now, "maintenance_released_by": deps.clean_text(user.get("id"))})
            set_order(state, order)
            set_vehicle(state, vehicle)
            save_maintenance_state(state, "reservations", "warehouse_items", "warehouse_movements", "plans", "orders", "vehicles")
            deps.record_vehicle_maintenance_history(vehicle_id=order["vehicle_id"], mileage=exit_mileage, record_date=completion_date, source="ordem de serviço", user_id=deps.clean_text(user.get("id")), notes=f"{order['order_number']} - {correction}".strip(" -"), action="complete_service_order", previous_data=before_vehicle, new_data={"vehicle": vehicle, "order": order})
            deps.record_audit("complete", "fleet_maintenance", order_id, f"Ordem {order['order_number']} concluída com baixa de estoque.", before=before_vehicle, after=order)
            flash("Ordem concluída, quilometragem atualizada e peças baixadas.", "success")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return maintenance_redirect(order_id)

    @app.route("/fleet/maintenance/orders/<order_id>/cancel", methods=["POST"])
    @deps.require_permission("fleet.maintenance.cancel")
    def cancel_fleet_service_order(order_id: str):
        state = maintenance_state()
        try:
            user, now = deps.current_user(), deps.now_iso()
            order = state_order(state, order_id)
            if deps.clean_text(order.get("status")) == "concluida":
                raise ValueError("Uma ordem concluída não pode ser cancelada.")
            reservations, movements = release_inventory(order, state["reservations"], state["warehouse_items"], state["warehouse_movements"], user=user, now=now)
            order.update({"status": "cancelada", "cancellation_reason": deps.clean_text(request.form.get("cancellation_reason")), "cancelled_by": deps.clean_text(user.get("id")), "cancelled_at": now, "updated_at": now})
            if not order["cancellation_reason"]:
                raise ValueError("Informe o motivo do cancelamento.")
            state["reservations"], state["warehouse_movements"] = reservations, movements
            set_order(state, order)
            save_maintenance_state(state, "reservations", "warehouse_movements", "orders")
            deps.record_audit("cancel", "fleet_maintenance", order_id, f"Ordem {order['order_number']} cancelada e reservas liberadas.", after=order)
            flash("Ordem cancelada e reservas devolvidas.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return maintenance_redirect(order_id)

    @app.route("/fleet/maintenance/orders/<order_id>/archive", methods=["POST"])
    @deps.require_permission("fleet.admin")
    def archive_fleet_service_order(order_id: str):
        state = maintenance_state()
        try:
            order = state_order(state, order_id)
            if deps.clean_text(order.get("status")) == "concluida":
                raise ValueError("Ordens concluídas são permanentes e não podem ser arquivadas.")
            archived = {**order, "deleted_at": deps.now_iso(), "updated_at": deps.now_iso()}
            set_order(state, archived)
            save_maintenance_state(state, "orders")
            deps.record_audit("delete", "fleet_maintenance", order_id, "Ordem arquivada por exclusão lógica.", before=order, after=archived)
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return maintenance_redirect()

    @app.route("/fleet/maintenance/vehicles/<vehicle_id>/release", methods=["POST"])
    @deps.require_permission("fleet.maintenance.release_vehicle")
    def release_fleet_vehicle(vehicle_id: str):
        state = maintenance_state()
        try:
            if critical_open_orders(state, vehicle_id):
                raise ValueError("O veículo possui ordem crítica aberta e não pode ser liberado.")
            user, now = deps.current_user(), deps.now_iso()
            vehicle = state_vehicle(state, vehicle_id)
            before = dict(vehicle)
            vehicle.update({"status": "disponivel", "status_label": "Disponível", "maintenance_block_reason": "", "maintenance_released_at": now, "maintenance_released_by": deps.clean_text(user.get("id")), "updated_at": now})
            set_vehicle(state, vehicle)
            save_maintenance_state(state, "vehicles")
            deps.record_vehicle_maintenance_history(vehicle_id=vehicle_id, mileage=None, record_date=now[:10], source="manutenção", user_id=deps.clean_text(user.get("id")), notes=deps.clean_text(request.form.get("release_notes")), action="release", previous_data=before, new_data=vehicle)
            deps.record_audit("release", "fleet_maintenance", vehicle_id, "Veículo liberado após manutenção.", before=before, after=vehicle)
            flash("Veículo liberado para operação.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return maintenance_redirect(vehicle_id=vehicle_id)

    @app.route("/fleet/maintenance/plans", methods=["POST"])
    @deps.require_permission("fleet.maintenance.plans.manage")
    def save_vehicle_maintenance_plan():
        state = maintenance_state()
        plan_id = deps.clean_text(request.form.get("id") or request.form.get("plan_id"))
        try:
            before = next((item for item in state["plans"] if deps.clean_text(item.get("id")) == plan_id), None)
            plan = build_maintenance_plan(request.form, plans=state["plans"], vehicles=state["vehicles"], now=deps.now_iso())
            state["plans"] = deps.upsert_item(state["plans"], plan, "id")
            save_maintenance_state(state, "plans")
            deps.record_audit("save", "fleet_maintenance_plans", plan["id"], f"Plano {plan['title']} salvo.", before=before, after=plan)
            flash("Plano preventivo salvo.", "success")
            return maintenance_redirect(vehicle_id=plan["vehicle_id"])
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
            return maintenance_redirect(vehicle_id=deps.clean_text(request.form.get("vehicle_id")))

    @app.route("/fleet/maintenance/plans/<plan_id>/delete", methods=["POST"])
    @deps.require_permission("fleet.maintenance.plans.manage")
    def delete_vehicle_maintenance_plan(plan_id: str):
        state = maintenance_state()
        plan = next((item for item in state["plans"] if deps.clean_text(item.get("id")) == plan_id), None)
        if not plan:
            deps.flash_action_error(ValueError("Plano não encontrado."), "fleet")
            return maintenance_redirect()
        archived = {**plan, "is_active": False, "deleted_at": deps.now_iso(), "updated_at": deps.now_iso()}
        state["plans"] = deps.upsert_item(state["plans"], archived, "id")
        save_maintenance_state(state, "plans")
        deps.record_audit("delete", "fleet_maintenance_plans", plan_id, "Plano arquivado por exclusão lógica.", before=plan, after=archived)
        return maintenance_redirect(vehicle_id=deps.clean_text(plan.get("vehicle_id")))

    @app.route("/fleet/maintenance/orders/<order_id>/attachments", methods=["POST"])
    @deps.require_permission("fleet.maintenance.edit")
    def save_fleet_maintenance_attachment(order_id: str):
        state = maintenance_state()
        saved_paths: list[Path] = []
        try:
            order = state_order(state, order_id)
            vehicle = state_vehicle(state, order["vehicle_id"])
            attachment_type = deps.clean_text(request.form.get("attachment_type"), "outros")
            if attachment_type not in ATTACHMENT_TYPES:
                raise ValueError("Tipo de anexo inválido.")
            files = [item for item in request.files.getlist("attachment_file") if item and item.filename]
            if not files:
                raise ValueError("Selecione ao menos um arquivo.")
            destination_dir = deps.fleet_uploads_dir / deps.fleet_storage_key(vehicle) / "Manutencoes" / secure_filename(order["order_number"])
            destination_dir.mkdir(parents=True, exist_ok=True)
            user, now = deps.current_user(), deps.now_iso()
            records = state["attachments"]
            for uploaded in files:
                safe_name, _extension = deps.validate_uploaded_file(uploaded, field_label="Anexo da manutenção", allowed_extensions=deps.fleet_maintenance_extensions, allowed_label=", ".join(sorted(deps.fleet_maintenance_extensions)))
                destination = destination_dir / f"{now.replace(':', '').replace('-', '')}-{uuid4().hex[:8]}-{safe_name}"
                uploaded.save(destination)
                saved_paths.append(destination)
                relative_path = destination.relative_to(deps.fleet_uploads_dir).as_posix()
                record = {
                    "id": f"FMA-{uuid4().hex.upper()}", "service_order_id": order_id,
                    "vehicle_id": order["vehicle_id"], "attachment_type": attachment_type,
                    "attachment_type_label": ATTACHMENT_TYPES[attachment_type], "original_name": safe_name,
                    "file_path": relative_path, "file_url": url_for("uploaded_fleet_file", relative_path=relative_path),
                    "content_type": deps.clean_text(uploaded.mimetype), "size_bytes": destination.stat().st_size,
                    "notes": deps.clean_text(request.form.get("notes")), "uploaded_by": deps.clean_text(user.get("id")),
                    "created_at": now, "deleted_at": "",
                }
                records.append(record)
                deps.record_audit("upload", "fleet_maintenance", order_id, f"Anexo {safe_name} incluído na ordem {order['order_number']}.", after={**record, "file_path": "[protegido]", "file_url": "[protegido]"})
            state["attachments"] = records
            save_maintenance_state(state, "attachments")
            flash("Anexo salvo na pasta da manutenção.", "success")
        except Exception as exc:  # noqa: BLE001
            for path in saved_paths:
                path.unlink(missing_ok=True)
            deps.flash_action_error(exc, "upload")
        return maintenance_redirect(order_id)

    @app.route("/vehicles", methods=["POST"])
    def save_vehicle():
        try:
            current_vehicles = deps.load_vehicles_registry(include_archived=True)
            requested_id = deps.clean_text(request.form.get("vehicle_id"))
            before = next(
                (item for item in current_vehicles if deps.clean_text(item.get("vehicle_id")) == requested_id),
                None,
            ) if requested_id else None
            enforce_permission("fleet.edit" if before else "fleet.create")
            record = deps.create_vehicle_record(request.form, save_photos=False)
            for permission in sorted(deps.required_vehicle_change_permissions(before, record)):
                enforce_permission(permission)
            record = deps.attach_vehicle_photos(record)
            deps.save_vehicles_registry(deps.upsert_item(current_vehicles, record, "vehicle_id"))
            deps.record_audit(
                "save",
                "fleet",
                record["vehicle_id"],
                f"Veículo {record['vehicle_id']} salvo.",
                before=before,
                after=record,
            )
            flash(f"Veículo {record['vehicle_id']} salvo com sucesso.", "success")
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return redirect(url_for("index", _anchor="fleet-pane"))

    @app.route("/vehicles/<vehicle_id>/delete", methods=["POST"])
    @deps.require_permission("fleet.delete")
    def delete_vehicle(vehicle_id: str):
        current_vehicles = deps.load_vehicles_registry(include_archived=True)
        before = next(
            (item for item in current_vehicles if deps.clean_text(item.get("vehicle_id")) == deps.clean_text(vehicle_id)),
            None,
        )
        if not before:
            deps.flash_action_error(ValueError(f"Veículo {vehicle_id} não encontrado."), "fleet")
            return redirect(url_for("index", _anchor="fleet-pane"))
        after = {
            **before,
            "status": "baixado",
            "status_label": "Baixado",
            "deleted_at": deps.now_iso(),
            "deleted_by": deps.clean_text(deps.current_user().get("email")),
            "updated_at": deps.now_iso(),
        }
        deps.save_vehicles_registry(deps.upsert_item(current_vehicles, after, "vehicle_id"))
        deps.record_audit(
            "delete",
            "fleet",
            vehicle_id,
            f"Veículo {vehicle_id} arquivado por exclusão lógica.",
            before=before,
            after=after,
        )
        flash(f"Veículo {vehicle_id} arquivado. O histórico foi preservado.", "success")
        return redirect(url_for("index", _anchor="fleet-pane"))

    @app.route("/fleet/documents", methods=["POST"])
    @deps.require_permission("fleet.documents.manage")
    def save_fleet_document():
        try:
            record = deps.create_fleet_document_record(request.form)
            documents = deps.load_fleet_documents(include_archived=True)
            before = next((item for item in documents if deps.clean_text(item.get("id")) == record["id"]), None)
            deps.save_fleet_documents(deps.upsert_item(documents, record, "id"))
            deps.record_audit(
                "save",
                "fleet_documents",
                record["id"],
                f"Documento {record['document_type_label']} salvo para {record['vehicle_id']}.",
                before=document_audit_payload(before),
                after=document_audit_payload(record),
            )
            flash("Documento da frota salvo com sucesso.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "upload")
        return redirect(url_for("index", _anchor="fleet-documents-panel"))

    @app.route("/fleet/documents/<document_id>/delete", methods=["POST"])
    @deps.require_permission("fleet.documents.manage")
    def delete_fleet_document(document_id: str):
        documents = deps.load_fleet_documents(include_archived=True)
        before = next(
            (item for item in documents if deps.clean_text(item.get("id")) == deps.clean_text(document_id)),
            None,
        )
        if not before:
            deps.flash_action_error(ValueError(f"Documento {document_id} não encontrado."), "upload")
            return redirect(url_for("index", _anchor="fleet-documents-panel"))
        after = {
            **before,
            "deleted_at": deps.now_iso(),
            "deleted_by": deps.clean_text(deps.current_user().get("email")),
            "updated_at": deps.now_iso(),
        }
        deps.save_fleet_documents(deps.upsert_item(documents, after, "id"))
        deps.record_audit(
            "delete",
            "fleet_documents",
            document_id,
            f"Documento {document_id} arquivado por exclusão lógica.",
            before=document_audit_payload(before),
            after=document_audit_payload(after),
        )
        flash("Documento arquivado. O arquivo e a auditoria foram preservados.", "success")
        return redirect(url_for("index", _anchor="fleet-documents-panel"))

    @app.route("/fleet/document-alerts", methods=["POST"])
    @deps.require_permission("fleet.admin")
    def save_fleet_document_alerts():
        settings = deps.load_settings()
        before = settings.get("fleet_document_alert_days")
        settings["fleet_document_alert_days"] = deps.normalize_fleet_alert_days(request.form.get("alert_days"))
        deps.save_settings(settings)
        deps.record_audit(
            "save",
            "fleet_documents",
            "alert_days",
            "Prazos de alerta dos documentos atualizados.",
            before={"alert_days": before},
            after={"alert_days": settings["fleet_document_alert_days"]},
        )
        flash("Alertas de documentos atualizados.", "success")
        return redirect(url_for("index", _anchor="fleet-documents-panel"))

    @app.route("/uploads/frota/<path:relative_path>", methods=["GET"])
    @deps.require_permission("fleet.view")
    def uploaded_fleet_file(relative_path: str):
        normalized = relative_path.replace("\\", "/")
        if "/Documentos/" in f"/{normalized}" and not deps.has_permission(deps.current_user(), "fleet.documents.view"):
            abort(403)
        return send_from_directory(deps.fleet_uploads_dir, relative_path, as_attachment=False)
