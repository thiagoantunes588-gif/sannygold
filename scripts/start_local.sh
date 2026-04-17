#!/bin/bash
set -euo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-5007}"
HOST="${FLASK_HOST:-127.0.0.1}"
VENV="$BASE/.venv"

cd "$BASE"

mkdir -p data uploads preview tmp

if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

python3 -m pip install -r requirements.txt

echo "Sistema SannyGold iniciado em: http://$HOST:$PORT"
echo "Pressione Ctrl+C para encerrar."

PORT="$PORT" FLASK_HOST="$HOST" python3 -m app.main
