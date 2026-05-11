"""
APScheduler setup and nightly jobs.

Schedule (America/Toronto):
  02:00 — nightly_hevy_poll()       fetch Hevy workouts + body weight, enrich with
                                    muscle groups, write to daily_snapshot, compute
                                    recovery status, populate daily_records.
  03:00 — nightly_claude_analysis() analyze YESTERDAY (skip if already done).
                                    By 3am all Apple Health webhooks have arrived and
                                    the Hevy poll has completed.

The frontend always shows yesterday's completed analysis, so there is no
intra-day re-analysis job.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database
import hevy
import muscle_map

log = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("America/Toronto")

ALL_MUSCLES = [
    "chest", "shoulders", "triceps",
    "lats", "upper_back", "biceps", "forearms", "traps",
    "quadriceps", "hamstrings", "glutes", "calves",
    "abdominals", "lower_back",
]


def _local_today() -> str:
    return datetime.now(LOCAL_TZ).date().isoformat()


def compute_recovery_status(target_date: str) -> dict[str, dict]:
    """
    For each muscle group, find the last date it received any volume,
    then compute days_since_trained and recovery_pct.

    Recovery is linear: 0 % immediately after training, 100 % at 72 h (3 days).
    Looks back up to 14 days. Muscles with no data in that window are
    treated as fully recovered.
    """
    from_date = (date.fromisoformat(target_date) - timedelta(days=14)).isoformat()
    snapshots = database.get_snapshots(from_date, target_date)

    last_trained: dict[str, date] = {}
    for snap in snapshots:
        snap_date = date.fromisoformat(snap["date"])
        muscle_volume = snap.get("muscle_volume") or {}
        for muscle, volume in muscle_volume.items():
            if volume and volume > 0:
                if muscle not in last_trained or snap_date > last_trained[muscle]:
                    last_trained[muscle] = snap_date

    target = date.fromisoformat(target_date)
    result: dict[str, dict] = {}
    for muscle in ALL_MUSCLES:
        if muscle in last_trained:
            days = (target - last_trained[muscle]).days
            recovery_pct = min(100, round((days / 3) * 100))
        else:
            days = 14
            recovery_pct = 100
        result[muscle] = {"days_since_trained": days, "recovery_pct": recovery_pct}
    return result


def _enrich_workouts(raw_workouts: list[dict]) -> list[dict]:
    """Attach primary_muscle_group, secondary_muscle_groups, and type to each
    exercise via the SQLite exercise_templates lookup."""
    enriched = []
    with database.get_sqlite() as conn:
        for workout in raw_workouts:
            enriched_exercises = []
            for ex in workout.get("exercises") or []:
                template_id = ex.get("exercise_template_id")
                mg = muscle_map.get_muscle_groups(template_id, conn) if template_id else {
                    "primary": "unknown", "secondary": [], "type": "weight_reps"
                }
                enriched_exercises.append({
                    **ex,
                    "primary_muscle_group":    mg["primary"],
                    "secondary_muscle_groups": mg["secondary"],
                    "type":                    mg["type"],
                })
            enriched.append({**workout, "source": "hevy", "exercises": enriched_exercises})
    return enriched


async def nightly_hevy_poll() -> None:
    """
    Runs at 02:00 local time.

    1. Fetch workouts (last 24 h) and latest body weight from Hevy API.
    2. Save raw payloads to DuckDB.
    3. Enrich exercises with muscle groups from exercise_templates.
    4. Compute aggregate muscle volume for the day.
    5. Write to daily_snapshot via upsert_snapshot_hevy().
    6. Compute and store recovery status snapshot.
    7. If snapshot is now complete (Apple Health also arrived):
       - Populate daily_records with metrics + workout data.
       - Log that Claude analysis can now run.
    """
    today = _local_today()
    log.info("[hevy_poll] starting for %s", today)

    try:
        body_weight_kg = await hevy.fetch_latest_body_weight()
        raw_workouts = await hevy.fetch_workouts_since()
    except Exception:
        log.exception("[hevy_poll] Hevy API fetch failed — aborting poll")
        return

    log.info("[hevy_poll] fetched %d workout(s), body_weight=%.2f kg",
             len(raw_workouts), body_weight_kg or 0)

    # Raw blob — errors swallowed inside append_raw_blob
    database.append_raw_blob(
        "raw_hevy_workouts", today,
        {"workouts": raw_workouts, "body_weight_kg": body_weight_kg},
    )

    enriched = _enrich_workouts(raw_workouts)

    for workout in enriched:
        workout_id = workout.get("id")
        if workout_id:
            database.upsert_workout_sets(workout_id, workout.get("exercises") or [])
            log.info("[hevy_poll] sets stored for workout %s (%s)", workout_id, workout.get("title"))

    daily_volume = muscle_map.aggregate_daily_volume(enriched, body_weight_kg)
    log.info("[hevy_poll] muscle volume: %s",
             ", ".join(f"{m}:{v:.0f}" for m, v in sorted(daily_volume.items(), key=lambda x: -x[1])))

    snapshot_complete = database.upsert_snapshot_hevy(
        today, body_weight_kg, daily_volume, enriched
    )

    recovery = compute_recovery_status(today)
    database.upsert_snapshot_recovery_status(today, recovery)

    # Populate daily_records whenever the snapshot is complete and the row is missing.
    # Checking the record here (not just snapshot_complete) handles the crash-recovery
    # case where snapshot_complete was set 1 but upsert_daily_record_snapshot never ran.
    snapshot = database.get_snapshot(today)
    if snapshot and snapshot.get("snapshot_complete"):
        if database.get_daily_record(today) is None:
            database.upsert_daily_record_snapshot(today, snapshot)
            log.info("[hevy_poll] daily_records populated for %s — ready for Claude", today)
        else:
            log.info("[hevy_poll] daily_records already present for %s", today)
    else:
        log.info("[hevy_poll] snapshot not yet complete for %s (Apple Health pending)", today)


async def nightly_claude_analysis() -> None:
    """
    Runs at 03:00 local time — analyzes YESTERDAY's date.

    By 3am all of the previous day's Apple Health webhooks have arrived.
    Skips if no snapshot exists or analysis already ran (force=False).
    """
    import claude_analysis

    yesterday = (datetime.now(LOCAL_TZ).date() - timedelta(days=1)).isoformat()
    log.info("[claude_analysis] nightly job starting for %s", yesterday)

    snapshot = database.get_snapshot(yesterday)
    if not snapshot:
        log.info("[claude_analysis] no snapshot for %s — skipping", yesterday)
        return

    rec = database.get_daily_record(yesterday)
    if rec and rec.get("analysis", {}).get("scores", {}).get("overall") is not None:
        log.info("[claude_analysis] analysis already exists for %s — skipping", yesterday)
        return

    # Always recompute recovery and attach soreness check-in before analysis.
    snapshot["recovery_status"] = compute_recovery_status(yesterday)
    snapshot["soreness"] = database.get_soreness_for_date(yesterday)

    baselines = database.get_metric_baselines(30)
    history   = database.get_weekly_summary(yesterday)
    try:
        parsed, raw = claude_analysis.run_analysis(yesterday, snapshot, baselines, history)
        database.upsert_daily_record_analysis(yesterday, parsed, raw, force=False)
        log.info("[claude_analysis] nightly analysis written for %s (overall=%s)",
                 yesterday, parsed.get("scores", {}).get("overall"))
    except Exception:
        log.exception("[claude_analysis] nightly analysis failed for %s", yesterday)


async def backfill_hevy(since_days: int = 7) -> dict[str, int]:
    """
    Fetch Hevy workouts from the past N days and write each workout to the
    snapshot matching its actual start date (not today). Used to recover
    missed workouts when the nightly poll was skipped.

    Returns {date: workout_count} for every date written.
    """
    since = datetime.now(timezone.utc) - timedelta(days=since_days)
    log.info("[hevy_backfill] fetching workouts since %s (%d days)", since.date(), since_days)

    try:
        body_weight_kg = await hevy.fetch_latest_body_weight()
        raw_workouts   = await hevy.fetch_workouts_since(since=since)
    except Exception:
        log.exception("[hevy_backfill] Hevy API fetch failed")
        raise

    log.info("[hevy_backfill] fetched %d workout(s)", len(raw_workouts))

    # Group by actual workout date in local timezone
    by_date: dict[str, list[dict]] = {}
    for workout in raw_workouts:
        start_str = workout.get("start_time", "")
        try:
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            date_str = start_dt.astimezone(LOCAL_TZ).date().isoformat()
        except (ValueError, AttributeError):
            log.warning("[hevy_backfill] could not parse start_time %r — skipping", start_str)
            continue
        by_date.setdefault(date_str, []).append(workout)

    results: dict[str, int] = {}
    for date_str, workouts in sorted(by_date.items()):
        enriched = _enrich_workouts(workouts)

        for workout in enriched:
            workout_id = workout.get("id")
            if workout_id:
                database.upsert_workout_sets(workout_id, workout.get("exercises") or [])

        daily_volume = muscle_map.aggregate_daily_volume(enriched, body_weight_kg)
        database.upsert_snapshot_hevy(date_str, body_weight_kg, daily_volume, enriched)

        recovery = compute_recovery_status(date_str)
        database.upsert_snapshot_recovery_status(date_str, recovery)

        results[date_str] = len(workouts)
        log.info("[hevy_backfill] wrote %d workout(s) to %s", len(workouts), date_str)

    # Recompute recovery for today and yesterday — these depend on the historical
    # workout data we just wrote and their cached recovery_status is now stale.
    today     = _local_today()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    for d in (yesterday, today):
        if database.get_snapshot(d):
            refreshed = compute_recovery_status(d)
            database.upsert_snapshot_recovery_status(d, refreshed)
            log.info("[hevy_backfill] refreshed recovery_status for %s", d)

    return results


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=LOCAL_TZ)

    # 02:00 — Hevy workout poll (fetch yesterday's workouts, enrich, store)
    scheduler.add_job(nightly_hevy_poll, "cron", hour=2, minute=0,
                      id="nightly_hevy_poll", replace_existing=True)

    # 03:00 — Analyze yesterday (skip if already done; data guaranteed complete by 3am)
    scheduler.add_job(nightly_claude_analysis, "cron", hour=3, minute=0,
                      id="nightly_claude_analysis", replace_existing=True)

    return scheduler
