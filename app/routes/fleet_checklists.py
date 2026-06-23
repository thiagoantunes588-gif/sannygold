from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from uuid import uuid4

from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from app.services.fleet_checklists import (
    BLOCK_STATUSES,
    BLOCK_TYPES,
    CHECKLIST_CATEGORIES,
    CHECKLIST_STATUSES,
    CHECKLIST_TYPES,
    DEPARTURE_TYPES,
    FINAL_CHECKLIST_STATUSES,
    OCCURRENCE_SEVERITIES,
    OCCURRENCE_STATUSES,
    OCCURRENCE_TYPES,
    RESPONSE_TYPES,
    RETURN_TYPES,
    active_blocks_for_vehicle,
    build_blocks_from_failures,
    build_checklist_draft,
    build_checklist_responses,
    build_occurrences_from_failures,
    build_operational_dashboard,
    build_template_item,
    build_template_version,
    build_vehicle_assignment,
    clean_text,
    clone_template_items,
    close_vehicle_assignment,
    complete_checklist_transaction,
    driver_authorized,
    evidence_sha256,
    next_id,
    next_occurrence_number,
    release_block_allowed,
    template_matches_vehicle,
    validate_checklist_completion,
)


def register_fleet_checklist_routes(app, deps) -> None:
    def state() -> dict:
        return {
            "templates": deps.load_fleet_checklist_templates(include_archived=True),
            "template_items": deps.load_fleet_checklist_template_items(include_archived=True),
            "checklists": deps.load_fleet_checklists(include_archived=True),
            "responses": deps.load_fleet_checklist_responses(include_archived=True),
            "evidence": deps.load_fleet_checklist_evidence(include_archived=True),
            "occurrences": deps.load_fleet_occurrences(include_archived=True),
            "blocks": deps.load_vehicle_operational_blocks(include_archived=True),
            "assignments": deps.load_fleet_vehicle_assignments(include_archived=True),
            "driver_authorizations": deps.load_fleet_driver_authorizations(include_archived=True),
            "vehicles": deps.load_vehicles_registry(include_archived=True),
            "service_orders": deps.load_fleet_service_orders(include_archived=True),
            "documents": deps.load_fleet_documents(include_archived=True),
        }

    def save(current: dict, *keys: str) -> None:
        savers = {
            "templates": deps.save_fleet_checklist_templates,
            "template_items": deps.save_fleet_checklist_template_items,
            "checklists": deps.save_fleet_checklists,
            "responses": deps.save_fleet_checklist_responses,
            "evidence": deps.save_fleet_checklist_evidence,
            "occurrences": deps.save_fleet_occurrences,
            "blocks": deps.save_vehicle_operational_blocks,
            "assignments": deps.save_fleet_vehicle_assignments,
            "driver_authorizations": deps.save_fleet_driver_authorizations,
            "vehicles": deps.save_vehicles_registry,
        }
        for key in keys:
            savers[key](current[key])

    def upsert(records: list[dict], record: dict) -> list[dict]:
        return deps.upsert_item(records, record, "id")

    def checklist_redirect(checklist_id: str = "", vehicle_id: str = ""):
        values = {}
        if checklist_id:
            values["checklist"] = checklist_id
        if vehicle_id:
            values["vehicle"] = vehicle_id
        return redirect(url_for("fleet_checklists_home", **values))

    def find(records: list[dict], record_id: str, label: str) -> dict:
        record = next((item for item in records if clean_text(item.get("id")) == clean_text(record_id) and not clean_text(item.get("deleted_at"))), None)
        if not record:
            raise ValueError(f"{label} não encontrado.")
        return record

    def can_driver_operate(current: dict, checklist: dict | None = None, vehicle: dict | None = None) -> bool:
        user = deps.current_user()
        user_id = clean_text(user.get("id"))
        if not user_id or clean_text(user.get("role")) == "guest":
            return False
        if checklist and clean_text(checklist.get("driver_id")) != user_id:
            return False
        if vehicle and not driver_authorized(user_id, vehicle, current["driver_authorizations"]):
            return False
        return any(clean_text(item.get("user_id")) == user_id and clean_text(item.get("status")) == "ativo" and not clean_text(item.get("deleted_at")) for item in current["driver_authorizations"])

    def enforce(permission: str, *, current: dict | None = None, checklist: dict | None = None, vehicle: dict | None = None) -> None:
        user = deps.current_user()
        if deps.has_permission(user, permission) or (current is not None and can_driver_operate(current, checklist=checklist, vehicle=vehicle)):
            return
        deps.record_audit("access_denied", "permissions", permission, f"Acesso negado à Fase 3 da Frota: {permission}.", after={"path": request.path, "method": request.method})
        abort(403)

    @app.route("/fleet/checklists", methods=["GET"])
    @deps.require_permission("fleet.checklist.view")
    def fleet_checklists_home():
        current = state()
        user = deps.current_user()
        all_events = deps.load_events()
        users = [{"id": clean_text(item.get("id")), "nome": clean_text(item.get("nome")), "role": clean_text(item.get("role"))} for item in deps.load_users() if clean_text(item.get("status")) == "ativo"]
        user_map = {item["id"]: item["nome"] for item in users}
        vehicle_map = {clean_text(item.get("vehicle_id")): item for item in current["vehicles"]}
        driver_only = clean_text(user.get("role")) == "leitura" and any(clean_text(item.get("user_id")) == clean_text(user.get("id")) and clean_text(item.get("status")) == "ativo" for item in current["driver_authorizations"])
        if driver_only:
            user_id = clean_text(user.get("id"))
            allowed_vehicles = [item for item in current["vehicles"] if driver_authorized(clean_text(user.get("id")), item, current["driver_authorizations"])]
            allowed_ids = {clean_text(item.get("vehicle_id")) for item in allowed_vehicles}
            driver_route_ids = {
                clean_text(item.get("route_id")) for item in current["checklists"] + current["assignments"]
                if clean_text(item.get("driver_id")) == user_id and clean_text(item.get("route_id"))
            }
            current["checklists"] = [item for item in current["checklists"] if clean_text(item.get("driver_id")) == user_id]
            current["occurrences"] = [item for item in current["occurrences"] if clean_text(item.get("responsible_user_id")) == user_id]
            current["assignments"] = [item for item in current["assignments"] if clean_text(item.get("driver_id")) == user_id]
            current["vehicles"] = allowed_vehicles
            all_events = [item for item in all_events if clean_text(item.get("event_id")) in driver_route_ids]
            users = [item for item in users if item["id"] == user_id]
            user_map = {item["id"]: item["nome"] for item in users}
        filters = {key: clean_text(request.args.get(key)) for key in ("date", "vehicle", "driver", "route", "operation", "status", "severity", "company", "cost_center")}
        if filters["company"]:
            current["vehicles"] = [item for item in current["vehicles"] if clean_text(item.get("operating_company")) == filters["company"]]
        if filters["cost_center"]:
            current["vehicles"] = [item for item in current["vehicles"] if clean_text(item.get("cost_center")) == filters["cost_center"]]
        allowed_vehicle_ids = {clean_text(item.get("vehicle_id")) for item in current["vehicles"]}
        if filters["vehicle"]:
            allowed_vehicle_ids &= {filters["vehicle"]}
        current["checklists"] = [item for item in current["checklists"] if clean_text(item.get("vehicle_id")) in allowed_vehicle_ids]
        current["occurrences"] = [item for item in current["occurrences"] if clean_text(item.get("vehicle_id")) in allowed_vehicle_ids]
        current["blocks"] = [item for item in current["blocks"] if clean_text(item.get("vehicle_id")) in allowed_vehicle_ids]
        current["assignments"] = [item for item in current["assignments"] if clean_text(item.get("vehicle_id")) in allowed_vehicle_ids]
        for key, field in (("driver", "driver_id"), ("route", "route_id"), ("operation", "operation_id"), ("status", "status")):
            if filters[key]:
                current["checklists"] = [item for item in current["checklists"] if clean_text(item.get(field)) == filters[key]]
        if filters["date"]:
            current["checklists"] = [item for item in current["checklists"] if clean_text(item.get("completed_at") or item.get("started_at") or item.get("created_at"))[:10] == filters["date"]]
            current["occurrences"] = [item for item in current["occurrences"] if clean_text(item.get("occurrence_date") or item.get("created_at"))[:10] == filters["date"]]
        if filters["severity"]:
            current["occurrences"] = [item for item in current["occurrences"] if clean_text(item.get("severity")) == filters["severity"]]
        dashboard = build_operational_dashboard(checklists=current["checklists"], occurrences=current["occurrences"], blocks=current["blocks"], assignments=current["assignments"], vehicles=current["vehicles"])
        dashboard["counts"]["routes_without_checklist"] = sum(
            1 for event in all_events
            if any(clean_text(vehicle_id) in allowed_vehicle_ids for vehicle_id in (event.get("vehicle_ids") or []))
            and not any(clean_text(item.get("route_id")) == clean_text(event.get("event_id")) and clean_text(item.get("checklist_type")) in DEPARTURE_TYPES and clean_text(item.get("status")) in {"concluido", "concluido_com_ressalvas"} for item in current["checklists"])
        )
        for item in dashboard["active_blocks"]:
            item["vehicle_plate"] = clean_text(vehicle_map.get(clean_text(item.get("vehicle_id")), {}).get("plate"))
        for item in dashboard["open_occurrences"]:
            item["vehicle_plate"] = clean_text(vehicle_map.get(clean_text(item.get("vehicle_id")), {}).get("plate"))
        for item in dashboard["open_assignments"]:
            item["vehicle_plate"] = clean_text(vehicle_map.get(clean_text(item.get("vehicle_id")), {}).get("plate"))
            item["driver_name"] = user_map.get(clean_text(item.get("driver_id")), clean_text(item.get("driver_id")))
        for collection in (current["checklists"], current["occurrences"], current["blocks"], current["assignments"]):
            for item in collection:
                item["vehicle_plate"] = clean_text(vehicle_map.get(clean_text(item.get("vehicle_id")), {}).get("plate"))
                item["driver_name"] = user_map.get(clean_text(item.get("driver_id")), clean_text(item.get("driver_id")))
        selected_id = clean_text(request.args.get("checklist"))
        selected = next((item for item in current["checklists"] if clean_text(item.get("id")) == selected_id), None)
        selected_template = next((item for item in current["templates"] if selected and clean_text(item.get("id")) == clean_text(selected.get("template_id"))), None)
        selected_items = [item for item in current["template_items"] if selected_template and clean_text(item.get("template_id")) == clean_text(selected_template.get("id")) and not clean_text(item.get("deleted_at"))]
        selected_responses = {clean_text(item.get("template_item_id")): item for item in current["responses"] if selected and clean_text(item.get("checklist_id")) == selected_id and not clean_text(item.get("deleted_at"))}
        selected_evidence = [item for item in current["evidence"] if selected and clean_text(item.get("checklist_id")) == selected_id and not clean_text(item.get("deleted_at"))]
        for evidence in selected_evidence:
            evidence["file_url"] = url_for("uploaded_fleet_file", relative_path=clean_text(evidence.get("file_path")))
        active_templates = [item for item in current["templates"] if bool(item.get("is_active")) and not clean_text(item.get("deleted_at"))]
        for template in active_templates:
            template["item_count"] = sum(1 for item in current["template_items"] if clean_text(item.get("template_id")) == clean_text(template.get("id")) and not clean_text(item.get("deleted_at")))
        selected_vehicle_id = clean_text(request.args.get("vehicle") or (selected or {}).get("vehicle_id"))
        permissions = {permission: deps.has_permission(user, permission) for permission in (
            "fleet.checklist.create", "fleet.checklist.complete", "fleet.checklist.cancel", "fleet.checklist.templates.manage",
            "fleet.occurrence.create", "fleet.occurrence.assign", "fleet.occurrence.resolve", "fleet.vehicle.block",
            "fleet.vehicle.release", "fleet.route.override", "fleet.audit.view", "fleet.admin",
        )}
        return render_template(
            "fleet_checklists.html", current_user=user, dashboard=dashboard, templates=active_templates,
            template_items=current["template_items"], vehicles=[item for item in current["vehicles"] if not clean_text(item.get("deleted_at"))],
            users=users, events=all_events, selected_checklist=selected, selected_template=selected_template,
            selected_items=selected_items, selected_responses=selected_responses, selected_evidence=selected_evidence,
            selected_vehicle_id=selected_vehicle_id, permissions=permissions, checklist_types=CHECKLIST_TYPES,
            checklist_statuses=CHECKLIST_STATUSES, response_types=RESPONSE_TYPES, categories=CHECKLIST_CATEGORIES,
            occurrence_types=OCCURRENCE_TYPES, occurrence_severities=OCCURRENCE_SEVERITIES,
            occurrence_statuses=OCCURRENCE_STATUSES, block_types=BLOCK_TYPES,
            driver_authorizations=current["driver_authorizations"], driver_only=driver_only, filters=filters,
            occurrences=current["occurrences"], blocks=current["blocks"], assignments=current["assignments"],
            companies=sorted({clean_text(item.get("operating_company")) for item in current["vehicles"] if clean_text(item.get("operating_company"))}),
            cost_centers=sorted({clean_text(item.get("cost_center")) for item in current["vehicles"] if clean_text(item.get("cost_center"))}),
            today_iso=date.today().isoformat(),
        )

    @app.route("/fleet/checklists/templates", methods=["POST"])
    @deps.require_permission("fleet.checklist.templates.manage")
    def save_fleet_checklist_template():
        current = state()
        try:
            now, user_id = deps.now_iso(), clean_text(deps.current_user().get("id"))
            template, previous = build_template_version(request.form, templates=current["templates"], user_id=user_id, now=now)
            if previous:
                current["templates"] = upsert(current["templates"], previous)
                current["template_items"].extend(clone_template_items(current["template_items"], source_template_id=previous["id"], target_template_id=template["id"], now=now))
            current["templates"] = upsert(current["templates"], template)
            save(current, "templates", "template_items")
            deps.record_audit("save", "fleet_checklist_templates", template["id"], f"Modelo {template['name']} versão {template['version']} salvo.", before=previous, after=template)
            flash("Modelo de checklist salvo em nova versão.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return checklist_redirect()

    @app.route("/fleet/checklists/templates/<template_id>/items", methods=["POST"])
    @deps.require_permission("fleet.checklist.templates.manage")
    def save_fleet_checklist_template_item(template_id: str):
        current = state()
        try:
            source = find(current["templates"], template_id, "Modelo")
            now, user_id = deps.now_iso(), clean_text(deps.current_user().get("id"))
            in_use = any(clean_text(item.get("template_id")) == template_id for item in current["checklists"])
            target = source
            if in_use:
                target, previous = build_template_version({**source, "template_id": template_id}, templates=current["templates"], user_id=user_id, now=now)
                current["templates"] = upsert(current["templates"], previous)
                current["templates"] = upsert(current["templates"], target)
                current["template_items"].extend(clone_template_items(current["template_items"], source_template_id=template_id, target_template_id=target["id"], now=now))
            item = build_template_item(request.form, template_id=target["id"], items=current["template_items"], now=now)
            current["template_items"].append(item)
            save(current, "templates", "template_items")
            deps.record_audit("save", "fleet_checklist_templates", target["id"], f"Item {item['title']} adicionado ao modelo versão {target['version']}.", after=item)
            flash("Item configurável adicionado ao modelo.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return checklist_redirect()

    @app.route("/fleet/checklists/templates/<template_id>/items/<item_id>/archive", methods=["POST"])
    @deps.require_permission("fleet.checklist.templates.manage")
    def archive_fleet_checklist_template_item(template_id: str, item_id: str):
        current = state()
        try:
            source = find(current["templates"], template_id, "Modelo")
            item = find(current["template_items"], item_id, "Item")
            if clean_text(item.get("template_id")) != clean_text(source.get("id")):
                raise ValueError("O item não pertence ao modelo informado.")
            now, user_id = deps.now_iso(), clean_text(deps.current_user().get("id"))
            in_use = any(clean_text(record.get("template_id")) == template_id for record in current["checklists"])
            target = source
            target_item_id = item_id
            if in_use:
                target, previous = build_template_version({**source, "template_id": template_id}, templates=current["templates"], user_id=user_id, now=now)
                current["templates"] = upsert(current["templates"], previous)
                current["templates"] = upsert(current["templates"], target)
                cloned = clone_template_items(current["template_items"], source_template_id=template_id, target_template_id=target["id"], now=now)
                current["template_items"].extend(cloned)
                cloned_item = next(record for record in cloned if clean_text(record.get("source_item_id")) == item_id)
                target_item_id = clean_text(cloned_item.get("id"))
            target_item = find(current["template_items"], target_item_id, "Item")
            archived = {**target_item, "deleted_at": now, "updated_at": now}
            current["template_items"] = upsert(current["template_items"], archived)
            save(current, "templates", "template_items")
            deps.record_audit("delete", "fleet_checklist_templates", target["id"], "Item de modelo arquivado por exclusão lógica.", before=target_item, after=archived)
            flash("Item arquivado na versão atual do modelo.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return checklist_redirect()

    @app.route("/fleet/checklists/driver-authorizations", methods=["POST"])
    @deps.require_permission("fleet.checklist.templates.manage")
    def save_fleet_driver_authorization():
        current = state()
        try:
            user_id = clean_text(request.form.get("user_id"))
            if not any(clean_text(item.get("id")) == user_id and clean_text(item.get("status")) == "ativo" for item in deps.load_users()):
                raise ValueError("Selecione um usuário ativo.")
            now = deps.now_iso()
            existing = next((item for item in current["driver_authorizations"] if clean_text(item.get("user_id")) == user_id and not clean_text(item.get("deleted_at"))), None)
            record = {
                **(existing or {}), "id": clean_text((existing or {}).get("id")) or next_id(current["driver_authorizations"], "DRV"),
                "user_id": user_id, "employee_id": clean_text(request.form.get("employee_id")),
                "authorized_vehicle_ids": [clean_text(item) for item in request.form.getlist("authorized_vehicle_ids") if clean_text(item)],
                "authorized_vehicle_types": [clean_text(item) for item in clean_text(request.form.get("authorized_vehicle_types")).split("|") if clean_text(item)],
                "is_usual_driver": clean_text(request.form.get("is_usual_driver")) in {"1", "true", "on"},
                "status": clean_text(request.form.get("status"), "ativo"), "created_by": clean_text((existing or {}).get("created_by")) or clean_text(deps.current_user().get("id")),
                "created_at": clean_text((existing or {}).get("created_at")) or now, "updated_at": now, "deleted_at": "",
            }
            current["driver_authorizations"] = upsert(current["driver_authorizations"], record)
            save(current, "driver_authorizations")
            deps.record_audit("save", "fleet_drivers", record["id"], "Autorização de motorista atualizada.", before=existing, after=record)
            flash("Autorização do usuário atualizada.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return checklist_redirect()

    @app.route("/fleet/checklists", methods=["POST"])
    def create_fleet_checklist():
        current = state()
        try:
            template = find(current["templates"], clean_text(request.form.get("template_id")), "Modelo")
            vehicle = next((item for item in current["vehicles"] if clean_text(item.get("vehicle_id")) == clean_text(request.form.get("vehicle_id")) and not clean_text(item.get("deleted_at"))), None)
            if not vehicle:
                raise ValueError("Selecione um veículo ativo.")
            enforce("fleet.checklist.create", current=current, vehicle=vehicle)
            if clean_text(template.get("checklist_type")) in DEPARTURE_TYPES and active_blocks_for_vehicle(current["blocks"], clean_text(vehicle.get("vehicle_id"))):
                raise ValueError("O veículo possui bloqueio operacional ativo e não pode iniciar checklist de saída ou entrega.")
            driver_id = clean_text(request.form.get("driver_id"))
            if not deps.has_permission(deps.current_user(), "fleet.checklist.create") and driver_id != clean_text(deps.current_user().get("id")):
                raise PermissionError("O motorista só pode iniciar checklist em seu próprio nome.")
            if driver_id and not deps.has_permission(deps.current_user(), "fleet.admin") and not driver_authorized(driver_id, vehicle, current["driver_authorizations"]):
                raise ValueError("O usuário selecionado não está autorizado para este veículo ou tipo.")
            checklist = build_checklist_draft(request.form, template=template, vehicle=vehicle, checklists=current["checklists"], user_id=clean_text(deps.current_user().get("id")), now=deps.now_iso())
            current["checklists"].append(checklist)
            save(current, "checklists")
            deps.record_audit("create", "fleet_checklists", checklist["id"], f"Checklist {checklist['checklist_type']} iniciado para {checklist['vehicle_id']}.", after=checklist)
            flash("Checklist iniciado e salvo como rascunho.", "success")
            return checklist_redirect(checklist["id"])
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
            return checklist_redirect(vehicle_id=clean_text(request.form.get("vehicle_id")))

    @app.route("/fleet/checklists/<checklist_id>/draft", methods=["POST"])
    def save_fleet_checklist_draft(checklist_id: str):
        current = state()
        try:
            checklist = find(current["checklists"], checklist_id, "Checklist")
            vehicle = next((item for item in current["vehicles"] if clean_text(item.get("vehicle_id")) == clean_text(checklist.get("vehicle_id"))), {})
            enforce("fleet.checklist.create", current=current, checklist=checklist, vehicle=vehicle)
            if clean_text(checklist.get("status")) in FINAL_CHECKLIST_STATUSES:
                raise ValueError("Checklist finalizado não pode voltar para rascunho.")
            was_draft = clean_text(checklist.get("status")) == "rascunho"
            items = [item for item in current["template_items"] if clean_text(item.get("template_id")) == clean_text(checklist.get("template_id"))]
            current["responses"] = build_checklist_responses(request.form, checklist=checklist, template_items=items, existing=current["responses"], now=deps.now_iso())
            checklist = {**checklist, "status": "em_preenchimento", "start_mileage": int(request.form.get("start_mileage")) if clean_text(request.form.get("start_mileage")) else checklist.get("start_mileage"), "end_mileage": int(request.form.get("end_mileage")) if clean_text(request.form.get("end_mileage")) else checklist.get("end_mileage"), "fuel_level": clean_text(request.form.get("fuel_level"), clean_text(checklist.get("fuel_level"))), "notes": clean_text(request.form.get("notes"), clean_text(checklist.get("notes"))), "location_text": clean_text(request.form.get("location_text"), clean_text(checklist.get("location_text"))), "latitude": request.form.get("latitude") or checklist.get("latitude"), "longitude": request.form.get("longitude") or checklist.get("longitude"), "updated_at": deps.now_iso()}
            current["checklists"] = upsert(current["checklists"], checklist)
            save(current, "responses", "checklists")
            if was_draft:
                deps.record_audit("save_draft", "fleet_checklists", checklist_id, "Primeiro rascunho do checklist salvo.", after={"status": checklist["status"]})
            if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
                return jsonify({"ok": True, "status": "rascunho_salvo", "updated_at": checklist["updated_at"]})
            flash("Rascunho salvo. O checklist ainda não foi concluído.", "success")
        except Exception as exc:  # noqa: BLE001
            if request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html:
                return jsonify({"ok": False, "error": str(exc)}), 400
            deps.flash_action_error(exc, "fleet")
        return checklist_redirect(checklist_id)

    @app.route("/fleet/checklists/<checklist_id>/evidence", methods=["POST"])
    def save_fleet_checklist_evidence(checklist_id: str):
        current = state()
        saved_paths: list[Path] = []
        try:
            checklist = find(current["checklists"], checklist_id, "Checklist")
            vehicle = next((item for item in current["vehicles"] if clean_text(item.get("vehicle_id")) == clean_text(checklist.get("vehicle_id"))), {})
            enforce("fleet.checklist.create", current=current, checklist=checklist, vehicle=vehicle)
            uploaded = request.files.get("evidence_file")
            if not uploaded or not uploaded.filename:
                raise ValueError("Selecione uma foto ou evidência.")
            safe_name, _extension = deps.validate_uploaded_file(uploaded, field_label="Evidência do checklist", allowed_extensions=deps.checklist_evidence_extensions, allowed_label=", ".join(sorted(deps.checklist_evidence_extensions)))
            category = secure_filename(clean_text(request.form.get("evidence_type"), "Outras")) or "Outras"
            year = clean_text(checklist.get("created_at"))[:4] or str(date.today().year)
            destination_dir = deps.fleet_uploads_dir / deps.fleet_storage_key(vehicle) / "Checklists" / year / checklist_id / category
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination = destination_dir / f"{uuid4().hex[:12]}-{safe_name}"
            uploaded.save(destination)
            saved_paths.append(destination)
            relative = destination.relative_to(deps.fleet_uploads_dir).as_posix()
            now = deps.now_iso()
            record = {
                "id": next_id(current["evidence"], "EVD"), "checklist_id": checklist_id,
                "response_id": clean_text(request.form.get("response_id")), "template_item_id": clean_text(request.form.get("template_item_id")),
                "evidence_type": category, "original_name": safe_name, "file_path": relative,
                "content_type": clean_text(uploaded.mimetype), "size_bytes": destination.stat().st_size,
                "sha256": evidence_sha256(destination), "uploaded_by": clean_text(deps.current_user().get("id")),
                "created_at": now, "deleted_at": "",
            }
            current["evidence"].append(record)
            save(current, "evidence")
            deps.record_audit("upload", "fleet_checklists", checklist_id, "Evidência adicionada ao checklist.", after={**record, "file_path": "[protegido]"})
            flash("Evidência salva.", "success")
        except Exception as exc:  # noqa: BLE001
            for path in saved_paths:
                path.unlink(missing_ok=True)
            deps.flash_action_error(exc, "upload")
        return checklist_redirect(checklist_id)

    @app.route("/fleet/checklists/<checklist_id>/complete", methods=["POST"])
    def complete_fleet_checklist(checklist_id: str):
        current = state()
        try:
            checklist = find(current["checklists"], checklist_id, "Checklist")
            vehicle = next((item for item in current["vehicles"] if clean_text(item.get("vehicle_id")) == clean_text(checklist.get("vehicle_id"))), None)
            if not vehicle:
                raise ValueError("Veículo do checklist não encontrado.")
            enforce("fleet.checklist.complete", current=current, checklist=checklist, vehicle=vehicle)
            if clean_text(checklist.get("status")) in FINAL_CHECKLIST_STATUSES:
                raise ValueError("Este checklist já foi finalizado.")
            if clean_text(checklist.get("checklist_type")) in DEPARTURE_TYPES and active_blocks_for_vehicle(current["blocks"], clean_text(vehicle.get("vehicle_id"))):
                raise ValueError("O veículo foi bloqueado após o início do checklist e não pode ser entregue.")
            now, user_id = deps.now_iso(), clean_text(deps.current_user().get("id"))
            template_items = [item for item in current["template_items"] if clean_text(item.get("template_id")) == clean_text(checklist.get("template_id"))]
            current["responses"] = build_checklist_responses(request.form, checklist=checklist, template_items=template_items, existing=current["responses"], now=now)
            result = validate_checklist_completion(checklist, current["responses"], template_items, current["evidence"], signature_name=clean_text(request.form.get("signature_name")))
            start_mileage = int(request.form.get("start_mileage")) if clean_text(request.form.get("start_mileage")) else checklist.get("start_mileage")
            end_mileage = int(request.form.get("end_mileage")) if clean_text(request.form.get("end_mileage")) else checklist.get("end_mileage")
            checklist = {**checklist, "status": result["status"], "general_status": result["general_status"], "completed_at": now, "signature_name": clean_text(request.form.get("signature_name")), "confirmation_hash": result["confirmation_hash"], "start_mileage": start_mileage, "end_mileage": end_mileage, "fuel_level": clean_text(request.form.get("fuel_level"), clean_text(checklist.get("fuel_level"))), "notes": clean_text(request.form.get("notes"), clean_text(checklist.get("notes"))), "updated_at": now}
            mileage = start_mileage if checklist["checklist_type"] in DEPARTURE_TYPES else end_mileage if checklist["checklist_type"] in RETURN_TYPES else end_mileage or start_mileage
            if checklist["checklist_type"] in DEPARTURE_TYPES and mileage is None:
                raise ValueError("Informe a quilometragem de saída.")
            if checklist["checklist_type"] in RETURN_TYPES:
                assignment = next((item for item in current["assignments"] if clean_text(item.get("vehicle_id")) == checklist["vehicle_id"] and clean_text(item.get("status")) == "entregue"), None)
                if not assignment:
                    raise ValueError("Não existe entrega aberta para registrar o retorno.")
                if mileage is None or mileage < int(assignment.get("start_mileage") or 0):
                    raise ValueError("A quilometragem de retorno não pode ser inferior à saída.")
                checklist["distance_travelled"] = mileage - int(assignment.get("start_mileage") or 0)
            occurrences = build_occurrences_from_failures(checklist, result["failures"], current["occurrences"], user_id=user_id, now=now)
            blocks = build_blocks_from_failures(checklist, result["critical_failures"], occurrences, current["blocks"], user_id=user_id, now=now)
            override_reason = clean_text(request.form.get("assignment_override_justification"))
            if override_reason and not deps.has_permission(deps.current_user(), "fleet.route.override"):
                raise PermissionError("Somente usuário autorizado pode substituir uma entrega aberta.")
            if checklist["checklist_type"] in DEPARTURE_TYPES and result["status"] != "reprovado":
                previous_assignment = next((item for item in current["assignments"] if clean_text(item.get("vehicle_id")) == checklist["vehicle_id"] and clean_text(item.get("status")) == "entregue" and not clean_text(item.get("deleted_at"))), None)
                if previous_assignment and override_reason:
                    replaced = {**previous_assignment, "status": "substituida", "returned_at": now, "received_return_by": user_id, "replacement_justification": override_reason, "updated_at": now}
                    current["assignments"] = upsert(current["assignments"], replaced)
                    deps.record_audit("update", "fleet_assignments", replaced["id"], "Entrega aberta substituída com autorização.", before=previous_assignment, after=replaced)
                assignment = build_vehicle_assignment(checklist, current["assignments"], user_id=user_id, now=now, override_reason=override_reason)
                current["assignments"].append(assignment)
                vehicle = {**vehicle, "status": "em_operacao", "status_label": "Em operação", "current_driver_id": checklist["driver_id"], "updated_at": now}
            elif checklist["checklist_type"] in RETURN_TYPES:
                assignment = close_vehicle_assignment(checklist, current["assignments"], user_id=user_id, now=now)
                current["assignments"] = upsert(current["assignments"], assignment)
                still_blocked = active_blocks_for_vehicle(current["blocks"], checklist["vehicle_id"])
                vehicle = {**vehicle, "status": "bloqueado" if still_blocked else "disponivel", "status_label": "Bloqueado" if still_blocked else "Disponível", "current_driver_id": "", "updated_at": now}
            if blocks:
                current["blocks"].extend(blocks)
                vehicle = {**vehicle, "status": "bloqueado", "status_label": "Bloqueado", "maintenance_block_reason": blocks[0]["reason"], "maintenance_blocked_at": now, "maintenance_blocked_by": user_id, "updated_at": now}
            transaction = complete_checklist_transaction(db_path=deps.sqlite_db_path, checklist=checklist, responses=current["responses"], vehicle=vehicle, mileage=mileage, mileage_source=f"checklist de {CHECKLIST_TYPES.get(checklist['checklist_type'], checklist['checklist_type']).lower()}", user_id=user_id, correction_allowed=deps.has_permission(deps.current_user(), "fleet.admin"), correction_justification=clean_text(request.form.get("mileage_correction_justification")))
            vehicle = transaction["vehicle"]
            current["checklists"] = upsert(current["checklists"], checklist)
            current["vehicles"] = deps.upsert_item(current["vehicles"], vehicle, "vehicle_id")
            current["occurrences"].extend(occurrences)
            save(current, "checklists", "responses", "occurrences", "blocks", "assignments", "vehicles")
            deps.record_audit("complete", "fleet_checklists", checklist_id, f"Checklist concluído com status {checklist['status']}.", after={"checklist": checklist, "occurrences": [item["id"] for item in occurrences], "blocks": [item["id"] for item in blocks]})
            if blocks:
                deps.flash_action_warning("Veículo bloqueado por falha crítica", blocks[0]["reason"], next_step="Abra a ocorrência, avalie a falha e confirme uma ordem de serviço antes de liberar.", target_href=f"/fleet/checklists?checklist={checklist_id}#ocorrencias", target_tab="", action="Ver ocorrência")
            else:
                flash("Checklist concluído e responsabilidade atualizada.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return checklist_redirect(checklist_id)

    @app.route("/fleet/checklists/<checklist_id>/cancel", methods=["POST"])
    def cancel_fleet_checklist(checklist_id: str):
        current = state()
        try:
            checklist = find(current["checklists"], checklist_id, "Checklist")
            enforce("fleet.checklist.cancel", current=current, checklist=checklist)
            if clean_text(checklist.get("status")) in {"concluido", "concluido_com_ressalvas", "reprovado"}:
                raise ValueError("Checklist concluído ou reprovado não pode ser cancelado.")
            reason = clean_text(request.form.get("cancellation_reason"))
            if len(reason) < 5:
                raise ValueError("Informe o motivo do cancelamento.")
            updated = {**checklist, "status": "cancelado", "cancellation_reason": reason, "updated_at": deps.now_iso()}
            current["checklists"] = upsert(current["checklists"], updated)
            save(current, "checklists")
            deps.record_audit("cancel", "fleet_checklists", checklist_id, "Checklist cancelado.", before=checklist, after=updated)
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return checklist_redirect(checklist_id)

    @app.route("/fleet/occurrences", methods=["POST"])
    def create_fleet_occurrence():
        current = state()
        enforce("fleet.occurrence.create", current=current)
        try:
            vehicle_id = clean_text(request.form.get("vehicle_id"))
            vehicle = next((item for item in current["vehicles"] if clean_text(item.get("vehicle_id")) == vehicle_id), None)
            if not vehicle:
                raise ValueError("Selecione um veículo.")
            now, user_id = deps.now_iso(), clean_text(deps.current_user().get("id"))
            if not deps.has_permission(deps.current_user(), "fleet.occurrence.create") and not driver_authorized(user_id, vehicle, current["driver_authorizations"]):
                raise PermissionError("O motorista não está autorizado para este veículo.")
            driver_id = clean_text(request.form.get("driver_id")) if deps.has_permission(deps.current_user(), "fleet.occurrence.create") else user_id
            occurrence_type = clean_text(request.form.get("occurrence_type"), "outro")
            severity = clean_text(request.form.get("severity"), "media")
            if occurrence_type not in OCCURRENCE_TYPES or severity not in OCCURRENCE_SEVERITIES:
                raise ValueError("Tipo ou severidade inválidos.")
            title, description = clean_text(request.form.get("title")), clean_text(request.form.get("description"))
            if not title or not description:
                raise ValueError("Informe título e descrição da ocorrência.")
            record = {
                "id": next_id(current["occurrences"], "OCC"), "occurrence_number": next_occurrence_number(current["occurrences"], now[:10]),
                "vehicle_id": vehicle_id, "driver_id": driver_id or user_id, "route_id": clean_text(request.form.get("route_id")),
                "operation_id": clean_text(request.form.get("operation_id")), "checklist_id": clean_text(request.form.get("checklist_id")),
                "service_order_id": clean_text(request.form.get("service_order_id")), "occurrence_type": occurrence_type,
                "severity": severity, "status": "aberta", "title": title, "description": description,
                "occurrence_date": clean_text(request.form.get("occurrence_date"), now[:10]), "reported_at": now,
                "location": clean_text(request.form.get("location")), "responsible_user_id": user_id, "assigned_user_id": "",
                "resolution": "", "resolved_at": "", "resolved_by": "", "created_at": now, "updated_at": now, "deleted_at": "",
            }
            current["occurrences"].append(record)
            save(current, "occurrences")
            deps.record_audit("create", "fleet_occurrences", record["id"], f"Ocorrência {record['occurrence_number']} criada.", after=record)
            flash("Ocorrência registrada. Possível infração permanece apenas como relato.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return checklist_redirect(vehicle_id=clean_text(request.form.get("vehicle_id")))

    @app.route("/fleet/occurrences/<occurrence_id>/assign", methods=["POST"])
    @deps.require_permission("fleet.occurrence.assign")
    def assign_fleet_occurrence(occurrence_id: str):
        current = state()
        try:
            occurrence = find(current["occurrences"], occurrence_id, "Ocorrência")
            assigned_user_id = clean_text(request.form.get("assigned_user_id"))
            if not any(clean_text(item.get("id")) == assigned_user_id and clean_text(item.get("status")) == "ativo" for item in deps.load_users()):
                raise ValueError("Selecione um usuário ativo para a ocorrência.")
            now = deps.now_iso()
            updated = {**occurrence, "assigned_user_id": assigned_user_id, "status": "em_analise", "updated_at": now}
            current["occurrences"] = upsert(current["occurrences"], updated)
            save(current, "occurrences")
            deps.record_audit("update", "fleet_occurrences", occurrence_id, "Responsável da ocorrência alterado.", before=occurrence, after=updated)
            flash("Ocorrência encaminhada ao responsável.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return checklist_redirect()

    @app.route("/fleet/occurrences/<occurrence_id>/resolve", methods=["POST"])
    @deps.require_permission("fleet.occurrence.resolve")
    def resolve_fleet_occurrence(occurrence_id: str):
        current = state()
        try:
            occurrence = find(current["occurrences"], occurrence_id, "Ocorrência")
            resolution = clean_text(request.form.get("resolution"))
            if len(resolution) < 10:
                raise ValueError("Descreva a resolução com pelo menos 10 caracteres.")
            now = deps.now_iso()
            updated = {**occurrence, "status": "resolvida", "resolution": resolution, "resolved_at": now, "resolved_by": clean_text(deps.current_user().get("id")), "updated_at": now}
            current["occurrences"] = upsert(current["occurrences"], updated)
            save(current, "occurrences")
            deps.record_audit("resolve", "fleet_occurrences", occurrence_id, "Ocorrência resolvida.", before=occurrence, after=updated)
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return checklist_redirect()

    @app.route("/fleet/vehicles/<vehicle_id>/operational-blocks", methods=["POST"])
    @deps.require_permission("fleet.vehicle.block")
    def create_vehicle_operational_block(vehicle_id: str):
        current = state()
        try:
            vehicle = next((item for item in current["vehicles"] if clean_text(item.get("vehicle_id")) == vehicle_id), None)
            if not vehicle:
                raise ValueError("Veículo não encontrado.")
            reason = clean_text(request.form.get("reason"))
            if len(reason) < 5:
                raise ValueError("Informe o motivo do bloqueio.")
            now, user_id = deps.now_iso(), clean_text(deps.current_user().get("id"))
            block_type = clean_text(request.form.get("block_type"), "decisao_administrativa")
            if block_type not in BLOCK_TYPES:
                raise ValueError("Tipo de bloqueio inválido.")
            block = {"id": next_id(current["blocks"], "BLK"), "vehicle_id": vehicle_id, "occurrence_id": clean_text(request.form.get("occurrence_id")), "checklist_id": clean_text(request.form.get("checklist_id")), "service_order_id": clean_text(request.form.get("service_order_id")), "block_type": block_type, "reason": reason, "severity": clean_text(request.form.get("severity"), "alta"), "blocked_at": now, "blocked_by": user_id, "status": "ativo", "released_at": "", "released_by": "", "release_reason": "", "resolution_confirmed": False, "created_at": now, "updated_at": now, "deleted_at": ""}
            current["blocks"].append(block)
            vehicle = {**vehicle, "status": "bloqueado", "status_label": "Bloqueado", "maintenance_block_reason": reason, "updated_at": now}
            current["vehicles"] = deps.upsert_item(current["vehicles"], vehicle, "vehicle_id")
            save(current, "blocks", "vehicles")
            deps.record_vehicle_maintenance_history(vehicle_id=vehicle_id, mileage=None, record_date=now[:10], source="bloqueio operacional", user_id=user_id, notes=reason, action="operational_block", previous_data=None, new_data=block)
            deps.record_audit("block", "fleet_blocks", block["id"], "Veículo bloqueado operacionalmente.", after=block)
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return checklist_redirect(vehicle_id=vehicle_id)

    @app.route("/fleet/operational-blocks/<block_id>/release", methods=["POST"])
    @deps.require_permission("fleet.vehicle.release")
    def release_vehicle_operational_block(block_id: str):
        current = state()
        try:
            block = find(current["blocks"], block_id, "Bloqueio")
            reason = clean_text(request.form.get("release_reason"))
            if len(reason) < 10 or not request.form.get("resolution_confirmed"):
                raise ValueError("Confirme a resolução e informe justificativa de liberação com pelo menos 10 caracteres.")
            allowed, reasons = release_block_allowed(block=block, blocks=current["blocks"], occurrences=current["occurrences"], service_orders=current["service_orders"], documents=current["documents"])
            if not allowed:
                raise ValueError(" ".join(reasons))
            now, user_id = deps.now_iso(), clean_text(deps.current_user().get("id"))
            updated = {**block, "status": "liberado", "released_at": now, "released_by": user_id, "release_reason": reason, "resolution_confirmed": True, "updated_at": now}
            current["blocks"] = upsert(current["blocks"], updated)
            vehicle = next((item for item in current["vehicles"] if clean_text(item.get("vehicle_id")) == clean_text(block.get("vehicle_id"))), None)
            if vehicle:
                vehicle = {**vehicle, "status": "disponivel", "status_label": "Disponível", "maintenance_block_reason": "", "updated_at": now}
                current["vehicles"] = deps.upsert_item(current["vehicles"], vehicle, "vehicle_id")
            save(current, "blocks", "vehicles")
            deps.record_vehicle_maintenance_history(vehicle_id=clean_text(block.get("vehicle_id")), mileage=None, record_date=now[:10], source="liberação operacional", user_id=user_id, notes=reason, action="operational_release", previous_data=block, new_data=updated)
            deps.record_audit("release", "fleet_blocks", block_id, "Bloqueio operacional liberado.", before=block, after=updated)
            flash("Veículo liberado após validação formal.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return checklist_redirect()
