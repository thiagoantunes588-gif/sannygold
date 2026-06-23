from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BASE_DIR = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = BASE_DIR / "scripts" / "sannygold_launcher.py"
MACOS_INSTALLER_PATH = BASE_DIR / "scripts" / "install_macos_launcher.sh"
ORGANIZE_INSTALLERS_PATH = BASE_DIR / "scripts" / "organize_dropbox_installers.sh"
MACOS_LAUNCH_AGENT_INSTALLER_PATH = BASE_DIR / "scripts" / "install_macos_launch_agent.sh"
MACOS_LAUNCH_AGENT_UNINSTALLER_PATH = BASE_DIR / "scripts" / "uninstall_macos_launch_agent.sh"
MACOS_AUTOSTART_DOC_PATH = BASE_DIR / "docs" / "macos-autostart.md"
START_LOCAL_PATH = BASE_DIR / "scripts" / "start_local.sh"
START_WINDOWS_PATH = BASE_DIR / "scripts" / "start_windows.ps1"
START_WINDOWS_LAUNCHER_PATH = BASE_DIR / "scripts" / "start_windows_launcher.ps1"
INSTALL_WINDOWS_LAUNCHER_PATH = BASE_DIR / "scripts" / "install_windows_launcher.ps1"
BUILD_WINDOWS_APP_PATH = BASE_DIR / "scripts" / "build_windows_app.ps1"
BUILD_WINDOWS_INSTALLER_PATH = BASE_DIR / "scripts" / "build_windows_installer.ps1"
PACKAGE_WINDOWS_PORTABLE_PATH = BASE_DIR / "scripts" / "package_windows_portable.ps1"
PACKAGE_WINDOWS_SOURCE_PORTABLE_PATH = BASE_DIR / "scripts" / "package_windows_source_portable.py"
WINDOWS_PORTABLE_BOOTSTRAP_PATH = BASE_DIR / "scripts" / "windows_portable_bootstrap.py"
BUILD_ALL_WINDOWS_PATH = BASE_DIR / "scripts" / "build_all_windows.ps1"
BUILD_ALL_WINDOWS_BAT_PATH = BASE_DIR / "scripts" / "build_all_windows.bat"
WINDOWS_INNO_SCRIPT_PATH = BASE_DIR / "installer" / "windows" / "sannygold-windows.iss"
WINDOWS_INSTALLER_DOC_PATH = BASE_DIR / "docs" / "instalador-windows.md"
WINDOWS_README_PATH = BASE_DIR / "installer" / "windows" / "LEIA-ME.md"
MAC_README_PATH = BASE_DIR / "installer" / "mac" / "LEIA-ME.md"
MOBILE_README_PATH = BASE_DIR / "installer" / "celular" / "LEIA-ME.md"
INSTALLERS_README_PATH = BASE_DIR / "installer" / "LEIA-ME.md"
WINDOWS_PREINSTALL_README_PATH = BASE_DIR / "LEIA-ANTES-DE-INSTALAR-WINDOWS.md"
EXPORT_CONTEXT_PATH = BASE_DIR / "scripts" / "export_chatgpt_context.py"
spec = importlib.util.spec_from_file_location("sannygold_launcher_for_tests", LAUNCHER_PATH)
launcher = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(launcher)
export_spec = importlib.util.spec_from_file_location("export_chatgpt_context_for_tests", EXPORT_CONTEXT_PATH)
exporter = importlib.util.module_from_spec(export_spec)
assert export_spec and export_spec.loader
export_spec.loader.exec_module(exporter)


