#!/usr/bin/env bash
# Build a standalone macOS .app (arm64) into dist/EditMyRaw.app using PyInstaller.
# PyInstaller is used instead of py2app because it bundles namespace packages
# (google-genai/google-auth) and native libs (opencv, cryptography, rawpy) reliably.
set -euo pipefail
cd "$(dirname "$0")"

echo "▶  Building EditMyRaw.app (PyInstaller)…"
rm -rf build dist .venv-build EditMyRaw.spec
python3 -m venv .venv-build
.venv-build/bin/pip install -q --upgrade pip
echo "   Installing app + PyInstaller…"
.venv-build/bin/pip install -q . pyinstaller
echo "   Bundling…"
.venv-build/bin/pyinstaller --noconfirm --clean --windowed --name EditMyRaw \
  --osx-bundle-identifier com.jyharju.editmyraw \
  --collect-all cv2 \
  --collect-all rawpy \
  --collect-all google \
  --collect-submodules google.genai \
  --collect-data certifi \
  --collect-data editmyraw \
  app_main.py

echo ""
echo "✓  Built dist/EditMyRaw.app"
echo "   Share it:   (cd dist && zip -qr EditMyRaw-app.zip EditMyRaw.app)"
echo "   First launch on another Mac: right-click the app -> Open (unsigned)."
