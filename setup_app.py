"""
setup_app.py — build a standalone macOS .app with py2app.

Build with:  ./build_app.sh   (or: python setup_app.py py2app)
Produces dist/EditMyRaw.app — an Apple-Silicon (arm64) bundle that needs no
Python install. Unsigned: first launch needs right-click -> Open (Gatekeeper).
"""

from setuptools import setup

APP = ["app_main.py"]

OPTIONS = {
    "argv_emulation": False,
    # Force-copy only packages with dynamic imports / data files py2app can't trace.
    # Everything else (httpx, anyio, google-auth deps, flask helpers) is traced.
    "packages": [
        "editmyraw", "rawpy", "cv2", "numpy", "PIL",
        "flask", "google", "pydantic", "pydantic_core",
    ],
    "includes": ["editmyraw.server", "editmyraw.cli"],
    "plist": {
        "CFBundleName": "EditMyRaw",
        "CFBundleDisplayName": "EditMyRaw",
        "CFBundleIdentifier": "com.jyharju.editmyraw",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
    },
}

setup(
    app=APP,
    name="EditMyRaw",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
