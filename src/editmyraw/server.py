"""server.py — EditMyRaw browser GUI (Flask, local only)."""

from __future__ import annotations

import base64
import io
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import traceback
import webbrowser
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from . import config, pipeline

HERE = Path(__file__).resolve().parent
WEB = HERE / "web"
HOST = "127.0.0.1"
PORT_CANDIDATES = [8473, 8474, 7655, 9124, 8190, 5455, 9445]  # avoid 8765 / 7321

MODELS = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.5-pro",
          "gemini-3-pro-preview", "gemini-3.5-flash"]
IMAGE_MODELS = ["gemini-2.5-flash-image", "gemini-3.1-flash-image", "gemini-3-pro-image"]

app = Flask(__name__, static_folder=None)
_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_counter = {"n": 0}


# ----- static -----
@app.get("/")
def index():
    return send_from_directory(WEB, "index.html")


@app.get("/static/<path:name>")
def static_files(name):
    return send_from_directory(WEB, name)


@app.get("/config")
def get_config():
    return jsonify({
        "default_out": os.path.join(os.path.expanduser("~"), "EditMyRaw-exports"),
        "models": MODELS, "image_models": IMAGE_MODELS,
        "key": config.key_status(),
    })


# ----- API key management (secure, local) -----
@app.get("/key")
def key_get():
    return jsonify(config.key_status())


@app.post("/key")
def key_set():
    body = request.get_json(force=True) or {}
    key = (body.get("key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "Empty key."}), 400
    config.save_api_key(key)
    if body.get("model"):
        config.set_model(model=body["model"])
    if body.get("image_model"):
        config.set_model(image_model=body["image_model"])
    return jsonify({"ok": True, "key": config.key_status()})


@app.post("/key/clear")
def key_clear():
    config.clear_api_key()
    return jsonify({"ok": True, "key": config.key_status()})


@app.post("/key/test")
def key_test():
    settings = config.load_settings()
    if not settings.api_key:
        return jsonify({"ok": False, "error": "No key set."})
    try:
        from .gemini import GeminiClient
        client = GeminiClient(settings)
        models = list(client._client.models.list())
        return jsonify({"ok": True, "model_count": len(models), "source": settings.key_source})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:300]})


# ----- native file pickers -----
def _osa(script):
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
        return [ln for ln in r.stdout.strip().split("\n") if ln.strip()] if r.returncode == 0 else []
    except Exception:
        return []


_PICK = {
    "file": 'POSIX path of (choose file with prompt "Choose reference image")',
    "folder": 'POSIX path of (choose folder with prompt "Choose folder")',
    "files": ('set fs to choose file with prompt "Choose images" with multiple selections allowed\n'
              'set t to ""\nrepeat with f in fs\nset t to t & POSIX path of f & "\n"\nend repeat\nreturn t'),
}


def _tk_pick(kind):
    """Cross-platform native picker (Windows/Linux) via tkinter."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception:
        return []
    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    try:
        if kind == "files":
            res = list(root.tk.splitlist(filedialog.askopenfilenames(title="Choose images")))
        elif kind == "folder":
            d = filedialog.askdirectory(title="Choose folder")
            res = [d] if d else []
        else:
            f = filedialog.askopenfilename(title="Choose reference image")
            res = [f] if f else []
    finally:
        root.destroy()
    return [p for p in res if p]


def _pick_paths(kind):
    # macOS: native osascript dialog. Other platforms: tkinter.
    if sys.platform == "darwin":
        return _osa(_PICK.get(kind, _PICK["file"]))
    return _tk_pick(kind)


def _reveal(path):
    if sys.platform == "darwin":
        subprocess.run(["open", path])
    elif sys.platform.startswith("win"):
        os.startfile(path)  # noqa: type
    else:
        subprocess.run(["xdg-open", path])


@app.post("/pick")
def pick():
    kind = (request.get_json(force=True) or {}).get("kind", "file")
    paths = _pick_paths(kind)
    if kind == "folder":
        return jsonify({"paths": paths, "expanded": pipeline.expand_inputs(paths) if paths else []})
    return jsonify({"paths": paths})


@app.post("/openfolder")
def openfolder():
    d = (request.get_json(force=True) or {}).get("dir", "")
    if d and os.path.isdir(d):
        _reveal(d)
        return jsonify({"ok": True})
    return jsonify({"ok": False})


# ----- processing + SSE -----
def _data_url(pil_img):
    buf = io.BytesIO()
    pil_img.convert("RGB").save(buf, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _worker(job_id, cfg):
    q = _jobs[job_id]["q"]
    try:
        inputs = cfg.pop("inputs", [])
        res = pipeline.run(inputs=inputs,
                           progress=lambda fr, m: q.put({"type": "progress", "frac": fr, "msg": m}),
                           **cfg)
        q.put({"type": "progress", "frac": 0.97, "msg": "Building previews…"})
        rows = [{
            "stem": oc.stem, "before": _data_url(oc.before), "after": _data_url(oc.after),
            "generated": oc.generated, "diagnosis": oc.recipe.diagnosis,
            "recipe": oc.recipe.model_dump(mode="json"),
        } for oc in res["outcomes"][:48]]  # cap browser preview; all files are on disk
        q.put({"type": "done", "count": res["count"], "out_dir": res["out_dir"],
               "zip": res["zip_path"], "gemini_log": res["gemini_log"],
               "global_tone": res["global_tone"], "key_source": res["key_source"], "rows": rows})
    except Exception:
        q.put({"type": "error", "msg": traceback.format_exc()[-1800:]})


@app.post("/process")
def process():
    cfg = request.get_json(force=True) or {}
    with _lock:
        _counter["n"] += 1
        job_id = str(_counter["n"])
        _jobs[job_id] = {"q": queue.Queue()}
    threading.Thread(target=_worker, args=(job_id, cfg), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.get("/progress/<job_id>")
def progress(job_id):
    def stream():
        q = _jobs.get(job_id, {}).get("q")
        if q is None:
            yield f"data: {json.dumps({'type':'error','msg':'Unknown job.'})}\n\n"
            return
        while True:
            try:
                ev = q.get(timeout=30)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            yield f"data: {json.dumps(ev)}\n\n"
            if ev["type"] in ("done", "error"):
                with _lock:
                    _jobs.pop(job_id, None)
                return
    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def find_free_port():
    for p in PORT_CANDIDATES:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((HOST, p))
                return p
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def main():
    port = find_free_port()
    url = f"http://{HOST}:{port}/"
    print(f"EditMyRaw running: {url}")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host=HOST, port=port, threaded=True, debug=False)


if __name__ == "__main__":
    main()
