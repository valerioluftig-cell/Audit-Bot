"""
Web app for the Louisiana Parish Audit Pipeline.

Development usage:
    cd audit_project/webapp
    uvicorn app:app --reload --port 8000

Standalone (PyInstaller) usage:
    Double-click AuditPipeline.exe  — browser opens automatically.
"""
import json
import os
import queue
import sys
import tempfile
import threading
import uuid
from pathlib import Path

# ── Path helpers — work both from source and when frozen by PyInstaller ────────

def _frozen() -> bool:
    return getattr(sys, "frozen", False)

def _resource_dir() -> Path:
    """Root directory for bundled read-only assets (static files, pipeline code)."""
    if _frozen():
        return Path(sys._MEIPASS)          # PyInstaller extracts here
    return Path(__file__).parent.parent    # audit_project/ when running from source

def _config_dir() -> Path:
    """User-writable directory for config.json (api key, etc.)."""
    if _frozen():
        return Path(sys.executable).parent  # same folder as the .exe
    return Path(__file__).parent.parent     # audit_project/

def _get_api_key() -> str | None:
    """Read API key from config.json (never hardcoded)."""
    try:
        cfg = json.loads((_config_dir() / "config.json").read_text())
        return cfg.get("api_key") or None
    except Exception:
        return None

API_KEY = _get_api_key()

# Add pipeline to import path
_pipeline_dir = _resource_dir() / "pipeline"
if str(_pipeline_dir) not in sys.path:
    sys.path.insert(0, str(_pipeline_dir))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from pipeline import run_pipeline  # noqa: E402

app = FastAPI(title="Parish Audit Pipeline")

JOBS: dict[str, dict] = {}




# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    html = _resource_dir() / "webapp" / "static" / "index.html"
    if not html.exists():
        # fallback for dev layout where __file__ is inside webapp/
        html = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html.read_text(encoding="utf-8"))



@app.post("/run")
async def run(files: list[UploadFile] = File(...), year: int = Form(...)):
    """Accept uploaded PDFs, kick off background pipeline, return job_id."""
    api_key = API_KEY

    job_id = str(uuid.uuid4())[:8]

    job_dir = Path(tempfile.mkdtemp(prefix=f"audit_{job_id}_"))
    pdf_dir = job_dir / "pdfs"
    out_dir = job_dir / "output"
    cache_dir = out_dir / "cache"
    pdf_dir.mkdir(); out_dir.mkdir(); cache_dir.mkdir()

    for f in files:
        (pdf_dir / f.filename).write_bytes(await f.read())

    q: queue.Queue[str] = queue.Queue()
    JOBS[job_id] = {"queue": q, "status": "running", "output_dir": str(out_dir)}

    def _run():
        try:
            # Inject API key into environment for this thread
            os.environ["ANTHROPIC_API_KEY"] = api_key
            run_pipeline(
                input_dir=str(pdf_dir),
                year=year,
                output_dir=str(out_dir),
                cache_dir=str(cache_dir),
                skip_cache=True,
                progress_callback=lambda msg: q.put(msg),
            )
            JOBS[job_id]["status"] = "done"
        except Exception as exc:
            q.put(f"[ERROR] {exc}")
            JOBS[job_id]["status"] = "error"
        finally:
            q.put("__DONE__")

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": job_id}


@app.get("/progress/{job_id}")
def progress(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404)

    def stream():
        q = JOBS[job_id]["queue"]
        while True:
            try:
                msg = q.get(timeout=25)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            yield f"data: {json.dumps(msg)}\n\n"
            if msg == "__DONE__":
                break

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/files/{job_id}")
def list_files(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404)
    out_dir = Path(JOBS[job_id]["output_dir"])
    all_files = sorted(f.name for f in out_dir.glob("*.xlsx"))
    return {
        "by_statement": [f for f in all_files if f.startswith("Louisiana")],
        "by_parish":    [f for f in all_files if not f.startswith("Louisiana")],
        "status": JOBS[job_id]["status"],
    }


@app.get("/download/{job_id}/{filename}")
def download(job_id: str, filename: str):
    if job_id not in JOBS:
        raise HTTPException(404)
    path = Path(JOBS[job_id]["output_dir"]) / filename
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(str(path), filename=filename)
