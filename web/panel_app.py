#!/usr/bin/env python3
"""Painel web local para gerar rotas a partir de CSVs."""

from __future__ import annotations

import argparse
import cgi
import csv
import html
import importlib.util
import json
import shutil
import sys
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote


BASE_DIR = Path(__file__).resolve().parents[1]
RUNS_DIR = BASE_DIR / "tmp" / "panel_runs"
DATA_DIR = BASE_DIR / "data"
CLIENTS_PATH = DATA_DIR / "clients.json"
PLANNER_PATH = BASE_DIR / "scripts" / "plan_routes.py"
DELIVERIES_TEMPLATE = BASE_DIR / "assets" / "templates" / "deliveries.csv"
VEHICLES_TEMPLATE = BASE_DIR / "assets" / "templates" / "vehicles.csv"


def load_planner_module():
    spec = importlib.util.spec_from_file_location("plan_routes", PLANNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load planner module from {PLANNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PLANNER = load_planner_module()


def ensure_runs_dir() -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CLIENTS_PATH.exists():
        CLIENTS_PATH.write_text("[]\n", encoding="utf-8")


def text_value(field_storage, name: str, default: str = "") -> str:
    value = field_storage.getvalue(name)
    if value is None:
        return default
    return str(value).strip()


def load_clients() -> list[dict]:
    if not CLIENTS_PATH.exists():
        return []
    data = json.loads(CLIENTS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Cadastro de clientes invalido.")
    return data


def save_clients(clients: list[dict]) -> None:
    CLIENTS_PATH.write_text(json.dumps(clients, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def create_client_record(form) -> dict:
    client_id = text_value(form, "client_id")
    customer_name = text_value(form, "customer_name")
    address = text_value(form, "client_address")
    lat = text_value(form, "client_lat")
    lng = text_value(form, "client_lng")

    if not client_id:
        raise ValueError("Informe o ID do cliente.")
    if not customer_name:
        raise ValueError("Informe o nome do cliente.")
    if not address:
        raise ValueError("Informe o endereco do cliente.")
    if not lat or not lng:
        raise ValueError("Informe latitude e longitude do cliente.")

    lat_value = float(lat)
    lng_value = float(lng)
    default_service_minutes = int(text_value(form, "default_service_minutes", "20"))
    default_priority = int(text_value(form, "default_priority", "3"))

    if default_service_minutes <= 0:
        raise ValueError("Tempo padrao de atendimento deve ser maior que zero.")
    if default_priority <= 0:
        raise ValueError("Prioridade padrao deve ser maior que zero.")

    return {
        "client_id": client_id,
        "customer_name": customer_name,
        "address": address,
        "lat": lat_value,
        "lng": lng_value,
        "equipment_number": text_value(form, "equipment_number"),
        "default_service_minutes": default_service_minutes,
        "default_priority": default_priority,
    }


def upsert_client(record: dict) -> None:
    clients = load_clients()
    by_id = {client["client_id"]: client for client in clients}
    by_id[record["client_id"]] = record
    ordered = sorted(by_id.values(), key=lambda item: item["customer_name"].lower())
    save_clients(ordered)


def build_clients_csv() -> str:
    clients = load_clients()
    fieldnames = [
        "client_id",
        "customer_name",
        "address",
        "lat",
        "lng",
        "equipment_number",
        "default_service_minutes",
        "default_priority",
    ]
    rows = [",".join(fieldnames)]
    for client in clients:
        values = []
        for field in fieldnames:
            raw = str(client.get(field, ""))
            escaped = '"' + raw.replace('"', '""') + '"' if "," in raw or '"' in raw else raw
            values.append(escaped)
        rows.append(",".join(values))
    return "\n".join(rows) + "\n"


def save_uploaded_file(field_storage, name: str, destination: Path) -> Path:
    item = field_storage[name]
    if not getattr(item, "file", None):
        raise ValueError(f"Arquivo ausente: {name}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output_file:
        shutil.copyfileobj(item.file, output_file)
    return destination


def build_route_plan(deliveries_path: Path, vehicles_path: Path, speed_kmph: float, mobile_output: bool) -> dict:
    deliveries = PLANNER.load_deliveries(deliveries_path)
    vehicles = PLANNER.load_vehicles(vehicles_path)
    routes, unassigned = PLANNER.build_routes(deliveries, vehicles, speed_kmph)
    payload = PLANNER.serialize(routes, unassigned, vehicles)
    if mobile_output:
        payload = PLANNER.serialize_mobile(payload)
    return payload


def run_planner(run_id: str, deliveries_path: Path, vehicles_path: Path, speed_kmph: float, mobile_output: bool) -> dict:
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    payload = build_route_plan(deliveries_path, vehicles_path, speed_kmph, mobile_output)

    json_path = run_dir / "route-plan.json"
    pdf_path = run_dir / "route-plan.pdf"
    html_path = run_dir / "route-plan.html"

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    PLANNER.write_simple_pdf(PLANNER.build_pdf_lines(payload), pdf_path)
    PLANNER.write_standalone_html(payload, html_path)

    return {
        "run_id": run_id,
        "run_dir": run_dir,
        "payload": payload,
        "json_path": json_path,
        "pdf_path": pdf_path,
        "html_path": html_path,
    }


def page_template(title: str, body: str) -> bytes:
    markup = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg: #f3efe7;
      --panel: rgba(255, 251, 244, 0.94);
      --panel-strong: #fffaf0;
      --ink: #17211f;
      --muted: #61706b;
      --line: rgba(23, 33, 31, 0.08);
      --accent: #d95d39;
      --accent-dark: #ad4324;
      --green: #2f7a5f;
      --green-soft: #dcefe4;
      --shadow: 0 28px 60px rgba(26, 38, 34, 0.14);
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(217, 93, 57, 0.18), transparent 28%),
        radial-gradient(circle at bottom right, rgba(47, 122, 95, 0.16), transparent 22%),
        linear-gradient(145deg, #efe9df 0%, #f8f5ef 44%, #ece6dc 100%);
      min-height: 100vh;
      padding: 28px;
    }}
    .shell {{
      width: min(1160px, 100%);
      margin: 0 auto;
      display: grid;
      gap: 24px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 30px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
      padding: 28px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 24px;
      align-items: start;
    }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 14px;
      border-radius: 999px;
      background: rgba(255, 250, 240, 0.86);
      border: 1px solid var(--line);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 12px;
      font-weight: 700;
      color: var(--muted);
    }}
    h1 {{
      margin: 18px 0 12px;
      font-size: clamp(40px, 5vw, 62px);
      line-height: 0.95;
      letter-spacing: -0.04em;
      max-width: 11ch;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 28px;
      letter-spacing: -0.03em;
    }}
    h3 {{
      margin: 0 0 8px;
      font-size: 18px;
      letter-spacing: -0.02em;
    }}
    p {{
      margin: 0 0 16px;
      color: var(--muted);
      line-height: 1.6;
    }}
    .chips, .stats, .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .chip, .stat, .card, .preview, .upload-box {{
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
    }}
    .chip {{
      padding: 12px 16px;
      font-size: 14px;
    }}
    .stats {{
      margin-top: 22px;
    }}
    .stat {{
      min-width: 160px;
      padding: 18px;
    }}
    .stat strong {{
      display: block;
      font-size: 28px;
      margin-bottom: 6px;
      letter-spacing: -0.04em;
    }}
    .upload-form {{
      display: grid;
      gap: 14px;
    }}
    .upload-box {{
      padding: 16px;
    }}
    label {{
      display: block;
      margin-bottom: 8px;
      font-size: 14px;
      font-weight: 700;
    }}
    input[type="file"],
    input[type="text"],
    input[type="number"] {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px 14px;
      background: #ffffff;
      color: var(--ink);
      font: inherit;
    }}
    .checkbox-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 14px;
      color: var(--muted);
    }}
    .checkbox-row input {{
      width: 18px;
      height: 18px;
    }}
    button,
    .button-link {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 0;
      border-radius: 999px;
      padding: 14px 18px;
      font: inherit;
      font-weight: 700;
      text-decoration: none;
      cursor: pointer;
      transition: transform 160ms ease, opacity 160ms ease;
    }}
    button:hover,
    .button-link:hover {{
      transform: translateY(-1px);
      opacity: 0.96;
    }}
    .primary {{
      background: linear-gradient(180deg, var(--accent) 0%, var(--accent-dark) 100%);
      color: #fff9f3;
    }}
    .secondary {{
      background: #ffffff;
      color: var(--ink);
      border: 1px solid var(--line);
    }}
    .preview {{
      padding: 20px;
    }}
    .preview-list {{
      display: grid;
      gap: 10px;
      margin-top: 14px;
    }}
    .route-row {{
      display: grid;
      grid-template-columns: 42px 1fr auto;
      gap: 12px;
      align-items: center;
      padding: 14px;
      border-radius: 20px;
      background: #fffdf8;
      border: 1px solid var(--line);
    }}
    .route-index {{
      width: 42px;
      height: 42px;
      border-radius: 14px;
      display: grid;
      place-items: center;
      background: rgba(23, 33, 31, 0.06);
      font-weight: 800;
    }}
    .route-meta strong {{
      display: block;
      margin-bottom: 4px;
    }}
    .route-meta span {{
      font-size: 13px;
      color: var(--muted);
    }}
    .eta {{
      color: var(--green);
      font-size: 13px;
      font-weight: 700;
    }}
    .inline-code {{
      font-family: "SFMono-Regular", Consolas, monospace;
      background: rgba(23, 33, 31, 0.06);
      border-radius: 10px;
      padding: 2px 6px;
    }}
    .notice {{
      padding: 16px;
      border-radius: 20px;
      background: #fff5ef;
      border: 1px solid rgba(217, 93, 57, 0.16);
      color: #8f4b35;
    }}
    .success {{
      padding: 16px;
      border-radius: 20px;
      background: var(--green-soft);
      color: var(--green);
      font-weight: 700;
    }}
    ul {{
      margin: 12px 0 0;
      padding-left: 18px;
      color: var(--muted);
    }}
    @media (max-width: 980px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    {body}
  </main>
</body>
</html>"""
    return markup.encode("utf-8")


def form_page(plan_message: str = "", client_message: str = "", client_message_kind: str = "success") -> bytes:
    clients = load_clients()
    plan_message_markup = f'<div class="notice">{html.escape(plan_message)}</div>' if plan_message else ""
    client_class = "success" if client_message_kind == "success" else "notice"
    client_message_markup = f'<div class="{client_class}">{html.escape(client_message)}</div>' if client_message else ""
    client_rows = []

    for client in clients[:8]:
        client_rows.append(
            f"""
            <div class="route-row">
              <div class="route-index">{html.escape(client.get("client_id", "?")[:2].upper())}</div>
              <div class="route-meta">
                <strong>{html.escape(client.get("customer_name") or "Sem nome")}</strong>
                <span>{html.escape(client.get("address") or "Sem endereco")}</span>
              </div>
              <div class="eta">P{html.escape(str(client.get("default_priority", 3)))}</div>
            </div>
            """
        )

    if not client_rows:
        client_rows.append(
            """
            <div class="route-row">
              <div class="route-index">0</div>
              <div class="route-meta">
                <strong>Nenhum cliente cadastrado</strong>
                <span>Crie sua base para facilitar a operacao diaria.</span>
              </div>
              <div class="eta">-</div>
            </div>
            """
        )

    body = f"""
    <section class="panel grid">
      <div>
        <div class="eyebrow">Painel Local de Roteirizacao</div>
        <h1>Suba os CSVs e gere a rota em um clique.</h1>
        <p>Este painel roda localmente no seu computador e reaproveita o planejador existente do projeto. Ele gera tres saidas: JSON para integracao, HTML para visualizacao e PDF para operacao.</p>
        <div class="chips">
          <div class="chip">Upload de deliveries.csv e vehicles.csv</div>
          <div class="chip">Saida automatica em JSON, HTML e PDF</div>
          <div class="chip">Preview rapida da rota principal</div>
        </div>
        <div class="stats">
          <div class="stat">
            <strong>1</strong>
            <span>acao para gerar rota</span>
          </div>
          <div class="stat">
            <strong>3</strong>
            <span>formatos de saida</span>
          </div>
          <div class="stat">
            <strong>100%</strong>
            <span>local, sem dependencia web</span>
          </div>
        </div>
      </div>

      <div class="panel" style="padding:22px;">
        <h2>Novo planejamento</h2>
        <p>Use seus arquivos reais ou teste com os modelos prontos do projeto.</p>
        {plan_message_markup}
        <form class="upload-form" method="post" action="/plan" enctype="multipart/form-data">
          <div class="upload-box">
            <label for="deliveries">deliveries.csv</label>
            <input id="deliveries" name="deliveries" type="file" accept=".csv,text/csv" required>
          </div>
          <div class="upload-box">
            <label for="vehicles">vehicles.csv</label>
            <input id="vehicles" name="vehicles" type="file" accept=".csv,text/csv" required>
          </div>
          <div class="upload-box">
            <label for="speed_kmph">Velocidade media urbana (km/h)</label>
            <input id="speed_kmph" name="speed_kmph" type="number" min="1" step="0.5" value="35">
          </div>
          <label class="checkbox-row" for="mobile_output">
            <input id="mobile_output" name="mobile_output" type="checkbox" value="1" checked>
            Gerar JSON compacto com foco mobile
          </label>
          <button class="primary" type="submit">Gerar rota agora</button>
        </form>
      </div>
    </section>

    <section class="panel grid">
      <div class="preview">
        <h2>Cadastro de clientes</h2>
        <p>Salve os principais pontos de atendimento para montar uma base operacional local.</p>
        {client_message_markup}
        <form class="upload-form" method="post" action="/clients">
          <div class="upload-box">
            <label for="client_id">ID do cliente</label>
            <input id="client_id" name="client_id" type="text" placeholder="CLI-001" required>
          </div>
          <div class="upload-box">
            <label for="customer_name">Nome do cliente</label>
            <input id="customer_name" name="customer_name" type="text" placeholder="Farmacia Central" required>
          </div>
          <div class="upload-box">
            <label for="client_address">Endereco</label>
            <input id="client_address" name="client_address" type="text" placeholder="Av. Paulista, 1400" required>
          </div>
          <div class="grid" style="grid-template-columns:repeat(2, 1fr);gap:14px;">
            <div class="upload-box">
              <label for="client_lat">Latitude</label>
              <input id="client_lat" name="client_lat" type="number" step="any" placeholder="-23.5614" required>
            </div>
            <div class="upload-box">
              <label for="client_lng">Longitude</label>
              <input id="client_lng" name="client_lng" type="number" step="any" placeholder="-46.6559" required>
            </div>
          </div>
          <div class="grid" style="grid-template-columns:repeat(3, 1fr);gap:14px;">
            <div class="upload-box">
              <label for="equipment_number">Equipamento</label>
              <input id="equipment_number" name="equipment_number" type="text" placeholder="EQ-198">
            </div>
            <div class="upload-box">
              <label for="default_service_minutes">Servico padrao (min)</label>
              <input id="default_service_minutes" name="default_service_minutes" type="number" min="1" value="20">
            </div>
            <div class="upload-box">
              <label for="default_priority">Prioridade padrao</label>
              <input id="default_priority" name="default_priority" type="number" min="1" value="3">
            </div>
          </div>
          <button class="primary" type="submit">Salvar cliente</button>
        </form>
      </div>

      <div class="preview">
        <h2>Base de clientes</h2>
        <p>Os clientes ficam salvos em <span class="inline-code">{html.escape(str(CLIENTS_PATH))}</span>.</p>
        <div class="actions">
          <a class="button-link secondary" href="/clients/export.csv">Exportar cadastro CSV</a>
        </div>
        <div class="preview-list" style="margin-top:16px;">
          {''.join(client_rows)}
        </div>
      </div>

    </section>

    <section class="panel grid">
      <div class="preview">
        <h2>Como usar na pratica</h2>
        <ul>
          <li>Cadastre seus clientes mais recorrentes para formar a base da operacao.</li>
          <li>Baixe ou prepare os CSVs seguindo o contrato de dados.</li>
          <li>Suba os dois arquivos acima e clique em gerar.</li>
          <li>Abra o HTML para validar visualmente e entregue o JSON ao app ou painel interno.</li>
        </ul>
      </div>
      <div class="preview">
        <h2>Arquivos modelo</h2>
        <p>Esses links servem para testar o painel em poucos minutos.</p>
        <div class="actions">
          <a class="button-link secondary" href="/templates/deliveries.csv">deliveries.csv</a>
          <a class="button-link secondary" href="/templates/vehicles.csv">vehicles.csv</a>
        </div>
        <p style="margin-top:16px;">Servidor: <span class="inline-code">python3 web/panel_app.py --port 8010</span></p>
      </div>
    </section>
    """
    return page_template("Gestor de Rota - Painel", body)


def result_page(run: dict) -> bytes:
    payload = run["payload"]
    routes = payload.get("routes") or []
    summary = payload.get("summary") or {}
    primary_route = routes[0] if routes else {}
    next_stop = primary_route.get("next_stop") or (primary_route.get("stops") or [{}])[0]
    route_rows = []

    for index, stop in enumerate((primary_route.get("stops") or [])[:6], start=1):
        route_rows.append(
            f"""
            <div class="route-row">
              <div class="route-index">{index}</div>
              <div class="route-meta">
                <strong>{html.escape(stop.get("customer_name") or "Sem cliente")}</strong>
                <span>{html.escape(stop.get("address") or "Sem endereco")}</span>
              </div>
              <div class="eta">{html.escape(stop.get("arrival") or "--:--")}</div>
            </div>
            """
        )

    if not route_rows:
        route_rows.append(
            """
            <div class="route-row">
              <div class="route-index">0</div>
              <div class="route-meta">
                <strong>Nenhuma parada atribuida</strong>
                <span>Revise janelas, capacidade ou frota.</span>
              </div>
              <div class="eta">-</div>
            </div>
            """
        )

    run_id = run["run_id"]
    body = f"""
    <section class="panel">
      <div class="success">Rota gerada com sucesso. Os arquivos desta execucao ficam salvos em <span class="inline-code">{html.escape(str(run['run_dir']))}</span>.</div>
    </section>

    <section class="panel grid">
      <div>
        <div class="eyebrow">Resultado Pronto</div>
        <h1>Planejamento gerado e pronto para operar.</h1>
        <p>Aqui esta a primeira leitura da execucao. Voce pode baixar os arquivos finais ou validar rapidamente a rota principal na lateral.</p>
        <div class="stats">
          <div class="stat">
            <strong>{summary.get("assigned_deliveries", 0)}/{summary.get("total_deliveries", 0)}</strong>
            <span>paradas atribuidas</span>
          </div>
          <div class="stat">
            <strong>{round(float(summary.get("assigned_ratio", 0)) * 100)}%</strong>
            <span>roteirizacao concluida</span>
          </div>
          <div class="stat">
            <strong>{summary.get("total_distance_km", 0)} km</strong>
            <span>distancia total</span>
          </div>
        </div>
        <div class="actions" style="margin-top:20px;">
          <a class="button-link primary" href="/runs/{quote(run_id)}/route-plan.html" target="_blank" rel="noreferrer">Abrir HTML</a>
          <a class="button-link secondary" href="/runs/{quote(run_id)}/route-plan.pdf" target="_blank" rel="noreferrer">Baixar PDF</a>
          <a class="button-link secondary" href="/runs/{quote(run_id)}/route-plan.json" target="_blank" rel="noreferrer">Abrir JSON</a>
          <a class="button-link secondary" href="/">Novo planejamento</a>
        </div>
      </div>

      <div class="preview">
        <h2>Preview da rota principal</h2>
        <p>Veiculo: <span class="inline-code">{html.escape(primary_route.get("vehicle_id") or "--")}</span></p>
        <div class="preview-list">
          <div class="route-row">
            <div class="route-index">1</div>
            <div class="route-meta">
              <strong>{html.escape(next_stop.get("customer_name") or "Sem cliente")}</strong>
              <span>{html.escape(next_stop.get("address") or "Sem endereco")}</span>
            </div>
            <div class="eta">{html.escape(next_stop.get("arrival") or "--:--")}</div>
          </div>
          {''.join(route_rows)}
        </div>
      </div>
    </section>
    """
    return page_template("Gestor de Rota - Resultado", body)


class PanelHandler(BaseHTTPRequestHandler):
    server_version = "GestorRotaPanel/1.0"

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self.respond_html(form_page())
            return
        if path == "/health":
            self.respond_text("ok\n")
            return
        if path == "/clients/export.csv":
            self.respond_text(build_clients_csv(), content_type="text/csv; charset=utf-8")
            return
        if path.startswith("/templates/"):
            self.serve_template(path)
            return
        if path.startswith("/runs/"):
            self.serve_run_file(path)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Pagina nao encontrada")

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path not in {"/plan", "/clients"}:
            self.send_error(HTTPStatus.NOT_FOUND, "Pagina nao encontrada")
            return

        try:
            ctype, _ = cgi.parse_header(self.headers.get("content-type", ""))
            field_storage = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": self.headers.get("content-type", ""),
                },
            )

            if path == "/plan":
                if ctype != "multipart/form-data":
                    raise ValueError("Envie os arquivos usando multipart/form-data.")

                run_id = uuid.uuid4().hex[:12]
                run_dir = RUNS_DIR / run_id
                input_dir = run_dir / "inputs"
                deliveries_path = save_uploaded_file(field_storage, "deliveries", input_dir / "deliveries.csv")
                vehicles_path = save_uploaded_file(field_storage, "vehicles", input_dir / "vehicles.csv")

                speed_kmph = float(text_value(field_storage, "speed_kmph", "35"))
                mobile_output = bool(text_value(field_storage, "mobile_output", ""))
                run = run_planner(run_id, deliveries_path, vehicles_path, speed_kmph, mobile_output)
                self.respond_html(result_page(run))
                return

            record = create_client_record(field_storage)
            upsert_client(record)
            self.respond_html(form_page(client_message=f"Cliente {record['customer_name']} salvo com sucesso."))
        except Exception as exc:  # noqa: BLE001
            self.respond_html(
                form_page(
                    plan_message=str(exc) if path == "/plan" else "",
                    client_message="" if path == "/plan" else str(exc),
                    client_message_kind="error",
                ),
                status=HTTPStatus.BAD_REQUEST,
            )

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    def serve_template(self, path: str) -> None:
        name = path.rsplit("/", 1)[-1]
        template_map = {
            "deliveries.csv": DELIVERIES_TEMPLATE,
            "vehicles.csv": VEHICLES_TEMPLATE,
        }
        file_path = template_map.get(name)
        if not file_path or not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Template nao encontrado")
            return
        self.serve_file(file_path, "text/csv; charset=utf-8")

    def serve_run_file(self, path: str) -> None:
        parts = [part for part in path.split("/") if part]
        if len(parts) != 3:
            self.send_error(HTTPStatus.NOT_FOUND, "Arquivo nao encontrado")
            return

        _, run_id, filename = parts
        target = (RUNS_DIR / run_id / filename).resolve()
        runs_root = RUNS_DIR.resolve()

        if not str(target).startswith(str(runs_root)) or not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Arquivo nao encontrado")
            return

        if filename.endswith(".json"):
            content_type = "application/json; charset=utf-8"
        elif filename.endswith(".html"):
            content_type = "text/html; charset=utf-8"
        elif filename.endswith(".pdf"):
            content_type = "application/pdf"
        else:
            content_type = "application/octet-stream"
        self.serve_file(target, content_type)

    def serve_file(self, path: Path, content_type: str) -> None:
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def respond_html(self, content: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def respond_text(self, content: str, status: HTTPStatus = HTTPStatus.OK, content_type: str = "text/plain; charset=utf-8") -> None:
        data = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local route planning panel.")
    parser.add_argument("--host", default="127.0.0.1", help="Host for local server")
    parser.add_argument("--port", default=8010, type=int, help="Port for local server")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_runs_dir()
    server = ThreadingHTTPServer((args.host, args.port), PanelHandler)
    print(f"Painel disponivel em http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
