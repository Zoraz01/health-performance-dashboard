"""
Workout timeseries and raw blob storage.
"""

import json
import logging

from db.connection import get_sqlite, get_duckdb

log = logging.getLogger(__name__)

_RAW_TABLES = {"raw_apple_health", "raw_apple_health_workouts", "raw_hevy_workouts"}


def append_raw_blob(table: str, date: str, payload: dict) -> None:
    """Append a raw JSON payload to the named DuckDB table.

    Errors are logged and swallowed — raw blob loss is acceptable and must
    never block the SQLite snapshot path.
    """
    if table not in _RAW_TABLES:
        log.error("append_raw_blob: unknown table %r", table)
        return
    try:
        payload_str = json.dumps(payload)
        with get_duckdb() as con:
            con.execute(
                f"INSERT INTO {table} (date, payload) VALUES (?, ?::JSON)",
                (date, payload_str),
            )
        log.debug("raw blob appended → %s [%s]", table, date)
    except Exception:
        log.exception("DuckDB write failed for %s [%s] — continuing", table, date)


def upsert_workout_hr_samples(workout_id: str, source: str, samples: list[dict]) -> None:
    """Replace all per-minute HR/calorie/step samples for one workout (idempotent)."""
    if not samples:
        return
    rows = [
        (
            workout_id, source, s["ts"],
            s.get("hr_avg"), s.get("hr_min"), s.get("hr_max"),
            s.get("calories"), s.get("steps"),
        )
        for s in samples
    ]
    with get_duckdb() as con:
        con.execute("BEGIN")
        try:
            con.execute("DELETE FROM workout_hr_samples WHERE workout_id = ?", (workout_id,))
            con.executemany(
                "INSERT INTO workout_hr_samples "
                "(workout_id, source, ts, hr_avg, hr_min, hr_max, calories, steps) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    log.debug("workout_hr_samples: %d rows stored for %s", len(rows), workout_id)


def upsert_workout_sets(workout_id: str, exercises: list[dict]) -> None:
    """Replace all set-level rows for one Hevy workout (idempotent)."""
    rows = []
    for ex in exercises:
        ex_idx = ex.get("index", 0)
        for s in ex.get("sets") or []:
            rows.append((
                workout_id,
                ex_idx,
                ex.get("title", ""),
                ex.get("exercise_template_id"),
                ex.get("primary_muscle_group"),
                s.get("index", 0),
                s.get("type"),
                s.get("weight_kg"),
                s.get("reps"),
                s.get("duration_seconds"),
                s.get("rpe"),
            ))
    if not rows:
        return
    with get_duckdb() as con:
        con.execute("BEGIN")
        try:
            con.execute("DELETE FROM workout_sets WHERE workout_id = ?", (workout_id,))
            con.executemany(
                "INSERT INTO workout_sets "
                "(workout_id, exercise_index, exercise_title, exercise_template_id, "
                "primary_muscle_group, set_index, set_type, weight_kg, reps, "
                "duration_seconds, rpe) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    log.debug("workout_sets: %d rows stored for %s", len(rows), workout_id)


def get_workout_hr_samples(workout_id: str) -> list[dict]:
    """Return per-minute HR/calorie/step samples for a workout, ordered by time."""
    with get_duckdb() as con:
        rows = con.execute(
            "SELECT ts, hr_avg, hr_min, hr_max, calories, steps "
            "FROM workout_hr_samples WHERE workout_id = ? ORDER BY ts",
            (workout_id,),
        ).fetchall()
    return [
        {
            "ts":       str(r[0]),
            "hr_avg":   r[1],
            "hr_min":   r[2],
            "hr_max":   r[3],
            "calories": r[4],
            "steps":    r[5],
        }
        for r in rows
    ]


def get_workout_sets(workout_id: str) -> list[dict]:
    """Return set-level data for a Hevy workout, grouped by exercise."""
    with get_duckdb() as con:
        rows = con.execute(
            "SELECT exercise_index, exercise_title, exercise_template_id, "
            "primary_muscle_group, set_index, set_type, weight_kg, reps, "
            "duration_seconds, rpe "
            "FROM workout_sets WHERE workout_id = ? ORDER BY exercise_index, set_index",
            (workout_id,),
        ).fetchall()
    exercises: dict[int, dict] = {}
    for r in rows:
        ex_idx = r[0]
        if ex_idx not in exercises:
            exercises[ex_idx] = {
                "exercise_index":      ex_idx,
                "title":               r[1],
                "exercise_template_id": r[2],
                "primary_muscle_group": r[3],
                "sets": [],
            }
        exercises[ex_idx]["sets"].append({
            "set_index":        r[4],
            "type":             r[5],
            "weight_kg":        r[6],
            "reps":             r[7],
            "duration_seconds": r[8],
            "rpe":              r[9],
        })
    return list(exercises.values())
