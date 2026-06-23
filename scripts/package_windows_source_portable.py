from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path


APP_NAME = "SannyGold Sistema"
PORTABLE_FILE_NAME = "SannyGold-Sistema-Windows-Portable.zip"
DROPBOX_SYSTEM_FOLDER = "Sistema SannyGold"

ROOT_ITEMS = [
    "app",
    "scripts",
    "docs",
    "assets",
    "api",
    "web",
    "references",
    "requirements.txt",
    "README.md",
    "LEIA-ANTES-DE-INSTALAR-WINDOWS.md",
    ".env.example",
]

EXCLUDED_NAMES = {
    ".DS_Store",
    ".env",
    ".env.local",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    ".vercel",
    "__pycache__",
    "backups",
    "build",
    "data",
    "dist",
    "logs",
    "node_modules",
    "output",
    "preview",
    "tests",
    "tmp",
    "uploads",
}

REQUIRED_ZIP_ENTRIES = [
    f"{APP_NAME}/abrir-sistema.bat",
    f"{APP_NAME}/instalar-dependencias.bat",
    f"{APP_NAME}/configurar-dropbox.bat",
    f"{APP_NAME}/diagnostico-dropbox.bat",
    f"{APP_NAME}/LEIA-PRIMEIRO.txt",
    f"{APP_NAME}/app/main.py",
    f"{APP_NAME}/scripts/windows_portable_bootstrap.py",
    f"{APP_NAME}/requirements.txt",
]


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def readable_size(path: Path) -> str:
    size = path.stat().st_size
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.2f} KB"
    return f"{size} bytes"


