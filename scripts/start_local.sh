#!/bin/bash
set -euo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-5007}"
VENV="$BASE/.venv"
ENV_FILE="$BASE/.env.local"
DEFAULT_DROPBOX_BACKUP_DIR="${HOME}/Dropbox/Sistema SannyGold/Backups"

cd "$BASE"

mkdir -p data uploads preview tmp logs backups

shell_escape() {
  printf "%q" "$1"
}

if [ ! -f "$ENV_FILE" ]; then
  SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  {
    echo "SANNYGOLD_ENV=local"
    echo "SANNYGOLD_SECRET_KEY=$SECRET_KEY"
    echo "SANNYGOLD_ADMIN_EMAIL=contato@sannygold.com"
    echo "SANNYGOLD_ADMIN_PASSWORD=$(shell_escape "troque-esta-senha")"
    echo "SANNYGOLD_ADMIN_NAME=$(shell_escape "Administrador SannyGold")"
    echo "ROTAFLOW_STORAGE_DIR=$(shell_escape "$BASE")"
    echo "SANNYGOLD_SQLITE_PATH=$(shell_escape "$BASE/data/sannygold.db")"
    echo "SANNYGOLD_STORAGE_BACKEND=sqlite"
    echo "SANNYGOLD_SQLITE_MIRROR_JSON=1"
    echo "DROPBOX_BACKUP_DIR=$(shell_escape "$DEFAULT_DROPBOX_BACKUP_DIR")"
    echo "SANNYGOLD_BACKUP_RETENTION_LIMIT=30"
    echo "SANNYGOLD_DROPBOX_BACKUP_RETENTION_LIMIT=30"
    echo "PORT=$(shell_escape "$PORT")"
    echo "FLASK_HOST=$(shell_escape "${FLASK_HOST:-0.0.0.0}")"
    echo "FLASK_DEBUG=0"
    echo "SANNYGOLD_SESSION_COOKIE_SECURE=0"
    echo "SANNYGOLD_CSRF_DISABLED=0"
  } > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export ROTAFLOW_STORAGE_DIR="${ROTAFLOW_STORAGE_DIR:-$BASE}"
export SANNYGOLD_SQLITE_PATH="${SANNYGOLD_SQLITE_PATH:-$BASE/data/sannygold.db}"
export SANNYGOLD_STORAGE_BACKEND="${SANNYGOLD_STORAGE_BACKEND:-sqlite}"
export SANNYGOLD_SQLITE_MIRROR_JSON="${SANNYGOLD_SQLITE_MIRROR_JSON:-1}"
export DROPBOX_BACKUP_DIR="${DROPBOX_BACKUP_DIR:-${SANNYGOLD_BACKUP_COPY_DIR:-$DEFAULT_DROPBOX_BACKUP_DIR}}"
export FLASK_DEBUG="${FLASK_DEBUG:-0}"
export PORT="${PORT:-5007}"

if [ "${SANNYGOLD_WIFI:-0}" = "1" ]; then
  HOST="${FLASK_HOST:-0.0.0.0}"
else
  HOST="${FLASK_HOST:-127.0.0.1}"
fi
export FLASK_HOST="$HOST"

resolve_path_for_check() {
  python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve(strict=False))' "$1"
}

path_is_inside_or_same() {
  local child="${1%/}"
  local parent="${2%/}"
  case "$child" in
    "$parent"|"$parent"/*) return 0 ;;
    *) return 1 ;;
  esac
}

assert_not_inside_dropbox() {
  local label="$1"
  local path="$2"
  local resolved_path
  resolved_path="$(resolve_path_for_check "$path")"
  if path_is_inside_or_same "$resolved_path" "$DROPBOX_ROOT"; then
    echo "Configuração insegura: $label não pode ficar dentro do Dropbox." >&2
    echo "Use o banco ativo em data/ e copie apenas backups .zip para DROPBOX_BACKUP_DIR." >&2
    exit 1
  fi
}

DROPBOX_ROOT="$(resolve_path_for_check "${HOME}/Dropbox")"
STORAGE_ROOT_FOR_CHECK="$(resolve_path_for_check "$ROTAFLOW_STORAGE_DIR")"
assert_not_inside_dropbox "a pasta inteira do sistema" "$BASE"
assert_not_inside_dropbox "ROTAFLOW_STORAGE_DIR" "$ROTAFLOW_STORAGE_DIR"
assert_not_inside_dropbox "data/" "$STORAGE_ROOT_FOR_CHECK/data"
assert_not_inside_dropbox "uploads/" "$STORAGE_ROOT_FOR_CHECK/uploads"
assert_not_inside_dropbox "SANNYGOLD_SQLITE_PATH" "$SANNYGOLD_SQLITE_PATH"

DROPBOX_BACKUP_PARENT="$(dirname "$DROPBOX_BACKUP_DIR")"
if [ -d "${HOME}/Dropbox" ] && path_is_inside_or_same "$(resolve_path_for_check "$DROPBOX_BACKUP_PARENT")" "$DROPBOX_ROOT"; then
  mkdir -p "$DROPBOX_BACKUP_DIR"
fi

if [ "${SANNYGOLD_START_LOCAL_SETUP_ONLY:-0}" = "1" ]; then
  exit 0
fi

if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

REQ_HASH="$(shasum -a 256 requirements.txt | awk '{print $1}')"
STAMP_FILE="$VENV/.requirements.sha256"
if [ ! -f "$STAMP_FILE" ] || [ "$(cat "$STAMP_FILE")" != "$REQ_HASH" ]; then
  python3 -m pip install -r requirements.txt
  echo "$REQ_HASH" > "$STAMP_FILE"
fi

python3 scripts/create_local_backup.py --trigger inicializacao_local --if-older-hours 24 || true
python3 scripts/migrate_json_to_sqlite.py --data-dir "$BASE/data" --db "$SANNYGOLD_SQLITE_PATH" || true

LOCAL_URL="http://127.0.0.1:$PORT"
LAN_IP="$(python3 - <<'PY'
import socket
try:
    candidates = socket.gethostbyname_ex(socket.gethostname())[2]
except OSError:
    candidates = []
for candidate in candidates:
    if candidate and not candidate.startswith("127."):
        print(candidate)
        raise SystemExit
try:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("10.255.255.255", 1))
        print(probe.getsockname()[0])
except OSError:
    print("127.0.0.1")
PY
)"
WIFI_URL="http://$LAN_IP:$PORT"

echo "Sistema SannyGold iniciado em: $LOCAL_URL"
if [ "$HOST" = "0.0.0.0" ]; then
  echo "Acesso no celular pelo Wi-Fi: $WIFI_URL"
fi
echo "Pressione Ctrl+C para encerrar."

PORT="$PORT" FLASK_HOST="$HOST" python3 -m waitress --host="$HOST" --port="$PORT" app.main:app
