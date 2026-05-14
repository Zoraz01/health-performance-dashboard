"""
Production FastAPI server — replaces test_server.py.

Startup:
  - Initialises both databases (idempotent DDL).
  - Starts the APScheduler (nightly Hevy poll at 02:00 America/Toronto).

Webhooks:
  POST /webhook/apple-health           — ingest metrics into daily_snapshot
  POST /webhook/apple-health-workouts  — merge workouts into daily_snapshot
  POST /webhook/apple-health-sleep     — ingest sleep_analysis entries into daily_snapshot

REST (frontend):
  GET  /health
  GET  /api/today
  GET  /api/snapshot/{date}
  GET  /api/snapshots?from=YYYY-MM-DD&to=YYYY-MM-DD
  GET  /api/record/{date}
  GET  /api/scores?days=30
  GET  /api/soreness[?date=YYYY-MM-DD]
  POST /api/soreness
  POST /api/hevy/poll    — manual trigger for the nightly job
"""

import hmac
import logging
import logging.config
import os
from contextlib import asynccontextmanager
from datetime import date as date_cls, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import httpx
import jwt as pyjwt
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# Startup environment validation — fail fast with a clear message
# ---------------------------------------------------------------------------
_REQUIRED_ENV = [
    "APPLE_HEALTH_WEBHOOK_SECRET",
    "CLERK_SECRET_KEY",
    "CLERK_ISSUER",
]
for _var in _REQUIRED_ENV:
    if not os.environ.get(_var):
        raise RuntimeError(f"Required environment variable {_var!r} is not set — check backend/.env")

import apple_health
import auth
import claude_analysis
import database
import scheduler as sched

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


class _AccessFilter(logging.Filter):
    """Drop uvicorn access log records for noisy self-referential paths."""
    _SKIP = ("/api/admin/logs", "/health")

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn.access args: (client_addr, method, path, http_ver, status)
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
            "filename": str(LOG_DIR / "server.log"),
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
        # Uvicorn's internal loggers — apply our format so access/error
        # lines also carry timestamps instead of the bare "INFO: ..." prefix.
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

# Attach noise filter to access logger imperatively — can't self-reference
# this module inside dictConfig at import time.
logging.getLogger("uvicorn.access").addFilter(_AccessFilter())

log = logging.getLogger(__name__)


WEBHOOK_SECRET = os.environ["APPLE_HEALTH_WEBHOOK_SECRET"]
_OWNER_EMAIL   = os.environ.get("OWNER_EMAIL", "").lower().strip()


# ---------------------------------------------------------------------------
# Lifespan — DB init + scheduler
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    log.info("DB initialised")
    scheduler = sched.create_scheduler()
    scheduler.start()
    log.info("APScheduler started — Hevy poll 02:00, Claude analysis 03:00 (America/Toronto)")
    yield
    scheduler.shutdown(wait=False)
    log.info("APScheduler stopped")


app = FastAPI(title="FitPulse API", lifespan=lifespan)

