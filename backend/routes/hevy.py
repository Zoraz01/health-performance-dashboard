import logging

from fastapi import APIRouter, Depends, Query

import database
import scheduler as sched
from deps import get_current_user
from rate_limit import hevy_limiter

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/hevy/poll")
async def trigger_hevy_poll(
    _: dict = Depends(get_current_user),
    __: None = Depends(hevy_limiter),
):
    log.info("[api] manual Hevy poll triggered")
    await sched.nightly_hevy_poll()
    return {"status": "ok", "message": "Hevy poll completed"}


@router.post("/api/hevy/backfill")
async def trigger_hevy_backfill(
    days: int = Query(default=7, ge=1, le=30),
    _: dict = Depends(get_current_user),
    __: None = Depends(hevy_limiter),
):
    log.info("[api] Hevy backfill triggered (last %d days)", days)
    results = await sched.backfill_hevy(since_days=days)
    return {"status": "ok", "days_requested": days, "dates_written": results}


@router.post("/api/workouts/dedup")
async def dedup_workouts(_: dict = Depends(get_current_user)):
    log.info("[api] workout cross-source dedup backfill triggered")
    changed = database.dedup_existing_workouts()
    return {"status": "ok", "dates_changed": len(changed), "details": changed}
