"""
APScheduler setup and scheduled jobs.

Schedule (America/Toronto):
  02:00 / 08:00 / 14:00 / 20:00
        — nightly_hevy_poll()       fetch last 24h of Hevy workouts + body weight,
                                    enrich with muscle groups, write to daily_snapshot,
                                    compute recovery status, populate daily_records.
                                    Upserts are idempotent — safe to run 4× per day.
  03:00 — nightly_claude_analysis() analyze YESTERDAY (skip if already done).
                                    By 3am all Apple Health webhooks have arrived and
                                    the 02:00 Hevy poll has completed.

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
from config import settings

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


def _get_owner_user_id() -> int | None:
    """Return the owner's local DB user ID, or None if not yet registered."""
    if not settings.owner_email:
        return None
    owner = database.get_user_by_email(settings.owner_email)
    return owner["id"] if owner else None


def compute_recovery_status(target_date: str, user_id: int | None = None) -> dict[str, dict]:
    """
    For each muscle group, compute days_since_trained and recovery_pct.

    Recovery window scales with volume intensity relative to the 14-day peak
    for that muscle:
      intensity ≈ 1.0 (full primary session) → 3 days to full recovery
      intensity ≈ 0.1 (secondary/spillover)  → ~0.75 days to full recovery
      Formula: recovery_days = 0.5 + intensity * 2.5  (range 0.5–3.0)

    This prevents a muscle from showing 0% recovery just because it appeared
    as a secondary group in an unrelated session (e.g. back during leg day).
    """
    from_date = (date.fromisoformat(target_date) - timedelta(days=14)).isoformat()
    snapshots = database.get_snapshots(from_date, target_date, user_id=user_id)

    last_trained: dict[str, date] = {}
    last_volume:  dict[str, float] = {}
    max_volume:   dict[str, float] = {}
    for snap in snapshots:
        snap_date = date.fromisoformat(snap["date"])
        muscle_volume = snap.get("muscle_volume") or {}
        for muscle, volume in muscle_volume.items():
            if volume and volume > 0:
                vol = float(volume)
                if muscle not in last_trained or snap_date > last_trained[muscle]:
                    last_trained[muscle] = snap_date
                    last_volume[muscle]  = vol
                max_volume[muscle] = max(max_volume.get(muscle, 0.0), vol)

    target = date.fromisoformat(target_date)
    result: dict[str, dict] = {}
    for muscle in ALL_MUSCLES:
        if muscle in last_trained:
            days = (target - last_trained[muscle]).days
            vol  = last_volume.get(muscle, 0.0)
            peak = max_volume.get(muscle) or vol or 1.0
            # Fraction of the heaviest session this muscle has seen in 14 days.
            # Secondary hits (0.4× multiplier in muscle_map) typically land at 0.1–0.4.
            intensity     = min(1.0, vol / peak)
            recovery_days = 0.5 + intensity * 2.5
            recovery_pct  = min(100, round((days / recovery_days) * 100))
        else:
            days = 14
            recovery_pct = 100
        result[muscle] = {"days_since_trained": days, "recovery_pct": recovery_pct}
    return result


def _enrich_workouts(raw_workouts: list[dict]) -> list[dict]:
    """Attach muscle groups, type, and computed duration_min to each workout."""
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
            entry = {**workout, "source": "hevy", "exercises": enriched_exercises}
            # Compute duration from start/end timestamps (Hevy API doesn't provide it)
            try:
                start_dt = datetime.fromisoformat(workout["start_time"].replace("Z", "+00:00"))
                end_dt   = datetime.fromisoformat(workout["end_time"].replace("Z", "+00:00"))
                entry["duration_min"] = round((end_dt - start_dt).total_seconds() / 60, 1)
            except (KeyError, ValueError, AttributeError):
                pass
            enriched.append(entry)
    return enriched


