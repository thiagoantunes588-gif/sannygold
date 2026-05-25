#!/usr/bin/env python3
"""Build a sanitized ChatGPT context pack for Sistema Geral SannyGold."""

from __future__ import annotations

import ast
import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPORT_ROOT = ROOT / "output" / "chatgpt-export"
PACK_NAME = "sistema-geral-sannygold-chatgpt"
PACK_DIR = EXPORT_ROOT / PACK_NAME

IGNORE_DIRS = {
    ".git",
    ".venv",
    ".vercel",
    "__pycache__",
    "data",
    "gestor-de-rota-empresa",
    "output",
    "tmp",
    "uploads",
}

SOURCE_DIRS = {
    "agents",
    "api",
    "app",
    "assets",
    "docs",
    "preview",
    "references",
    "scripts",
    "tests",
    "web",
}

SOURCE_FILES = {
    ".gitignore",
    "README.md",
    "SKILL.md",
    "render.yaml",
    "requirements.txt",
    "vercel.json",
}

TEXT_SUFFIXES = {
    ".csv",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".txt",
    ".yaml",
    ".yml",
}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def should_ignore(path: Path) -> bool:
    parts = set(path.relative_to(ROOT).parts)
    return bool(parts & IGNORE_DIRS)


def safe_read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def sanitize_text(text: str) -> str:
    text = text.replace("Sanny123Gold", "[SENHA_PADRAO_REMOVIDA]")
    text = re.sub(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        "[EMAIL_REMOVIDO]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?<!\w)(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-.\s]?\d{4}(?!\w)",
        "[TELEFONE_REMOVIDO]",
        text,
    )
    text = re.sub(
        r"(SANNYGOLD_ADMIN_PASSWORD\s*=\s*)(['\"]?)[^'\"\n]+",
        r"\1'[SENHA_REMOVIDA]'",
        text,
    )
    text = re.sub(
        r"(default_password\s*=\s*os\.environ\.get\([^,]+,\s*)['\"][^'\"]+['\"]",
        r"\1'[SENHA_PADRAO_REMOVIDA]'",
        text,
    )
    text = re.sub(
        r"((?:password|senha|secret|token|api_key|SECRET_KEY)[^=\n:]{0,60}[=:]\s*)['\"][^'\"\n]+['\"]",
        r"\1'[REMOVIDO]'",
        text,
        flags=re.IGNORECASE,
    )
    return text


def run_command(args: list[str], timeout: int = 90) -> tuple[int, str]:
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
            env={**os.environ, "PYTHONPYCACHEPREFIX": "/private/tmp/sannygold-pycache"},
        )
        return result.returncode, result.stdout.strip()
    except Exception as exc:  # pragma: no cover - export helper resilience
        return 999, f"{type(exc).__name__}: {exc}"


def filter_git_status(status: str) -> str:
    hidden_prefixes = (
        "?? output/chatgpt-export/",
        "?? gestor-de-rota-empresa/",
    )
    lines = [
        line
        for line in status.splitlines()
        if not any(line.startswith(prefix) for prefix in hidden_prefixes)
    ]
    return "\n".join(lines)


def build_tree() -> str:
    lines = ["/"]
    for path in sorted(ROOT.rglob("*")):
        if should_ignore(path):
            continue
        if path.is_dir():
            continue
        relative = rel(path)
        size = path.stat().st_size
        lines.append(f"- {relative} ({size:,} bytes)")
    return "\n".join(lines)


def extract_routes() -> list[dict[str, str]]:
    source = ROOT / "app" / "main.py"
    routes: list[dict[str, str]] = []
    tree = ast.parse(safe_read(source))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr == "route"
                and isinstance(func.value, ast.Name)
                and func.value.id == "app"
            ):
                continue
            route = ""
            methods = "GET"
            if decorator.args and isinstance(decorator.args[0], ast.Constant):
                route = str(decorator.args[0].value)
            for keyword in decorator.keywords:
                if keyword.arg == "methods":
                    if isinstance(keyword.value, (ast.List, ast.Tuple)):
                        values = [
                            item.value
                            for item in keyword.value.elts
                            if isinstance(item, ast.Constant)
                        ]
                        methods = ", ".join(str(value) for value in values)
            routes.append(
                {
                    "line": str(node.lineno),
                    "route": route,
                    "methods": methods,
                    "function": node.name,
                }
            )
    return sorted(routes, key=lambda item: (item["route"], item["line"]))


def extract_symbols() -> str:
    files = [
        ROOT / "app" / "main.py",
        ROOT / "app" / "security.py",
        ROOT / "app" / "help_assistant.py",
        ROOT / "app" / "executive.py",
        ROOT / "web" / "panel_app.py",
    ]
    parts: list[str] = ["# Inventario tecnico\n"]
    for file_path in files:
        if not file_path.exists():
            continue
        parts.append(f"\n## {rel(file_path)}\n")
        tree = ast.parse(safe_read(file_path))
        symbols = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        for node in symbols:
            kind = "classe" if isinstance(node, ast.ClassDef) else "funcao"
            doc = ast.get_docstring(node)
            detail = f" - {doc.splitlines()[0]}" if doc else ""
            parts.append(f"- L{node.lineno}: `{node.name}` ({kind}){detail}")
        parts.append("")
    return "\n".join(parts)


