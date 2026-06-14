#!/bin/bash
# Double-click in Finder to launch EditMyRaw in your browser.
cd "$(dirname "$0")"
exec ./.venv/bin/python -m editmyraw.cli web
