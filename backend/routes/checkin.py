import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

import database
import scheduler as sched
from deps import get_current_user

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/soreness")
async def get_soreness(date: Optional[str] = None, user: dict = Depends(get_current_user)):
    uid = user["id"]
    with database.get_sqlite() as conn:
        if date:
            rows = conn.execute(
                "SELECT * FROM soreness_log WHERE date = ? AND user_id = ? ORDER BY logged_at DESC",
                (date, uid),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM soreness_log WHERE user_id = ? ORDER BY date DESC, logged_at DESC LIMIT 100",
                (uid,),
            ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/soreness")
async def log_soreness(request: Request, user: dict = Depends(get_current_user)):
    body     = await request.json()
    date     = body.get("date")
    muscle   = body.get("muscle")
    soreness = body.get("soreness")

    if not date or not muscle or soreness is None:
        raise HTTPException(
            status_code=400, detail="date, muscle, and soreness are required"
        )
    if muscle not in sched.ALL_MUSCLES:
        raise HTTPException(
            status_code=400, detail=f"Invalid muscle '{muscle}'. Must be one of: {', '.join(sched.ALL_MUSCLES)}"
        )
    try:
        soreness_int = int(soreness)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="soreness must be an integer")
    if not 0 <= soreness_int <= 5:
        raise HTTPException(status_code=400, detail="soreness must be 0–5")

    with database.get_sqlite() as conn:
        conn.execute(
            "INSERT INTO soreness_log (date, muscle, soreness, user_id) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(date, muscle) DO UPDATE SET "
            "soreness = excluded.soreness, logged_at = CURRENT_TIMESTAMP",
            (date, muscle, soreness_int, user["id"]),
        )
    log.info("[api/soreness] %s → %s = %d", date, muscle, soreness_int)
    return {"status": "ok", "date": date, "muscle": muscle, "soreness": soreness_int}


@router.get("/api/checkin/today")
async def get_today_checkin(date: Optional[str] = None, user: dict = Depends(get_current_user)):
    uid      = user["id"]
    target   = date or datetime.now(sched.LOCAL_TZ).date().isoformat()
    soreness = database.get_soreness_for_date(target, user_id=uid)
    snapshot = database.get_snapshot(target, user_id=uid) or {}
    note     = (snapshot.get("notes") or "").strip()
    if not soreness and not note:
        return {"checked_in": False, "date": target}
    return {"checked_in": True, "date": target, "soreness": soreness, "note": note}


@router.post("/api/checkin")
async def submit_checkin(request: Request, user: dict = Depends(get_current_user)):
    """Accept a check-in submission.
    Body: { date, soreness: {muscle: 0-5, ...}, note: str, force?: bool }
    Without force, first submission wins. With force=true, overwrites existing.
    """
    uid      = user["id"]
    body     = await request.json()
    date     = body.get("date")
    soreness = body.get("soreness") or {}
    note     = (body.get("note") or "").strip()
    force    = bool(body.get("force", False))

    if not date:
        raise HTTPException(status_code=400, detail="date is required")

    if not force:
        existing_soreness = database.get_soreness_for_date(date, user_id=uid)
        existing_snapshot = database.get_snapshot(date, user_id=uid) or {}
        existing_note     = (existing_snapshot.get("notes") or "").strip()
        if existing_soreness or existing_note:
            return {"status": "already_checked_in", "date": date}

    with database.get_sqlite() as conn:
        for muscle, value in soreness.items():
            if muscle not in sched.ALL_MUSCLES:
                continue
            try:
                val = int(value)
            except (TypeError, ValueError):
                continue
            if not 0 <= val <= 5:
                continue
            conn.execute(
                "INSERT INTO soreness_log (date, muscle, soreness, user_id) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(date, muscle) DO UPDATE SET "
                "soreness = excluded.soreness, logged_at = CURRENT_TIMESTAMP",
                (date, muscle, val, uid),
            )

    database.upsert_snapshot_notes(date, note, user_id=uid)

    log.info("[api/checkin] %s — %d muscle(s), note=%s, force=%s", date, len(soreness), bool(note), force)
    return {"status": "ok", "date": date,
            "muscles_logged": len(soreness), "note_saved": bool(note)}