def summarize_json_data() -> str:
    data_dir = ROOT / "data"
    parts = [
        "# Modelo de dados local",
        "",
        "Os arquivos reais de `data/` nao foram copiados para evitar expor clientes, contatos, enderecos e valores. Abaixo vai apenas a estrutura.",
        "",
    ]
    if not data_dir.exists():
        parts.append("Pasta `data/` nao encontrada.")
        return "\n".join(parts)
    for path in sorted(data_dir.glob("*.json")):
        try:
            payload = json.loads(safe_read(path))
        except Exception as exc:
            parts.append(f"## {path.name}\n- Erro ao ler JSON: {exc}\n")
            continue
        parts.append(f"## {path.name}")
        if isinstance(payload, list):
            keys = sorted({key for item in payload if isinstance(item, dict) for key in item.keys()})
            parts.append(f"- Tipo: lista")
            parts.append(f"- Registros: {len(payload)}")
            parts.append(f"- Campos encontrados: {', '.join(keys) if keys else 'n/d'}")
        elif isinstance(payload, dict):
            parts.append("- Tipo: objeto")
            parts.append(f"- Chaves principais: {', '.join(sorted(payload.keys())) if payload else 'n/d'}")
            for key, value in payload.items():
                if isinstance(value, list):
                    item_keys = sorted({item_key for item in value if isinstance(item, dict) for item_key in item.keys()})
                    parts.append(f"- `{key}`: lista com {len(value)} item(ns); campos: {', '.join(item_keys) if item_keys else 'n/d'}")
                elif isinstance(value, dict):
                    parts.append(f"- `{key}`: objeto com chaves: {', '.join(sorted(value.keys())) if value else 'n/d'}")
                else:
                    parts.append(f"- `{key}`: {type(value).__name__}")
        else:
            parts.append(f"- Tipo: {type(payload).__name__}")
        parts.append("")
    return "\n".join(parts)


def strip_tags(raw: str) -> str:
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw


def summarize_ui() -> str:
    template = ROOT / "app" / "templates" / "index.html"
    if not template.exists():
        return "# Telas e interface\n\nTemplate principal nao encontrado."
    text = safe_read(template)
    title_match = re.search(r"<title>(.*?)</title>", text, re.S)
    ids = sorted(set(re.findall(r'\bid="([^"]+)"', text)))
    headings = []
    for match in re.finditer(r"<h([1-3])[^>]*>(.*?)</h\1>", text, re.S):
        label = strip_tags(match.group(2))
        if label:
            headings.append((match.group(1), label[:140]))
    parts = [
        "# Telas e interface",
        "",
        f"- Titulo HTML: {strip_tags(title_match.group(1)) if title_match else 'n/d'}",
        f"- IDs/ancoras de tela: {len(ids)}",
        f"- Titulos H1-H3 encontrados: {len(headings)}",
        "",
        "## Principais titulos",
    ]
    for level, label in headings[:80]:
        parts.append(f"- H{level}: {label}")
    parts.extend(["", "## Principais IDs de tela"])
    for item in ids[:180]:
        parts.append(f"- `{item}`")
    if len(ids) > 180:
        parts.append(f"- ...mais {len(ids) - 180} IDs")
    return "\n".join(parts)


def write_routes_doc(routes: list[dict[str, str]]) -> str:
    parts = ["# Rotas Flask", "", f"Total de rotas encontradas: {len(routes)}", ""]
    parts.append("| Rota | Metodos | Funcao | Linha |")
    parts.append("| --- | --- | --- | --- |")
    for route in routes:
        parts.append(
            f"| `{route['route']}` | {route['methods']} | `{route['function']}` | {route['line']} |"
        )
    return "\n".join(parts)


def copy_sanitized_sources(target: Path) -> None:
    for source in sorted(ROOT.rglob("*")):
        if should_ignore(source) or not source.is_file():
            continue
        relative = rel(source)
        top = relative.split("/", 1)[0]
        if top not in SOURCE_DIRS and relative not in SOURCE_FILES:
            continue
        if source.suffix.lower() not in TEXT_SUFFIXES and relative not in SOURCE_FILES:
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(sanitize_text(safe_read(source)), encoding="utf-8")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")


def build_context(git_status: str, tests_output: str, tests_code: int) -> str:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""
# Contexto para ChatGPT - Sistema Geral SannyGold

Gerado em: {now}

## Como usar

1. Envie este ZIP para o ChatGPT.
2. Comece pelo arquivo `01_LEIA_PRIMEIRO.md`.
3. Depois peca: "Analise este sistema como produto e operacao. Me de melhorias priorizadas por impacto, facilidade e risco."

