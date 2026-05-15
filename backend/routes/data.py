import logging
from datetime import date as date_cls, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response

import database
import scheduler as sched
from deps import get_current_user

log = logging.getLogger(__name__)
router = APIRouter()


def _validate_date(date: str) -> str:
    try:
        date_cls.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid date: {date!r}. Expected YYYY-MM-DD.")
    return date


# ---------------------------------------------------------------------------
# Batch loading — three concurrent fetches replace /api/today
# ---------------------------------------------------------------------------

@router.get("/api/data/snapshots")
async def get_data_snapshots(response: Response, user: dict = Depends(get_current_user)):
    response.headers["Cache-Control"] = "private, max-age=300"
    uid = user["id"]
    today     = datetime.now(sched.LOCAL_TZ).date().isoformat()
    yesterday = (date_cls.fromisoformat(today) - timedelta(days=1)).isoformat()
    return {
        "date":               today,
        "snapshot":           database.get_snapshot(today, user_id=uid),
        "yesterday_snapshot": database.get_snapshot(yesterday, user_id=uid),
    }


@router.get("/api/data/record")
async def get_data_record(response: Response, user: dict = Depends(get_current_user)):
    response.headers["Cache-Control"] = "private, max-age=300"
    uid = user["id"]
    today     = datetime.now(sched.LOCAL_TZ).date().isoformat()
    yesterday = (date_cls.fromisoformat(today) - timedelta(days=1)).isoformat()
    record    = database.get_daily_record(today, user_id=uid) or database.get_daily_record(yesterday, user_id=uid)
    return {"record": record}


@router.get("/api/data/baselines")
async def get_data_baselines(response: Response, user: dict = Depends(get_current_user)):
    response.headers["Cache-Control"] = "private, max-age=300"
    return {"baselines": database.get_metric_baselines(30, user_id=user["id"])}


@router.get("/api/data/muscle-volume")
async def get_muscle_volume_30d(response: Response, user: dict = Depends(get_current_user)):
    response.headers["Cache-Control"] = "private, max-age=300"
    uid = user["id"]
    baselines, history_days = database.get_muscle_volume_baselines(user_id=uid)
    return {
        "muscle_volume": database.get_muscle_volume_30d(user_id=uid),
        "baselines":     baselines,
        "history_days":  history_days,
    }


# ---------------------------------------------------------------------------
# Date-parameterised reads (History + Trends tabs)
# ---------------------------------------------------------------------------

@router.get("/api/snapshot/{date}")
async def get_snapshot(date: str, user: dict = Depends(get_current_user)):
    _validate_date(date)
    row = database.get_snapshot(date, user_id=user["id"])
    if not row:
        raise HTTPException(status_code=404, detail=f"No snapshot for {date}")
    return row


@router.get("/api/snapshots")
async def get_snapshots(
    from_date: str      = Query(..., alias="from"),
    to_date: str        = Query(..., alias="to"),
    limit: int | None   = Query(default=None, ge=1, le=365),
    offset: int         = Query(default=0, ge=0),
    user: dict = Depends(get_current_user),
):
    _validate_date(from_date)
    _validate_date(to_date)
    return database.get_snapshots(from_date, to_date, limit=limit, offset=offset, user_id=user["id"])


@router.get("/api/record/{date}")
async def get_daily_record(date: str, user: dict = Depends(get_current_user)):
    _validate_date(date)
    row = database.get_daily_record(date, user_id=user["id"])
    if not row:
        raise HTTPException(status_code=404, detail=f"No record for {date}")
    return row


@router.get("/api/scores")
async def get_scores(
    days: int = Query(default=30, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    return database.get_score_history(days, user_id=user["id"])


@router.get("/api/activity")
async def get_activity_history(
    days: int = Query(default=30, ge=1, le=365),
    user: dict = Depends(get_current_user),
):
    return database.get_activity_history(days, user_id=user["id"])


@router.get("/api/timeseries/{date}")
async def get_daily_timeseries(
    date: str,
    metric: str = Query(default="heart_rate"),
    _: dict = Depends(get_current_user),
):
    _validate_date(date)
    samples = database.get_daily_timeseries(date, metric)
    return {"date": date, "metric": metric, "samples": samples}


# ---------------------------------------------------------------------------
# Workout timeseries
# ---------------------------------------------------------------------------

@router.get("/api/workout/{workout_id}/hr")
async def get_workout_hr(workout_id: str, _: dict = Depends(get_current_user)):
    samples = database.get_workout_hr_samples(workout_id)
    if not samples:
        raise HTTPException(status_code=404, detail="No HR samples for this workout")
    return {"workout_id": workout_id, "samples": samples}


@router.get("/api/workout/{workout_id}/sets")
async def get_workout_sets(workout_id: str, _: dict = Depends(get_current_user)):
    exercises = database.get_workout_sets(workout_id)
    if not exercises:
        raise HTTPException(status_code=404, detail="No set data for this workout")
    return {"workout_id": workout_id, "exercises": exercises}
