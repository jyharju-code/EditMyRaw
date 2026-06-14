"""
desktop.py — run EditMyRaw as a real native desktop window (pywebview).

Starts the Flask server on a loopback port in a background thread, then shows
the UI in its own OS window (WKWebView on macOS, WebView2 on Windows) — with its
own icon, app-switcher entry, and close-to-quit. Falls back to opening a browser
tab if no webview backend is available.
"""

from __future__ import annotations

import socket
import threading
import time

from . import server


def _wait_for_server(port: int, timeout: float = 12.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def run_desktop() -> None:
    try:
        import webview
    except Exception:
        # No native webview backend -> behave like the browser version.
        server.main()
        return

    port = server.find_free_port()
    threading.Thread(
        target=lambda: server.app.run(host=server.HOST, port=port, threaded=True),
        daemon=True,
    ).start()
    _wait_for_server(port)
    url = f"http://{server.HOST}:{port}/"
    try:
        webview.create_window("EditMyRaw", url, width=1240, height=900, min_size=(900, 640))
        webview.start()
    except Exception:
        # Native window backend failed at runtime -> fall back to a browser tab.
        import webbrowser
        print(f"EditMyRaw running: {url}")
        webbrowser.open(url)
        while True:
            time.sleep(3600)