## O que este pacote contem

- Visao geral do produto e da operacao.
- Arvore de arquivos sem pastas pesadas ou sensiveis.
- Rotas Flask extraidas do codigo.
- Inventario tecnico de funcoes e classes principais.
- Resumo de telas, secoes e IDs do template principal.
- Modelo de dados resumido, sem dados reais de clientes.
- Codigo importante em `codigo-sanitizado/`, com e-mails, telefones, senhas e segredos mascarados.
- Estado atual dos testes.

## O que ficou fora de proposito

- `data/`: contem base operacional local e pode ter clientes, telefones, enderecos, valores e historico.
- `uploads/`: arquivos enviados/importados.
- `.git`, `.venv`, `.vercel`, `tmp/`, `output/`.
- `gestor-de-rota-empresa/`: copia/atalho legado detectado dentro do projeto, excluido para nao duplicar o sistema.

## Resumo do sistema

Sistema interno da SannyGold para organizar clientes, eventos, banheiros, equipamentos, frota, rotas, PDFs operacionais, almoxarifado, financeiro, acessos e memoria operacional.

Foco atual do produto:

- Operacao de banheiros moveis, banheiros quimicos, trailers de luxo, equipamentos de apoio e eventos.
- Uso interno por perfis admin, operacional, financeiro, leitura e visitante.
- Saida operacional em PDF/impresso e links de endereco.
- Historico por cliente, equipamento, evento, pendencias, financeiro e almoxarifado.

## Stack

- Python Flask.
- Templates Jinja/HTML em `app/templates/index.html`.
- Persistencia local em JSON na pasta `data/`.
- Testes com `unittest`.
- Deploy preparado por `render.yaml`, `vercel.json` e wrappers em `api/`.

## Estado Git no momento da exportacao

```text
{git_status or "Sem alteracoes reportadas por git status."}
```

## Testes executados durante a exportacao

Comando: `PYTHONPYCACHEPREFIX=/private/tmp/sannygold-pycache python3 -m unittest discover tests`

Codigo de saida: `{tests_code}`

```text
{tests_output or "Sem saida."}
```

## Pergunta pronta para colar no ChatGPT

```text
Analise o pacote do Sistema Geral SannyGold. Quero dicas praticas para melhorar organizacao, usabilidade, memoria operacional, financeiro, relatorios, seguranca, estabilidade e facilidade de uso da equipe. Priorize em uma tabela com: melhoria, motivo, impacto, dificuldade, risco e primeiro passo.
```
"""


def main() -> None:
    if PACK_DIR.exists():
        shutil.rmtree(PACK_DIR)
    PACK_DIR.mkdir(parents=True, exist_ok=True)

    git_code, git_status = run_command(["git", "status", "--short"], timeout=15)
    if git_code != 0:
        git_status = f"Erro ao consultar git status:\n{git_status}"
    else:
        git_status = filter_git_status(git_status)

    tests_code, tests_output = run_command(["python3", "-m", "unittest", "discover", "tests"], timeout=120)

    routes = extract_routes()
    write(PACK_DIR / "01_LEIA_PRIMEIRO.md", build_context(git_status, tests_output, tests_code))
    write(PACK_DIR / "02_ARVORE_DE_ARQUIVOS.txt", build_tree())
    write(PACK_DIR / "03_ROTAS_FLASK.md", write_routes_doc(routes))
    write(PACK_DIR / "04_INVENTARIO_TECNICO.md", extract_symbols())
    write(PACK_DIR / "05_MODELO_DE_DADOS_SEM_DADOS_REAIS.md", summarize_json_data())
    write(PACK_DIR / "06_TELAS_E_INTERFACE.md", summarize_ui())
    write(
        PACK_DIR / "07_PROMPT_PARA_CHATGPT.md",
        """
# Prompt para usar no ChatGPT

Analise este pacote do Sistema Geral SannyGold como se voce fosse consultor de produto, operacao e software.

Quero respostas praticas, nao genericas. Considere que o sistema e usado para operacao interna da SannyGold com clientes, eventos, banheiros, equipamentos, rotas, PDF/impresso, financeiro, almoxarifado e acessos.

Entregue:

1. Diagnostico geral.
2. Melhorias prioritarias por impacto.
3. Pontos de confusao na usabilidade.
4. Riscos tecnicos ou de seguranca.
5. Melhorias de memoria operacional.
6. Ideias de relatorios e dashboards.
7. Uma lista de proximas tarefas em ordem.

Para cada sugestao, diga: motivo, impacto, dificuldade, risco e primeiro passo.
""",
    )

    copy_sanitized_sources(PACK_DIR / "codigo-sanitizado")

    archive_base = EXPORT_ROOT / PACK_NAME
    zip_path = shutil.make_archive(str(archive_base), "zip", PACK_DIR)
    print(PACK_DIR)
    print(zip_path)


if __name__ == "__main__":
    main()
