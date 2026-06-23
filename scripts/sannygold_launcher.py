#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import os
import platform
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path


APP_NAME = "SannyGold Sistema"
DROPBOX_SYSTEM_FOLDER = "Sistema SannyGold"


def resolve_base_dir() -> Path:
    configured = os.environ.get("SANNYGOLD_PROJECT_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


BASE_DIR = resolve_base_dir()


def safe_port(value: str | int | None, default: int = 5007) -> int:
    try:
        port = int(str(value or default).strip())
    except (TypeError, ValueError):
        return default
    return port if 1 <= port <= 65535 else default


DEFAULT_PORT = safe_port(os.environ.get("PORT"), 5007)
DEFAULT_HOST = os.environ.get("FLASK_HOST", "0.0.0.0") or "0.0.0.0"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "launcher.log"
LOCK_FILE = LOG_DIR / "launcher.lock"
ENV_FILE = BASE_DIR / ".env.local"
REQUIREMENTS_FILE = BASE_DIR / "requirements.txt"
VENV_DIR = BASE_DIR / ".venv"
DEFAULT_DROPBOX_ROOT = Path.home() / "Dropbox"
DEFAULT_DROPBOX_BACKUP_DIR = DEFAULT_DROPBOX_ROOT / DROPBOX_SYSTEM_FOLDER / "Backups"
DEFAULT_DROPBOX_INSTALLERS_DIR = DEFAULT_DROPBOX_ROOT / DROPBOX_SYSTEM_FOLDER / "Instaladores"
DROPBOX_NOT_FOUND_MESSAGE = "Dropbox não encontrado. O sistema funcionará localmente, mas o backup externo não está ativo."


def ensure_runtime_dirs() -> None:
    for folder in ("data", "uploads", "preview", "tmp", "logs", "backups"):
        (BASE_DIR / folder).mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    ensure_runtime_dirs()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def parse_env_line(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    try:
        parsed = shlex.split(value)
    except ValueError:
        return value.strip("\"'")
    return parsed[0] if parsed else ""


def load_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = parse_env_line(value)
    return values


def resolve_port(env_values: dict[str, str] | None = None, default: int = DEFAULT_PORT) -> int:
    env_values = env_values if env_values is not None else load_env_file()
    raw_value = os.environ.get("PORT") or env_values.get("PORT") or str(default)
    return safe_port(raw_value, default)


def resolve_host(env_values: dict[str, str] | None = None, default: str = DEFAULT_HOST) -> str:
    env_values = env_values if env_values is not None else load_env_file()
    return (os.environ.get("FLASK_HOST") or env_values.get("FLASK_HOST") or default or "0.0.0.0").strip()


def local_url(port: int = DEFAULT_PORT) -> str:
    return f"http://127.0.0.1:{port}/"


def write_env_file_if_missing(
    path: Path = ENV_FILE,
    *,
    base_dir: Path = BASE_DIR,
    dropbox_backup_dir: Path = DEFAULT_DROPBOX_BACKUP_DIR,
) -> None:
    if path.exists():
        return
    ensure_runtime_dirs()
    if dropbox_root_from_backup_dir(dropbox_backup_dir).exists():
        dropbox_backup_dir.mkdir(parents=True, exist_ok=True)
    secret_key = secrets.token_urlsafe(48)
    values = {
        "SANNYGOLD_ENV": "local",
        "SANNYGOLD_SECRET_KEY": secret_key,
        "SANNYGOLD_ADMIN_EMAIL": "contato@sannygold.com",
        "SANNYGOLD_ADMIN_PASSWORD": "troque-esta-senha",
        "SANNYGOLD_ADMIN_NAME": "Administrador SannyGold",
        "ROTAFLOW_STORAGE_DIR": str(base_dir),
        "SANNYGOLD_SQLITE_PATH": str(base_dir / "data" / "sannygold.db"),
        "SANNYGOLD_STORAGE_BACKEND": "sqlite",
        "SANNYGOLD_SQLITE_MIRROR_JSON": "1",
        "DROPBOX_BACKUP_DIR": str(dropbox_backup_dir),
        "SANNYGOLD_BACKUP_RETENTION_LIMIT": "30",
        "SANNYGOLD_DROPBOX_BACKUP_RETENTION_LIMIT": "30",
        "PORT": str(DEFAULT_PORT),
        "FLASK_HOST": DEFAULT_HOST,
        "FLASK_DEBUG": "0",
        "SANNYGOLD_SESSION_COOKIE_SECURE": "0",
        "SANNYGOLD_CSRF_DISABLED": "0",
    }
    path.write_text(
        "\n".join(f"{key}={shlex.quote(value)}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        pass


def default_env_values(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, base_dir: Path = BASE_DIR) -> dict[str, str]:
    return {
        "SANNYGOLD_ENV": "local",
        "ROTAFLOW_STORAGE_DIR": str(base_dir),
        "SANNYGOLD_SQLITE_PATH": str(base_dir / "data" / "sannygold.db"),
        "SANNYGOLD_STORAGE_BACKEND": "sqlite",
        "SANNYGOLD_SQLITE_MIRROR_JSON": "1",
        "DROPBOX_BACKUP_DIR": str(DEFAULT_DROPBOX_BACKUP_DIR),
        "SANNYGOLD_BACKUP_RETENTION_LIMIT": "30",
        "SANNYGOLD_DROPBOX_BACKUP_RETENTION_LIMIT": "30",
        "FLASK_DEBUG": "0",
        "FLASK_HOST": host,
        "PORT": str(port),
        "PYTHONUNBUFFERED": "1",
    }


def merged_env(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> dict[str, str]:
    write_env_file_if_missing()
    loaded = load_env_file()
    env = os.environ.copy()
    for key, value in loaded.items():
        env.setdefault(key, value)
    env.setdefault("SANNYGOLD_SECRET_KEY", secrets.token_urlsafe(48))
    for key, value in default_env_values(host, port).items():
        if key in {"FLASK_DEBUG", "FLASK_HOST", "PORT", "PYTHONUNBUFFERED"}:
            env[key] = value
        else:
            env.setdefault(key, value)
    return env


def is_windows() -> bool:
    return platform.system().lower().startswith("win")


def venv_python(venv_dir: Path = VENV_DIR) -> Path:
    return venv_dir / "Scripts" / "python.exe" if is_windows() else venv_dir / "bin" / "python"


def system_python_command() -> list[str]:
    if is_windows():
        py_launcher = shutil.which("py")
        if py_launcher:
            return [py_launcher, "-3"]
        python_exe = shutil.which("python")
        if python_exe:
            return [python_exe]
    return [sys.executable]


def popen_kwargs() -> dict:
    if is_windows():
        return {}
    return {"start_new_session": True}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_python_runtime(status_callback=None) -> Path:
    ensure_runtime_dirs()
    python_path = venv_python()
    if not python_path.exists():
        if status_callback:
            status_callback("Preparando ambiente Python...")
        log("Creating virtual environment")
        subprocess.run([*system_python_command(), "-m", "venv", str(VENV_DIR)], cwd=BASE_DIR, check=True)
    requirements_hash = file_sha256(REQUIREMENTS_FILE)
    stamp_file = VENV_DIR / ".requirements.sha256"
    installed_hash = stamp_file.read_text(encoding="utf-8").strip() if stamp_file.exists() else ""
    if installed_hash != requirements_hash:
        if status_callback:
            status_callback("Instalando dependencias locais...")
        log("Installing requirements")
        subprocess.run([str(python_path), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)], cwd=BASE_DIR, check=True)
        stamp_file.write_text(requirements_hash, encoding="utf-8")
    return python_path


def detect_local_ip() -> str:
    configured = os.environ.get("SANNYGOLD_LAN_IP", "").strip()
    if configured:
        return configured
    try:
        for candidate in socket.gethostbyname_ex(socket.gethostname())[2]:
            if candidate and not candidate.startswith("127."):
                return candidate
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("10.255.255.255", 1))
            detected = probe.getsockname()[0]
            if detected and not detected.startswith("127."):
                return detected
    except OSError:
        pass
    return "127.0.0.1"


def mobile_url(port: int = DEFAULT_PORT) -> str:
    return f"http://{detect_local_ip()}:{port}/"


def read_launcher_lock(path: Path = LOCK_FILE) -> dict[str, str]:
    if not path.exists():
        return {}
    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def acquire_launcher_lock(path: Path = LOCK_FILE, *, port: int = DEFAULT_PORT) -> bool:
    ensure_runtime_dirs()
    existing = read_launcher_lock(path)
    try:
        existing_pid = int(existing.get("pid", "0") or 0)
    except ValueError:
        existing_pid = 0
    if existing_pid and is_process_running(existing_pid):
        return False
    path.write_text(
        "\n".join(
            [
                f"pid={os.getpid()}",
                f"port={port}",
                f"started_at={datetime.now().isoformat(timespec='seconds')}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return True


def release_launcher_lock(path: Path = LOCK_FILE) -> None:
    try:
        existing = read_launcher_lock(path)
        if str(os.getpid()) == existing.get("pid"):
            path.unlink(missing_ok=True)
    except OSError as exc:
        log(f"Could not release launcher lock: {exc}")


def is_port_open(host: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def health_url(port: int = DEFAULT_PORT) -> str:
    return f"http://127.0.0.1:{port}/health"


def is_system_healthy(port: int = DEFAULT_PORT, timeout: float = 0.8) -> bool:
    try:
        with urllib.request.urlopen(health_url(port), timeout=timeout) as response:
            return 200 <= response.status < 300
    except (OSError, urllib.error.URLError):
        return False


def newest_zip(folder: Path) -> Path | None:
    if not folder.exists():
        return None
    files = [item for item in folder.glob("*.zip") if item.is_file()]
    if not files:
        return None
    return max(files, key=lambda item: item.stat().st_mtime)


def human_size(path: Path | None) -> str:
    if not path or not path.exists():
        return ""
    size = float(path.stat().st_size)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


def path_is_inside(path: Path, parent: Path) -> bool:
    try:
        path_resolved = path.expanduser().resolve()
        parent_resolved = parent.expanduser().resolve()
        return path_resolved == parent_resolved or parent_resolved in path_resolved.parents
    except OSError:
        return False


def dropbox_root_from_backup_dir(path: Path | None) -> Path:
    if path:
        expanded = path.expanduser()
        for candidate in [expanded, *expanded.parents]:
            if candidate.name.lower() == "dropbox":
                return candidate
    return Path.home() / "Dropbox"


def unsafe_dropbox_paths(env: dict[str, str] | None = None, *, base_dir: Path = BASE_DIR, dropbox_dir: Path | None = None) -> list[str]:
    env = env or os.environ
    external_dir = dropbox_dir or Path(env.get("DROPBOX_BACKUP_DIR", str(DEFAULT_DROPBOX_BACKUP_DIR))).expanduser()
    dropbox_root = dropbox_root_from_backup_dir(external_dir)
    storage_root = Path(env.get("ROTAFLOW_STORAGE_DIR", str(base_dir))).expanduser()
    sqlite_path = Path(env.get("SANNYGOLD_SQLITE_PATH", str(storage_root / "data" / "sannygold.db"))).expanduser()
    checks = (
        ("pasta inteira do sistema", base_dir),
        ("ROTAFLOW_STORAGE_DIR", storage_root),
        ("data/", storage_root / "data"),
        ("uploads/", storage_root / "uploads"),
        ("sannygold.db", sqlite_path),
    )
    return [label for label, path in checks if path_is_inside(path, dropbox_root)]


def unsafe_dropbox_message(unsafe_paths: list[str]) -> str:
    return "Risco: banco ativo parece estar dentro do Dropbox" + (f" ({', '.join(unsafe_paths)})" if unsafe_paths else "")


def validate_safe_runtime_paths(env: dict[str, str] | None = None) -> None:
    unsafe_paths = unsafe_dropbox_paths(env)
    if unsafe_paths:
        raise RuntimeError(unsafe_dropbox_message(unsafe_paths))


def backup_summary(dropbox_dir: Path | None = None, local_dir: Path | None = None) -> dict[str, str]:
    local = newest_zip(local_dir or BASE_DIR / "backups")
    external_dir = dropbox_dir or Path(os.environ.get("DROPBOX_BACKUP_DIR", str(DEFAULT_DROPBOX_BACKUP_DIR))).expanduser()
    external = newest_zip(external_dir)
    unsafe_paths = unsafe_dropbox_paths(os.environ, dropbox_dir=external_dir)
    if local:
        local_label = f"{local.name} ({human_size(local)})"
    else:
        local_label = "Nenhum backup local encontrado"
    if unsafe_paths:
        dropbox_label = unsafe_dropbox_message(unsafe_paths)
    elif external_dir.exists() and external:
        dropbox_label = f"Dropbox OK: {external.name} ({human_size(external)})"
    elif external_dir.exists():
        dropbox_label = "Dropbox encontrado, sem backup ainda"
    else:
        dropbox_label = f"{DROPBOX_NOT_FOUND_MESSAGE} Pasta esperada: {external_dir}"
    return {
        "local": local_label,
        "dropbox": dropbox_label,
        "dropbox_dir": str(external_dir),
    }


def server_command(python_path: Path, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> list[str]:
    return [str(python_path), "-m", "waitress", "--host", host, "--port", str(port), "app.main:app"]


def run_startup_tasks(python_path: Path, env: dict[str, str]) -> None:
    commands = [
        [str(python_path), str(BASE_DIR / "scripts" / "create_local_backup.py"), "--trigger", "launcher_start", "--if-older-hours", "24"],
        [
            str(python_path),
            str(BASE_DIR / "scripts" / "migrate_json_to_sqlite.py"),
            "--data-dir",
            str(BASE_DIR / "data"),
            "--db",
            env.get("SANNYGOLD_SQLITE_PATH", str(BASE_DIR / "data" / "sannygold.db")),
        ],
    ]
    for command in commands:
        try:
            with LOG_FILE.open("a", encoding="utf-8") as output:
                subprocess.run(command, cwd=BASE_DIR, env=env, stdout=output, stderr=output, check=False)
        except Exception as exc:  # noqa: BLE001
            log(f"Startup task failed: {command!r} :: {exc}")


class SannyGoldLauncher:
    def __init__(self, *, diagnostic_only: bool = False) -> None:
        import tkinter as tk
        from tkinter import messagebox

        self.tk = tk
        self.messagebox = messagebox
        self.diagnostic_only = diagnostic_only
        self.process: subprocess.Popen | None = None
        self.opened_browser = False
        self.first_run = not ENV_FILE.exists()
        env_values = load_env_file()
        self.port = resolve_port(env_values)
        self.host = resolve_host(env_values)
        self.env = merged_env(self.host, self.port)
        self.lock_acquired = acquire_launcher_lock(port=self.port)
        self.external_launcher_detected = not self.lock_acquired

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("780x560")
        self.root.minsize(640, 420)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.config_window = None

        self.status_var = tk.StringVar(value="Inicializando launcher...")
        self.local_url_var = tk.StringVar(value=local_url(self.port))
        self.mobile_url_var = tk.StringVar(value=mobile_url(self.port))
        self.backup_var = tk.StringVar(value="Ultimo backup: verificando...")
        self.dropbox_var = tk.StringVar(value="Dropbox: verificando...")
        self.log_var = tk.StringVar(value=f"Log: {LOG_FILE}")

        self.build_ui()
        self.refresh_status()
        if self.lock_acquired and not self.diagnostic_only:
            threading.Thread(target=self.start_server, daemon=True).start()
        else:
            self.set_status("Modo diagnóstico aberto." if self.diagnostic_only else "Outro launcher SannyGold ja esta aberto ou iniciando o servidor.")
            if is_system_healthy(self.port):
                self.open_system()
        if self.first_run or self.diagnostic_only:
            self.root.after(700, self.open_initial_config)
        self.root.after(3000, self.periodic_refresh)

    def build_ui(self) -> None:
        tk = self.tk
        frame = tk.Frame(self.root, padx=22, pady=18)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=APP_NAME, font=("Helvetica", 20, "bold")).pack(anchor="w")
        tk.Label(frame, textvariable=self.status_var, font=("Helvetica", 12), fg="#176b4d").pack(anchor="w", pady=(6, 14))

        fields = tk.Frame(frame)
        fields.pack(fill="x", pady=(0, 14))
        self.add_row(fields, "Sistema", self.local_url_var)
        self.add_row(fields, "Celular no Wi-Fi", self.mobile_url_var)
        self.add_row(fields, "Ultimo backup", self.backup_var)
        self.add_row(fields, "Dropbox", self.dropbox_var)

        buttons = tk.Frame(frame)
        buttons.pack(fill="x", pady=(6, 14))
        tk.Button(buttons, text="Abrir sistema", command=self.open_system, width=18, height=2).pack(side="left", padx=(0, 8))
        tk.Button(buttons, text="Gerar backup", command=self.generate_backup, width=18, height=2).pack(side="left", padx=(0, 8))
        tk.Button(buttons, text="Parar servidor", command=self.stop_server, width=18, height=2).pack(side="left", padx=(0, 8))
        tk.Button(buttons, text="Configuração inicial", command=self.open_initial_config, width=20, height=2).pack(side="left")

        info = (
            "Use o celular conectado ao mesmo Wi-Fi para abrir o endereco acima. "
            "O computador precisa continuar ligado enquanto a equipe usa o sistema."
        )
        tk.Label(frame, text=info, wraplength=640, justify="left", fg="#60706a").pack(anchor="w", pady=(8, 8))
        tk.Label(frame, textvariable=self.log_var, wraplength=640, justify="left", fg="#60706a").pack(anchor="w")

    def add_row(self, parent, label: str, variable) -> None:
        tk = self.tk
        row = tk.Frame(parent)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=f"{label}:", width=16, anchor="w", font=("Helvetica", 11, "bold")).pack(side="left")
        tk.Label(row, textvariable=variable, anchor="w", justify="left", wraplength=500).pack(side="left", fill="x", expand=True)

    def open_initial_config(self) -> None:
        if self.config_window and self.config_window.winfo_exists():
            self.config_window.lift()
            return

        tk = self.tk
        window = tk.Toplevel(self.root)
        self.config_window = window
        window.title("Configuração inicial")
        window.geometry("760x460")
        window.minsize(640, 400)

        content = tk.Frame(window, padx=20, pady=16)
        content.pack(fill="both", expand=True)
        tk.Label(content, text="Configuração inicial", font=("Helvetica", 18, "bold")).pack(anchor="w")
        tk.Label(
            content,
            text="Confira onde o sistema roda e onde os backups são salvos. O banco ativo fica no computador; Dropbox recebe apenas arquivos .zip.",
            wraplength=700,
            justify="left",
            fg="#60706a",
        ).pack(anchor="w", pady=(4, 12))

        rows = tk.Frame(content)
        rows.pack(fill="x", pady=(0, 12))
        self.add_config_row(rows, "Pasta do sistema", str(BASE_DIR))
        self.add_config_row(rows, "Pasta do banco", self.env.get("SANNYGOLD_SQLITE_PATH", str(BASE_DIR / "data" / "sannygold.db")))
        self.add_config_row(rows, "Backups locais", str(BASE_DIR / "backups"))
        self.add_config_row(rows, "Pasta Dropbox", self.env.get("DROPBOX_BACKUP_DIR", str(DEFAULT_DROPBOX_BACKUP_DIR)))

        unsafe_paths = unsafe_dropbox_paths(self.env)
        configured_dropbox_dir = Path(self.env.get("DROPBOX_BACKUP_DIR", str(DEFAULT_DROPBOX_BACKUP_DIR))).expanduser()
        if not dropbox_root_from_backup_dir(configured_dropbox_dir).exists():
            warning = DROPBOX_NOT_FOUND_MESSAGE
        elif unsafe_paths:
            warning = unsafe_dropbox_message(unsafe_paths)
        else:
            warning = "Configuração segura: dados ativos locais e Dropbox reservado para backups."
        tk.Label(content, text=warning, wraplength=700, justify="left", fg="#9a5b00").pack(anchor="w", pady=(0, 12))

        buttons = tk.Frame(content)
        buttons.pack(fill="x")
        tk.Button(buttons, text="Testar Dropbox", command=self.test_dropbox, width=18, height=2).pack(side="left", padx=(0, 8))
        tk.Button(buttons, text="Gerar backup agora", command=self.generate_backup, width=20, height=2).pack(side="left", padx=(0, 8))
        tk.Button(buttons, text="Fechar", command=window.destroy, width=12, height=2).pack(side="left")

    def add_config_row(self, parent, label: str, value: str) -> None:
        tk = self.tk
        row = tk.Frame(parent)
        row.pack(fill="x", pady=5)
        tk.Label(row, text=f"{label}:", width=18, anchor="w", font=("Helvetica", 11, "bold")).pack(side="left")
        tk.Label(row, text=value, anchor="w", justify="left", wraplength=520).pack(side="left", fill="x", expand=True)

    def test_dropbox(self) -> None:
        folder = Path(self.env.get("DROPBOX_BACKUP_DIR", str(DEFAULT_DROPBOX_BACKUP_DIR))).expanduser()
        if not dropbox_root_from_backup_dir(folder).exists():
            self.messagebox.showwarning("SannyGold", DROPBOX_NOT_FOUND_MESSAGE)
            self.refresh_status()
            return
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".sannygold-write-test.tmp"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            self.messagebox.showerror("SannyGold", f"Sem permissão para gravar no Dropbox.\n\n{exc}")
            self.refresh_status()
            return
        self.messagebox.showinfo("SannyGold", f"Dropbox OK\n\nPasta: {folder}")
        self.refresh_status()

    def set_status(self, text: str) -> None:
        log(text)
        self.root.after(0, self.status_var.set, text)

    def refresh_status(self) -> None:
        summary = backup_summary(Path(self.env.get("DROPBOX_BACKUP_DIR", str(DEFAULT_DROPBOX_BACKUP_DIR))).expanduser())
        self.backup_var.set(summary["local"])
        self.dropbox_var.set(summary["dropbox"])
        self.mobile_url_var.set(mobile_url(self.port))
        if is_system_healthy(self.port):
            self.status_var.set("Sistema rodando")
        elif is_port_open("127.0.0.1", self.port):
            self.status_var.set("Porta em uso, mas o sistema nao respondeu ao status")
        elif self.external_launcher_detected:
            self.status_var.set("Outro launcher SannyGold esta aberto ou iniciando o servidor")
        else:
            self.status_var.set("Servidor parado")

    def periodic_refresh(self) -> None:
        self.refresh_status()
        self.root.after(3000, self.periodic_refresh)

    def start_server(self) -> None:
        try:
            if is_system_healthy(self.port):
                self.set_status("Sistema ja estava rodando")
                self.open_system()
                return
            if is_port_open("127.0.0.1", self.port):
                self.set_status("A porta local ja esta em uso por outro processo")
                return

            validate_safe_runtime_paths(self.env)
            python_path = ensure_python_runtime(self.set_status)
            self.env = merged_env(self.host, self.port)
            validate_safe_runtime_paths(self.env)
            self.set_status("Preparando backup e banco local...")
            run_startup_tasks(python_path, self.env)

            command = server_command(python_path, self.host, self.port)
            self.set_status("Iniciando servidor local...")
            with LOG_FILE.open("a", encoding="utf-8") as output:
                self.process = subprocess.Popen(
                    command,
                    cwd=BASE_DIR,
                    env=self.env,
                    stdout=output,
                    stderr=output,
                    **popen_kwargs(),
                )

            for _ in range(45):
                if self.process.poll() is not None:
                    self.set_status("Servidor encerrou antes de ficar pronto. Veja o log.")
                    return
                if is_system_healthy(self.port):
                    self.set_status("Sistema rodando")
                    self.open_system()
                    return
                time.sleep(0.5)
            self.set_status("Servidor demorou para responder. Veja o log.")
        except Exception as exc:  # noqa: BLE001
            log(f"Launcher error: {exc}")
            self.set_status("Erro ao iniciar. Veja o log.")
            self.root.after(0, self.messagebox.showerror, "SannyGold", f"Nao foi possivel iniciar o sistema.\n\n{exc}")

    def open_system(self) -> None:
        webbrowser.open(local_url(self.port), new=2)
        self.opened_browser = True

    def generate_backup(self) -> None:
        threading.Thread(target=self._generate_backup, daemon=True).start()

    def _generate_backup(self) -> None:
        try:
            validate_safe_runtime_paths(self.env)
            python_path = ensure_python_runtime(self.set_status)
            self.env = merged_env(self.host, self.port)
            validate_safe_runtime_paths(self.env)
            self.set_status("Gerando backup...")
            command = [str(python_path), str(BASE_DIR / "scripts" / "create_local_backup.py"), "--trigger", "launcher_manual"]
            with LOG_FILE.open("a", encoding="utf-8") as output:
                result = subprocess.run(command, cwd=BASE_DIR, env=self.env, stdout=output, stderr=output, check=False)
            if result.returncode == 0:
                self.set_status("Backup gerado")
            else:
                self.set_status("Falha ao gerar backup. Veja o log.")
            self.root.after(0, self.refresh_status)
        except Exception as exc:  # noqa: BLE001
            log(f"Backup error: {exc}")
            self.set_status("Erro no backup. Veja o log.")

    def stop_server(self) -> None:
        if self.process and self.process.poll() is None:
            self.set_status("Parando servidor...")
            try:
                if is_windows():
                    self.process.terminate()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.process.wait(timeout=8)
            except Exception as exc:  # noqa: BLE001
                log(f"Graceful stop failed: {exc}")
                self.process.kill()
            self.set_status("Servidor parado")
            return
        if is_system_healthy(self.port):
            self.messagebox.showinfo(
                "SannyGold",
                "O servidor ja estava aberto antes deste launcher. Feche a outra janela ou processo que iniciou o sistema.",
            )
            return
        self.set_status("Servidor parado")

    def on_close(self) -> None:
        if self.process and self.process.poll() is None:
            should_stop = self.messagebox.askyesno(
                "SannyGold",
                "Deseja parar o servidor antes de fechar o launcher?",
            )
            if should_stop:
                self.stop_server()
        if self.lock_acquired:
            release_launcher_lock()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    ensure_runtime_dirs()
    log("Launcher opened")
    app = SannyGoldLauncher(diagnostic_only="--diagnostico" in argv or "--diagnostico-sannygold" in argv)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
