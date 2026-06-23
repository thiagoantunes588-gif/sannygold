from __future__ import annotations

from flask import redirect, request, send_file, url_for


def register_backup_routes(app, deps) -> None:
    @app.route("/backup/system.zip", methods=["GET"])
    @deps.require_permission("settings.manage")
    def download_system_backup():
        try:
            backup = deps.create_data_backup(trigger="download", audit_action=None)
            deps.record_audit(
                "download",
                "backup",
                backup["filename"],
                "Backup completo gerado e baixado.",
                after={key: value for key, value in backup.items() if key != "path"},
            )
            return send_file(
                backup["path"],
                mimetype="application/zip",
                as_attachment=True,
                download_name=backup["filename"],
            )
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "backup")
            return redirect(url_for("index", _anchor="admin-backup-panel"))

    @app.route("/backup/generate", methods=["POST"])
    @deps.require_permission("settings.manage")
    def generate_system_backup():
        try:
            backup = deps.create_data_backup(trigger="manual", audit_action="create")
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "backup")
            return redirect(url_for("index", _anchor="admin-backup-panel"))
        copy_info = backup.get("external_copy") or {}
        copy_warning = copy_info.get("warning", "")
        if backup["missing_files"] or backup.get("skipped_files") or copy_warning:
            warning_detail = (
                f"O backup foi criado, mas {len(backup['missing_files'])} arquivo(s) esperado(s) não existiam na pasta de dados."
                if backup["missing_files"]
                else "O backup foi criado, mas alguns arquivos temporários ou inseguros foram ignorados."
                if backup.get("skipped_files")
                else f"O backup local foi criado, mas a cópia para Dropbox não foi concluída: {copy_warning}"
            )
            deps.flash_action_warning(
                "Backup gerado: backup local gerado com aviso",
                warning_detail,
                next_step="O arquivo local foi preservado em backups/. Revise a pasta Dropbox no painel antes de depender da cópia externa.",
                target_href="#admin-backup-panel",
                target_tab="access-tab",
                action="Ver backups",
            )
        else:
            copy_detail = f" Cópia Dropbox salva em {copy_info['path']}." if copy_info.get("path") else ""
            deps.flash_action_success(
                "Backup gerado com sucesso",
                f"Backup {backup['filename']} salvo na pasta de backups.{copy_detail}",
                next_step="Baixe o último backup ou mantenha o arquivo guardado para restauração manual.",
                target_href="#admin-backup-panel",
                target_tab="access-tab",
                action="Ver backups",
            )
        return redirect(url_for("index", _anchor="admin-backup-panel"))

    @app.route("/backup/dropbox/test", methods=["POST"])
    @deps.require_permission("settings.manage")
    def test_dropbox_backup_dir():
        result = deps.test_backup_copy_dir()
        if result.get("status") == "sucesso":
            deps.flash_action_success(
                "Pasta Dropbox testada com sucesso",
                result.get("status_detail") or "O sistema conseguiu acessar a pasta configurada para cópias de backup.",
                next_step="Gere um backup para copiar o arquivo .zip para essa pasta.",
                target_href="#admin-backup-panel",
                target_tab="access-tab",
                action="Ver backups",
            )
        else:
            deps.flash_action_warning(
                result.get("status_label") or "Aviso: Dropbox não configurado",
                result.get("warning") or result.get("status_detail") or "O backup local continuará funcionando, mas a cópia para Dropbox não será feita.",
                next_step="Configure DROPBOX_BACKUP_DIR com uma pasta Dropbox existente e tente novamente.",
                target_href="#admin-backup-panel",
                target_tab="access-tab",
                action="Ver backups",
            )
        return redirect(url_for("index", _anchor="admin-backup-panel"))

    @app.route("/backup/schedule", methods=["POST"])
    @deps.require_permission("settings.manage")
    def update_backup_schedule():
        try:
            result = deps.update_backup_schedule(request.form)
            deps.flash_action_success(
                "Agendamento de backup atualizado",
                result["message"],
                next_step="O sistema usará esse horário para gerar o próximo backup automático.",
                target_href="#admin-backup-panel",
                target_tab="access-tab",
                action="Ver backups",
            )
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "backup")
        return redirect(url_for("index", _anchor="admin-backup-panel"))

    @app.route("/backup/latest.zip", methods=["GET"])
    @deps.require_permission("settings.manage")
    def download_latest_system_backup():
        latest = next(iter(deps.list_backup_files()), None)
        if not latest:
            deps.flash_action_warning(
                "Aviso: nenhum backup disponível",
                "Ainda não existe backup salvo para download. O sistema não tem um arquivo compactado pronto para baixar.",
                next_step="Clique em Gerar backup agora e, depois que concluir, tente baixar novamente.",
                target_href="#admin-backup-panel",
                target_tab="access-tab",
                action="Gerar backup",
            )
            return redirect(url_for("index", _anchor="admin-backup-panel"))
        deps.record_audit("download", "backup", latest.name, "Último backup baixado.")
        return send_file(
            latest,
            mimetype="application/zip",
            as_attachment=True,
            download_name=latest.name,
        )

    @app.route("/backup/latest/restore", methods=["POST"])
    @deps.require_permission("settings.manage")
    def restore_latest_system_backup():
        latest = next(iter(deps.list_backup_files()), None)
        if not latest:
            deps.flash_action_warning(
                "Aviso: nenhum backup para restaurar",
                "Ainda não existe backup salvo. O sistema não alterou nenhum arquivo de dados.",
                next_step="Gere um backup ou copie manualmente um arquivo válido para a pasta backups/.",
                target_href="#admin-backup-panel",
                target_tab="access-tab",
                action="Ver backups",
            )
            return redirect(url_for("index", _anchor="admin-backup-panel"))
        try:
            safety_backup = deps.create_data_backup(trigger="pre_restore", audit_action=None)
            result = deps.restore_data_backup(latest)
            deps.record_audit(
                "restore",
                "backup",
                latest.name,
                f"Backup {latest.name} restaurado. Backup preventivo criado em {safety_backup['filename']}.",
                before={"safety_backup": safety_backup["filename"]},
                after=result,
            )
            deps.flash_action_success(
                "Backup restaurado com sucesso",
                f"Os arquivos de dados do backup {latest.name} foram restaurados.",
                next_step=f"Um backup preventivo foi criado antes da restauração: {safety_backup['filename']}. Revise a Central do Dia e a auditoria.",
                target_href="#admin-backup-panel",
                target_tab="access-tab",
                action="Ver backups",
            )
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "backup")
        return redirect(url_for("index", _anchor="admin-backup-panel"))

    @app.route("/backup/latest/test-restore", methods=["POST"])
    @deps.require_permission("settings.manage")
    def test_restore_latest_system_backup():
        latest = next(iter(deps.list_backup_files()), None)
        if not latest:
            deps.flash_action_warning(
                "Aviso: nenhum backup para testar",
                "Ainda não existe backup salvo para validar restauração.",
                next_step="Gere um backup e depois rode o teste de restauração.",
                target_href="#admin-backup-panel",
                target_tab="access-tab",
                action="Ver backups",
            )
            return redirect(url_for("index", _anchor="admin-backup-panel"))
        try:
            result = deps.test_restore_backup(latest)
            deps.record_audit(
                "validate",
                "backup",
                latest.name,
                "Teste de restauração em pasta temporária concluído sem alterar dados reais.",
                after={key: value for key, value in result.items() if key != "temp_dir"},
            )
            deps.flash_action_success(
                "Teste de restauração concluído",
                f"Backup {latest.name} validado em pasta temporária. {result['restorable_file_count']} arquivo(s) seriam restaurados.",
                next_step="Os dados reais não foram alterados. Use restauração real apenas com o sistema parado e backup preventivo.",
                target_href="#admin-backup-panel",
                target_tab="access-tab",
                action="Ver backups",
            )
        except Exception as exc:  # noqa: BLE001
            deps.flash_action_error(exc, "backup")
        return redirect(url_for("index", _anchor="admin-backup-panel"))
