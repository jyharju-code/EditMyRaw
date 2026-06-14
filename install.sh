#!/usr/bin/env bash
#
# EditMyRaw one-line installer for macOS.
#   curl -fsSL https://raw.githubusercontent.com/jyharju-code/EditMyRaw/main/install.sh | bash
#
# Uses `uv` to fetch a managed Python and all dependencies (~200 MB, one time).
# No Xcode tools or pre-installed Python required. Creates a double-click launcher
# on your Desktop. Set EDITMYRAW_NO_LAUNCH=1 to install without launching.

set -euo pipefail

REPO_TARBALL="https://github.com/jyharju-code/EditMyRaw/archive/refs/heads/main.tar.gz"
APP_DIR="$HOME/.editmyraw-app"
LAUNCHER="$HOME/Desktop/EditMyRaw.command"
PYVER="3.12"

echo "▶  Installing EditMyRaw…"

# 1) uv — manages Python + dependencies, no system Python needed.
if ! command -v uv >/dev/null 2>&1; then
  echo "   Installing uv (one-time, ~15 MB)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
UV="$(command -v uv)"

# 2) Fresh environment with a managed Python.
echo "   Creating environment in $APP_DIR…"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR"
"$UV" venv --python "$PYVER" "$APP_DIR/.venv" >/dev/null
PY="$APP_DIR/.venv/bin/python"

# 3) Install EditMyRaw + dependencies (~200 MB).
echo "   Downloading and installing dependencies (~200 MB, one time)…"
"$UV" pip install --python "$PY" "editmyraw @ $REPO_TARBALL"

# 4) Desktop launcher.
cat > "$LAUNCHER" <<EOF
#!/bin/bash
exec "$PY" -m editmyraw.cli web
EOF
chmod +x "$LAUNCHER"

echo ""
echo "✓  Installed."
echo "   → Double-click 'EditMyRaw.command' on your Desktop to start it."
echo "   → It opens in your browser. Add a free Gemini API key in the app"
echo "     (Settings panel). Get one at https://aistudio.google.com/apikey"
echo ""

if [ "${EDITMYRAW_NO_LAUNCH:-}" != "1" ]; then
  echo "Launching EditMyRaw now…"
  exec "$PY" -m editmyraw.cli web
fi