class DesktopLauncherTest(unittest.TestCase):
    def test_server_command_uses_waitress_wsgi_server(self):
        command = launcher.server_command(Path("/usr/bin/python3"), "0.0.0.0", 5007)

        self.assertEqual(command[:3], ["/usr/bin/python3", "-m", "waitress"])
        self.assertIn("--host", command)
        self.assertIn("0.0.0.0", command)
        self.assertIn("--port", command)
        self.assertIn("5007", command)
        self.assertEqual(command[-1], "app.main:app")

    def test_backup_summary_reports_local_and_dropbox_status(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            local_dir = root / "backups"
            dropbox_dir = root / "Dropbox" / "Backups"
            local_dir.mkdir(parents=True)
            dropbox_dir.mkdir(parents=True)
            (local_dir / "sannygold-data-backup-20260525-100000-a.zip").write_bytes(b"local")
            (dropbox_dir / "sannygold-data-backup-20260525-110000-b.zip").write_bytes(b"dropbox")

            summary = launcher.backup_summary(dropbox_dir=dropbox_dir, local_dir=local_dir)

        self.assertIn("sannygold-data-backup-20260525-100000-a.zip", summary["local"])
        self.assertIn("Dropbox OK", summary["dropbox"])
        self.assertIn("sannygold-data-backup-20260525-110000-b.zip", summary["dropbox"])

    def test_launcher_detects_unsafe_dropbox_runtime_paths(self):
        with tempfile.TemporaryDirectory() as tempdir:
            dropbox_root = Path(tempdir) / "Dropbox"
            project_root = dropbox_root / "Sistema"
            env = {
                "DROPBOX_BACKUP_DIR": str(dropbox_root / "SannyGold" / "Backups"),
                "ROTAFLOW_STORAGE_DIR": str(project_root),
                "SANNYGOLD_SQLITE_PATH": str(project_root / "data" / "sannygold.db"),
            }

            unsafe = launcher.unsafe_dropbox_paths(
                env,
                base_dir=project_root,
                dropbox_dir=dropbox_root / "SannyGold" / "Backups",
            )

        self.assertIn("pasta inteira do sistema", unsafe)
        self.assertIn("data/", unsafe)
        self.assertIn("uploads/", unsafe)
        self.assertIn("sannygold.db", unsafe)

    def test_venv_python_uses_platform_specific_paths(self):
        with patch.object(launcher.platform, "system", return_value="Windows"):
            self.assertEqual(launcher.venv_python(Path("C:/Sistema/.venv")), Path("C:/Sistema/.venv") / "Scripts" / "python.exe")
        with patch.object(launcher.platform, "system", return_value="Darwin"):
            self.assertEqual(launcher.venv_python(Path("/Sistema/.venv")), Path("/Sistema/.venv") / "bin" / "python")

    def test_popen_kwargs_avoid_start_new_session_on_windows(self):
        with patch.object(launcher.platform, "system", return_value="Windows"):
            self.assertNotIn("start_new_session", launcher.popen_kwargs())
        with patch.object(launcher.platform, "system", return_value="Darwin"):
            self.assertEqual(launcher.popen_kwargs(), {"start_new_session": True})

    def test_env_parser_handles_shell_quoted_values(self):
        self.assertEqual(launcher.parse_env_line("'valor com espaco'"), "valor com espaco")
        self.assertEqual(launcher.parse_env_line("simples"), "simples")

    def test_port_and_url_can_be_configured_without_crashing(self):
        old_port = os.environ.get("PORT")
        try:
            os.environ.pop("PORT", None)
            self.assertEqual(launcher.resolve_port({"PORT": "5012"}), 5012)
            self.assertEqual(launcher.resolve_port({"PORT": "99999"}), launcher.DEFAULT_PORT)
            self.assertEqual(launcher.resolve_port({"PORT": "abc"}), launcher.DEFAULT_PORT)
            self.assertEqual(launcher.local_url(5012), "http://127.0.0.1:5012/")
        finally:
            if old_port is None:
                os.environ.pop("PORT", None)
            else:
                os.environ["PORT"] = old_port

    def test_launcher_lock_prevents_duplicate_launcher_processes(self):
        with tempfile.TemporaryDirectory() as tempdir:
            lock_file = Path(tempdir) / "launcher.lock"

            self.assertTrue(launcher.acquire_launcher_lock(lock_file, port=5007))
            self.assertFalse(launcher.acquire_launcher_lock(lock_file, port=5007))
            launcher.release_launcher_lock(lock_file)
            self.assertFalse(lock_file.exists())

    def test_macos_packaging_script_creates_named_app_wrapper(self):
        script = MACOS_INSTALLER_PATH.read_text(encoding="utf-8")

        self.assertIn("SannyGold Sistema.app", script)
        self.assertIn("scripts/sannygold_launcher.py", script)
        self.assertIn("osacompile", script)
        self.assertIn("logs/macos-launcher.log", script)
        self.assertIn("CFBundleDisplayName SannyGold Sistema", script)
        self.assertIn("com.sannygold.sistema.local", script)
        self.assertIn('$DROPBOX_INSTALLERS_DIR/Mac', script)
        self.assertIn('MAC_INSTALLERS_DIR="$MAC_ROOT_DIR/Instalador"', script)
        self.assertIn("SannyGold-Sistema-Mac.zip", script)
        self.assertIn("organize_dropbox_installers.sh", script)
        self.assertIn("ditto -c -k --keepParent", script)

    def test_dropbox_installer_organizer_creates_platform_structure_and_moves_legacy_items(self):
        self.assertTrue(ORGANIZE_INSTALLERS_PATH.exists())
        with tempfile.TemporaryDirectory() as tempdir:
            dropbox_root = Path(tempdir) / "Sistema SannyGold"
            installers_dir = dropbox_root / "Instaladores"
            installers_dir.mkdir(parents=True)
            (installers_dir / "SannyGold-Sistema-Instalacao-20260531-223322.zip").write_bytes(b"zip")
            (installers_dir / "SannyGold-Sistema-Windows-Setup.exe").write_bytes(b"exe")
            (installers_dir / "SannyGold Sistema.app").mkdir()

            result = subprocess.run(
                ["bash", str(ORGANIZE_INSTALLERS_PATH), str(dropbox_root)],
                cwd=BASE_DIR,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            self.assertTrue((installers_dir / "Mac" / "Instalador").exists())
            self.assertTrue((installers_dir / "Mac" / "Atualizações").exists())
            self.assertTrue((installers_dir / "Windows" / "Instalador").exists())
            self.assertTrue((installers_dir / "Windows" / "Atualizações").exists())
            self.assertTrue((installers_dir / "Celular" / "Android").exists())
            self.assertTrue((installers_dir / "Celular" / "iPhone-iOS").exists())
            self.assertTrue((installers_dir / "Celular" / "Atalho-Web").exists())
            self.assertTrue((installers_dir / "Mac" / "LEIA-ME.md").exists())
            self.assertTrue((installers_dir / "Windows" / "LEIA-ME.md").exists())
            self.assertTrue((installers_dir / "Celular" / "LEIA-ME.md").exists())
            self.assertTrue((installers_dir / "LEIA-ME.md").exists())
            self.assertTrue((dropbox_root / "Backups").exists())
            self.assertFalse((installers_dir / "SannyGold Sistema.app").exists())
            self.assertFalse((installers_dir / "SannyGold-Sistema-Windows-Setup.exe").exists())
            self.assertTrue((installers_dir / "Mac" / "Instalador" / "SannyGold Sistema.app").exists())
            self.assertTrue((installers_dir / "Windows" / "Instalador" / "SannyGold-Sistema-Windows-Setup.exe").exists())
            review_names = [item.name for item in (installers_dir / "_Revisao_Antes_de_Excluir").iterdir()]
            self.assertTrue(any(name.endswith("SannyGold-Sistema-Instalacao-20260531-223322.zip") for name in review_names))

    def test_macos_launch_agent_scripts_are_documented_and_logged(self):
        install_script = MACOS_LAUNCH_AGENT_INSTALLER_PATH.read_text(encoding="utf-8")
        uninstall_script = MACOS_LAUNCH_AGENT_UNINSTALLER_PATH.read_text(encoding="utf-8")
        doc = MACOS_AUTOSTART_DOC_PATH.read_text(encoding="utf-8")

        self.assertIn("com.sannygold.sistema.launchagent", install_script)
        self.assertIn("plistlib.dump", install_script)
        self.assertIn("RunAtLoad", install_script)
        self.assertIn("scripts/start_local.sh", install_script)
        self.assertIn("logs/launchagent.out.log", install_script)
        self.assertIn("logs/launchagent.err.log", install_script)
        self.assertIn("launchctl bootstrap", install_script)
        self.assertIn("launchctl bootout", uninstall_script)
        self.assertIn("PORT=5007", doc)
        self.assertIn("FLASK_HOST=0.0.0.0", doc)
        self.assertIn("logs/launchagent.err.log", doc)
        self.assertIn("bash scripts/uninstall_macos_launch_agent.sh", doc)

    def test_start_local_prepares_logs_and_reads_port_configuration(self):
        script = START_LOCAL_PATH.read_text(encoding="utf-8")

        self.assertIn("mkdir -p data uploads preview tmp logs backups", script)
        self.assertIn("SECRET_KEY=\"$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')\"", script)
        self.assertNotIn("SECRET_KEY='[REMOVIDO]'PY'", script)
        self.assertIn("echo \"PORT=$(shell_escape \"$PORT\")\"", script)
        self.assertIn("echo \"FLASK_HOST=$(shell_escape", script)
        self.assertIn("export PORT=\"${PORT:-5007}\"", script)
        self.assertIn("python3 -m waitress", script)

    def test_start_local_has_valid_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(START_LOCAL_PATH)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_start_local_creates_env_file_with_required_defaults(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "project"
            scripts_dir = root / "scripts"
            home_dir = Path(tempdir) / "home"
            scripts_dir.mkdir(parents=True)
            home_dir.mkdir()
            shutil.copy2(START_LOCAL_PATH, scripts_dir / "start_local.sh")

            env = {
                "HOME": str(home_dir),
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "SANNYGOLD_START_LOCAL_SETUP_ONLY": "1",
            }
            result = subprocess.run(
                ["bash", str(scripts_dir / "start_local.sh")],
                cwd=root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            env_text = (root / ".env.local").read_text(encoding="utf-8")
            values = dict(line.split("=", 1) for line in env_text.splitlines() if "=" in line)
            self.assertRegex(values["SANNYGOLD_SECRET_KEY"], r"^[A-Za-z0-9_-]{50,}$")
            self.assertIn("ROTAFLOW_STORAGE_DIR", values)
            self.assertIn("SANNYGOLD_SQLITE_PATH", values)
            self.assertEqual(values["SANNYGOLD_STORAGE_BACKEND"], "sqlite")
            self.assertEqual(values["SANNYGOLD_SQLITE_MIRROR_JSON"], "1")
            self.assertIn("DROPBOX_BACKUP_DIR", values)
            self.assertEqual(values["PORT"], "5007")
            self.assertEqual(values["FLASK_HOST"], "0.0.0.0")
            self.assertNotIn("[REMOVIDO]", env_text)
            self.assertNotIn("PY'", env_text)

    def test_launcher_env_file_has_portable_local_paths(self):
        with tempfile.TemporaryDirectory() as tempdir:
            env_path = Path(tempdir) / ".env.local"

            launcher.write_env_file_if_missing(env_path)

            env_text = env_path.read_text(encoding="utf-8")
            values = launcher.load_env_file(env_path)
        self.assertIn("ROTAFLOW_STORAGE_DIR", values)
        self.assertEqual(Path(values["ROTAFLOW_STORAGE_DIR"]), BASE_DIR)
        self.assertEqual(Path(values["SANNYGOLD_SQLITE_PATH"]), BASE_DIR / "data" / "sannygold.db")
        self.assertEqual(values["SANNYGOLD_STORAGE_BACKEND"], "sqlite")
        self.assertEqual(values["SANNYGOLD_SQLITE_MIRROR_JSON"], "1")
        self.assertEqual(Path(values["DROPBOX_BACKUP_DIR"]), Path.home() / "Dropbox" / "Sistema SannyGold" / "Backups")
        self.assertIn("Sistema SannyGold", env_text)
        self.assertIn("PORT=", env_text)
        self.assertIn("FLASK_HOST=", env_text)

    def test_start_local_refuses_sqlite_database_inside_dropbox(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "project"
            scripts_dir = root / "scripts"
            home_dir = Path(tempdir) / "home"
            scripts_dir.mkdir(parents=True)
            home_dir.mkdir()
            shutil.copy2(START_LOCAL_PATH, scripts_dir / "start_local.sh")
            (root / ".env.local").write_text(
                "\n".join(
                    [
                        "SANNYGOLD_ENV=local",
                        "SANNYGOLD_SECRET_KEY=teste_chave_segura_com_mais_de_50_caracteres_123456",
                        f"ROTAFLOW_STORAGE_DIR={root}",
                        f"SANNYGOLD_SQLITE_PATH='{home_dir}/Dropbox/Sistema SannyGold/data/sannygold.db'",
                        "SANNYGOLD_STORAGE_BACKEND=sqlite",
                        "SANNYGOLD_SQLITE_MIRROR_JSON=1",
                        f"DROPBOX_BACKUP_DIR='{home_dir}/Dropbox/Sistema SannyGold/Backups'",
                        "PORT=5007",
                        "FLASK_HOST=127.0.0.1",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                ["bash", str(scripts_dir / "start_local.sh")],
                cwd=root,
                env={
                    "HOME": str(home_dir),
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "SANNYGOLD_START_LOCAL_SETUP_ONLY": "1",
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SANNYGOLD_SQLITE_PATH não pode ficar dentro do Dropbox", result.stderr)

    def test_start_local_refuses_project_root_inside_dropbox(self):
        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "home"
            root = home_dir / "Dropbox" / "Sistema"
            scripts_dir = root / "scripts"
            scripts_dir.mkdir(parents=True)
            shutil.copy2(START_LOCAL_PATH, scripts_dir / "start_local.sh")

            result = subprocess.run(
                ["bash", str(scripts_dir / "start_local.sh")],
                cwd=root,
                env={
                    "HOME": str(home_dir),
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "SANNYGOLD_START_LOCAL_SETUP_ONLY": "1",
                },
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("a pasta inteira do sistema não pode ficar dentro do Dropbox", result.stderr)

    def test_export_sanitizer_preserves_secret_key_generation_syntax(self):
        snippet = """SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
echo "SANNYGOLD_SECRET_KEY=$SECRET_KEY"
"""

        sanitized = exporter.sanitize_text(snippet)

        self.assertIn(
            "SECRET_KEY=\"$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')\"",
            sanitized,
        )
        self.assertNotIn("SECRET_KEY='[REMOVIDO]'PY'", sanitized)
        self.assertNotRegex(sanitized, re.compile(r"\[REMOVIDO\].*PY"))

    def test_windows_start_script_exists_with_required_defaults(self):
        self.assertTrue(START_WINDOWS_PATH.exists())
        script = START_WINDOWS_PATH.read_text(encoding="utf-8")

        self.assertIn('$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path', script)
        for folder in ("data", "uploads", "preview", "tmp", "logs", "backups"):
            self.assertIn(f'"{folder}"', script)
        self.assertIn('if (-not (Test-Path $EnvFile))', script)
        self.assertIn('"SANNYGOLD_ENV" = "local"', script)
        self.assertIn('"ROTAFLOW_STORAGE_DIR" = $ProjectRoot', script)
        self.assertIn('"SANNYGOLD_SQLITE_PATH" = (Join-Path $ProjectRoot "data\\sannygold.db")', script)
        self.assertIn('"SANNYGOLD_STORAGE_BACKEND" = "sqlite"', script)
        self.assertIn('"SANNYGOLD_SQLITE_MIRROR_JSON" = "1"', script)
        self.assertIn('"DROPBOX_BACKUP_DIR" = $DropboxBackupDir', script)
        self.assertIn('"PORT" = $DefaultPort', script)
        self.assertIn('"FLASK_HOST" = $DefaultHost', script)
        self.assertIn('"FLASK_DEBUG" = "0"', script)
        self.assertIn('"SANNYGOLD_SESSION_COOKIE_SECURE" = "0"', script)
        self.assertIn('"SANNYGOLD_CSRF_DISABLED" = "0"', script)

    def test_windows_start_script_uses_windows_paths_and_keeps_database_out_of_dropbox(self):
        script = START_WINDOWS_PATH.read_text(encoding="utf-8")

        self.assertIn('$VenvPython = Join-Path $VenvDir "Scripts\\python.exe"', script)
        self.assertIn('$DropboxBackupDir = Join-Path $env:USERPROFILE "Dropbox\\Sistema SannyGold\\Backups"', script)
        self.assertIn('Set-EnvDefault -Name "SANNYGOLD_SQLITE_PATH" -Value (Join-Path $ProjectRoot "data\\sannygold.db")', script)
        self.assertIn('Assert-NotInsideDropbox -Label "a pasta inteira do sistema"', script)
        self.assertIn('Assert-NotInsideDropbox -Label "data/"', script)
        self.assertIn('Assert-NotInsideDropbox -Label "uploads/"', script)
        self.assertIn('Assert-NotInsideDropbox -Label "SANNYGOLD_SQLITE_PATH"', script)
        self.assertIn('nao pode ficar dentro do Dropbox', script)
        self.assertIn('Use Dropbox apenas para backups .zip', script)

    def test_windows_start_script_creates_venv_installs_requirements_and_runs_waitress(self):
        script = START_WINDOWS_PATH.read_text(encoding="utf-8")

        self.assertIn('return @("py", "-3")', script)
        self.assertIn('return @("python")', script)
        self.assertIn('Invoke-Python -PythonCommand $PythonCommand -Arguments @("-m", "venv", $VenvDir)', script)
        self.assertIn('Get-FileHash -Algorithm SHA256 -Path $requirementsPath', script)
        self.assertIn('& $VenvPython -m pip install -r $requirementsPath', script)
        self.assertIn('scripts\\create_local_backup.py', script)
        self.assertIn('--if-older-hours 24', script)
        self.assertIn('scripts\\migrate_json_to_sqlite.py', script)
        self.assertIn('Write-Host "URL local: $localUrl"', script)
        self.assertIn('URL para celular no Wi-Fi', script)
        self.assertIn('Pasta Dropbox para backups', script)
        self.assertIn('& $VenvPython -m waitress --host $env:FLASK_HOST --port $env:PORT app.main:app', script)

    def test_windows_launcher_installer_scripts_create_desktop_shortcut(self):
        self.assertTrue(INSTALL_WINDOWS_LAUNCHER_PATH.exists())
        self.assertTrue(START_WINDOWS_LAUNCHER_PATH.exists())
        installer = INSTALL_WINDOWS_LAUNCHER_PATH.read_text(encoding="utf-8")
        starter = START_WINDOWS_LAUNCHER_PATH.read_text(encoding="utf-8")

        self.assertIn('return @("py", "-3")', installer)
        self.assertIn('return @("python")', installer)
        self.assertIn('$VenvPython = Join-Path $VenvDir "Scripts\\python.exe"', installer)
        self.assertIn('& $VenvPython -m pip install -r $RequirementsPath', installer)
        self.assertIn('$DropboxBackupDir = Join-Path $DropboxRoot "Sistema SannyGold\\Backups"', installer)
        self.assertIn('"SannyGold Sistema.lnk"', installer)
        self.assertIn('$shortcut.TargetPath = "powershell.exe"', installer)
        self.assertIn('-ExecutionPolicy Bypass -File', installer)
        self.assertIn('start_windows_launcher.ps1', installer)
        self.assertIn('windows-launcher.log', installer)
        self.assertIn('Dropbox nao encontrado', installer)
        self.assertIn('a pasta inteira do sistema nao pode ficar dentro do Dropbox', installer)
        self.assertIn('Nao coloque data, uploads ou sannygold.db dentro do Dropbox', installer)

        self.assertIn('$VenvPython = Join-Path $ProjectRoot ".venv\\Scripts\\python.exe"', starter)
        self.assertIn('$LauncherScript = Join-Path $ProjectRoot "scripts\\sannygold_launcher.py"', starter)
        self.assertIn('& $VenvPython $LauncherScript', starter)
        self.assertIn('windows-launcher.log', starter)

    def test_launcher_defaults_support_windows_installer_first_run(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir) / "SannyGold Sistema"
            env_path = root / ".env.local"
            root.mkdir()

            launcher.write_env_file_if_missing(
                env_path,
                base_dir=root,
                dropbox_backup_dir=Path(tempdir) / "Dropbox" / "Sistema SannyGold" / "Backups",
            )

            values = launcher.load_env_file(env_path)

        self.assertEqual(Path(values["ROTAFLOW_STORAGE_DIR"]), root)
        self.assertEqual(Path(values["SANNYGOLD_SQLITE_PATH"]), root / "data" / "sannygold.db")
        self.assertEqual(Path(values["DROPBOX_BACKUP_DIR"]).parts[-2:], ("Sistema SannyGold", "Backups"))
        self.assertIn("Sistema SannyGold", launcher.DROPBOX_SYSTEM_FOLDER)
        self.assertEqual(launcher.APP_NAME, "SannyGold Sistema")
        launcher_source = LAUNCHER_PATH.read_text(encoding="utf-8")
        self.assertIn("--diagnostico", launcher_source)
        self.assertIn("diagnostic_only", launcher_source)

    def test_launcher_reports_dropbox_not_found_with_user_friendly_message(self):
        with tempfile.TemporaryDirectory() as tempdir:
            missing_dropbox = Path(tempdir) / "Dropbox" / "Sistema SannyGold" / "Backups"
            summary = launcher.backup_summary(dropbox_dir=missing_dropbox, local_dir=Path(tempdir) / "backups")

        self.assertIn("Dropbox não encontrado. O sistema funcionará localmente, mas o backup externo não está ativo.", summary["dropbox"])
        self.assertIn("Sistema SannyGold", summary["dropbox_dir"])

    def test_windows_pyinstaller_build_script_uses_safe_project_bundle(self):
        self.assertTrue(BUILD_WINDOWS_APP_PATH.exists())
        script = BUILD_WINDOWS_APP_PATH.read_text(encoding="utf-8")

        self.assertIn("PyInstaller", script)
        self.assertIn("[System.Environment]::OSVersion.Platform", script)
        self.assertIn("Windows 10/11", script)
        self.assertIn('--name", $AppName', script)
        self.assertIn("--windowed", script)
        self.assertIn("--onedir", script)
        self.assertIn("--contents-directory", script)
        self.assertIn("SannyGold Sistema", script)
        self.assertIn("SannyGold Sistema.exe", script)
        self.assertIn("sannygold.ico", script)
        self.assertIn("sannygold-wizard.bmp", script)
        self.assertIn("sannygold-small.bmp", script)
        self.assertIn("New-SannyGoldInstallerImages", script)
        self.assertIn("System.Drawing", script)
        self.assertIn("app\\static\\sannygold-logo.jpg", script)
        self.assertIn("dist\\windows", script)
        self.assertIn("logs\\build-windows.log", script)
        self.assertIn('/XD "__pycache__" ".pytest_cache" ".mypy_cache" "data" "uploads" "preview" "backups" "logs" "tmp" ".venv"', script)
        self.assertIn('/XF ".env" ".env.local"', script)

    def test_windows_portable_package_script_creates_source_zip_in_dropbox_windows_folder(self):
        self.assertTrue(PACKAGE_WINDOWS_PORTABLE_PATH.exists())
        self.assertTrue(PACKAGE_WINDOWS_SOURCE_PORTABLE_PATH.exists())
        self.assertTrue(WINDOWS_PORTABLE_BOOTSTRAP_PATH.exists())
        wrapper = PACKAGE_WINDOWS_PORTABLE_PATH.read_text(encoding="utf-8")
        packager = PACKAGE_WINDOWS_SOURCE_PORTABLE_PATH.read_text(encoding="utf-8")
        bootstrap = WINDOWS_PORTABLE_BOOTSTRAP_PATH.read_text(encoding="utf-8")

        self.assertIn("package_windows_source_portable.py", wrapper)
        self.assertIn("Python 3 nao encontrado", wrapper)
        self.assertIn("SannyGold-Sistema-Windows-Portable.zip", packager)
        self.assertIn("dist", packager)
        self.assertIn("installers", packager)
        self.assertIn("Instaladores", packager)
        self.assertIn("Windows", packager)
        self.assertIn("Instalador", packager)
        self.assertIn("abrir-sistema.bat", packager)
        self.assertIn("instalar-dependencias.bat", packager)
        self.assertIn("diagnostico-dropbox.bat", packager)
        self.assertIn("configurar-dropbox.bat", packager)
        self.assertIn("LEIA-PRIMEIRO.txt", packager)
        self.assertIn("app/main.py", packager)
        self.assertIn("scripts/windows_portable_bootstrap.py", packager)
        self.assertIn("requirements.txt", packager)
        self.assertIn('".env.local"', packager)
        self.assertIn('"data/sannygold.db"', packager)
        self.assertIn('"data"', packager)
        self.assertIn('"uploads"', packager)
        self.assertIn('"preview"', packager)
        self.assertIn('"backups"', packager)
        self.assertIn('"logs"', packager)
        self.assertIn('%PYTHON_CMD% "scripts\\windows_portable_bootstrap.py" --start', packager)
        self.assertNotIn("build_windows_app.ps1", packager)
        self.assertNotIn('"-m", "PyInstaller"', packager)
        self.assertNotIn("SannyGold Sistema.exe", packager)

        self.assertIn("secrets.token_urlsafe(48)", bootstrap)
        self.assertIn('return root / ".venv" / "Scripts" / "python.exe"', bootstrap)
        self.assertIn('"DROPBOX_BACKUP_DIR": str(default_dropbox_backup_dir())', bootstrap)
        self.assertIn('"SANNYGOLD_SQLITE_PATH": str(root / "data" / "sannygold.db")', bootstrap)
        self.assertIn("Extraia o sistema para uma pasta local fora do Dropbox", bootstrap)
        self.assertIn("Dropbox nao encontrado. O sistema funcionara localmente", bootstrap)
        self.assertIn("waitress", bootstrap)
        self.assertIn("http://127.0.0.1", bootstrap)

    def test_windows_inno_installer_script_has_professional_install_experience(self):
        self.assertTrue(WINDOWS_INNO_SCRIPT_PATH.exists())
        script = WINDOWS_INNO_SCRIPT_PATH.read_text(encoding="utf-8")
        info_before = (BASE_DIR / "installer" / "windows" / "INFO-ANTES-DE-INSTALAR-WINDOWS.txt").read_text(encoding="utf-8")

        self.assertIn('#define AppName "SannyGold Sistema"', script)
        self.assertIn('#define InstallerName "SannyGold Sistema - Instalador Windows"', script)
        self.assertIn("DefaultDirName={localappdata}\\SannyGold Sistema", script)
        self.assertIn("PrivilegesRequired=lowest", script)
        self.assertIn("OutputBaseFilename=SannyGold-Sistema-Windows-Setup", script)
        self.assertIn("SetupIconFile={#IconFile}", script)
        self.assertIn("WizardImageFile={#WizardImageFile}", script)
        self.assertIn("WizardSmallImageFile={#WizardSmallImageFile}", script)
        self.assertIn("WizardImageBackColor=$FDFAF1", script)
        self.assertIn("Criar atalho na Área de Trabalho", script)
        self.assertIn("Abrir SannyGold Sistema após instalar", script)
        self.assertIn("Diagnóstico SannyGold", script)
        self.assertIn("Pasta de Backups SannyGold", script)
        self.assertIn("--diagnostico", script)
        self.assertIn("UninstallDisplayIcon", script)
        self.assertIn("Local de instalação", script)
        self.assertIn("Local dos dados", script)
        self.assertIn("Local dos backups locais", script)
        self.assertIn("Local esperado do Dropbox", script)
        self.assertIn("Dropbox\\Sistema SannyGold\\Backups", script)
        self.assertIn("Instale o Sistema SannyGold para operação local com backup seguro no Dropbox.", info_before)
        self.assertIn("O Dropbox será usado apenas para backups e instaladores.", info_before)

    def test_windows_installer_build_script_outputs_to_platform_folder(self):
        self.assertTrue(BUILD_WINDOWS_INSTALLER_PATH.exists())
        script = BUILD_WINDOWS_INSTALLER_PATH.read_text(encoding="utf-8")

        self.assertIn("scripts\\build_windows_app.ps1", script)
        self.assertIn("Find-InnoCompiler", script)
        self.assertIn("ISCC.exe", script)
        self.assertIn("installer\\windows\\sannygold-windows.iss", script)
        self.assertIn("SannyGold-Sistema-Windows-Setup.exe", script)
        self.assertIn("Instale o Inno Setup para gerar o instalador .exe visual.", script)
        self.assertIn("C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe", script)
        self.assertIn("C:\\Program Files\\Inno Setup 6\\ISCC.exe", script)
        self.assertIn("C:\\Program Files (x86)\\Inno Setup 7\\ISCC.exe", script)
        self.assertIn("C:\\Program Files\\Inno Setup 7\\ISCC.exe", script)
        self.assertIn("Get-Command winget", script)
        self.assertIn("Inno Setup não encontrado. Deseja instalar agora via winget? S/N", script)
        self.assertIn("winget install --id JRSoftware.InnoSetup -e -s winget", script)
        self.assertIn("Resolve-InnoCompiler", script)
        self.assertIn("Build-PortableFallback", script)
        self.assertIn("scripts\\package_windows_portable.ps1", script)
        self.assertIn("Instalador visual não foi criado, mas a versão portátil foi gerada.", script)
        self.assertIn("A pasta Windows ficaria sem pacote instalavel", script)
        self.assertIn("$InstallerOutputDir", script)
        self.assertIn("$InstallerOutputPath", script)
        self.assertIn("/DOutputDir=$InstallerOutputDir", script)
        self.assertIn("Assert-MinimumInstallerSize", script)
        self.assertIn("10MB", script)
        self.assertIn("Copia local em:", script)
        self.assertIn("Dropbox", script)
        self.assertIn("Sistema SannyGold", script)
        self.assertIn("Instaladores", script)
        self.assertIn("Windows", script)
        self.assertIn("Mac", script)
        self.assertIn("Celular", script)
        self.assertIn("Arquivados", script)
        self.assertIn("_Revisao_Antes_de_Excluir", script)
        self.assertIn("Move-LegacyInstallerItems", script)
        self.assertIn("SannyGold-Sistema-Mac.zip", script)
        self.assertIn("LEIA-ME.md", script)
        self.assertIn("Tamanho do instalador", script)
        self.assertIn("INSTALADOR WINDOWS GERADO COM SUCESSO", script)
        self.assertIn("Dropbox nao encontrado", script)
        self.assertIn("dist\\installers", script)

    def test_windows_build_all_script_orchestrates_app_portable_installer_and_validation(self):
        self.assertTrue(BUILD_ALL_WINDOWS_PATH.exists())
        self.assertTrue(BUILD_ALL_WINDOWS_BAT_PATH.exists())
        script = BUILD_ALL_WINDOWS_PATH.read_text(encoding="utf-8")
        batch = BUILD_ALL_WINDOWS_BAT_PATH.read_text(encoding="utf-8")

        self.assertIn("scripts\\build_windows_app.ps1", script)
        self.assertIn("scripts\\package_windows_portable.ps1", script)
        self.assertIn("scripts\\build_windows_installer.ps1", script)
        self.assertIn("Assert-FinalWindowsFolder", script)
        self.assertIn("Find-InnoCompiler", script)
        self.assertIn("C:\\Program Files (x86)\\Inno Setup 7\\ISCC.exe", script)
        self.assertIn("C:\\Program Files\\Inno Setup 7\\ISCC.exe", script)
        self.assertIn("LEIA-ME.md", script)
        self.assertIn("SannyGold-Sistema-Windows-Portable.zip", script)
        self.assertIn("SannyGold-Sistema-Windows-Setup.exe", script)
        self.assertIn("Versão portátil criada. Instalador visual não criado porque Inno Setup não foi encontrado.", script)
        self.assertIn("ERRO: nenhum pacote Windows foi gerado.", script)
        self.assertIn("Inno Setup foi encontrado, mas o instalador visual nao foi gerado", script)
        self.assertIn("10MB", script)
        self.assertIn("BUILD WINDOWS CONCLUIDO", script)
        self.assertLess(script.index("scripts\\build_windows_app.ps1"), script.index("scripts\\package_windows_portable.ps1"))
        self.assertLess(script.index("scripts\\package_windows_portable.ps1"), script.index("scripts\\build_windows_installer.ps1"))
        self.assertLess(script.index("scripts\\build_windows_installer.ps1"), script.index("Assert-FinalWindowsFolder -InnoAvailable"))

        self.assertIn("powershell.exe -NoProfile -ExecutionPolicy Bypass -File", batch)
        self.assertIn("build_all_windows.ps1", batch)
        self.assertIn("pause", batch)

    def test_platform_readmes_explain_mac_windows_separation(self):
        main_readme = INSTALLERS_README_PATH.read_text(encoding="utf-8")
        mac_readme = MAC_README_PATH.read_text(encoding="utf-8")
        windows_readme = WINDOWS_README_PATH.read_text(encoding="utf-8")
        mobile_readme = MOBILE_README_PATH.read_text(encoding="utf-8")
        preinstall = WINDOWS_PREINSTALL_README_PATH.read_text(encoding="utf-8")
        doc = WINDOWS_INSTALLER_DOC_PATH.read_text(encoding="utf-8")

        self.assertIn("Mac/", main_readme)
        self.assertIn("Windows/", main_readme)
        self.assertIn("Celular/", main_readme)
        self.assertIn("_Revisao_Antes_de_Excluir", main_readme)
        self.assertIn("Dropbox deve guardar somente instaladores", main_readme)
        self.assertIn("SannyGold Sistema.app", mac_readme)
        self.assertIn("Instalador/", mac_readme)
        self.assertIn("SannyGold-Sistema-Windows-Setup.exe", windows_readme)
        self.assertIn("SannyGold-Sistema-Windows-Portable.zip", windows_readme)
        self.assertIn("abrir-sistema.bat", windows_readme)
        self.assertIn("Instalador/", windows_readme)
        self.assertIn("Android", mobile_readme)
        self.assertIn("iPhone", mobile_readme)
        self.assertIn("manifest.webmanifest", mobile_readme)
        self.assertIn("service-worker.js", mobile_readme)
        self.assertIn("Se esta pasta tiver apenas arquivos .md", preinstall)
        self.assertIn("O arquivo .md é apenas documentação. Ele não instala o sistema.", preinstall)
        self.assertIn("Testar Dropbox", preinstall)
        self.assertIn("SannyGold-Sistema-Windows-Portable.zip", preinstall)
        self.assertIn("abrir-sistema.bat", preinstall)
        self.assertIn("não mova a pasta instalada para dentro do Dropbox".lower(), preinstall.lower())
        self.assertIn("%LOCALAPPDATA%\\SannyGold Sistema", doc)
        self.assertIn("Dropbox\\Sistema SannyGold\\Instaladores\\Windows\\Instalador", doc)
        self.assertIn("Como saber se deu certo", doc)
        self.assertIn("Se a pasta tiver apenas arquivos `.md`, o instalador Windows ainda não foi gerado.", doc)
        self.assertIn("Instale o Inno Setup para gerar o instalador .exe visual.", doc)
        self.assertIn("winget install --id JRSoftware.InnoSetup -e -s winget", doc)
        self.assertIn("Instalador visual não foi criado, mas a versão portátil foi gerada.", doc)
        self.assertIn("SannyGold-Sistema-Windows-Portable.zip", doc)
        self.assertIn("diagnostico-dropbox.bat", doc)
        self.assertIn("configurar-dropbox.bat", doc)
        self.assertIn("LEIA-PRIMEIRO.txt", doc)
        self.assertIn("INSTALADOR WINDOWS GERADO COM SUCESSO", doc)
        self.assertIn("build_all_windows.ps1", doc)
        self.assertIn("build_all_windows.bat", doc)
        self.assertIn("ERRO: nenhum pacote Windows foi gerado.", doc)


if __name__ == "__main__":
    unittest.main()
