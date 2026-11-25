#!/usr/bin/env bash
# Linux paketi: dist/Siluet/ klasörü ve dist/Siluet-linux.tar.gz
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${PROJECT_DIR}/build/linux"
DIST_DIR="${PROJECT_DIR}/dist"
PYTHON="${PYTHON:-python3}"

"${PYTHON}" -m venv "${BUILD_DIR}/venv"
"${BUILD_DIR}/venv/bin/python" -m pip install --upgrade pip
"${BUILD_DIR}/venv/bin/python" -m pip install "pyinstaller>=6,<7" -r "${PROJECT_DIR}/requirements.txt"
# Testler derlemeden önce çalışır; başarısızlıkta paket üretilmez.
QT_QPA_PLATFORM=offscreen "${BUILD_DIR}/venv/bin/python" -m pytest -q "${PROJECT_DIR}/tests" -p no:cacheprovider
"${BUILD_DIR}/venv/bin/pyinstaller" --noconfirm --clean --distpath "${DIST_DIR}" --workpath "${BUILD_DIR}/work" \
  "${PROJECT_DIR}/packaging/siluet.spec"
cp "${PROJECT_DIR}/packaging/linux/kur.sh" "${PROJECT_DIR}/packaging/linux/KURULUM.txt" \
   "${PROJECT_DIR}/packaging/linux/siluet.png" "${DIST_DIR}/Siluet/"
cp "${PROJECT_DIR}/LICENSE" "${DIST_DIR}/Siluet/LICENSE.txt"
chmod +x "${DIST_DIR}/Siluet/kur.sh" "${DIST_DIR}/Siluet/Siluet"
tar -C "${DIST_DIR}" -czf "${DIST_DIR}/Siluet-linux.tar.gz" Siluet
echo "Derleme tamamlandı: ${DIST_DIR}/Siluet-linux.tar.gz"
