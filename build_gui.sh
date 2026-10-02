#!/bin/zsh
# Build the standalone GUI patcher app with PyInstaller (bundles wit if it is on PATH, or WIT=/path/to/wit).
# Output: dist/Kirby-Patcher.app (macOS) or dist/Kirby-Patcher/ (other OSes).
set -eu
cd "${0:a:h}"
command -v pyinstaller >/dev/null || { echo "pyinstaller not found (pip install pyinstaller tkinterdnd2)"; exit 1; }
pyinstaller --noconfirm Kirby-Patcher.spec
echo "built: dist/Kirby-Patcher"
