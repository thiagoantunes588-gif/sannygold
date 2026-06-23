#!/bin/bash
set -euo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="${LABEL:-com.sannygold.sistema.launchagent}"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${PLIST_DIR}/${LABEL}.plist"
ENV_FILE="${BASE}/.env.local"
PORT="${PORT:-5007}"
HOST="${FLASK_HOST:-0.0.0.0}"
USER_ID="$(id -u)"

mkdir -p "$PLIST_DIR" "$BASE/logs" "$BASE/data" "$BASE/backups" "$BASE/uploads" "$BASE/preview" "$BASE/tmp"

append_env_if_missing() {
  local key="$1"
  local value="$2"
  if [ ! -f "$ENV_FILE" ] || ! grep -q "^${key}=" "$ENV_FILE"; then
    printf "%s=%s\n" "$key" "$value" >> "$ENV_FILE"
  fi
}

touch "$ENV_FILE"
chmod 600 "$ENV_FILE"
append_env_if_missing "PORT" "$PORT"
append_env_if_missing "FLASK_HOST" "$HOST"

python3 - "$PLIST_PATH" "$BASE" "$LABEL" "$PORT" "$HOST" <<'PY'
from __future__ import annotations

import plistlib
import shlex
import sys
from pathlib import Path

plist_path = Path(sys.argv[1])
base = sys.argv[2]
label = sys.argv[3]
port = sys.argv[4]
host = sys.argv[5]
command = (
    f"cd {shlex.quote(base)} && "
    f"SANNYGOLD_WIFI=1 PORT={shlex.quote(port)} FLASK_HOST={shlex.quote(host)} "
    "bash scripts/start_local.sh"
)
payload = {
    "Label": label,
    "WorkingDirectory": base,
    "ProgramArguments": ["/bin/bash", "-lc", command],
    "RunAtLoad": True,
    "KeepAlive": False,
    "StandardOutPath": f"{base}/logs/launchagent.out.log",
    "StandardErrorPath": f"{base}/logs/launchagent.err.log",
    "EnvironmentVariables": {
        "SANNYGOLD_WIFI": "1",
        "PORT": port,
        "FLASK_HOST": host,
    },
}
with plist_path.open("wb") as handle:
    plistlib.dump(payload, handle, sort_keys=False)
PY

launchctl bootout "gui/${USER_ID}" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${USER_ID}" "$PLIST_PATH"
launchctl enable "gui/${USER_ID}/${LABEL}" >/dev/null 2>&1 || true

echo "LaunchAgent instalado e carregado:"
echo "$PLIST_PATH"
echo
echo "Ver status:"
echo "launchctl print gui/${USER_ID}/${LABEL}"
echo
echo "Logs:"
echo "$BASE/logs/launchagent.out.log"
echo "$BASE/logs/launchagent.err.log"
echo "$BASE/logs/backup.log"
