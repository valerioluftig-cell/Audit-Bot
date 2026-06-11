# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for the Louisiana Parish Audit Pipeline.

Build with:
    pyinstaller audit_pipeline.spec --clean --noconfirm

Output: dist/AuditPipeline/AuditPipeline.exe  (one-directory bundle)
Copy the entire dist/AuditPipeline/ folder to any Windows PC and double-click the .exe.
"""

import os
from PyInstaller.utils.hooks import collect_all

all_datas, all_binaries, all_hiddenimports = [], [], []

for pkg in ["pdfplumber", "pdfminer", "openpyxl", "anthropic", "httpx",
            "certifi", "charset_normalizer", "starlette", "fastapi",
            "uvicorn", "anyio", "multipart", "h11", "sniffio",
            "python_multipart", "anthropic._legacy_response"]:
    try:
        d, b, h = collect_all(pkg)
        all_datas     += d
        all_binaries  += b
        all_hiddenimports += h
    except Exception:
        pass

project_root = os.path.abspath(os.path.dirname(SPEC))   # noqa: F821

# Include pipeline Python files as source (for dynamic import of validate etc.)
all_datas += [
    (os.path.join(project_root, "pipeline"), "pipeline"),
]

# Include manual_pages.json if it exists
manual_pages = os.path.join(project_root, "manual_pages.json")
if os.path.exists(manual_pages):
    all_datas += [(manual_pages, ".")]

a = Analysis(
    [os.path.join(project_root, "launcher.py")],
    pathex=[
        project_root,                                  # finds server.py
        os.path.join(project_root, "pipeline"),        # finds validate.py etc.
    ],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hiddenimports + [
        # uvicorn internals
        "uvicorn.logging",
        "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan", "uvicorn.lifespan.on",
        "uvicorn.main",
        # fastapi / starlette
        "fastapi", "fastapi.responses", "fastapi.staticfiles",
        "starlette.routing", "starlette.middleware.base",
        "starlette.responses", "starlette.requests",
        # file upload
        "python_multipart", "multipart",
        # PDF
        "pdfplumber", "pdfminer.high_level", "pdfminer.layout",
        "pdfminer.pdfpage", "pdfminer.pdfinterp", "pdfminer.converter",
        # Excel
        "openpyxl", "openpyxl.styles", "openpyxl.utils",
        # API client
        "anthropic", "httpx", "httpcore",
        # pipeline modules (dynamically imported at runtime)
        "validate", "extractor", "parse", "write_excel", "pipeline",
        # stdlib
        "email.mime.text", "email.mime.multipart",
        "queue", "threading", "uuid", "webbrowser",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "IPython", "notebook"],
    noarchive=False,
)

pyz = PYZ(a.pure)   # noqa: F821

exe = EXE(   # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AuditPipeline",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,   # show terminal window so users can see progress & errors
    icon=None,
)

coll = COLLECT(   # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AuditPipeline",
)
