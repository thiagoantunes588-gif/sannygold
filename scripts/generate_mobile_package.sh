#!/bin/bash
set -euo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
PREVIEW_DIR="$BASE/preview"

python3 "$BASE/scripts/plan_routes.py" \
  --deliveries "$BASE/assets/templates/deliveries.csv" \
  --vehicles "$BASE/assets/templates/vehicles.csv" \
  --output "$PREVIEW_DIR/route-plan-mobile.json" \
  --mobile \
  --pdf-output "$PREVIEW_DIR/route-plan.pdf" \
  --html-output "$PREVIEW_DIR/route-app.html"

echo "Pacote mobile interno atualizado em:"
echo "  $PREVIEW_DIR/index.html"
echo "  $PREVIEW_DIR/route-app.html"
echo "  $PREVIEW_DIR/route-plan.pdf"
echo "  $PREVIEW_DIR/route-plan-mobile.json"
