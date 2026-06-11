"""
Standalone launcher — entry point for the PyInstaller build.

When frozen (double-click .exe):
  - sys._MEIPASS contains all bundled assets
  - The browser opens automatically
  - Everything runs from this single process

When run from source (python launcher.py):
  - Works identically to python server.py
"""
import multiprocessing
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def main():
    # Make pipeline importable (needed for the dynamic validate import inside server.py)
    pipeline_dir = str(_resource_dir() / "pipeline")
    if pipeline_dir not in sys.path:
        sys.path.insert(0, pipeline_dir)

    # Open browser after the server is ready
    def _open_browser():
        time.sleep(2.0)
        webbrowser.open("http://localhost:8000")

    threading.Thread(target=_open_browser, daemon=True).start()

    # Start uvicorn with the app from server.py
    import uvicorn
    from server import app  # server.py is the single-file application

    print("Parish Audit Pipeline @ http://localhost:8000  (Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    multiprocessing.freeze_support()   # required for PyInstaller on Windows
    main()