async def nightly_hevy_poll() -> None:
    """
    Runs at 02:00 local time.

    Fetches the last 24 h of Hevy workouts, groups them by their actual
    workout date (not the poll date), and writes each group to the correct
    daily_snapshot. This handles workouts that happen after the previous 2am
    poll — they are correctly attributed to the day they occurred rather than
    the day the next poll runs.

    Today always gets a hevy_at stamp (even if no workouts happened) so the
    snapshot_complete flag can trigger once Apple Health data arrives.
    """
    today = _local_today()
    log.info("[hevy_poll] starting for %s", today)

    owner_user_id = _get_owner_user_id()
    if owner_user_id is None:
        log.warning("[hevy_poll] owner not yet registered — skipping user-scoped writes")

    try:
        body_weight_kg = await hevy.fetch_latest_body_weight()
        raw_workouts = await hevy.fetch_workouts_since()
    except Exception:
        log.exception("[hevy_poll] Hevy API fetch failed — aborting poll")
        return

    log.info("[hevy_poll] fetched %d workout(s), body_weight=%.2f kg",
             len(raw_workouts), body_weight_kg or 0)

    database.append_raw_blob(
        "raw_hevy_workouts", today,
        {"workouts": raw_workouts, "body_weight_kg": body_weight_kg},
    )

    # Group workouts by their actual local workout date, not the poll date.
    by_date: dict[str, list[dict]] = {}
    for workout in raw_workouts:
        start_str = workout.get("start_time", "")
        try:
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            date_str = start_dt.astimezone(LOCAL_TZ).date().isoformat()
        except (ValueError, AttributeError):
            log.warning("[hevy_poll] unparseable start_time %r — skipping workout", start_str)
            continue
        by_date.setdefault(date_str, []).append(workout)

    # Always stamp today so snapshot_complete can trigger when Apple Health arrives,
    # even on rest days when no workouts fell in the 24h window.
    if today not in by_date:
        by_date[today] = []

    for date_str, date_workouts in sorted(by_date.items()):
        enriched = _enrich_workouts(date_workouts)

        for workout in enriched:
            workout_id = workout.get("id")
            if workout_id:
                database.upsert_workout_sets(workout_id, workout.get("exercises") or [])
                log.info("[hevy_poll] sets stored for workout %s (%s)", workout_id, workout.get("title"))

        daily_volume = muscle_map.aggregate_daily_volume(enriched, body_weight_kg)
        if daily_volume:
            log.info("[hevy_poll] %s muscle volume: %s", date_str,
                     ", ".join(f"{m}:{v:.0f}" for m, v in sorted(daily_volume.items(), key=lambda x: -x[1])))

        database.upsert_snapshot_hevy(date_str, body_weight_kg, daily_volume, enriched, user_id=owner_user_id)

        recovery = compute_recovery_status(date_str, user_id=owner_user_id)
        database.upsert_snapshot_recovery_status(date_str, recovery, user_id=owner_user_id)

        snapshot = database.get_snapshot(date_str, user_id=owner_user_id)
        if snapshot and snapshot.get("snapshot_complete"):
            if database.get_daily_record(date_str, user_id=owner_user_id) is None:
                database.upsert_daily_record_snapshot(date_str, snapshot, user_id=owner_user_id)
                log.info("[hevy_poll] daily_records populated for %s — ready for Claude", date_str)
            else:
                log.info("[hevy_poll] daily_records already present for %s", date_str)
        else:
            log.info("[hevy_poll] snapshot not yet complete for %s (Apple Health pending)", date_str)


async def nightly_claude_analysis() -> None:
    """
    Runs at 03:00 local time — analyzes YESTERDAY's date.

    By 3am all of the previous day's Apple Health webhooks have arrived.
    Skips if no snapshot exists or analysis already ran (force=False).
    """
    import claude_analysis

    yesterday = (datetime.now(LOCAL_TZ).date() - timedelta(days=1)).isoformat()
    log.info("[claude_analysis] nightly job starting for %s", yesterday)

    owner_user_id = _get_owner_user_id()
    if owner_user_id is None:
        log.warning("[claude_analysis] owner not yet registered — skipping")
        return

    snapshot = database.get_snapshot(yesterday, user_id=owner_user_id)
    if not snapshot:
        log.info("[claude_analysis] no snapshot for %s — skipping", yesterday)
        return

    rec = database.get_daily_record(yesterday, user_id=owner_user_id)
    if rec and rec.get("analysis", {}).get("scores", {}).get("overall") is not None:
        log.info("[claude_analysis] analysis already exists for %s — skipping", yesterday)
        return

    # Always recompute recovery and attach soreness check-in before analysis.
    snapshot["recovery_status"] = compute_recovery_status(yesterday, user_id=owner_user_id)
    snapshot["soreness"] = database.get_soreness_for_date(yesterday, user_id=owner_user_id)

    baselines         = database.get_metric_baselines(30, user_id=owner_user_id)
    history           = database.get_weekly_summary(yesterday, user_id=owner_user_id)
    prev_date         = (date.fromisoformat(yesterday) - timedelta(days=1)).isoformat()
    prev_analysis     = database.get_daily_record(prev_date, user_id=owner_user_id)
    muscle_volume_30d = database.get_muscle_volume_30d(user_id=owner_user_id)
    try:
        parsed, raw = await claude_analysis.run_analysis(
            yesterday, snapshot, baselines, history, prev_analysis,
            muscle_volume_30d=muscle_volume_30d,
        )
        database.upsert_daily_record_analysis(yesterday, parsed, raw, force=False, user_id=owner_user_id)
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

    owner_user_id = _get_owner_user_id()
    if owner_user_id is None:
        log.warning("[hevy_backfill] owner not yet registered — writes will have NULL user_id")

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
        database.upsert_snapshot_hevy(date_str, body_weight_kg, daily_volume, enriched, user_id=owner_user_id)

        recovery = compute_recovery_status(date_str, user_id=owner_user_id)
        database.upsert_snapshot_recovery_status(date_str, recovery, user_id=owner_user_id)

        results[date_str] = len(workouts)
        log.info("[hevy_backfill] wrote %d workout(s) to %s", len(workouts), date_str)

    # Recompute recovery for today and yesterday — these depend on the historical
    # workout data we just wrote and their cached recovery_status is now stale.
    today     = _local_today()
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    for d in (yesterday, today):
        if database.get_snapshot(d, user_id=owner_user_id):
            refreshed = compute_recovery_status(d, user_id=owner_user_id)
            database.upsert_snapshot_recovery_status(d, refreshed, user_id=owner_user_id)
            log.info("[hevy_backfill] refreshed recovery_status for %s", d)

    return results


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=LOCAL_TZ)

    # 02:00 / 08:00 / 14:00 / 20:00 — Hevy workout poll (every 6h)
    scheduler.add_job(nightly_hevy_poll, "cron", hour="2,8,14,20", minute=0,
                      id="nightly_hevy_poll", replace_existing=True)

    # 03:00 — Analyze yesterday (skip if already done; data guaranteed complete by 3am)
    scheduler.add_job(nightly_claude_analysis, "cron", hour=3, minute=0,
                      id="nightly_claude_analysis", replace_existing=True)

    return scheduler
