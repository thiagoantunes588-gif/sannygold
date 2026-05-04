from __future__ import annotations

from datetime import datetime


DEFAULT_SECRET_KEY = "rotaflow-local-dev"
MIN_PASSWORD_LENGTH = 10


def password_policy_issues(password: str, user_identifiers: list[str] | None = None) -> list[str]:
    issues: list[str] = []
    value = password or ""
    identifiers = [item.strip().lower() for item in (user_identifiers or []) if item and item.strip()]

    if len(value) < MIN_PASSWORD_LENGTH:
        issues.append(f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
    if not any(char.islower() for char in value):
        issues.append("A senha precisa incluir ao menos uma letra minúscula.")
    if not any(char.isupper() for char in value):
        issues.append("A senha precisa incluir ao menos uma letra maiúscula.")
    if not any(char.isdigit() for char in value):
        issues.append("A senha precisa incluir ao menos um número.")
    if any(char.isspace() for char in value):
        issues.append("A senha não pode conter espaços.")

    normalized = value.lower()
    for identifier in identifiers:
        if len(identifier) >= 4 and identifier in normalized:
            issues.append("A senha não pode repetir partes óbvias do nome ou do email do usuário.")
            break

    return issues


def password_change_required(user: dict | None) -> bool:
    if not user:
        return False
    return bool(user.get("must_change_password"))


def build_security_posture(
    *,
    secret_key: str,
    users: list[dict],
    current_user: dict,
    last_backup_at: str = "",
    session_lifetime_hours: int = 12,
) -> dict:
    active_users = [user for user in users if str(user.get("status") or "") == "ativo"]
    admins = [user for user in active_users if str(user.get("role") or "") == "admin"]
    password_rotation_pending = [user for user in active_users if password_change_required(user)]
    items: list[dict] = []

    if secret_key == DEFAULT_SECRET_KEY:
        items.append(
            {
                "level": "danger",
                "title": "Secret key padrão em uso",
                "detail": "Defina uma chave forte no ambiente antes de expor o sistema fora do uso local.",
            }
        )
    else:
        items.append(
            {
                "level": "ready",
                "title": "Secret key customizada",
                "detail": "A aplicação já usa uma chave exclusiva para sessão e cookies.",
            }
        )

    if password_rotation_pending:
        items.append(
            {
                "level": "warning",
                "title": "Trocas de senha pendentes",
                "detail": f"{len(password_rotation_pending)} usuário(s) ainda precisam trocar a senha inicial.",
            }
        )
    else:
        items.append(
            {
                "level": "ready",
                "title": "Senhas iniciais tratadas",
                "detail": "Nenhum usuário ativo está marcado com troca de senha pendente.",
            }
        )

    if not admins:
        items.append(
            {
                "level": "danger",
                "title": "Sem administrador ativo",
                "detail": "Ative ao menos um usuário admin para governança e suporte da operação.",
            }
        )
    else:
        items.append(
            {
                "level": "ready",
                "title": "Governança mínima ativa",
                "detail": f"{len(admins)} administrador(es) ativo(s) com acesso total cadastrado(s).",
            }
        )

    if session_lifetime_hours > 8:
        items.append(
            {
                "level": "warning",
                "title": "Sessão prolongada",
                "detail": f"A sessão atual expira em {session_lifetime_hours}h; avalie reduzir para ambientes externos.",
            }
        )

    if not last_backup_at:
        items.append(
            {
                "level": "warning",
                "title": "Backup ainda não registrado",
                "detail": "Faça o primeiro backup completo antes do uso contínuo em equipe.",
            }
        )
    else:
        try:
            last_backup_dt = datetime.fromisoformat(last_backup_at)
            days_since_backup = max((datetime.now() - last_backup_dt).days, 0)
        except ValueError:
            days_since_backup = 999
        if days_since_backup > 7:
            items.append(
                {
                    "level": "warning",
                    "title": "Backup desatualizado",
                    "detail": f"O último backup registrado tem {days_since_backup} dia(s).",
                }
            )
        else:
            items.append(
                {
                    "level": "ready",
                    "title": "Backup recente",
                    "detail": "Existe ao menos um backup recente registrado no sistema.",
                }
            )

    return {
        "current_user_requires_password_change": password_change_required(current_user),
        "items": items,
        "active_users": len(active_users),
        "admins": len(admins),
        "password_rotation_pending": len(password_rotation_pending),
        "critical_count": sum(1 for item in items if item["level"] == "danger"),
        "attention_count": sum(1 for item in items if item["level"] == "warning"),
    }
