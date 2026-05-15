import hmac
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

import apple_health
import database
from config import settings
from rate_limit import webhook_limiter

log = logging.getLogger(__name__)
router = APIRouter()


def _verify_bearer(authorization: Optional[str]) -> None:
    if not authorization or not hmac.compare_digest(
        authorization, f"Bearer {settings.apple_health_webhook_secret}"
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _resolve_token_user(user_token: str) -> dict:
    """Look up user by webhook token; raise 401 if invalid or inactive."""
    user = database.get_user_by_webhook_token(user_token)
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Invalid or inactive token")
    return user


def _owner_user_id() -> int | None:
    """Return the owner's DB user_id for legacy (no-token) backward-compat routes."""
    if not settings.owner_email:
        return None
    owner = database.get_user_by_email(settings.owner_email)
    return owner["id"] if owner else None


# ---------------------------------------------------------------------------
# Token-based routes (new — used by Health Auto Export after reconfiguration)
# ---------------------------------------------------------------------------

@router.post("/webhook/apple-health/{user_token}")
async def webhook_apple_health_metrics_token(
    user_token: str,
    request: Request,
    _rl: None = Depends(webhook_limiter),
):
    user = _resolve_token_user(user_token)
    uid = user["id"]
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
        fields = apple_health.ingest_metrics(payload, target_date, user_id=uid)
        total_fields += len(fields)
        log.info("[webhook/apple-health] %d fields ingested for %s (user %d)", len(fields), target_date, uid)
    return {"status": "ok", "dates": sorted(dates), "fields_ingested": total_fields}


@router.post("/webhook/apple-health-workouts/{user_token}")
async def webhook_apple_health_workouts_token(
    user_token: str,
    request: Request,
    _rl: None = Depends(webhook_limiter),
):
    user = _resolve_token_user(user_token)
    uid = user["id"]
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
        workouts = apple_health.ingest_workouts(payload, target_date, user_id=uid)
        total_workouts += len(workouts)
        log.info("[webhook/apple-health-workouts] %d workouts ingested for %s (user %d)",
                 len(workouts), target_date, uid)
    return {"status": "ok", "dates": sorted(dates), "workouts_ingested": total_workouts}


@router.post("/webhook/apple-health-sleep/{user_token}")
async def webhook_apple_health_sleep_token(
    user_token: str,
    request: Request,
    _rl: None = Depends(webhook_limiter),
):
    """Ingest sleep_analysis payloads via token URL, log raw JSON, upsert sleep columns."""
    user = _resolve_token_user(user_token)
    uid = user["id"]
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    (settings.log_dir / f"sleep_payload_{ts}.json").write_text(json.dumps(payload, indent=2))
    log.info("[webhook/apple-health-sleep] payload logged to sleep_payload_%s.json", ts)

    dates = apple_health._detect_all_dates(payload)
    if not dates:
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
            database.upsert_snapshot_apple_health(target_date, sleep_fields, user_id=uid)
            total_fields += len(sleep_fields)
            log.info("[webhook/apple-health-sleep] %d sleep fields for %s (user %d): %s",
                     len(sleep_fields), target_date, uid, sleep_fields)
        else:
            log.info("[webhook/apple-health-sleep] no sleep data for %s", target_date)

    return {"status": "ok", "dates": sorted(dates), "sleep_fields": total_fields,
            "note": "raw payload saved to logs/"}


# ---------------------------------------------------------------------------
# Legacy routes — keep until Health Auto Export is reconfigured with token URL
# ---------------------------------------------------------------------------

@router.post("/webhook/apple-health")
async def webhook_apple_health_metrics(
    request: Request,
    authorization: Optional[str] = Header(None),
    _rl: None = Depends(webhook_limiter),
):
    _verify_bearer(authorization)
    uid = _owner_user_id()
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
        fields = apple_health.ingest_metrics(payload, target_date, user_id=uid)
        total_fields += len(fields)
        log.info("[webhook/apple-health] %d fields ingested for %s", len(fields), target_date)
    return {"status": "ok", "dates": sorted(dates), "fields_ingested": total_fields}


@router.post("/webhook/apple-health-workouts")
async def webhook_apple_health_workouts(
    request: Request,
    authorization: Optional[str] = Header(None),
    _rl: None = Depends(webhook_limiter),
):
    _verify_bearer(authorization)
    uid = _owner_user_id()
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
        workouts = apple_health.ingest_workouts(payload, target_date, user_id=uid)
        total_workouts += len(workouts)
        log.info("[webhook/apple-health-workouts] %d workouts ingested for %s",
                 len(workouts), target_date)
    return {"status": "ok", "dates": sorted(dates), "workouts_ingested": total_workouts}


@router.post("/webhook/apple-health-sleep")
async def webhook_apple_health_sleep(
    request: Request,
    authorization: Optional[str] = Header(None),
    _rl: None = Depends(webhook_limiter),
):
    """Ingest sleep_analysis payloads, log raw JSON, upsert sleep columns."""
    _verify_bearer(authorization)
    uid = _owner_user_id()
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    (settings.log_dir / f"sleep_payload_{ts}.json").write_text(json.dumps(payload, indent=2))
    log.info("[webhook/apple-health-sleep] payload logged to sleep_payload_%s.json", ts)

    dates = apple_health._detect_all_dates(payload)
    if not dates:
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
            database.upsert_snapshot_apple_health(target_date, sleep_fields, user_id=uid)
            total_fields += len(sleep_fields)
            log.info("[webhook/apple-health-sleep] %d sleep fields for %s: %s",
                     len(sleep_fields), target_date, sleep_fields)
        else:
            log.info("[webhook/apple-health-sleep] no sleep data for %s", target_date)

    return {"status": "ok", "dates": sorted(dates), "sleep_fields": total_fields,
            "note": "raw payload saved to logs/"}
