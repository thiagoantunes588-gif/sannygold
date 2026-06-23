#!/bin/bash
set -euo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
export SANNYGOLD_WIFI=1
export FLASK_HOST="${FLASK_HOST:-0.0.0.0}"
export PORT="${PORT:-5007}"

"$BASE/scripts/start_local.sh"
