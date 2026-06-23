#!/bin/bash
set -euo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="${APP_NAME:-SannyGold Sistema.app}"
APP_DIR="${APP_DIR:-$HOME/Applications}"
APP_PATH="$APP_DIR/$APP_NAME"
APP_IDENTIFIER="${APP_IDENTIFIER:-com.sannygold.sistema.local}"
DROPBOX_SYSTEM_ROOT="${DROPBOX_SYSTEM_ROOT:-$HOME/Dropbox/Sistema SannyGold}"
DROPBOX_INSTALLERS_DIR="$DROPBOX_SYSTEM_ROOT/Instaladores"
MAC_ROOT_DIR="$DROPBOX_INSTALLERS_DIR/Mac"
MAC_INSTALLERS_DIR="$MAC_ROOT_DIR/Instalador"
MAC_ZIP_PATH="$MAC_INSTALLERS_DIR/SannyGold-Sistema-Mac.zip"
ORGANIZER_SCRIPT="$BASE/scripts/organize_dropbox_installers.sh"
TMP_SCRIPT="$(mktemp -t sannygold-launcher.XXXXXX.applescript)"

mkdir -p "$APP_DIR"
mkdir -p "$BASE/logs"

cat > "$TMP_SCRIPT" <<APPLESCRIPT
on run
  set projectPath to "$BASE"
  do shell script "cd " & quoted form of projectPath & "; mkdir -p logs data backups uploads preview tmp; nohup /usr/bin/env python3 scripts/sannygold_launcher.py >> logs/macos-launcher.log 2>&1 &"
end run
APPLESCRIPT

rm -rf "$APP_PATH"
osacompile -o "$APP_PATH" "$TMP_SCRIPT"
rm -f "$TMP_SCRIPT"

/usr/libexec/PlistBuddy -c "Set :CFBundleName SannyGold Sistema" "$APP_PATH/Contents/Info.plist" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName SannyGold Sistema" "$APP_PATH/Contents/Info.plist" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $APP_IDENTIFIER" "$APP_PATH/Contents/Info.plist" >/dev/null 2>&1 || true

echo "Launcher criado em: $APP_PATH"
echo "Log do app: $BASE/logs/macos-launcher.log"
echo "Log do launcher: $BASE/logs/launcher.log"
echo "Icone: usando o icone padrao de aplicativo AppleScript como placeholder."

if [ -d "$DROPBOX_SYSTEM_ROOT" ]; then
  bash "$ORGANIZER_SCRIPT" "$DROPBOX_SYSTEM_ROOT"
  mkdir -p "$MAC_INSTALLERS_DIR"
  rm -rf "$MAC_INSTALLERS_DIR/$APP_NAME"
  ditto "$APP_PATH" "$MAC_INSTALLERS_DIR/$APP_NAME"
  rm -f "$MAC_ZIP_PATH"
  ditto -c -k --keepParent "$APP_PATH" "$MAC_ZIP_PATH"
  echo "Instalador Mac publicado em: $MAC_INSTALLERS_DIR/$APP_NAME"
  echo "Zip Mac publicado em: $MAC_ZIP_PATH"
else
  echo "Dropbox nao encontrado em: $DROPBOX_SYSTEM_ROOT"
  echo "O app foi criado localmente, mas nao foi publicado na pasta de instaladores."
fi
