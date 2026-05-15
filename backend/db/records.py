"""
daily_records read/write — two-phase write: snapshot metrics first, analysis second.
"""

import json
import logging

from db.connection import get_sqlite

log = logging.getLogger(__name__)


def upsert_daily_record_snapshot(date: str, snapshot: dict, user_id: int | None = None) -> None:
    """Write the metrics + workout portion of daily_records when snapshot completes.

    Called as soon as both Apple Health and Hevy data have arrived — before
    Claude runs. Claude analysis fields are NULL until upsert_daily_record_analysis()
    fills them in. Safe to call multiple times (idempotent on non-Claude fields).
    """
    snap = snapshot or {}
    workouts: list[dict] = snap.get("workouts") or []
    workout_names = [w.get("name") or w.get("title") for w in workouts
                     if w.get("name") or w.get("title")]
    muscle_volume: dict = snap.get("muscle_volume") or {}
    top_muscle = max(muscle_volume, key=muscle_volume.get) if muscle_volume else None
    total_volume = round(sum(muscle_volume.values()), 2) if muscle_volume else None

    with get_sqlite() as conn:
        conn.execute(
            """
            INSERT INTO daily_records (
                date, user_id,
                steps, active_calories, basal_calories, resting_hr, hrv_ms,
                cardio_recovery, exercise_minutes, stand_hours, distance_mi,
                flights_climbed, body_weight_kg, avg_heart_rate, walking_hr_avg,
                sleep_total_min, sleep_deep_min, sleep_rem_min, sleep_awake_min,
                workout_count, workout_names, muscle_volume, top_muscle_group,
                total_volume_kg, recovery_status
            ) VALUES (
                ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(date) DO UPDATE SET
                user_id         = COALESCE(daily_records.user_id, excluded.user_id),
                steps           = excluded.steps,
                active_calories = excluded.active_calories,
                basal_calories  = excluded.basal_calories,
                resting_hr      = excluded.resting_hr,
                hrv_ms          = excluded.hrv_ms,
                cardio_recovery = excluded.cardio_recovery,
                exercise_minutes = excluded.exercise_minutes,
                stand_hours     = excluded.stand_hours,
                distance_mi     = excluded.distance_mi,
                flights_climbed = excluded.flights_climbed,
                body_weight_kg  = excluded.body_weight_kg,
                avg_heart_rate  = excluded.avg_heart_rate,
                walking_hr_avg  = excluded.walking_hr_avg,
                sleep_total_min = excluded.sleep_total_min,
                sleep_deep_min  = excluded.sleep_deep_min,
                sleep_rem_min   = excluded.sleep_rem_min,
                sleep_awake_min = excluded.sleep_awake_min,
                workout_count   = excluded.workout_count,
                workout_names   = excluded.workout_names,
                muscle_volume   = excluded.muscle_volume,
                top_muscle_group = excluded.top_muscle_group,
                total_volume_kg = excluded.total_volume_kg,
                recovery_status = excluded.recovery_status
            """,
            (
                date, user_id,
                snap.get("steps"), snap.get("active_calories"), snap.get("basal_calories"),
                snap.get("resting_hr"), snap.get("hrv_ms"), snap.get("cardio_recovery"),
                snap.get("exercise_minutes"), snap.get("stand_hours"), snap.get("distance_mi"),
                snap.get("flights_climbed"), snap.get("body_weight_kg"),
                snap.get("avg_heart_rate"), snap.get("walking_hr_avg"),
                snap.get("sleep_total_min"), snap.get("sleep_deep_min"),
                snap.get("sleep_rem_min"), snap.get("sleep_awake_min"),
                len(workouts),
                json.dumps(workout_names) if workout_names else None,
                json.dumps(muscle_volume) if muscle_volume else None,
                top_muscle, total_volume,
                json.dumps(snap.get("recovery_status")) if snap.get("recovery_status") else None,
            ),
        )
    log.info("daily_records snapshot written for %s", date)


