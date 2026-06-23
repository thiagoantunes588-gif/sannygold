from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import subprocess
import sys
import webbrowser
from pathlib import Path


APP_NAME = "SannyGold Sistema"
DEFAULT_PORT = "5007"
DEFAULT_HOST = "0.0.0.0"
DROPBOX_SYSTEM_FOLDER = "Sistema SannyGold"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def log(root: Path, message: str) -> None:
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "portable.log").open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


def readable_command(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    log(cwd, f"Executando: {readable_command(command)}")
    result = subprocess.run(command, cwd=str(cwd), env=env, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"Comando falhou com codigo {result.returncode}: {readable_command(command)}")
    return result


def resolve_for_check(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def is_inside_or_same(child: Path, parent: Path) -> bool:
    child_resolved = resolve_for_check(child)
    parent_resolved = resolve_for_check(parent)
    return child_resolved == parent_resolved or parent_resolved in child_resolved.parents


def default_dropbox_root() -> Path:
    return Path.home() / "Dropbox"


def default_dropbox_backup_dir() -> Path:
    return default_dropbox_root() / DROPBOX_SYSTEM_FOLDER / "Backups"


def venv_python(root: Path) -> Path:
    if os.name == "nt":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def ensure_runtime_dirs(root: Path) -> None:
    for folder in ("data", "uploads", "preview", "backups", "logs", "tmp"):
        (root / folder).mkdir(parents=True, exist_ok=True)


def read_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_file.exists():
        return values
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def write_env_file(env_file: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def env_defaults(root: Path) -> dict[str, str]:
    return {
        "SANNYGOLD_ENV": "local",
        "SANNYGOLD_SECRET_KEY": secrets.token_urlsafe(48),
        "SANNYGOLD_ADMIN_EMAIL": "contato@sannygold.com",
        "SANNYGOLD_ADMIN_PASSWORD": "troque-esta-senha",
        "SANNYGOLD_ADMIN_NAME": "Administrador SannyGold",
        "ROTAFLOW_STORAGE_DIR": str(root),
        "SANNYGOLD_SQLITE_PATH": str(root / "data" / "sannygold.db"),
        "SANNYGOLD_STORAGE_BACKEND": "sqlite",
        "SANNYGOLD_SQLITE_MIRROR_JSON": "1",
        "DROPBOX_BACKUP_DIR": str(default_dropbox_backup_dir()),
        "SANNYGOLD_BACKUP_RETENTION_LIMIT": "30",
        "SANNYGOLD_DROPBOX_BACKUP_RETENTION_LIMIT": "30",
        "PORT": DEFAULT_PORT,
        "FLASK_HOST": DEFAULT_HOST,
        "FLASK_DEBUG": "0",
        "SANNYGOLD_SESSION_COOKIE_SECURE": "0",
        "SANNYGOLD_CSRF_DISABLED": "0",
    }


def ensure_env_file(root: Path) -> dict[str, str]:
    env_file = root / ".env.local"
    values = read_env_file(env_file)
    defaults = env_defaults(root)
    changed = not env_file.exists()
    for key, value in defaults.items():
        if not values.get(key):
            values[key] = value
            changed = True
    if changed:
        write_env_file(env_file, values)
        log(root, ".env.local criado ou atualizado com valores portateis seguros.")
    return values


def assert_not_inside_dropbox(label: str, path: Path, dropbox_root: Path) -> None:
    if is_inside_or_same(path, dropbox_root):
        raise RuntimeError(
            f"Configuracao insegura: {label} nao pode ficar dentro do Dropbox. "
            "Extraia o sistema para uma pasta local fora do Dropbox."
        )


def assert_safe_paths(root: Path, env_values: dict[str, str]) -> None:
    dropbox_root = default_dropbox_root()
    assert_not_inside_dropbox("a pasta inteira do sistema", root, dropbox_root)
    assert_not_inside_dropbox("data/", root / "data", dropbox_root)
    assert_not_inside_dropbox("uploads/", root / "uploads", dropbox_root)
    assert_not_inside_dropbox("SANNYGOLD_SQLITE_PATH", Path(env_values["SANNYGOLD_SQLITE_PATH"]), dropbox_root)


def ensure_dropbox(root: Path, env_values: dict[str, str]) -> None:
    backup_dir = Path(env_values["DROPBOX_BACKUP_DIR"]).expanduser()
    if default_dropbox_root().exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        print(f"Dropbox configurado para backups: {backup_dir}")
        log(root, f"Dropbox configurado para backups: {backup_dir}")
    else:
        message = "Dropbox nao encontrado. O sistema funcionara localmente, mas o backup externo nao esta ativo."
        print(message)
        log(root, message)


def ensure_venv(root: Path) -> Path:
    python_path = venv_python(root)
    if not python_path.exists():
        print("Criando ambiente virtual .venv...")
        run([sys.executable, "-m", "venv", str(root / ".venv")], cwd=root)
    if not python_path.exists():
        raise RuntimeError(f"Python da .venv nao encontrado em: {python_path}")
    return python_path


def requirements_hash(requirements: Path) -> str:
    digest = hashlib.sha256()
    digest.update(requirements.read_bytes())
    return digest.hexdigest()


def ensure_requirements(root: Path, python_path: Path) -> None:
    requirements = root / "requirements.txt"
    if not requirements.exists():
        raise RuntimeError("requirements.txt nao encontrado no pacote portatil.")
    stamp_file = root / ".venv" / ".requirements.sha256"
    expected = requirements_hash(requirements)
    current = stamp_file.read_text(encoding="ascii").strip() if stamp_file.exists() else ""
    if current == expected:
        return
    print("Instalando dependencias do Sistema SannyGold...")
    run([str(python_path), "-m", "pip", "install", "-r", str(requirements)], cwd=root)
    stamp_file.write_text(expected, encoding="ascii")


def load_process_env(env_values: dict[str, str]) -> dict[str, str]:
    process_env = os.environ.copy()
    process_env.update(env_values)
    return process_env


def migrate_json_to_sqlite(root: Path, python_path: Path, process_env: dict[str, str]) -> None:
    migration_script = root / "scripts" / "migrate_json_to_sqlite.py"
    if not migration_script.exists():
        return
    result = run(
        [
            str(python_path),
            str(migration_script),
            "--data-dir",
            str(root / "data"),
            "--db",
            process_env["SANNYGOLD_SQLITE_PATH"],
        ],
        cwd=root,
        env=process_env,
        check=False,
    )
    if result.returncode != 0:
        print("Aviso: migracao JSON para SQLite nao foi concluida. O sistema continuara iniciando.")
        log(root, "Migracao JSON para SQLite retornou codigo diferente de zero.")


def setup(root: Path) -> tuple[dict[str, str], Path]:
    ensure_runtime_dirs(root)
    env_values = ensure_env_file(root)
    assert_safe_paths(root, env_values)
    ensure_dropbox(root, env_values)
    python_path = ensure_venv(root)
    ensure_requirements(root, python_path)
    return env_values, python_path


def diagnose_dropbox(root: Path) -> int:
    ensure_runtime_dirs(root)
    env_values = ensure_env_file(root)
    try:
        assert_safe_paths(root, env_values)
    except RuntimeError as exc:
        print(str(exc))
        log(root, str(exc))
        return 2

    backup_dir = Path(env_values["DROPBOX_BACKUP_DIR"]).expanduser()
    print(f"Pasta do sistema: {root}")
    print(f"Banco ativo: {env_values['SANNYGOLD_SQLITE_PATH']}")
    print(f"Pasta Dropbox configurada: {backup_dir}")
    if not default_dropbox_root().exists():
        print("Dropbox nao encontrado. O sistema funcionara localmente, mas o backup externo nao esta ativo.")
        return 0
    backup_dir.mkdir(parents=True, exist_ok=True)
    test_file = backup_dir / ".sannygold-teste-escrita.tmp"
    try:
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
    except OSError as exc:
        print(f"Sem permissao para gravar no Dropbox: {exc}")
        return 3
    backups = sorted(backup_dir.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
    if backups:
        latest = backups[0]
        print(f"Dropbox OK. Ultimo backup: {latest.name} ({latest.stat().st_size} bytes)")
    else:
        print("Dropbox encontrado, sem backup ainda.")
    return 0


def start_server(root: Path) -> int:
    env_values, python_path = setup(root)
    process_env = load_process_env(env_values)
    migrate_json_to_sqlite(root, python_path, process_env)

    port = process_env.get("PORT", DEFAULT_PORT)
    host = process_env.get("FLASK_HOST", DEFAULT_HOST)
    local_url = f"http://127.0.0.1:{port}"
    print(f"URL local: {local_url}")
    print(f"Pasta Dropbox para backups: {process_env['DROPBOX_BACKUP_DIR']}")
    print("Pressione Ctrl+C para encerrar.")
    try:
        webbrowser.open(local_url, new=2)
    except Exception as exc:  # pragma: no cover - depends on local Windows shell
        log(root, f"Nao foi possivel abrir navegador automaticamente: {exc}")

    command = [str(python_path), "-m", "waitress", "--host", host, "--port", port, "app.main:app"]
    return run(command, cwd=root, env=process_env, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Inicializador portatil Windows do Sistema SannyGold.")
    parser.add_argument("--setup-only", action="store_true", help="Prepara .venv, dependencias, pastas e .env.local sem iniciar servidor.")
    parser.add_argument("--diagnose-dropbox", action="store_true", help="Mostra diagnostico da pasta Dropbox configurada.")
    parser.add_argument("--start", action="store_true", help="Prepara e inicia o servidor local.")
    args = parser.parse_args()

    root = project_root()
    try:
        if args.diagnose_dropbox:
            return diagnose_dropbox(root)
        if args.setup_only:
            setup(root)
            print("Dependencias e configuracao preparadas.")
            return 0
        return start_server(root)
    except Exception as exc:
        message = f"Falha no pacote portatil SannyGold: {exc}"
        print(message)
        log(root, message)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
