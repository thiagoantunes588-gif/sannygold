#!/bin/bash
set -euo pipefail

BASE="$(cd "$(dirname "$0")/.." && pwd)"
DROPBOX_SYSTEM_ROOT="${1:-${DROPBOX_SYSTEM_ROOT:-$HOME/Dropbox/Sistema SannyGold}}"
INSTALLERS_DIR="$DROPBOX_SYSTEM_ROOT/Instaladores"
MAC_DIR="$INSTALLERS_DIR/Mac"
MAC_INSTALLER_DIR="$MAC_DIR/Instalador"
MAC_UPDATES_DIR="$MAC_DIR/Atualizações"
WINDOWS_DIR="$INSTALLERS_DIR/Windows"
WINDOWS_INSTALLER_DIR="$WINDOWS_DIR/Instalador"
WINDOWS_UPDATES_DIR="$WINDOWS_DIR/Atualizações"
MOBILE_DIR="$INSTALLERS_DIR/Celular"
MOBILE_ANDROID_DIR="$MOBILE_DIR/Android"
MOBILE_IOS_DIR="$MOBILE_DIR/iPhone-iOS"
MOBILE_WEB_SHORTCUT_DIR="$MOBILE_DIR/Atalho-Web"
ARCHIVE_DIR="$INSTALLERS_DIR/Arquivados"
REVIEW_DIR="$INSTALLERS_DIR/_Revisao_Antes_de_Excluir"
BACKUPS_DIR="$DROPBOX_SYSTEM_ROOT/Backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p \
  "$MAC_INSTALLER_DIR" "$MAC_UPDATES_DIR" \
  "$WINDOWS_INSTALLER_DIR" "$WINDOWS_UPDATES_DIR" \
  "$MOBILE_ANDROID_DIR" "$MOBILE_IOS_DIR" "$MOBILE_WEB_SHORTCUT_DIR" \
  "$ARCHIVE_DIR" "$REVIEW_DIR" "$BACKUPS_DIR"

copy_readmes() {
  cp "$BASE/installer/LEIA-ME.md" "$INSTALLERS_DIR/LEIA-ME.md"
  cp "$BASE/installer/mac/LEIA-ME.md" "$MAC_DIR/LEIA-ME.md"
  cp "$BASE/installer/windows/LEIA-ME.md" "$WINDOWS_DIR/LEIA-ME.md"
  cp "$BASE/installer/celular/LEIA-ME.md" "$MOBILE_DIR/LEIA-ME.md"
}

move_to_review() {
  local path="$1"
  [ -e "$path" ] || return 0
  local name
  name="$(basename "$path")"
  local target="$REVIEW_DIR/$TIMESTAMP-$name"
  local counter=1
  while [ -e "$target" ]; do
    target="$REVIEW_DIR/$TIMESTAMP-$counter-$name"
    counter=$((counter + 1))
  done
  mv "$path" "$target"
}

move_to_installer() {
  local source="$1"
  local destination="$2"
  [ -e "$source" ] || return 0
  if [ -e "$destination" ]; then
    move_to_review "$destination"
  fi
  mkdir -p "$(dirname "$destination")"
  mv "$source" "$destination"
}

move_to_installer "$INSTALLERS_DIR/SannyGold Sistema.app" "$MAC_INSTALLER_DIR/SannyGold Sistema.app"
move_to_installer "$INSTALLERS_DIR/SannyGold-Sistema-Mac.zip" "$MAC_INSTALLER_DIR/SannyGold-Sistema-Mac.zip"
move_to_installer "$MAC_DIR/SannyGold Sistema.app" "$MAC_INSTALLER_DIR/SannyGold Sistema.app"
move_to_installer "$MAC_DIR/SannyGold-Sistema-Mac.zip" "$MAC_INSTALLER_DIR/SannyGold-Sistema-Mac.zip"

move_to_installer "$INSTALLERS_DIR/SannyGold-Sistema-Windows-Setup.exe" "$WINDOWS_INSTALLER_DIR/SannyGold-Sistema-Windows-Setup.exe"
move_to_installer "$INSTALLERS_DIR/SannyGold-Sistema-Windows-Portable.zip" "$WINDOWS_INSTALLER_DIR/SannyGold-Sistema-Windows-Portable.zip"
move_to_installer "$WINDOWS_DIR/SannyGold-Sistema-Windows-Setup.exe" "$WINDOWS_INSTALLER_DIR/SannyGold-Sistema-Windows-Setup.exe"
move_to_installer "$WINDOWS_DIR/SannyGold-Sistema-Windows-Portable.zip" "$WINDOWS_INSTALLER_DIR/SannyGold-Sistema-Windows-Portable.zip"

move_to_review "$INSTALLERS_DIR/LEIA-ANTES-DE-INSTALAR.md"
move_to_review "$INSTALLERS_DIR/LEIA-MAC.md"
move_to_review "$INSTALLERS_DIR/LEIA-WINDOWS.md"
move_to_review "$INSTALLERS_DIR/LEIA-ANTES-DE-INSTALAR-WINDOWS.md"
move_to_review "$INSTALLERS_DIR/.DS_Store"
move_to_review "$MAC_DIR/LEIA-MAC.md"
move_to_review "$MAC_DIR/.DS_Store"
move_to_review "$WINDOWS_DIR/LEIA-WINDOWS.md"
move_to_review "$WINDOWS_DIR/LEIA-ANTES-DE-INSTALAR-WINDOWS.md"
move_to_review "$WINDOWS_DIR/.DS_Store"
move_to_review "$MOBILE_DIR/.DS_Store"

copy_readmes

shopt -s nullglob
for legacy_zip in "$INSTALLERS_DIR"/SannyGold-Sistema-Instalacao-*.zip; do
  move_to_review "$legacy_zip"
done
shopt -u nullglob

echo "Pasta organizada: $INSTALLERS_DIR"
echo "Mac: $MAC_INSTALLER_DIR"
echo "Windows: $WINDOWS_INSTALLER_DIR"
echo "Celular: $MOBILE_DIR"
echo "Arquivados: $ARCHIVE_DIR"
echo "Revisao antes de excluir: $REVIEW_DIR"
echo "Backups: $BACKUPS_DIR"
