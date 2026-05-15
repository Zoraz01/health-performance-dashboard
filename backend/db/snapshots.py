"""
Snapshot read/write — the primary write path for Apple Health and Hevy data.

Write paths:
  upsert_snapshot_apple_health()          — Apple Health metrics
  upsert_snapshot_apple_health_workouts() — Apple Health workouts column only
  upsert_snapshot_hevy()                  — Hevy muscle volume + workouts
  replace_workouts_for_source()           — merge helper used by both upsert paths

Never use INSERT OR REPLACE on daily_snapshot — it drops columns not in the statement.
"""

import json
import logging
import sqlite3
from datetime import datetime

from db.connection import get_sqlite, _now_iso
from db.schema import APPLE_HEALTH_COLUMNS

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cross-source workout deduplication
# ---------------------------------------------------------------------------

def _parse_workout_start(w: dict) -> datetime | None:
    """Parse start datetime from either a Hevy or Apple Health workout dict."""
    s = w.get("start_time") or w.get("start")
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.strptime(str(s), "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return None


def _cross_source_dedup(workouts: list[dict]) -> list[dict]:
    """
    Match apple_health entries to hevy entries whose start times are within
    5 minutes. When matched, stitch Apple Health biometrics (calories, HR)
    into the hevy entry and drop the apple_health entry.
    """
    hevy_entries = [w for w in workouts if w.get("source") == "hevy"]
    ah_entries   = [w for w in workouts if w.get("source") == "apple_health"]
    other        = [w for w in workouts if w.get("source") not in ("hevy", "apple_health")]

    if not hevy_entries or not ah_entries:
        return workouts

    absorbed: set[int] = set()
    for ah_idx, ah in enumerate(ah_entries):
        ah_dt = _parse_workout_start(ah)
        if ah_dt is None:
            continue
        for hevy_w in hevy_entries:
            hevy_dt = _parse_workout_start(hevy_w)
            if hevy_dt is None:
                continue
            if abs((ah_dt - hevy_dt).total_seconds()) <= 300:
                for field in ("active_calories", "avg_heart_rate", "max_heart_rate"):
                    if ah.get(field) is not None:
                        hevy_w[field] = ah[field]
                absorbed.add(ah_idx)
                log.info(
                    "[dedup] stitched apple_health '%s' → hevy '%s' (Δ%.0fs, %.0f kcal, avg %.0f bpm)",
                    ah.get("name"), hevy_w.get("title"),
                    abs((ah_dt - hevy_dt).total_seconds()),
                    ah.get("active_calories") or 0,
                    ah.get("avg_heart_rate") or 0,
                )
                break

    remaining_ah = [ah for i, ah in enumerate(ah_entries) if i not in absorbed]
    return other + hevy_entries + remaining_ah


def dedup_existing_workouts() -> dict[str, dict]:
    """
    One-shot backfill: apply cross-source dedup to every existing
    daily_snapshot.workouts row. Returns {date: {before, after}} for dates
    where the array actually changed.
    """
    with get_sqlite() as conn:
        rows = conn.execute(
            "SELECT date, workouts FROM daily_snapshot WHERE workouts IS NOT NULL"
        ).fetchall()

    changed: dict[str, dict] = {}
    with get_sqlite() as conn:
        for row in rows:
            date_str = row["date"]
            try:
                workouts = json.loads(row["workouts"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(workouts, list) or len(workouts) < 2:
                continue
            deduped = _cross_source_dedup(workouts)
            if len(deduped) != len(workouts):
                conn.execute(
                    "UPDATE daily_snapshot SET workouts = ? WHERE date = ?",
                    (json.dumps(deduped), date_str),
                )
                changed[date_str] = {"before": len(workouts), "after": len(deduped)}
                log.info(
                    "[dedup_backfill] %s: %d → %d workouts", date_str, len(workouts), len(deduped)
                )
    return changed


# ---------------------------------------------------------------------------
# Workout merge helper
# ---------------------------------------------------------------------------

def replace_workouts_for_source(
    conn: sqlite3.Connection, date: str, source: str, new_entries: list[dict],
    user_id: int | None = None,
) -> list[dict]:
    """Read the current workouts JSON for date, drop entries from source,
    append new_entries, cross-source dedup, write back. Returns merged list.

    Caller must already hold a get_sqlite() connection.
    """
    row = conn.execute(
        "SELECT workouts FROM daily_snapshot WHERE date = ?", (date,)
    ).fetchone()

    existing: list[dict] = []
    if row and row["workouts"]:
        try:
            existing = json.loads(row["workouts"])
        except (json.JSONDecodeError, TypeError):
            existing = []

    merged = [w for w in existing if w.get("source") != source] + new_entries
    merged = _cross_source_dedup(merged)

    conn.execute(
        "INSERT INTO daily_snapshot (date, user_id, workouts) VALUES (?, ?, ?) "
        "ON CONFLICT(date) DO UPDATE SET workouts = excluded.workouts, "
        "user_id = COALESCE(daily_snapshot.user_id, excluded.user_id)",
        (date, user_id, json.dumps(merged)),
    )
    return merged


# ---------------------------------------------------------------------------
# Snapshot completion check
# ---------------------------------------------------------------------------

def _maybe_complete(conn: sqlite3.Connection, date: str) -> bool:
    """Set snapshot_complete=1 if both apple_health_at and hevy_at are set.

    Single atomic UPDATE — avoids the SELECT+UPDATE TOCTOU race.
    Returns True only on the 0→1 transition so callers can queue Claude.
    """
    cursor = conn.execute(
        "UPDATE daily_snapshot SET snapshot_complete = 1 "
        "WHERE date = ? "
        "  AND apple_health_at IS NOT NULL "
        "  AND hevy_at IS NOT NULL "
        "  AND snapshot_complete = 0",
        (date,),
    )
    if cursor.rowcount == 1:
        log.info("snapshot complete for %s — ready for Claude", date)
        return True
    return False


# ---------------------------------------------------------------------------
# Partial upserts — the only legal write paths into daily_snapshot
# ---------------------------------------------------------------------------

def upsert_snapshot_apple_health(date: str, fields: dict, user_id: int | None = None) -> bool:
    """Write Apple-Health-derived metric fields and set apple_health_at.

    Returns True if this write completed the snapshot (triggers Claude).
    """
    fields = {k: v for k, v in fields.items() if k in APPLE_HEALTH_COLUMNS and v is not None}
    if not fields:
        log.warning("upsert_snapshot_apple_health: no valid fields for %s", date)
        return False

    cols = list(fields.keys()) + ["apple_health_at", "user_id"]
    placeholders = ", ".join("?" for _ in cols)
    update_clause = (
        ", ".join(f"{c} = excluded.{c}" for c in cols[:-1])
        + ", user_id = COALESCE(daily_snapshot.user_id, excluded.user_id)"
    )
    sql = (
        f"INSERT INTO daily_snapshot (date, {', '.join(cols)}) "
        f"VALUES (?, {placeholders}) "
        f"ON CONFLICT(date) DO UPDATE SET {update_clause}"
    )
    values = [date] + [fields[k] for k in fields] + [_now_iso(), user_id]

    with get_sqlite() as conn:
        conn.execute(sql, values)
        return _maybe_complete(conn, date)


def upsert_snapshot_apple_health_workouts(date: str, workouts: list[dict], user_id: int | None = None) -> None:
    """Merge Apple Health workout entries into the workouts column for date."""
    with get_sqlite() as conn:
        replace_workouts_for_source(conn, date, "apple_health", workouts, user_id=user_id)
    log.info("apple_health workouts upserted for %s (%d entries)", date, len(workouts))


def upsert_snapshot_recovery_status(date: str, recovery_status: dict, user_id: int | None = None) -> None:
    """Store the computed recovery status snapshot for date."""
    with get_sqlite() as conn:
        conn.execute(
            "INSERT INTO daily_snapshot (date, user_id, recovery_status) VALUES (?, ?, ?) "
            "ON CONFLICT(date) DO UPDATE SET recovery_status = excluded.recovery_status, "
            "user_id = COALESCE(daily_snapshot.user_id, excluded.user_id)",
            (date, user_id, json.dumps(recovery_status)),
        )
    log.info("recovery_status stored for %s", date)


def upsert_snapshot_notes(date: str, notes: str, user_id: int | None = None) -> None:
    """Store free-text check-in notes for date."""
    with get_sqlite() as conn:
        conn.execute(
            "INSERT INTO daily_snapshot (date, user_id, notes) VALUES (?, ?, ?) "
            "ON CONFLICT(date) DO UPDATE SET notes = excluded.notes, "
            "user_id = COALESCE(daily_snapshot.user_id, excluded.user_id)",
            (date, user_id, notes.strip()),
        )
    log.info("notes stored for %s", date)


def upsert_snapshot_hevy(
    date: str,
    body_weight_kg: float | None,
    muscle_volume: dict | None,
    workouts: list[dict],
    user_id: int | None = None,
) -> bool:
    """Write Hevy-derived fields and set hevy_at.

    body_weight_kg only overwrites if the column is currently NULL —
    Hevy is authoritative, Apple Health body_mass is the fallback.
    Returns True if this write completed the snapshot (triggers Claude).

    Both writes (metrics + workouts) run inside a single transaction so a
    crash between them cannot leave the snapshot row in a partial state.
    """
    sql = """
        INSERT INTO daily_snapshot
            (date, user_id, body_weight_kg, muscle_volume, hevy_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            body_weight_kg = COALESCE(daily_snapshot.body_weight_kg, excluded.body_weight_kg),
            muscle_volume  = excluded.muscle_volume,
            hevy_at        = excluded.hevy_at,
            user_id        = COALESCE(daily_snapshot.user_id, excluded.user_id)
    """
    with get_sqlite() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute(sql, (
                date,
                user_id,
                body_weight_kg,
                json.dumps(muscle_volume) if muscle_volume is not None else None,
                _now_iso(),
            ))
            replace_workouts_for_source(conn, date, "hevy", workouts, user_id=user_id)
            result = _maybe_complete(conn, date)
            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def get_snapshot(date: str, user_id: int | None = None) -> dict | None:
    """Return a single daily_snapshot row as a dict, or None."""
    with get_sqlite() as conn:
        if user_id is not None:
            row = conn.execute(
                "SELECT * FROM daily_snapshot WHERE date = ? AND user_id = ?", (date, user_id)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM daily_snapshot WHERE date = ?", (date,)
            ).fetchone()
    if not row:
        return None
    d = dict(row)
    for key in ("muscle_volume", "workouts", "recovery_status"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def get_snapshots(
    from_date: str,
    to_date: str,
    limit: int | None = None,
    offset: int = 0,
    user_id: int | None = None,
) -> list[dict]:
    """Return daily_snapshot rows between from_date and to_date inclusive.

    limit/offset enable pagination — omit limit for the full range.
    """
    uid_clause = " AND user_id = ?" if user_id is not None else ""
    uid_params = (user_id,) if user_id is not None else ()
    with get_sqlite() as conn:
        if limit is not None:
            rows = conn.execute(
                f"SELECT * FROM daily_snapshot WHERE date BETWEEN ? AND ?{uid_clause} "
                "ORDER BY date LIMIT ? OFFSET ?",
                (from_date, to_date) + uid_params + (limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM daily_snapshot WHERE date BETWEEN ? AND ?{uid_clause} ORDER BY date",
                (from_date, to_date) + uid_params,
            ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        for key in ("muscle_volume", "workouts"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        result.append(d)
    return result


def get_weekly_summary(before_date: str, days: int = 7, user_id: int | None = None) -> list[dict]:
    """
    Return per-day summaries for the N days immediately before before_date (exclusive).
    Used to build the 7-day training history section of the Claude prompt.
    """
    from datetime import date as _date, timedelta
    from_date = (_date.fromisoformat(before_date) - timedelta(days=days)).isoformat()
    uid_clause = " AND user_id = ?" if user_id is not None else ""
    uid_params = (user_id,) if user_id is not None else ()
    with get_sqlite() as conn:
        rows = conn.execute(
            f"""SELECT date, steps, exercise_minutes, sleep_total_min, hrv_ms,
                      workouts, muscle_volume
               FROM daily_snapshot
               WHERE date >= ? AND date < ?{uid_clause}
               ORDER BY date""",
            (from_date, before_date) + uid_params,
        ).fetchall()
    result = []
    for row in rows:
        d = dict(row)
        for key in ("workouts", "muscle_volume"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    d[key] = None
        result.append(d)
    return result


def get_soreness_for_date(date: str, user_id: int | None = None) -> dict[str, int]:
    """Return {muscle: soreness_level} for a given date from soreness_log."""
    uid_clause = " AND user_id = ?" if user_id is not None else ""
    uid_params = (user_id,) if user_id is not None else ()
    with get_sqlite() as conn:
        rows = conn.execute(
            f"SELECT muscle, soreness FROM soreness_log WHERE date = ?{uid_clause}",
            (date,) + uid_params,
        ).fetchall()
    return {row["muscle"]: row["soreness"] for row in rows}
