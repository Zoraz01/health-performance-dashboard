"""
FitPulse API — app wiring. All route handlers live in routes/.

Startup:
  - Validates config via pydantic-settings (fails fast on missing env vars).
  - Initialises both databases (idempotent DDL).
  - Starts the APScheduler (Hevy poll 02/08/14/20:00, Claude analysis 03:00 America/Toronto).

Endpoints:
  GET  /health                          — public health check
  Webhooks, data, checkin, analyze, hevy, admin — see routes/
"""

import logging
import logging.config
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import settings
import database
import scheduler as sched
from routes import admin, analyze, checkin, data, hevy, webhooks


# ---------------------------------------------------------------------------
# Logging — must be configured before any module emits a record
# ---------------------------------------------------------------------------

class _AccessFilter(logging.Filter):
    """Drop uvicorn access log records for noisy self-referential paths."""
    _SKIP = ("/api/admin/logs", "/health")

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            path = str(args[2]).split("?")[0]
            if any(path.startswith(s) for s in self._SKIP):
                return False
        return True


logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "timestamped": {
            "format": "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "file": {
            "class": "logging.FileHandler",
            "filename": str(settings.log_dir / "server.log"),
            "formatter": "timestamped",
        },
        "stderr": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "timestamped",
        },
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "timestamped",
        },
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["stderr", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["stderr", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["stdout", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["file", "stderr"],
    },
})

logging.getLogger("uvicorn.access").addFilter(_AccessFilter())

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — DB init + scheduler
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    log.info("DB initialised")
    scheduler = sched.create_scheduler()
    scheduler.start()
    log.info("APScheduler started — Hevy poll 02/08/14/20:00, Claude analysis 03:00 (America/Toronto)")
    yield
    scheduler.shutdown(wait=False)
    log.info("APScheduler stopped")


# ---------------------------------------------------------------------------
# App + middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="FitPulse API", lifespan=lifespan)

_allowed_origins = ["http://localhost:5173", "https://health.zorazhaseeb.com"]
if settings.frontend_origin:
    _allowed_origins.append(settings.frontend_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(webhooks.router)
app.include_router(data.router)
app.include_router(checkin.router)
app.include_router(analyze.router)
app.include_router(hevy.router)
app.include_router(admin.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# SPA static files — registered AFTER all API routes
# ---------------------------------------------------------------------------

_DIST = Path(__file__).parent.parent / "frontend" / "dist"
_DIST_ROOT = _DIST.resolve() if _DIST.exists() else None

if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str = ""):
        candidate = (_DIST_ROOT / full_path).resolve()
        if not candidate.is_relative_to(_DIST_ROOT):
            raise HTTPException(status_code=404)
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST_ROOT / "index.html")
