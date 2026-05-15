"""
Analytics and baseline queries — activity history, muscle volume, exercise templates,
intraday timeseries.
"""

import json
import logging

from db.connection import get_sqlite, get_duckdb

log = logging.getLogger(__name__)


def get_metric_baselines(days: int = 30, user_id: int | None = None) -> dict:
    """Return N-day trailing averages for the four recovery metrics."""
    uid_clause = " AND user_id = ?" if user_id is not None else ""
    uid_params = (user_id,) if user_id is not None else ()
    with get_sqlite() as conn:
        row = conn.execute(
            f"""
            SELECT
                AVG(hrv_ms)          AS hrv_avg,
                AVG(resting_hr)      AS resting_hr_avg,
                AVG(cardio_recovery) AS cardio_recovery_avg,
                AVG(walking_hr_avg)  AS walking_hr_baseline,
                AVG(spo2)            AS spo2_avg
            FROM daily_snapshot
            WHERE date >= date('now', ? || ' days')
              AND date < date('now'){uid_clause}
            """,
            (f"-{days}",) + uid_params,
        ).fetchone()
    return dict(row) if row else {}


def get_activity_history(days: int = 30, user_id: int | None = None) -> list[dict]:
    """Return daily activity rows for the ActivityCharts line chart."""
    uid_clause = " AND user_id = ?" if user_id is not None else ""
    uid_params = (user_id,) if user_id is not None else ()
    with get_sqlite() as conn:
        rows = conn.execute(
            f"""
            SELECT date, steps, active_calories, hrv_ms,
                   ROUND(body_weight_kg * 2.20462, 1) AS body_weight_lbs,
                   resting_hr, cardio_recovery
            FROM daily_snapshot
            WHERE date >= date('now', ? || ' days'){uid_clause}
            ORDER BY date ASC
            """,
            (f"-{days}",) + uid_params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_muscle_volume_30d(user_id: int | None = None) -> dict[str, float]:
    """Sum muscle_volume across the last 30 days of snapshots."""
    from datetime import date as _date, timedelta
    from_date = (_date.today() - timedelta(days=30)).isoformat()
    uid_clause = " AND user_id = ?" if user_id is not None else ""
    uid_params = (user_id,) if user_id is not None else ()
    with get_sqlite() as conn:
        rows = conn.execute(
            "SELECT muscle_volume FROM daily_snapshot "
            f"WHERE date >= ? AND muscle_volume IS NOT NULL AND muscle_volume != '{{}}'{uid_clause}",
            (from_date,) + uid_params,
        ).fetchall()
    totals: dict[str, float] = {}
    for row in rows:
        try:
            mv = json.loads(row[0])
            for k, v in mv.items():
                if isinstance(v, (int, float)) and v > 0:
                    totals[k] = round(totals.get(k, 0.0) + v, 2)
        except (json.JSONDecodeError, TypeError):
            pass
    return totals


def get_muscle_volume_baselines(user_id: int | None = None) -> tuple[dict[str, float], int]:
    """
    Compute per-muscle average 30-day volume from all available history.

    Returns (baselines, history_days) where:
      - baselines: {muscle: avg_kg_reps_per_30d} — empty if history < 30 days
      - history_days: days since the earliest snapshot (0 if no data)
    """
    from datetime import date as _date
    uid_clause = " AND user_id = ?" if user_id is not None else ""
    uid_params = (user_id,) if user_id is not None else ()
    with get_sqlite() as conn:
        first_row = conn.execute(
            f"SELECT MIN(date) FROM daily_snapshot WHERE 1=1{uid_clause}", uid_params
        ).fetchone()
        rows = conn.execute(
            "SELECT muscle_volume FROM daily_snapshot "
            f"WHERE muscle_volume IS NOT NULL AND muscle_volume != '{{}}'{uid_clause}",
            uid_params,
        ).fetchall()

    if not first_row or not first_row[0]:
        return {}, 0

    history_days = (_date.today() - _date.fromisoformat(first_row[0])).days
    if history_days < 30:
        return {}, history_days

    totals: dict[str, float] = {}
    for row in rows:
        try:
            mv = json.loads(row[0])
            for k, v in mv.items():
                if isinstance(v, (int, float)) and v > 0:
                    totals[k] = totals.get(k, 0.0) + v
        except (json.JSONDecodeError, TypeError):
            pass

    periods = history_days / 30
    baselines = {k: round(v / periods, 2) for k, v in totals.items()}
    return baselines, history_days


def get_exercise_template(template_id: str) -> dict | None:
    """Return a single exercise_templates row, or None."""
    with get_sqlite() as conn:
        row = conn.execute(
            "SELECT * FROM exercise_templates WHERE id = ?", (template_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    if d.get("secondary_muscle_groups"):
        try:
            d["secondary_muscle_groups"] = json.loads(d["secondary_muscle_groups"])
        except (json.JSONDecodeError, TypeError):
            d["secondary_muscle_groups"] = []
    return d


def upsert_daily_timeseries(date: str, samples: list[dict]) -> None:
    """Upsert per-sample intraday timeseries rows (idempotent)."""
    if not samples:
        return
    rows = [(date, s["ts"], s["metric"], s["value"]) for s in samples]
    with get_duckdb() as con:
        con.execute("BEGIN")
        try:
            con.executemany(
                "INSERT OR REPLACE INTO daily_timeseries (date, ts, metric, value) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    log.debug("daily_timeseries: %d rows stored for %s", len(rows), date)


def get_daily_timeseries(date: str, metric: str) -> list[dict]:
    """Return intraday samples for one date + metric, ordered by time."""
    with get_duckdb() as con:
        rows = con.execute(
            "SELECT ts, value FROM daily_timeseries "
            "WHERE date = ? AND metric = ? ORDER BY ts",
            (date, metric),
        ).fetchall()
    return [{"ts": str(r[0]), "value": r[1]} for r in rows]
