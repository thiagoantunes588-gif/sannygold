#!/bin/bash
set -euo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="${LABEL:-com.sannygold.sistema.launchagent}"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
USER_ID="$(id -u)"

launchctl bootout "gui/${USER_ID}" "$PLIST_PATH" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"

echo "LaunchAgent removido, se existia:"
echo "$PLIST_PATH"
echo
echo "Os dados, backups e logs do sistema foram preservados em:"
echo "$BASE"
