from __future__ import annotations

import io
from datetime import datetime

from flask import redirect, request, send_file, url_for


def register_finance_routes(app, deps) -> None:
    @app.route("/financial/receivables", methods=["POST"])
    @deps.require_permission("finance.payments")
    def save_financial_receivable():
        try:
            items = deps.load_financial_receivables()
            record = deps.create_financial_receivable_record(request.form, items)
            before = next((item for item in items if deps.clean_text(item.get("id")) == deps.clean_text(record.get("id"))), None)
            deps.save_financial_receivables(deps.upsert_item(items, record, "id"))
            deps.record_audit("save", "finance", record["id"], "Conta a receber salva.", before=before, after=record)
            deps.flash_action_success(
                "Conta a receber salva.",
                f"Cobrança de {record.get('client_name') or 'cliente não informado'} registrada no financeiro.",
                next_step="Acompanhe o vencimento e registre o pagamento quando o cliente pagar.",
                target_href="#receivables-panel",
                target_tab="summary-tab",
                action="Ver contas a receber",
            )
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "finance")
        return redirect(url_for("index"))

    @app.route("/financial/receivables/generate-monthly", methods=["POST"])
    @deps.require_permission("finance.payments")
    def generate_monthly_receivables():
        try:
            period = deps.clean_text(request.form.get("period")) or datetime.now().date().isoformat()[:7]
            due_day = int(deps.clean_text(request.form.get("due_day"), "10") or 10)
            created = deps.generate_monthly_contract_receivables(period, due_day)
            deps.record_audit("generate", "finance", period, f"{len(created)} cobrança(s) mensal(is) gerada(s).")
            deps.flash_action_success(
                "Sucesso: cobranças mensais geradas",
                f"{len(created)} cobrança(s) mensal(is) foram criadas para {period}.",
                next_step="Revise os vencimentos e acompanhe as pendências no painel financeiro.",
                target_href="#receivables-panel",
                target_tab="summary-tab",
                action="Ver cobranças",
            )
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "finance")
        return redirect(url_for("index"))

    @app.route("/financial/receivables/<receivable_id>/payment", methods=["POST"])
    @deps.require_permission("finance.payments")
    def update_receivable_payment(receivable_id: str):
        try:
            items = deps.load_financial_receivables()
            target = next((item for item in items if deps.clean_text(item.get("id")) == deps.clean_text(receivable_id)), None)
            if not target:
                raise ValueError("Conta a receber não encontrada.")
            before = dict(target)
            action = deps.clean_text(request.form.get("action"), "paid")
            total_amount = deps.parse_decimal(target.get("amount"))
            current_received = min(deps.parse_decimal(target.get("amount_received")), total_amount)
            received_date = deps.clean_text(request.form.get("received_date")) or datetime.now().date().isoformat()
            payment_method = deps.clean_text(request.form.get("payment_method")) or deps.clean_text(target.get("payment_method")) or "pix"
            if action == "cancel":
                target["status"] = "cancelado"
            else:
                remaining = max(total_amount - current_received, 0.0)
                payment_amount = deps.parse_decimal(request.form.get("payment_amount") or request.form.get("amount_received"), remaining)
                if payment_amount <= 0:
                    raise ValueError("Informe um valor de pagamento maior que zero.")
                if action != "partial":
                    payment_amount = remaining if remaining > 0 else total_amount
                new_received = min(current_received + payment_amount, total_amount)
                target["amount_received"] = new_received
                target["received_date"] = received_date
                target["payment_method"] = payment_method
                history = target.get("payment_history") if isinstance(target.get("payment_history"), list) else []
                history.append(
                    {
                        "id": f"PGT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                        "amount": round(payment_amount, 2),
                        "payment_method": payment_method,
                        "received_date": received_date,
                        "notes": deps.clean_text(request.form.get("payment_notes")),
                        "created_at": deps.now_iso(),
                    }
                )
                target["payment_history"] = history
                target["status"] = deps.normalize_receivable_status(
                    "parcial" if action == "partial" else "pago",
                    due_date=target.get("due_date"),
                    amount=total_amount,
                    amount_received=new_received,
                )
                target["collection_status"] = "pagamento_registrado"
            target["updated_at"] = deps.now_iso()
            deps.save_financial_receivables(items)
            deps.record_audit("payment", "finance", receivable_id, "Pagamento registrado.", before=before, after=target)
            deps.flash_action_success(
                "Pagamento registrado.",
                f"Pagamento da cobrança {receivable_id} foi baixado no financeiro.",
                next_step="Confira se o status ficou como pago ou parcial e gere recibo se necessário.",
                target_href="#receivables-panel",
                target_tab="summary-tab",
                action="Ver cobrança",
            )
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "finance")
        return redirect(url_for("index"))

    @app.route("/financial/receivables/<receivable_id>/delete", methods=["POST"])
    @deps.require_permission("finance.payments")
    def delete_financial_receivable(receivable_id: str):
        try:
            current_items = deps.load_financial_receivables()
            before = next((item for item in current_items if deps.clean_text(item.get("id")) == deps.clean_text(receivable_id)), None)
            items, deleted = deps.delete_item(current_items, "id", receivable_id)
            if not deleted:
                raise ValueError("Conta a receber não encontrada.")
            deps.save_financial_receivables(items)
            deps.record_audit("delete", "finance", receivable_id, "Conta a receber excluída.", before=before)
            deps.flash_action_success(
                "Recebimento excluído.",
                f"A cobrança {receivable_id} foi removida da lista financeira.",
                next_step="Revise o painel financeiro para confirmar os totais em aberto e vencidos.",
                target_href="#receivables-panel",
                target_tab="summary-tab",
                action="Ver financeiro",
            )
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "finance")
        return redirect(url_for("index", _anchor="receivables-panel"))

    @app.route("/financial/receivables/<receivable_id>/receipt.pdf", methods=["GET"])
    @deps.require_permission("finance.export")
    def download_receivable_receipt(receivable_id: str):
        target = next((item for item in deps.load_financial_receivables() if deps.clean_text(item.get("id")) == deps.clean_text(receivable_id)), None)
        if not target:
            deps.flash_action_error(ValueError("Conta a receber não encontrada."), "finance")
            return redirect(url_for("index"))
        deps.record_audit("generate_pdf", "finance", receivable_id, "Recibo financeiro PDF gerado.")
        return send_file(
            io.BytesIO(deps.build_receipt_pdf(target)),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"sannygold-recibo-{receivable_id}.pdf",
        )

    @app.route("/financial/entries", methods=["POST"])
    @deps.require_permission("finance.edit")
    def save_financial_entry():
        try:
            items = deps.load_financial_entries()
            record = deps.create_financial_entry_record(request.form, items)
            before = next((item for item in items if deps.clean_text(item.get("id")) == deps.clean_text(record.get("id"))), None)
            deps.save_financial_entries(deps.upsert_item(items, record, "id"))
            deps.record_audit("save", "finance", record["id"], "Lançamento financeiro salvo.", before=before, after=record)
            deps.flash_action_success(
                "Sucesso: lançamento financeiro salvo",
                f"Lançamento {record['id']} registrado como {record.get('entry_type')}.",
                next_step="Confira o painel financeiro para validar o impacto no mês.",
                target_href="#financial-decision-panel",
                target_tab="summary-tab",
                action="Abrir painel financeiro",
            )
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "finance")
        return redirect(url_for("index"))

    @app.route("/financial/monthly-closeouts", methods=["POST"])
    @deps.require_permission("finance.close")
    def save_financial_monthly_closeout():
        try:
            period = deps.clean_text(request.form.get("period")) or datetime.now().date().isoformat()[:7]
            record = deps.build_monthly_closeout(period, request.form.get("notes", ""))
            deps.record_audit("close", "finance", period, f"Fechamento financeiro de {period} gerado.", after=record)
            deps.flash_action_success(
                "Sucesso: fechamento financeiro gerado",
                f"Fechamento financeiro de {period} foi atualizado com os dados disponíveis.",
                next_step="Revise receitas, despesas e pendências antes de usar para decisão gerencial.",
                target_href="#financial-decision-panel",
                target_tab="summary-tab",
                action="Revisar financeiro",
            )
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "finance")
        return redirect(url_for("index"))

    @app.route("/financial/monthly-closeouts/<period>.pdf", methods=["GET"])
    @deps.require_permission("finance.export")
    def download_financial_monthly_closeout_pdf(period: str):
        try:
            payload = deps.build_monthly_closeout_pdf(period)
        except Exception as exc:  # noqa: BLE001
            return deps.friendly_error_text(exc, "finance"), 404
        deps.record_audit("generate_pdf", "finance", period, f"PDF do fechamento financeiro {period} gerado.")
        return send_file(
            io.BytesIO(payload),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"sannygold-fechamento-financeiro-{period}.pdf",
        )
