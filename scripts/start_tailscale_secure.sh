#!/bin/bash
set -euo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-5007}"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "Tailscale não foi encontrado. Instale o Tailscale no Mac e faça login antes de usar este script."
  echo "Guia: https://tailscale.com/kb/1016/install-mac"
  exit 1
fi

if ! tailscale status >/dev/null 2>&1; then
  echo "Tailscale não está conectado. Abra o Tailscale, faça login e tente novamente."
  exit 1
fi

TAILSCALE_IP="$(tailscale ip -4 2>/dev/null | head -n 1 || true)"
if [ -z "$TAILSCALE_IP" ]; then
  echo "Não foi possível descobrir o IP Tailscale. Rode: tailscale ip -4"
  exit 1
fi

TAILSCALE_URL="http://$TAILSCALE_IP:$PORT/"

echo "Iniciando SannyGold para acesso privado via Tailscale."
echo "Endereço no computador: http://127.0.0.1:$PORT/"
echo "Endereço no celular autorizado pelo Tailscale: $TAILSCALE_URL"
echo "Nenhuma porta pública será aberta. Não use tailscale funnel para este sistema."
echo "Mantenha esta janela aberta enquanto usa o sistema local."

cd "$BASE"
SANNYGOLD_TAILSCALE_URL="$TAILSCALE_URL" SANNYGOLD_WIFI=1 FLASK_HOST=0.0.0.0 PORT="$PORT" bash scripts/start_local.sh
