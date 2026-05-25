from __future__ import annotations

from flask import redirect, send_file, url_for


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
        if backup["missing_files"]:
            deps.flash_action_warning(
                "Aviso: backup gerado com arquivos ausentes",
                f"O backup foi criado, mas {len(backup['missing_files'])} arquivo(s) esperado(s) não existiam na pasta de dados.",
                next_step="Confira se esses arquivos realmente não são usados. Os dados existentes foram preservados no backup.",
                target_href="#admin-backup-panel",
                target_tab="access-tab",
                action="Ver backups",
            )
        else:
            deps.flash_action_success(
                "Backup gerado com sucesso",
                f"Backup {backup['filename']} salvo na pasta de backups.",
                next_step="Baixe o último backup ou mantenha o arquivo guardado para restauração manual.",
                target_href="#admin-backup-panel",
                target_tab="access-tab",
                action="Ver backups",
            )
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