def upsert_daily_record_analysis(
    date: str,
    parsed: dict,
    raw: str,
    history_days: int | None = None,
    force: bool = False,
    user_id: int | None = None,
) -> None:
    """Fill in Claude's analysis fields on an existing daily_records row.

    force=True  — always overwrite (used by /api/analyze endpoint and 4-h cron).
    force=False — skip if score_overall is already set (used by nightly job).
    """
    scores = parsed.get("scores", {})
    where_clause = "" if force else "WHERE daily_records.score_overall IS NULL"
    with get_sqlite() as conn:
        cursor = conn.execute(
            f"""
            INSERT INTO daily_records (
                date, user_id, muscle_fatigue,
                score_overall, score_training, score_recovery,
                score_balance, score_consistency,
                summary, critique, callout, history_days, raw_response
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                user_id           = COALESCE(daily_records.user_id, excluded.user_id),
                muscle_fatigue    = excluded.muscle_fatigue,
                score_overall     = excluded.score_overall,
                score_training    = excluded.score_training,
                score_recovery    = excluded.score_recovery,
                score_balance     = excluded.score_balance,
                score_consistency = excluded.score_consistency,
                summary           = excluded.summary,
                critique          = excluded.critique,
                callout           = excluded.callout,
                history_days      = excluded.history_days,
                raw_response      = excluded.raw_response
            {where_clause}
            """,
            (
                date, user_id,
                json.dumps(parsed.get("muscle_fatigue")) if parsed.get("muscle_fatigue") is not None else None,
                scores.get("overall"),
                scores.get("training_quality"),
                scores.get("recovery"),
                scores.get("volume_balance"),
                scores.get("consistency"),
                parsed.get("summary"),
                json.dumps(parsed.get("critique")) if parsed.get("critique") is not None else None,
                parsed.get("callout"),
                history_days,
                raw,
            ),
        )
    if cursor.rowcount == 0:
        log.info("daily_records analysis already set for %s — skipping", date)
    else:
        log.info("daily_records analysis written for %s (force=%s)", date, force)


def get_daily_record(date: str, user_id: int | None = None) -> dict | None:
    """Return a daily_records row structured with nested subfields, or None."""
    uid_clause = " AND user_id = ?" if user_id is not None else ""
    uid_params = (user_id,) if user_id is not None else ()
    with get_sqlite() as conn:
        row = conn.execute(
            f"SELECT * FROM daily_records WHERE date = ?{uid_clause}",
            (date,) + uid_params,
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    for key in ("critique", "muscle_fatigue", "workout_names", "muscle_volume", "recovery_status"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return {
        "date": d["date"],
        "metrics": {k: d.get(k) for k in (
            "steps", "active_calories", "basal_calories", "resting_hr",
            "hrv_ms", "cardio_recovery", "exercise_minutes", "stand_hours",
            "distance_mi", "flights_climbed", "body_weight_kg",
            "avg_heart_rate", "walking_hr_avg",
            "sleep_total_min", "sleep_deep_min", "sleep_rem_min", "sleep_awake_min",
        )},
        "workouts": {
            "count":            d.get("workout_count"),
            "names":            d.get("workout_names"),
            "muscle_volume":    d.get("muscle_volume"),
            "top_muscle_group": d.get("top_muscle_group"),
            "total_volume_kg":  d.get("total_volume_kg"),
            "muscle_fatigue":   d.get("muscle_fatigue"),
            "recovery_status":  d.get("recovery_status"),
        },
        "analysis": {
            "scores": {
                "overall":          d.get("score_overall"),
                "training_quality": d.get("score_training"),
                "recovery":         d.get("score_recovery"),
                "volume_balance":   d.get("score_balance"),
                "consistency":      d.get("score_consistency"),
            },
            "summary":      d.get("summary"),
            "critique":     d.get("critique"),
            "callout":      d.get("callout"),
            "history_days": d.get("history_days"),
            "raw_response": d.get("raw_response"),
        },
        "created_at": d.get("created_at"),
    }


def get_score_history(days: int = 30, user_id: int | None = None) -> list[dict]:
    """Return the last N days of score columns for ScoreChart.jsx."""
    uid_clause = " AND user_id = ?" if user_id is not None else ""
    uid_params = (user_id,) if user_id is not None else ()
    with get_sqlite() as conn:
        rows = conn.execute(
            f"""
            SELECT date,
                   score_overall     AS overall,
                   score_training    AS training_quality,
                   score_recovery    AS recovery,
                   score_balance     AS volume_balance,
                   score_consistency AS consistency
            FROM (
                SELECT date, score_overall, score_training, score_recovery,
                       score_balance, score_consistency, user_id
                FROM daily_records
                WHERE score_overall IS NOT NULL{uid_clause}
                ORDER BY date DESC
                LIMIT ?
            )
            ORDER BY date ASC
            """,
            uid_params + (days,),
        ).fetchall()
    return [dict(r) for r in rows]