_allowed_origins = ["http://localhost:5173", "https://health.zorazhaseeb.com"]
if os.environ.get("FRONTEND_ORIGIN"):
    _allowed_origins.append(os.environ["FRONTEND_ORIGIN"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---------------------------------------------------------------------------
# Webhook auth (HMAC secret from Health Auto Export)
# ---------------------------------------------------------------------------

def _verify_bearer(authorization: Optional[str]) -> None:
    if not authorization or not hmac.compare_digest(
        authorization, f"Bearer {WEBHOOK_SECRET}"
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# JWT auth — protects all /api/* routes
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """FastAPI dependency — verifies Clerk JWT and returns (or lazily creates) the local user row."""
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = auth.verify_clerk_token(creds.credentials)
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
    except httpx.HTTPError as exc:
        log.error("JWKS fetch failed: %s", exc)
        raise HTTPException(status_code=503, detail="Auth service temporarily unavailable")

    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Token missing sub claim")

    user = database.get_user_by_clerk_id(clerk_user_id)
    if user:
        if not user.get("is_active"):
            raise HTTPException(status_code=401, detail="User inactive")
    else:
        # First login — fetch email from Clerk and create local record
        email = auth.get_clerk_user_email(clerk_user_id)
        user = database.create_user_from_clerk(clerk_user_id, email)
        log.info("[auth] first login — created user %s (clerk_id=%s)", email, clerk_user_id)

    if _OWNER_EMAIL and user.get("email", "").lower().strip() != _OWNER_EMAIL:
        raise HTTPException(status_code=403, detail="Access denied")

    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Stricter gate — only users with is_admin=1 in the DB can reach /api/admin/* routes."""
    if not user.get("is_admin"):
        log.warning("[auth] admin access denied for %s", user.get("email"))
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------

@app.post("/webhook/apple-health")
async def webhook_apple_health_metrics(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    _verify_bearer(authorization)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    dates = apple_health._detect_all_dates(payload)
    if not dates:
        log.warning("[webhook/apple-health] no date in payload — skipped")
        return {"status": "ok", "ingested": False, "reason": "no date in payload"}

    total_fields = 0
    for target_date in sorted(dates):
        fields = apple_health.ingest_metrics(payload, target_date)
        total_fields += len(fields)
        log.info("[webhook/apple-health] %d fields ingested for %s", len(fields), target_date)
    return {"status": "ok", "dates": sorted(dates), "fields_ingested": total_fields}


@app.post("/webhook/apple-health-workouts")
async def webhook_apple_health_workouts(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    _verify_bearer(authorization)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    raw = payload.get("data", {}).get("workouts") or []
    dates: set[str] = set()
    for w in raw:
        start = w.get("start")
        if start:
            try:
                dates.add(apple_health._local_date(start))
            except ValueError:
                pass

    if not dates:
        log.warning("[webhook/apple-health-workouts] no workouts in payload — skipped")
        return {"status": "ok", "ingested": False, "reason": "no workouts in payload"}

    total_workouts = 0
    for target_date in sorted(dates):
        workouts = apple_health.ingest_workouts(payload, target_date)
        total_workouts += len(workouts)
        log.info("[webhook/apple-health-workouts] %d workouts ingested for %s",
                 len(workouts), target_date)
    return {"status": "ok", "dates": sorted(dates), "workouts_ingested": total_workouts}


@app.post("/webhook/apple-health-sleep")
async def webhook_apple_health_sleep(
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """Dedicated endpoint for sleep_analysis payloads.

    Expects the same envelope as the metrics endpoint but only processes
    the sleep_analysis metric. Saves the raw payload to DuckDB for
    inspection, then parses and upserts sleep columns into daily_snapshot.
    """
    _verify_bearer(authorization)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Log the raw payload to a file so we can inspect the format once.
    import json as _json
    from datetime import datetime as _dt
    from pathlib import Path
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
    (log_dir / f"sleep_payload_{ts}.json").write_text(_json.dumps(payload, indent=2))
    log.info("[webhook/apple-health-sleep] payload logged to sleep_payload_%s.json", ts)

    dates = apple_health._detect_all_dates(payload)
    if not dates:
        # Try to find dates from sleep_analysis entries directly.
        for m in payload.get("data", {}).get("metrics") or []:
            if m.get("name") == "sleep_analysis":
                for entry in m.get("data") or []:
                    ts_str = entry.get("date") or ""
                    try:
                        dates.add(apple_health._local_date(ts_str))
                    except Exception:
                        pass
    if not dates:
        log.warning("[webhook/apple-health-sleep] no date detected in payload")
        return {"status": "ok", "ingested": False, "reason": "no date in payload",
                "note": "raw payload saved to logs/"}

    database.append_raw_blob("raw_apple_health", min(sorted(dates)), payload)

    total_fields = 0
    for target_date in sorted(dates):
        sleep_fields = apple_health._parse_sleep_from_payload(payload, target_date)
        if sleep_fields:
            database.upsert_snapshot_apple_health(target_date, sleep_fields)
            total_fields += len(sleep_fields)
            log.info("[webhook/apple-health-sleep] %d sleep fields for %s: %s",
                     len(sleep_fields), target_date, sleep_fields)
        else:
            log.info("[webhook/apple-health-sleep] no sleep data for %s", target_date)

    return {"status": "ok", "dates": sorted(dates), "sleep_fields": total_fields,
            "note": "raw payload saved to logs/"}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Snapshot / record reads
# ---------------------------------------------------------------------------

@app.get("/api/today")
async def get_today(_: dict = Depends(get_current_user)):
    today     = datetime.now(sched.LOCAL_TZ).date().isoformat()
    yesterday = (date_cls.fromisoformat(today) - timedelta(days=1)).isoformat()

    record = database.get_daily_record(today) or database.get_daily_record(yesterday)
    record_date = record.get("date") if record else None
    log.debug("[api/today] serving %s, record_date=%s", today, record_date)

    return {
        "date":               today,
        "snapshot":           database.get_snapshot(today),
        "yesterday_snapshot": database.get_snapshot(yesterday),
        "record":             record,
        "baselines":          database.get_metric_baselines(30),
    }


@app.get("/api/snapshot/{date}")
async def get_snapshot(date: str, _: dict = Depends(get_current_user)):
    row = database.get_snapshot(date)
    if not row:
        raise HTTPException(status_code=404, detail=f"No snapshot for {date}")
    return row


@app.get("/api/snapshots")
async def get_snapshots(
    from_date: str = Query(..., alias="from"),
    to_date: str   = Query(..., alias="to"),
    _: dict = Depends(get_current_user),
):
    return database.get_snapshots(from_date, to_date)


@app.get("/api/record/{date}")
async def get_daily_record(date: str, _: dict = Depends(get_current_user)):
    row = database.get_daily_record(date)
    if not row:
        raise HTTPException(status_code=404, detail=f"No record for {date}")
    return row


@app.get("/api/scores")
async def get_scores(days: int = Query(default=30, ge=1, le=365), _: dict = Depends(get_current_user)):
    return database.get_score_history(days)


@app.get("/api/activity")
async def get_activity_history(days: int = Query(default=30, ge=1, le=365), _: dict = Depends(get_current_user)):
    return database.get_activity_history(days)


@app.get("/api/timeseries/{date}")
async def get_daily_timeseries(date: str, metric: str = Query(default="heart_rate"), _: dict = Depends(get_current_user)):
    samples = database.get_daily_timeseries(date, metric)
    return {"date": date, "metric": metric, "samples": samples}


# ---------------------------------------------------------------------------
# Workout timeseries
# ---------------------------------------------------------------------------

@app.get("/api/workout/{workout_id}/hr")
async def get_workout_hr(workout_id: str, _: dict = Depends(get_current_user)):
    samples = database.get_workout_hr_samples(workout_id)
    if not samples:
        raise HTTPException(status_code=404, detail="No HR samples for this workout")
    return {"workout_id": workout_id, "samples": samples}


@app.get("/api/workout/{workout_id}/sets")
async def get_workout_sets(workout_id: str, _: dict = Depends(get_current_user)):
    exercises = database.get_workout_sets(workout_id)
    if not exercises:
        raise HTTPException(status_code=404, detail="No set data for this workout")
    return {"workout_id": workout_id, "exercises": exercises}


# ---------------------------------------------------------------------------
# Soreness log
# ---------------------------------------------------------------------------

@app.get("/api/soreness")
async def get_soreness(date: Optional[str] = None, _: dict = Depends(get_current_user)):
    with database.get_sqlite() as conn:
        if date:
            rows = conn.execute(
                "SELECT * FROM soreness_log WHERE date = ? ORDER BY logged_at DESC",
                (date,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM soreness_log ORDER BY date DESC, logged_at DESC LIMIT 100"
            ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/soreness")
async def log_soreness(request: Request, _: dict = Depends(get_current_user)):
    body = await request.json()
    date     = body.get("date")
    muscle   = body.get("muscle")
    soreness = body.get("soreness")

    if not date or not muscle or soreness is None:
        raise HTTPException(
            status_code=400, detail="date, muscle, and soreness are required"
        )
    try:
        soreness_int = int(soreness)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="soreness must be an integer")
    if not 0 <= soreness_int <= 5:
        raise HTTPException(status_code=400, detail="soreness must be 0–5")

    with database.get_sqlite() as conn:
        conn.execute(
            "INSERT INTO soreness_log (date, muscle, soreness) VALUES (?, ?, ?) "
            "ON CONFLICT(date, muscle) DO UPDATE SET "
            "soreness = excluded.soreness, logged_at = CURRENT_TIMESTAMP",
            (date, muscle, soreness_int),
        )
    log.info("[api/soreness] %s → %s = %d", date, muscle, soreness_int)
    return {"status": "ok", "date": date, "muscle": muscle, "soreness": soreness_int}


# ---------------------------------------------------------------------------
# Check-in — unified endpoint (soreness + free-text note)
# ---------------------------------------------------------------------------

@app.get("/api/checkin/today")
async def get_today_checkin(_: dict = Depends(get_current_user)):
    today    = datetime.now(sched.LOCAL_TZ).date().isoformat()
    soreness = database.get_soreness_for_date(today)
    snapshot = database.get_snapshot(today) or {}
    note     = (snapshot.get("notes") or "").strip()
    if not soreness and not note:
        return {"checked_in": False, "date": today}
    return {"checked_in": True, "date": today, "soreness": soreness, "note": note}


@app.post("/api/checkin")
async def submit_checkin(request: Request, _: dict = Depends(get_current_user)):
    """
    Accept today's check-in in one shot — one submission per day, first wins.
    Body: { date, soreness: {muscle: 0-5, ...}, note: str }
    """
    body     = await request.json()
    date     = body.get("date")
    soreness = body.get("soreness") or {}
    note     = (body.get("note") or "").strip()

    if not date:
        raise HTTPException(status_code=400, detail="date is required")

    # One check-in per day: if soreness or a note already exists, silently skip.
    existing_soreness = database.get_soreness_for_date(date)
    existing_snapshot = database.get_snapshot(date) or {}
    existing_note     = (existing_snapshot.get("notes") or "").strip()
    if existing_soreness or existing_note:
        return {"status": "already_checked_in", "date": date}

    with database.get_sqlite() as conn:
        for muscle, value in soreness.items():
            try:
                val = int(value)
            except (TypeError, ValueError):
                continue
            if not 0 <= val <= 5:
                continue
            conn.execute(
                "INSERT INTO soreness_log (date, muscle, soreness) VALUES (?, ?, ?) "
                "ON CONFLICT(date, muscle) DO UPDATE SET "
                "soreness = excluded.soreness, logged_at = CURRENT_TIMESTAMP",
                (date, muscle, val),
            )

    if note:
        database.upsert_snapshot_notes(date, note)

    log.info("[api/checkin] %s — %d muscle(s), note=%s", date, len(soreness), bool(note))
    return {"status": "ok", "date": date,
            "muscles_logged": len(soreness), "note_saved": bool(note)}


# ---------------------------------------------------------------------------
# Claude analysis — manual trigger
# ---------------------------------------------------------------------------

@app.post("/api/analyze/{date}")
async def trigger_analysis(date: str, _: dict = Depends(get_current_user)):
    snapshot = database.get_snapshot(date)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No snapshot for {date}")

    # Always recompute recovery before analysis so the prompt reflects fresh data,
    # not a stale cached value from a previous backfill or poll.
    from scheduler import compute_recovery_status
    fresh_recovery = compute_recovery_status(date)
    database.upsert_snapshot_recovery_status(date, fresh_recovery)
    snapshot["recovery_status"] = fresh_recovery

    # Pull today's soreness check-in and attach it to the snapshot for the prompt.
    snapshot["soreness"] = database.get_soreness_for_date(date)

    baselines     = database.get_metric_baselines(30)
    history       = database.get_weekly_summary(date)
    prev_date     = (date_cls.fromisoformat(date) - timedelta(days=1)).isoformat()
    prev_analysis = database.get_daily_record(prev_date)

    try:
        parsed, raw = claude_analysis.run_analysis(date, snapshot, baselines, history, prev_analysis)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        log.exception("[api/analyze] failed for %s: %s", date, e)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    database.upsert_daily_record_analysis(date, parsed, raw, force=True)
    log.info("[api/analyze] analysis written for %s", date)
    return {"status": "ok", "date": date, "analysis": parsed}


# ---------------------------------------------------------------------------
# Admin — /api/admin/* (require_admin gate)
# ---------------------------------------------------------------------------

@app.get("/api/admin/me")
async def admin_me(user: dict = Depends(require_admin)):
    """Returns the current admin user's identity. 403 if not admin."""
    return {"is_admin": True, "email": user.get("email"), "id": user.get("id")}


@app.get("/api/admin/logs")
async def get_admin_logs(
    lines: int = Query(default=300, ge=1, le=2000),
    _: dict = Depends(require_admin),
):
    """Return the last N lines from the backend log files, sorted by timestamp."""
    import re
    _TS = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
    entries = []
    for path, stream in [
        (LOG_DIR / "launchd.err.log", "stderr"),
        (LOG_DIR / "launchd.out.log", "stdout"),
    ]:
        if path.exists():
            for raw_line in path.read_text(errors="replace").splitlines():
                line = raw_line.strip()
                if line:
                    entries.append({"stream": stream, "line": line})

    # Assign a sort key to each line.
    # Lines with an ISO timestamp sort by that timestamp.
    # Continuation lines (tracebacks, ~~~^^^, etc.) inherit the last seen
    # timestamp so they stay grouped with their parent entry rather than
    # floating to the end (~ is ASCII 126, after all letters/digits).
    last_ts = "0000-00-00 00:00:00"
    last_idx = 0
    for i, e in enumerate(entries):
        m = _TS.match(e["line"])
        if m:
            last_ts = e["line"][:19]
            last_idx = 0
        else:
            last_idx += 1
        # Tie-break with a zero-padded counter so continuations stay in
        # original file order under the same timestamp.
        e["_sort"] = f"{last_ts}_{last_idx:06d}"

    entries.sort(key=lambda e: e["_sort"])
    # Strip internal sort key before returning
    for e in entries:
        del e["_sort"]
    return entries[-lines:]


@app.get("/api/admin/users")
async def list_admin_users(_: dict = Depends(require_admin)):
    """List all registered users with their admin status."""
    return database.list_users()


@app.post("/api/admin/users/{email}/promote")
async def promote_user(email: str, actor: dict = Depends(require_admin)):
    """Grant is_admin=1 to the user with the given email."""
    updated = database.set_user_admin(email, True)
    if not updated:
        raise HTTPException(status_code=404, detail=f"No user found with email {email!r}")
    log.info("[admin] %s promoted %s to admin", actor.get("email"), email)
    return {"status": "ok", "email": email, "is_admin": True}


@app.post("/api/admin/users/{email}/demote")
async def demote_user(email: str, actor: dict = Depends(require_admin)):
    """Revoke admin from the user with the given email. Cannot self-demote."""
    if email.lower().strip() == actor.get("email", "").lower().strip():
        raise HTTPException(status_code=400, detail="Cannot demote yourself")
    updated = database.set_user_admin(email, False)
    if not updated:
        raise HTTPException(status_code=404, detail=f"No user found with email {email!r}")
    log.info("[admin] %s demoted %s from admin", actor.get("email"), email)
    return {"status": "ok", "email": email, "is_admin": False}


# ---------------------------------------------------------------------------
# Manual Hevy poll
# ---------------------------------------------------------------------------

@app.post("/api/hevy/poll")
async def trigger_hevy_poll(_: dict = Depends(get_current_user)):
    log.info("[api] manual Hevy poll triggered")
    await sched.nightly_hevy_poll()
    return {"status": "ok", "message": "Hevy poll completed"}


@app.post("/api/hevy/backfill")
async def trigger_hevy_backfill(days: int = Query(default=7, ge=1, le=30), _: dict = Depends(get_current_user)):
    """Re-fetch Hevy workouts for the past N days and write each to its correct date snapshot."""
    log.info("[api] Hevy backfill triggered (last %d days)", days)
    results = await sched.backfill_hevy(since_days=days)
    return {"status": "ok", "days_requested": days, "dates_written": results}


@app.post("/api/workouts/dedup")
async def dedup_workouts(_: dict = Depends(get_current_user)):
    """Backfill: apply cross-source dedup to all existing workout arrays in daily_snapshot."""
    log.info("[api] workout cross-source dedup backfill triggered")
    changed = database.dedup_existing_workouts()
    return {"status": "ok", "dates_changed": len(changed), "details": changed}


# ---------------------------------------------------------------------------
# SPA static files — must be registered AFTER all API routes
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
