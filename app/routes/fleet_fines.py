from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from flask import abort, flash, redirect, render_template, request, send_file, send_from_directory, url_for
from werkzeug.utils import secure_filename

from app.services.fleet_fines import (
    DEADLINE_TYPES, DECISIONS, DOCUMENT_STATUSES, IDENTIFICATION_STATUSES, INFRACTION_STATUSES,
    JURISDICTIONS, NIC_STATUSES, NOTIFICATION_TYPES, PROCEEDING_STATUSES, PROCEEDING_TYPES,
    SENSITIVE_DOCUMENT_TYPES, as_bool, as_float, build_dashboard, build_deadlines, build_decision,
    attachment_access_allowed, build_audit_log, build_identification, build_infraction, build_proceeding,
    build_protocol, clean_text, complete_deadline, compute_nic_risk, confirm_identification,
    driver_can_view_infraction, file_sha256, import_mapping, financial_link_note,
    find_linked_financial_entry, next_id, normalize_plate, soft_delete, suggest_driver,
)


def register_fleet_fines_routes(app, deps) -> None:
    def state() -> dict:
        return {key: loader(include_archived=True) for key, loader in {
            "infractions": deps.load_fleet_traffic_infractions, "deadlines": deps.load_fleet_infraction_deadlines,
            "identifications": deps.load_fleet_infraction_driver_identifications,
            "document_templates": deps.load_fleet_infraction_document_templates,
            "document_template_items": deps.load_fleet_infraction_document_template_items,
            "documents": deps.load_fleet_infraction_documents, "proceedings": deps.load_fleet_infraction_proceedings,
            "protocols": deps.load_fleet_infraction_protocols, "payments": deps.load_fleet_infraction_payments,
            "attachments": deps.load_fleet_infraction_attachments, "decisions": deps.load_fleet_infraction_decisions,
            "audit_logs": deps.load_fleet_infraction_audit_logs,
        }.items()}

    def save(current: dict, *keys: str) -> None:
        savers = {
            "infractions": deps.save_fleet_traffic_infractions, "deadlines": deps.save_fleet_infraction_deadlines,
            "identifications": deps.save_fleet_infraction_driver_identifications,
            "document_templates": deps.save_fleet_infraction_document_templates,
            "document_template_items": deps.save_fleet_infraction_document_template_items,
            "documents": deps.save_fleet_infraction_documents, "proceedings": deps.save_fleet_infraction_proceedings,
            "protocols": deps.save_fleet_infraction_protocols, "payments": deps.save_fleet_infraction_payments,
            "attachments": deps.save_fleet_infraction_attachments, "decisions": deps.save_fleet_infraction_decisions,
            "audit_logs": deps.save_fleet_infraction_audit_logs,
        }
        for key in keys:
            savers[key](current[key])

    def find(records: list[dict], record_id: str, label: str) -> dict:
        record = next((item for item in records if clean_text(item.get("id")) == clean_text(record_id) and not clean_text(item.get("deleted_at"))), None)
        if not record:
            raise ValueError(f"{label} não encontrado.")
        return record

    def set_record(records: list[dict], record: dict) -> list[dict]:
        return deps.upsert_item(records, record, "id")

    def audit(current: dict, infraction_id: str, action: str, *, before=None, after=None, justification: str = "") -> None:
        now, user = deps.now_iso(), deps.current_user()
        log = build_audit_log(log_id=next_id(current["audit_logs"], "FAL"), infraction_id=infraction_id,
                              user_id=clean_text(user.get("id")), action=action,
                              before=deps.sanitize_audit_payload(before), after=deps.sanitize_audit_payload(after),
                              justification=justification, created_at=now)
        current["audit_logs"].append(log)
        save(current, "audit_logs")
        deps.record_audit(action, "fleet_fines", infraction_id, justification or action, before=before, after=after)

    def redirect_detail(infraction_id: str = ""):
        return redirect(url_for("fleet_fines_home", infraction=infraction_id) + ("#detalhe" if infraction_id else ""))

    def permissions(user: dict) -> dict:
        names = (
            "fleet.fines.create", "fleet.fines.edit", "fleet.fines.assign", "fleet.fines.driver_identify",
            "fleet.fines.documents.manage", "fleet.fines.proceedings.manage", "fleet.fines.protocol.manage",
            "fleet.fines.decide", "fleet.fines.payments.view", "fleet.fines.payments.manage",
            "fleet.fines.financial_responsibility.manage", "fleet.fines.reports.view",
            "fleet.fines.sensitive_documents.view", "fleet.fines.audit.view", "fleet.fines.settings.manage",
        )
        return {name: deps.has_permission(user, name) for name in names}

    @app.route("/fleet/fines", methods=["GET"])
    @deps.require_permission("fleet.fines.view")
    def fleet_fines_home():
        current, user = state(), deps.current_user()
        user_permissions = permissions(user)
        driver_authorizations = deps.load_fleet_driver_authorizations(include_archived=True)
        is_driver = clean_text(user.get("role")) == "leitura" and any(clean_text(item.get("user_id")) == clean_text(user.get("id")) and clean_text(item.get("status")) == "ativo" for item in driver_authorizations)
        if is_driver:
            current["infractions"] = [item for item in current["infractions"] if driver_can_view_infraction(item, clean_text(user.get("id")))]
            allowed = {clean_text(item.get("id")) for item in current["infractions"]}
            for key in ("deadlines", "identifications", "documents", "proceedings", "protocols", "payments", "attachments", "decisions", "audit_logs"):
                current[key] = [item for item in current[key] if clean_text(item.get("infraction_id")) in allowed]
        filters = {name: clean_text(request.args.get(name)) for name in ("period_start", "period_end", "vehicle", "driver", "authority", "status", "notification_type", "financial_responsibility")}
        filtered = [item for item in current["infractions"] if not clean_text(item.get("deleted_at"))]
        for key, field in (("vehicle", "vehicle_id"), ("driver", "driver_id"), ("authority", "issuing_authority"), ("status", "status"), ("notification_type", "notification_type"), ("financial_responsibility", "financial_responsibility")):
            if filters[key]:
                filtered = [item for item in filtered if clean_text(item.get(field)) == filters[key]]
        if filters["period_start"]:
            filtered = [item for item in filtered if clean_text(item.get("infraction_date")) >= filters["period_start"]]
        if filters["period_end"]:
            filtered = [item for item in filtered if clean_text(item.get("infraction_date")) <= filters["period_end"]]
        allowed_ids = {clean_text(item.get("id")) for item in filtered}
        current_deadlines = [item for item in current["deadlines"] if clean_text(item.get("infraction_id")) in allowed_ids]
        dashboard = build_dashboard(filtered, current_deadlines, current["payments"], current["proceedings"])
        vehicles = [item for item in deps.load_vehicles_registry(include_archived=True) if not clean_text(item.get("deleted_at"))]
        users = [item for item in deps.load_users() if clean_text(item.get("status")) == "ativo"]
        vehicle_map = {clean_text(item.get("vehicle_id")): item for item in vehicles}
        user_map = {clean_text(item.get("id")): clean_text(item.get("nome")) for item in users}
        for item in filtered:
            item["plate"] = clean_text(vehicle_map.get(clean_text(item.get("vehicle_id")), {}).get("plate")) or clean_text(item.get("vehicle_plate_snapshot"))
            item["driver_name"] = user_map.get(clean_text(item.get("driver_id")), "Não confirmado")
        for item in dashboard["deadlines"]:
            infraction = next((record for record in filtered if clean_text(record.get("id")) == clean_text(item.get("infraction_id"))), {})
            item["internal_number"] = clean_text(infraction.get("internal_number"))
            item["plate"] = clean_text(infraction.get("vehicle_plate_snapshot"))
            item["driver_name"] = user_map.get(clean_text(infraction.get("driver_id")), "Não confirmado")
        selected_id = clean_text(request.args.get("infraction"))
        selected = next((item for item in filtered if clean_text(item.get("id")) == selected_id), None)
        related = SimpleNamespace(**{key: [item for item in current[key] if selected and clean_text(item.get("infraction_id")) == selected_id and not clean_text(item.get("deleted_at"))] for key in ("deadlines", "identifications", "documents", "proceedings", "protocols", "payments", "attachments", "decisions", "audit_logs")})
        return render_template("fleet_fines.html", current_user=user, permissions=user_permissions, dashboard=dashboard,
                               infractions=filtered, selected=selected, related=related, vehicles=vehicles, users=users,
                               notification_types=NOTIFICATION_TYPES, jurisdictions=JURISDICTIONS, infraction_statuses=INFRACTION_STATUSES,
                               identification_statuses=IDENTIFICATION_STATUSES, nic_statuses=NIC_STATUSES, deadline_types=DEADLINE_TYPES,
                               proceeding_types=PROCEEDING_TYPES, proceeding_statuses=PROCEEDING_STATUSES,
                               document_statuses=DOCUMENT_STATUSES, decisions=DECISIONS, filters=filters,
                               is_driver=is_driver, today_iso=date.today().isoformat(), settings=deps.load_settings())

    @app.route("/fleet/fines", methods=["POST"])
    @deps.require_permission("fleet.fines.create")
    def create_fleet_infraction():
        current, now, user = state(), deps.now_iso(), deps.current_user()
        try:
            record = build_infraction(request.form, records=current["infractions"], vehicles=deps.load_vehicles_registry(include_archived=True), user_id=clean_text(user.get("id")), now=now)
            current["infractions"] = set_record(current["infractions"], record)
            current["deadlines"] = build_deadlines(request.form, infraction_id=record["id"], existing=current["deadlines"], user_id=clean_text(user.get("id")), now=now)
            suggestion = suggest_driver(record, assignments=deps.load_fleet_vehicle_assignments(include_archived=True), checklists=deps.load_fleet_checklists(include_archived=True), vehicles=deps.load_vehicles_registry(include_archived=True))
            identification = build_identification(record, suggestion, existing=current["identifications"], now=now)
            current["identifications"] = set_record(current["identifications"], identification)
            template = next((item for item in current["document_templates"] if clean_text(item.get("issuing_authority")).casefold() == clean_text(record.get("issuing_authority")).casefold() and as_bool(item.get("is_active")) and not clean_text(item.get("deleted_at"))), None)
            if template:
                for item in current["document_template_items"]:
                    if clean_text(item.get("template_id")) == clean_text(template.get("id")) and not clean_text(item.get("deleted_at")):
                        current["documents"].append({"id": next_id(current["documents"], "FDC"), "infraction_id": record["id"],
                                                     "document_type": clean_text(item.get("document_type")), "status": "pendente" if as_bool(item.get("is_required")) else "nao_solicitado",
                                                     "is_sensitive": clean_text(item.get("document_type")) in SENSITIVE_DOCUMENT_TYPES, "template_item_id": item["id"],
                                                     "created_at": now, "updated_at": now, "deleted_at": ""})
            record["driver_identification_status"] = identification["status"]
            record["nic_risk_status"] = compute_nic_risk(record, current["deadlines"])
            current["infractions"] = set_record(current["infractions"], record)
            save(current, "infractions", "deadlines", "identifications", "documents")
            audit(current, record["id"], "create", after=record, justification="Infração cadastrada e submetida à conferência humana.")
            flash(f"Infração {record['internal_number']} cadastrada.", "success")
            return redirect_detail(record["id"])
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
            return redirect_detail()

    @app.route("/fleet/fines/<infraction_id>/edit", methods=["POST"])
    @deps.require_permission("fleet.fines.edit")
    def edit_fleet_infraction(infraction_id: str):
        current, now, user = state(), deps.now_iso(), deps.current_user()
        try:
            before = dict(find(current["infractions"], infraction_id, "Infração"))
            payload = request.form.to_dict()
            payload["id"] = infraction_id
            record = build_infraction(payload, records=current["infractions"], vehicles=deps.load_vehicles_registry(include_archived=True), user_id=clean_text(user.get("id")), now=now)
            current["deadlines"] = build_deadlines(payload, infraction_id=infraction_id, existing=current["deadlines"], user_id=clean_text(user.get("id")), now=now)
            record["nic_risk_status"] = compute_nic_risk(record, current["deadlines"])
            current["infractions"] = set_record(current["infractions"], record)
            save(current, "infractions", "deadlines")
            audit(current, infraction_id, "edit", before=before, after=record, justification=clean_text(request.form.get("change_reason"), "Cadastro revisado."))
            flash("Infração atualizada.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return redirect_detail(infraction_id)

    @app.route("/fleet/fines/<infraction_id>/identify-driver", methods=["POST"])
    @deps.require_permission("fleet.fines.driver_identify")
    def identify_fleet_infraction_driver(infraction_id: str):
        current, now, user = state(), deps.now_iso(), deps.current_user()
        try:
            infraction = find(current["infractions"], infraction_id, "Infração")
            identification = next((item for item in current["identifications"] if clean_text(item.get("infraction_id")) == infraction_id and not clean_text(item.get("deleted_at"))), None)
            if not identification:
                raise ValueError("A sugestão de motorista ainda não foi calculada.")
            before = dict(identification)
            identification = confirm_identification(identification, driver_id=request.form.get("driver_id"), user_id=clean_text(user.get("id")), now=now,
                                                     notes=request.form.get("notes", ""), disagreement=request.form.get("disagreement", ""))
            current["identifications"] = set_record(current["identifications"], identification)
            infraction = {**infraction, "driver_id": identification["confirmed_driver_id"], "driver_identification_status": identification["status"],
                          "route_id": clean_text(infraction.get("route_id") or identification.get("route_id")), "operation_id": clean_text(infraction.get("operation_id") or identification.get("operation_id")), "updated_at": now}
            infraction["nic_risk_status"] = compute_nic_risk(infraction, current["deadlines"])
            current["infractions"] = set_record(current["infractions"], infraction)
            save(current, "identifications", "infractions")
            audit(current, infraction_id, "confirm_driver", before=before, after=identification, justification=clean_text(request.form.get("notes"), "Condutor confirmado após revisão humana."))
            flash("Motorista confirmado internamente. Isso não equivale à aceitação pelo órgão.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return redirect_detail(infraction_id)

    @app.route("/fleet/fines/<infraction_id>/release-driver-view", methods=["POST"])
    @deps.require_permission("fleet.fines.assign")
    def release_fleet_infraction_to_driver(infraction_id: str):
        current = state()
        try:
            before = find(current["infractions"], infraction_id, "Infração")
            if not clean_text(before.get("driver_id")) or clean_text(before.get("driver_identification_status")) != "confirmado_internamente":
                raise ValueError("Confirme internamente o motorista antes de liberar a ciência.")
            released = {**before, "released_to_driver_at": deps.now_iso(), "released_to_driver_by": clean_text(deps.current_user().get("id")), "updated_at": deps.now_iso()}
            current["infractions"] = set_record(current["infractions"], released)
            save(current, "infractions")
            audit(current, infraction_id, "release_driver_view", before=before, after=released, justification="Infração formalmente liberada para ciência do motorista relacionado.")
            flash("Infração liberada para ciência do motorista relacionado.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return redirect_detail(infraction_id)

    @app.route("/fleet/fines/<infraction_id>/proceedings", methods=["POST"])
    @deps.require_permission("fleet.fines.proceedings.manage")
    def create_fleet_infraction_proceeding(infraction_id: str):
        current, now, user = state(), deps.now_iso(), deps.current_user()
        try:
            find(current["infractions"], infraction_id, "Infração")
            record = build_proceeding(request.form, infraction_id=infraction_id, records=current["proceedings"], user_id=clean_text(user.get("id")), now=now)
            current["proceedings"].append(record)
            save(current, "proceedings")
            audit(current, infraction_id, "create_proceeding", after=record, justification="Processo administrativo aberto para preparação e revisão humana.")
            flash("Processo administrativo registrado.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return redirect_detail(infraction_id)

    @app.route("/fleet/fines/<infraction_id>/decision", methods=["POST"])
    @deps.require_permission("fleet.fines.decide")
    def decide_fleet_infraction(infraction_id: str):
        current, now, user = state(), deps.now_iso(), deps.current_user()
        try:
            infraction = find(current["infractions"], infraction_id, "Infração")
            record = build_decision(request.form, infraction_id=infraction_id, records=current["decisions"], user_id=clean_text(user.get("id")), now=now)
            current["decisions"].append(record)
            infraction = {**infraction, "decision_status": record["decision"], "status": "aguardando_pagamento" if record["decision"] in {"identify_pay", "recognize_pay"} else infraction.get("status"), "updated_at": now}
            current["infractions"] = set_record(current["infractions"], infraction)
            save(current, "decisions", "infractions")
            audit(current, infraction_id, "decision", after=record, justification=record["justification"])
            flash("Decisão humana registrada.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return redirect_detail(infraction_id)

    def save_uploaded(uploaded, *, infraction: dict, category: str) -> tuple[Path, str, str]:
        safe_name, _ = deps.validate_uploaded_file(uploaded, field_label="Anexo da multa", allowed_extensions=deps.fleet_fines_extensions, allowed_label=", ".join(sorted(deps.fleet_fines_extensions)))
        year = clean_text(infraction.get("infraction_date"))[:4] or str(date.today().year)
        plate = normalize_plate(infraction.get("vehicle_plate_snapshot")) or "SEM_PLACA"
        folder = deps.fleet_uploads_dir / plate / "Multas" / year / clean_text(infraction.get("internal_number")) / secure_filename(category)
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / f"{uuid4().hex[:10]}-{safe_name}"
        uploaded.save(destination)
        return destination, destination.relative_to(deps.fleet_uploads_dir).as_posix(), safe_name

    @app.route("/fleet/fines/<infraction_id>/attachments", methods=["POST"])
    @deps.require_permission("fleet.fines.documents.manage")
    def upload_fleet_infraction_attachment(infraction_id: str):
        current, destination = state(), None
        try:
            infraction = find(current["infractions"], infraction_id, "Infração")
            category = clean_text(request.form.get("category"), "Notificacao")
            destination, relative, safe_name = save_uploaded(request.files.get("file"), infraction=infraction, category=category)
            document_type = clean_text(request.form.get("document_type"), category.lower())
            sensitive = as_bool(request.form.get("is_sensitive")) or document_type in SENSITIVE_DOCUMENT_TYPES
            record = {"id": next_id(current["attachments"], "FAT"), "infraction_id": infraction_id,
                      "proceeding_id": clean_text(request.form.get("proceeding_id")), "category": category,
                      "document_type": document_type, "original_name": safe_name, "file_path": relative,
                      "content_type": clean_text(request.files["file"].mimetype), "size_bytes": destination.stat().st_size,
                      "sha256": file_sha256(destination), "is_sensitive": sensitive, "uploaded_by": clean_text(deps.current_user().get("id")),
                      "created_at": deps.now_iso(), "deleted_at": ""}
            current["attachments"].append(record)
            current["documents"].append({"id": next_id(current["documents"], "FDC"), "infraction_id": infraction_id,
                                         "document_type": document_type, "status": "recebido", "file_path": relative,
                                         "is_sensitive": sensitive, "attachment_id": record["id"], "created_at": deps.now_iso(), "updated_at": deps.now_iso(), "deleted_at": ""})
            save(current, "attachments", "documents")
            audit(current, infraction_id, "upload_document", after={**record, "file_path": "[protegido]"}, justification="Documento anexado à pasta protegida da multa.")
            flash("Anexo protegido salvo.", "success")
        except Exception as exc:  # noqa: BLE001
            if destination:
                destination.unlink(missing_ok=True)
            deps.flash_action_error(exc, "upload")
        return redirect_detail(infraction_id)

    @app.route("/fleet/fines/files/<attachment_id>", methods=["GET"])
    @deps.require_permission("fleet.fines.view")
    def fleet_infraction_file(attachment_id: str):
        current, user = state(), deps.current_user()
        record = find(current["attachments"], attachment_id, "Anexo")
        infraction = find(current["infractions"], clean_text(record.get("infraction_id")), "Infração")
        if not attachment_access_allowed(record, infraction, user_id=clean_text(user.get("id")), role=clean_text(user.get("role")),
                                         can_view_sensitive=deps.has_permission(user, "fleet.fines.sensitive_documents.view")):
            deps.record_audit("access_denied", "fleet_fines", clean_text(record.get("infraction_id")), "Documento sensível bloqueado.")
            abort(403)
        return send_from_directory(deps.fleet_uploads_dir, clean_text(record.get("file_path")), as_attachment=False)

    @app.route("/fleet/fines/<infraction_id>/protocols", methods=["POST"])
    @deps.require_permission("fleet.fines.protocol.manage")
    def create_fleet_infraction_protocol(infraction_id: str):
        current, destination = state(), None
        try:
            infraction = find(current["infractions"], infraction_id, "Infração")
            proof_path = ""
            uploaded = request.files.get("proof_file")
            if uploaded and uploaded.filename:
                destination, proof_path, _ = save_uploaded(uploaded, infraction=infraction, category="Protocolos")
            record = build_protocol(request.form, infraction_id=infraction_id, records=current["protocols"], user_id=clean_text(deps.current_user().get("id")), now=deps.now_iso(), proof_path=proof_path)
            current["protocols"].append(record)
            if record["proceeding_id"]:
                proceeding = find(current["proceedings"], record["proceeding_id"], "Processo")
                current["proceedings"] = set_record(current["proceedings"], {**proceeding, "status": "protocolado", "protocol_date": record["protocol_date"], "protocol_number": record["protocol_number"], "protocol_channel": record["protocol_channel"], "updated_at": deps.now_iso()})
            save(current, "protocols", "proceedings")
            audit(current, infraction_id, "protocol", after={**record, "proof_path": "[protegido]"}, justification="Protocolo registrado com comprovante ou exceção autorizada.")
            flash("Protocolo registrado.", "success")
        except Exception as exc:  # noqa: BLE001
            if destination:
                destination.unlink(missing_ok=True)
            deps.flash_action_error(exc, "fleet")
        return redirect_detail(infraction_id)

    @app.route("/fleet/fines/deadlines/<deadline_id>/complete", methods=["POST"])
    @deps.require_permission("fleet.fines.edit")
    def complete_fleet_infraction_deadline(deadline_id: str):
        current, destination = state(), None
        try:
            deadline = find(current["deadlines"], deadline_id, "Prazo")
            infraction = find(current["infractions"], clean_text(deadline.get("infraction_id")), "Infração")
            proof_path = ""
            uploaded = request.files.get("proof_file")
            if uploaded and uploaded.filename:
                destination, proof_path, _ = save_uploaded(uploaded, infraction=infraction, category="Protocolos")
            completed = complete_deadline(deadline, user_id=clean_text(deps.current_user().get("id")), now=deps.now_iso(), proof_path=proof_path, justification=request.form.get("justification", ""))
            current["deadlines"] = set_record(current["deadlines"], completed)
            save(current, "deadlines")
            audit(current, infraction["id"], "complete_deadline", before=deadline, after={**completed, "completion_proof_path": "[protegido]"}, justification=clean_text(request.form.get("justification"), "Prazo concluído com comprovante."))
            flash("Etapa concluída e auditada.", "success")
        except Exception as exc:  # noqa: BLE001
            if destination:
                destination.unlink(missing_ok=True)
            deps.flash_action_error(exc, "fleet")
        return redirect_detail(clean_text((locals().get("deadline") or {}).get("infraction_id")))

    @app.route("/fleet/fines/<infraction_id>/payments", methods=["POST"])
    @deps.require_permission("fleet.fines.payments.manage")
    def create_fleet_infraction_payment(infraction_id: str):
        current, now = state(), deps.now_iso()
        try:
            infraction = find(current["infractions"], infraction_id, "Infração")
            existing = next((item for item in current["payments"] if clean_text(item.get("infraction_id")) == infraction_id and not clean_text(item.get("deleted_at"))), None)
            financial_entries = deps.load_financial_entries()
            if existing and clean_text(existing.get("financial_entry_id")):
                raise ValueError("Esta multa já possui lançamento financeiro vinculado. Atualize o lançamento existente para evitar duplicidade.")
            amount = as_float(request.form.get("paid_amount") or request.form.get("original_amount") or infraction.get("final_amount") or infraction.get("original_amount"))
            if amount <= 0:
                raise ValueError("Informe o valor do pagamento.")
            unique_note = financial_link_note(infraction_id)
            finance_form = {"entry_type": "saida", "category": "multas_frota", "description": f"{infraction['internal_number']} - {infraction['issuing_authority']}",
                            "amount": str(amount), "entry_date": clean_text(request.form.get("payment_date"), date.today().isoformat()),
                            "status": "realizado" if clean_text(request.form.get("status"), "pago") == "pago" else "pendente",
                            "notes": unique_note}
            financial = find_linked_financial_entry(financial_entries, infraction_id)
            if not financial:
                financial = deps.create_financial_entry_record(finance_form, financial_entries)
                deps.save_financial_entries(deps.upsert_item(financial_entries, financial, "id"))
            record = {"id": next_id(current["payments"], "FPY"), "infraction_id": infraction_id,
                      "payer_company_id": clean_text(request.form.get("payer_company_id") or infraction.get("operating_company_id")),
                      "financial_entry_id": financial["id"], "due_date": clean_text(request.form.get("due_date")),
                      "original_amount": as_float(request.form.get("original_amount") or infraction.get("original_amount")),
                      "discount_amount": as_float(request.form.get("discount_amount")), "interest_amount": as_float(request.form.get("interest_amount")),
                      "additional_fees": as_float(request.form.get("additional_fees")), "paid_amount": amount,
                      "payment_date": clean_text(request.form.get("payment_date")), "payment_method": clean_text(request.form.get("payment_method")),
                      "barcode": clean_text(request.form.get("barcode")), "status": clean_text(request.form.get("status"), "pago"),
                      "receipt_path": "", "approved_by": clean_text(deps.current_user().get("id")), "created_at": now, "updated_at": now, "deleted_at": ""}
            current["payments"].append(record)
            infraction = {**infraction, "payment_status": record["status"], "status": "paga" if record["status"] == "pago" else "aguardando_pagamento", "updated_at": now}
            current["infractions"] = set_record(current["infractions"], infraction)
            save(current, "payments", "infractions")
            audit(current, infraction_id, "payment", after={**record, "barcode": "[protegido]"}, justification=f"Pagamento vinculado ao lançamento financeiro {financial['id']}.")
            flash("Pagamento registrado no financeiro existente.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "finance")
        return redirect_detail(infraction_id)

    @app.route("/fleet/fines/<infraction_id>/archive", methods=["POST"])
    @deps.require_permission("fleet.fines.edit")
    def archive_fleet_infraction(infraction_id: str):
        current, now = state(), deps.now_iso()
        try:
            before = find(current["infractions"], infraction_id, "Infração")
            if clean_text(before.get("nic_risk_status")) in {"atencao", "alto_risco", "prazo_vencido"}:
                raise ValueError("A infração não pode ser arquivada silenciosamente enquanto houver risco de NIC.")
            archived = soft_delete(before, now=now)
            current["infractions"] = set_record(current["infractions"], archived)
            save(current, "infractions")
            audit(current, infraction_id, "archive", before=before, after=archived, justification=clean_text(request.form.get("justification"), "Exclusão lógica."))
            flash("Infração arquivada por exclusão lógica.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        return redirect_detail()

    @app.route("/fleet/fines/import", methods=["POST"])
    @deps.require_permission("fleet.fines.create")
    def import_fleet_infractions():
        current, temp_path, created = state(), None, []
        try:
            uploaded = request.files.get("spreadsheet")
            safe_name, _ = deps.validate_uploaded_file(uploaded, field_label="Planilha de multas", allowed_extensions={".xlsx"}, allowed_label=".xlsx")
            temp_path = deps.data_dir / f".fleet-fines-import-{uuid4().hex}-{safe_name}"
            uploaded.save(temp_path)
            rows = deps.parse_xlsx_rows(temp_path)
            vehicles, users = deps.load_vehicles_registry(include_archived=True), deps.load_users()
            for index, raw in enumerate(rows, start=2):
                mapped = import_mapping(raw)
                vehicle = next((item for item in vehicles if normalize_plate(item.get("plate")) == normalize_plate(mapped.get("plate")) or (clean_text(mapped.get("renavam")) and clean_text(item.get("renavam")) == clean_text(mapped.get("renavam")))), None)
                if not vehicle:
                    raise ValueError(f"Linha {index}: veículo não encontrado no cadastro existente.")
                driver = next((item for item in users if clean_text(item.get("nome")).casefold() == clean_text(mapped.get("driver_name")).casefold()), None)
                payload = {**mapped, "vehicle_id": vehicle["vehicle_id"], "driver_id": clean_text((driver or {}).get("id")),
                           "notification_type": "autuacao", "jurisdiction_type": "outro", "duplicate_review_confirmed": "0"}
                record = build_infraction(payload, records=current["infractions"] + created, vehicles=vehicles, user_id=clean_text(deps.current_user().get("id")), now=deps.now_iso())
                record["import_status"] = "rascunho_conferencia_humana"
                created.append(record)
            current["infractions"].extend(created)
            save(current, "infractions")
            for record in created:
                audit(current, record["id"], "import", after=record, justification="Importação de planilha mantida como rascunho para conferência humana.")
            flash(f"{len(created)} infração(ões) importada(s) como rascunho.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "fleet")
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)
        return redirect_detail()

    @app.route("/fleet/fines/template.xlsx", methods=["GET"])
    @deps.require_permission("fleet.fines.create")
    def fleet_fines_template():
        headers = ["placa", "renavam", "numero_do_auto", "orgao", "codigo", "descricao", "data", "hora", "local", "valor", "pontos", "prazo_de_indicacao", "prazo_de_defesa", "prazo_de_pagamento", "motorista", "status", "observacoes"]
        return send_file(io.BytesIO(deps.build_simple_xlsx_bytes(headers, [], "Multas")), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name="modelo-multas-frota.xlsx")

    @app.route("/fleet/fines/settings", methods=["POST"])
    @deps.require_permission("fleet.fines.settings.manage")
    def save_fleet_fines_settings():
        try:
            settings = deps.load_settings()
            days = sorted({int(value.strip()) for value in clean_text(request.form.get("alert_days")).split(",") if value.strip()}, reverse=True)
            if not days or any(value < 0 or value > 365 for value in days):
                raise ValueError("Informe antecedências entre 0 e 365 dias.")
            links = {}
            for key, label in (("senatran", "Portal de Serviços Senatran"), ("detran_rj", "Detran-RJ"), ("prf", "PRF"), ("dnit", "DNIT"), ("municipal", "Órgão municipal")):
                href = clean_text(request.form.get(f"link_{key}"))
                if href:
                    if not href.startswith("https://"):
                        raise ValueError("Os atalhos oficiais devem usar HTTPS.")
                    links[label] = href
            before = dict(settings)
            settings["fleet_fines_alert_days"] = days
            settings["fleet_fines_official_links"] = links
            deps.save_settings(settings)
            deps.record_audit("save", "fleet_fines_settings", "alerts", "Configurações de alertas e atalhos oficiais atualizadas.", before=before, after=settings)
            flash("Configurações de multas atualizadas.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "settings")
        return redirect(url_for("fleet_fines_home") + "#configuracoes")

    @app.route("/fleet/fines/settings/document-templates", methods=["POST"])
    @deps.require_permission("fleet.fines.settings.manage")
    def create_fleet_infraction_document_template():
        current, now = state(), deps.now_iso()
        try:
            authority, name = clean_text(request.form.get("issuing_authority")), clean_text(request.form.get("name"))
            types = [clean_text(value) for value in clean_text(request.form.get("document_types")).split("|") if clean_text(value)]
            if not authority or not name or not types:
                raise ValueError("Informe órgão, nome e ao menos um tipo documental.")
            template = {"id": next_id(current["document_templates"], "FDT"), "issuing_authority": authority, "name": name,
                        "is_active": True, "created_at": now, "updated_at": now, "deleted_at": ""}
            current["document_templates"].append(template)
            for order, document_type in enumerate(types, start=1):
                current["document_template_items"].append({"id": next_id(current["document_template_items"], "FDTI"), "template_id": template["id"],
                                                           "document_type": document_type, "is_required": True, "display_order": order,
                                                           "created_at": now, "updated_at": now, "deleted_at": ""})
            save(current, "document_templates", "document_template_items")
            deps.record_audit("create", "fleet_fines_settings", template["id"], "Checklist documental por órgão criado.", after=template)
            flash("Checklist documental criado.", "success")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "settings")
        return redirect(url_for("fleet_fines_home") + "#configuracoes")

    def report_rows() -> list[list[str]]:
        current = state()
        return [[item.get("internal_number", ""), item.get("vehicle_plate_snapshot", ""), item.get("issuing_authority", ""), item.get("infraction_notice_number", ""), item.get("infraction_date", ""), item.get("driver_id", ""), item.get("status", ""), item.get("nic_risk_status", ""), item.get("original_amount", 0), item.get("payment_status", "")] for item in current["infractions"] if not clean_text(item.get("deleted_at"))]

    @app.route("/fleet/fines/reports.xlsx", methods=["GET"])
    @deps.require_permission("fleet.fines.reports.view")
    def fleet_fines_report_xlsx():
        headers = ["Número interno", "Placa", "Órgão", "Auto", "Data", "Motorista", "Status", "Risco NIC", "Valor", "Pagamento"]
        return send_file(io.BytesIO(deps.build_simple_xlsx_bytes(headers, report_rows(), "Multas")), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name="relatorio-multas-frota.xlsx")

    @app.route("/fleet/fines/reports.pdf", methods=["GET"])
    @deps.require_permission("fleet.fines.reports.view")
    def fleet_fines_report_pdf():
        lines = [" | ".join(str(value) for value in row) for row in report_rows()] or ["Nenhuma infração cadastrada."]
        return send_file(io.BytesIO(deps.build_simple_text_pdf("SannyGold - Multas da Frota", lines)), mimetype="application/pdf", as_attachment=True, download_name="relatorio-multas-frota.pdf")
