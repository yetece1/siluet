#!/usr/bin/env bash
# Silüet'i kullanıcı hesabına kurar (yönetici yetkisi gerekmez).
# Kaldırmak için: ./kur.sh --kaldir
set -euo pipefail
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${XDG_DATA_HOME:-$HOME/.local/share}/Siluet"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP="${APPS}/siluet.desktop"
BIN="$HOME/.local/bin/siluet"

if [[ "${1:-}" == "--kaldir" ]]; then
  rm -rf -- "${TARGET}"; rm -f -- "${DESKTOP}" "${BIN}"
  echo "Silüet kaldırıldı."; exit 0
fi

if [[ "${SOURCE}" != "${TARGET}" ]]; then
  rm -rf -- "${TARGET}"
  mkdir -p "$(dirname "${TARGET}")"
  cp -a "${SOURCE}" "${TARGET}"
fi
chmod +x "${TARGET}/Siluet"
mkdir -p "${APPS}" "$(dirname "${BIN}")"
ln -sf "${TARGET}/Siluet" "${BIN}"
cat > "${DESKTOP}" <<DESKTOP_ENTRY
[Desktop Entry]
Type=Application
Name=Silüet
Comment=HTS Excel dosyalarını anonimleştirir
Exec="${TARGET}/Siluet"
Icon=${TARGET}/siluet.png
Terminal=false
Categories=Office;Utility;
StartupWMClass=Siluet
DESKTOP_ENTRY
command -v update-desktop-database >/dev/null && update-desktop-database "${APPS}" >/dev/null 2>&1 || true
echo "Kuruldu. Uygulama menüsünde 'Silüet' olarak görünür."