def ignore_names(_directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if name in EXCLUDED_NAMES or name.endswith(".pyc") or name.endswith(".pyo"):
            ignored.add(name)
    return ignored


def write_text(path: Path, content: str) -> None:
    path.write_text(content.replace("\n", "\r\n"), encoding="ascii")


def create_batch_files(portable_root: Path) -> None:
    find_python = r"""
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PYTHON_CMD=py -3"
) else (
  where python >nul 2>nul
  if %ERRORLEVEL% NEQ 0 (
    echo Python 3 nao encontrado.
    echo Instale o Python 3 para Windows e marque a opcao "Add Python to PATH".
    echo Depois execute este arquivo novamente.
    pause
    exit /b 1
  )
  set "PYTHON_CMD=python"
)
"""

    write_text(
        portable_root / "abrir-sistema.bat",
        rf"""@echo off
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
echo [%date% %time%] Abrindo SannyGold Sistema portatil.>> "logs\portable.log"
{find_python}
%PYTHON_CMD% "scripts\windows_portable_bootstrap.py" --start
if %ERRORLEVEL% NEQ 0 (
  echo.
  echo Nao foi possivel abrir o Sistema SannyGold. Veja logs\portable.log.
  pause
)
""",
    )

    write_text(
        portable_root / "instalar-dependencias.bat",
        rf"""@echo off
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
echo [%date% %time%] Instalando dependencias portateis.>> "logs\portable.log"
{find_python}
%PYTHON_CMD% "scripts\windows_portable_bootstrap.py" --setup-only
if %ERRORLEVEL% NEQ 0 (
  echo.
  echo Falha ao preparar dependencias. Veja logs\portable.log.
  pause
  exit /b 1
)
echo.
echo Dependencias instaladas e configuracao preparada.
pause
""",
    )

    write_text(
        portable_root / "configurar-dropbox.bat",
        rf"""@echo off
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
echo [%date% %time%] Configurando Dropbox portatil.>> "logs\portable.log"
{find_python}
%PYTHON_CMD% "scripts\windows_portable_bootstrap.py" --setup-only
if %ERRORLEVEL% NEQ 0 (
  echo.
  echo Falha ao preparar configuracao. Veja logs\portable.log.
  pause
  exit /b 1
)
%PYTHON_CMD% "scripts\windows_portable_bootstrap.py" --diagnose-dropbox
echo.
pause
""",
    )

    write_text(
        portable_root / "diagnostico-dropbox.bat",
        rf"""@echo off
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
echo [%date% %time%] Executando diagnostico Dropbox.>> "logs\portable.log"
{find_python}
%PYTHON_CMD% "scripts\windows_portable_bootstrap.py" --diagnose-dropbox
echo.
pause
""",
    )


def create_readme(portable_root: Path) -> None:
    write_text(
        portable_root / "LEIA-PRIMEIRO.txt",
        r"""SannyGold Sistema - Versao Portatil Windows

Como usar:
1. Extraia SannyGold-Sistema-Windows-Portable.zip em uma pasta local do computador.
2. Nao extraia dentro do Dropbox.
3. Abra a pasta SannyGold Sistema.
4. De dois cliques em abrir-sistema.bat.

O que o abrir-sistema.bat faz:
- verifica se Python 3 existe;
- cria .venv se nao existir;
- instala requirements.txt;
- cria .env.local se nao existir;
- cria data, uploads, preview, backups, logs e tmp;
- configura DROPBOX_BACKUP_DIR para:
  %USERPROFILE%\Dropbox\Sistema SannyGold\Backups
- inicia o sistema em:
  http://127.0.0.1:5007

Outros arquivos:
- instalar-dependencias.bat prepara Python, .venv, dependencias e .env.local sem abrir o servidor.
- configurar-dropbox.bat prepara a pasta de backups no Dropbox quando o Dropbox existir.
- diagnostico-dropbox.bat mostra se o Dropbox esta pronto para backup.

Se Dropbox nao existir:
O sistema funciona localmente. O backup externo fica inativo ate o Dropbox ser instalado e sincronizado.

Seguranca:
O banco ativo fica em data\sannygold.db dentro desta pasta local.
Nunca coloque a pasta SannyGold Sistema, data, uploads, preview ou sannygold.db dentro do Dropbox.
O Dropbox deve guardar apenas instaladores e backups .zip.
""",
    )


def prepare_stage(root: Path) -> Path:
    stage_root = root / "build" / "windows-source-portable"
    portable_root = stage_root / APP_NAME
    if stage_root.exists():
        shutil.rmtree(stage_root)
    portable_root.mkdir(parents=True)

    for item_name in ROOT_ITEMS:
        source = root / item_name
        if not source.exists():
            continue
        destination = portable_root / item_name
        if source.is_dir():
            shutil.copytree(source, destination, ignore=ignore_names)
        else:
            shutil.copy2(source, destination)

    for folder in ("data", "uploads", "preview", "backups", "logs", "tmp"):
        (portable_root / folder).mkdir(parents=True, exist_ok=True)
    (portable_root / "logs" / "portable.log").write_text("", encoding="utf-8")
    create_batch_files(portable_root)
    create_readme(portable_root)

    forbidden = [".env.local", "data/sannygold.db"]
    for relative in forbidden:
        if (portable_root / relative).exists():
            raise RuntimeError(f"Arquivo sensivel nao pode entrar no portatil: {relative}")
    return portable_root


def zip_directory(portable_root: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(portable_root.rglob("*")):
            arcname = path.relative_to(portable_root.parent).as_posix()
            if path.is_dir():
                archive.writestr(f"{arcname}/", "")
            else:
                archive.write(path, arcname)


def verify_zip(output_path: Path) -> None:
    if not output_path.exists():
        raise RuntimeError(f"Zip portatil nao foi gerado: {output_path}")
    with zipfile.ZipFile(output_path, "r") as archive:
        entries = set(archive.namelist())
    missing = [entry for entry in REQUIRED_ZIP_ENTRIES if entry not in entries]
    if missing:
        raise RuntimeError("Zip portatil invalido. Entradas ausentes: " + ", ".join(missing))
    forbidden_fragments = [
        f"{APP_NAME}/.env.local",
        f"{APP_NAME}/data/sannygold.db",
        f"{APP_NAME}/.venv/",
        f"{APP_NAME}/backups/",
    ]
    for entry in entries:
        if entry == f"{APP_NAME}/backups/":
            continue
        if any(fragment in entry for fragment in forbidden_fragments):
            raise RuntimeError(f"Zip portatil contem arquivo proibido: {entry}")


def copy_to_dropbox(root: Path, output_path: Path) -> Path | None:
    dropbox_root = Path.home() / "Dropbox"
    if not dropbox_root.exists():
        return None
    installers_dir = dropbox_root / DROPBOX_SYSTEM_FOLDER / "Instaladores"
    windows_root = installers_dir / "Windows"
    windows_dir = windows_root / "Instalador"
    mobile_dir = installers_dir / "Celular"
    for folder in (
        installers_dir,
        windows_dir,
        windows_root / "Atualizações",
        installers_dir / "Mac" / "Instalador",
        installers_dir / "Mac" / "Atualizações",
        mobile_dir / "Android",
        mobile_dir / "iPhone-iOS",
        mobile_dir / "Atalho-Web",
        installers_dir / "Arquivados",
        installers_dir / "_Revisao_Antes_de_Excluir",
    ):
        folder.mkdir(parents=True, exist_ok=True)

    final_path = windows_dir / output_path.name
    shutil.copy2(output_path, final_path)

    readmes = [
        (root / "installer" / "LEIA-ME.md", installers_dir / "LEIA-ME.md"),
        (root / "installer" / "windows" / "LEIA-ME.md", windows_root / "LEIA-ME.md"),
        (root / "installer" / "mac" / "LEIA-ME.md", installers_dir / "Mac" / "LEIA-ME.md"),
        (root / "installer" / "celular" / "LEIA-ME.md", mobile_dir / "LEIA-ME.md"),
    ]
    for source, destination in readmes:
        if source.exists():
            shutil.copy2(source, destination)
    return final_path


def list_final_folder(folder: Path) -> None:
    print(f"\nListagem da pasta final: {folder}")
    if not folder.exists():
        print("Pasta final nao existe.")
        return
    for item in sorted(folder.iterdir()):
        if item.is_file():
            print(f"- {item.name} ({readable_size(item)})")
        else:
            print(f"- {item.name}/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera o pacote portatil Windows por codigo-fonte, sem Inno Setup e sem PyInstaller.")
    parser.add_argument(
        "--no-dropbox-copy",
        action="store_true",
        help="Nao copia o zip para Dropbox/Sistema SannyGold/Instaladores/Windows/Instalador.",
    )
    args = parser.parse_args()

    root = project_root()
    output_path = root / "dist" / "installers" / PORTABLE_FILE_NAME
    portable_root = prepare_stage(root)
    zip_directory(portable_root, output_path)
    verify_zip(output_path)

    print(f"Zip portatil gerado: {output_path}")
    print(f"Tamanho do zip portatil: {readable_size(output_path)}")

    final_path = None if args.no_dropbox_copy else copy_to_dropbox(root, output_path)
    if final_path:
        print(f"Copia Dropbox: {final_path}")
        print(f"Tamanho da copia Dropbox: {readable_size(final_path)}")
        list_final_folder(final_path.parent)
    elif args.no_dropbox_copy:
        print("Copia Dropbox ignorada por --no-dropbox-copy. O zip local foi gerado em dist/installers.")
        list_final_folder(output_path.parent)
    else:
        print("Dropbox nao encontrado. O zip local foi gerado em dist/installers.")
        list_final_folder(output_path.parent)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
