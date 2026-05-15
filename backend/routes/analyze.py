import logging
from datetime import date as date_cls, timedelta

from fastapi import APIRouter, Depends, HTTPException

import claude_analysis
import database
from deps import get_current_user
from rate_limit import analyze_limiter
from scheduler import compute_recovery_status, nightly_hevy_poll

log = logging.getLogger(__name__)
router = APIRouter()


def _validate_date(date: str) -> str:
    try:
        date_cls.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {date!r}. Expected YYYY-MM-DD.")
    return date


@router.post("/api/analyze/{date}")
async def trigger_analysis(
    date: str,
    user: dict = Depends(get_current_user),
    __: None = Depends(analyze_limiter),
):
    uid = user["id"]
    _validate_date(date)
    # Pull fresh Hevy data first so the analysis has up-to-date workout context.
    log.info("[api/analyze] pulling fresh Hevy data before analysis for %s", date)
    try:
        await nightly_hevy_poll()
    except Exception:
        log.warning("[api/analyze] Hevy poll failed — continuing with existing snapshot data")

    snapshot = database.get_snapshot(date, user_id=uid)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"No snapshot for {date}")

    # Always recompute recovery before analysis so the prompt reflects fresh data.
    fresh_recovery = compute_recovery_status(date, user_id=uid)
    database.upsert_snapshot_recovery_status(date, fresh_recovery, user_id=uid)
    snapshot["recovery_status"] = fresh_recovery

    snapshot["soreness"] = database.get_soreness_for_date(date, user_id=uid)

    baselines          = database.get_metric_baselines(30, user_id=uid)
    history            = database.get_weekly_summary(date, user_id=uid)
    prev_date          = (date_cls.fromisoformat(date) - timedelta(days=1)).isoformat()
    prev_analysis      = database.get_daily_record(prev_date, user_id=uid)
    muscle_volume_30d  = database.get_muscle_volume_30d(user_id=uid)

    try:
        parsed, raw = await claude_analysis.run_analysis(
            date, snapshot, baselines, history, prev_analysis,
            muscle_volume_30d=muscle_volume_30d,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        log.exception("[api/analyze] failed for %s: %s", date, e)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}")

    database.upsert_daily_record_analysis(date, parsed, raw, force=True, user_id=uid)
    log.info("[api/analyze] analysis written for %s", date)
    return {"status": "ok", "date": date, "analysis": parsed}
