"""
Parses Apple Health webhook payloads into normalized snapshot fields.

Phase 1: parse and aggregate logic only — no DB writes.
Phase 3: wire ingest_metrics / ingest_workouts to database.py calls.
"""

import json
import logging
import os
import sys
from datetime import datetime
from statistics import mean
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("America/Toronto")

# (metric_name, aggregation_method, snapshot_column)
METRIC_RULES: list[tuple[str, str, str]] = [
    ("step_count",                 "sum",            "steps"),
    ("active_energy",              "sum",            "active_calories"),
    ("basal_energy_burned",        "sum",            "basal_calories"),
    ("apple_exercise_time",        "sum",            "exercise_minutes"),
    ("apple_stand_hour",           "count_positive", "stand_hours"),
    ("walking_running_distance",   "sum",            "distance_mi"),
    ("flights_climbed",            "sum",            "flights_climbed"),
    ("heart_rate_variability",     "mean",           "hrv_ms"),
    ("resting_heart_rate",         "last",           "resting_hr"),
    ("cardio_recovery",            "last",           "cardio_recovery"),
    ("heart_rate",                 "mean",           "avg_heart_rate"),
    ("walking_heart_rate_average", "last",           "walking_hr_avg"),
    ("body_mass",                  "last",           "body_weight_kg"),
]


def _parse_dt(s: str) -> datetime:
    # Apple Health date format: "2026-04-30 10:00:00 -0400"
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")


def _local_date(s: str) -> str:
    """Return 'YYYY-MM-DD' in the entry's own timezone offset."""
    return _parse_dt(s).date().isoformat()


def _val(e: dict) -> float | None:
    """
    Extract the numeric value from a metric data entry.
    Most metrics use 'qty'; heart_rate uses 'Avg' (Health Auto Export quirk
    for interval-averaged readings that have Min/Avg/Max instead of a single qty).
    """
    if "qty" in e:
        return e["qty"]
    if "Avg" in e:
        return e["Avg"]
    return None


def _qty(obj: dict, key: str):
    """Pull qty from either a direct scalar or a {qty, units} wrapper."""
    v = obj.get(key)
    return v.get("qty") if isinstance(v, dict) else v


def aggregate_metric(
    entries: list[dict], method: str, target_date: str
) -> float | None:
    """
    Filter entries to target_date (local time) then apply method:
      sum            — total of all qty values
      mean           — average of qty values
      last           — most-recent single value (resting HR, HRV, cardio recovery)
      count_positive — count entries where qty > 0 (stand hours)
    Returns None when no entries match the target date.
    """
    todays = [e for e in entries if _local_date(e["date"]) == target_date]
    if not todays:
        return None

    if method == "sum":
        return sum((_val(e) or 0.0) for e in todays)

    if method == "mean":
        vals = [v for e in todays if (v := _val(e)) is not None]
        return mean(vals) if vals else None

    if method == "last":
        todays.sort(key=lambda e: _parse_dt(e["date"]))
        return _val(todays[-1])

    if method == "count_positive":
        return sum(1 for e in todays if (_val(e) or 0) > 0)

    raise ValueError(f"unknown aggregation method: {method!r}")


def parse_sleep(entries: list[dict], target_date: str) -> dict:
    """
    Stub — returns {} until a real sleep payload is available to inspect.
    Sleep tracking is not currently enabled; sleep columns remain NULL.
    Phase 3+: implement once we have a sleep_analysis sample.
    """
    return {}


def parse_metrics_payload(payload: dict, target_date: str) -> dict:
    """
    Extract scalar health fields from the Apple Health metrics webhook payload.

    Payload shape: {data: {metrics: [{name, units, data: [{date, qty, ...}]}]}}
    Returns {snapshot_column: value} restricted to target_date.
    Unknown metric names are silently skipped.
    """
    raw_metrics = payload.get("data", {}).get("metrics") or []
    by_name: dict[str, list] = {
        m["name"]: m.get("data") or []
        for m in raw_metrics
        if isinstance(m, dict) and "name" in m
    }

    out: dict = {}
    for metric_name, method, column in METRIC_RULES:
        entries = by_name.get(metric_name)
        if entries is None:
            continue
        value = aggregate_metric(entries, method, target_date)
        if value is not None:
            out[column] = value

    sleep_entries = by_name.get("sleep_analysis")
    if sleep_entries:
        out.update(parse_sleep(sleep_entries, target_date))

    return out


def parse_workouts_payload(payload: dict, target_date: str) -> list[dict]:
    """
    Extract Apple Health workouts for target_date.

    Payload shape: {data: {workouts: [...]}}
    Each returned dict has source='apple_health' — no muscle-group volume
    (that comes from Hevy only). All scalars are pulled from {qty, units} wrappers.
    """
    raw = payload.get("data", {}).get("workouts") or []
    out = []
    for w in raw:
        start = w.get("start")
        if not start:
            continue
        try:
            workout_date = _local_date(start)
        except ValueError:
            log.warning("unparseable workout start: %s", start)
            continue
        if workout_date != target_date:
            continue

        out.append({
            "source":          "apple_health",
            "name":            w.get("name"),
            "start":           start,
            "end":             w.get("end"),
            "duration_min":    round((w.get("duration") or 0) / 60, 1),
            "active_calories": _qty(w, "activeEnergyBurned"),
            "avg_heart_rate":  _qty(w, "avgHeartRate"),
            "max_heart_rate":  _qty(w, "maxHeartRate"),
            "distance_mi":     _qty(w, "distance"),
            "intensity":       _qty(w, "intensity"),
        })
    return out


def ingest_metrics(payload: dict, target_date: str) -> dict:
    """Parse metrics payload, append raw blob, then write to DB. Returns extracted fields."""
    import database
    fields = parse_metrics_payload(payload, target_date)
    log.info("[apple_health] metrics for %s: %d fields extracted", target_date, len(fields))
    database.append_raw_blob("raw_apple_health", target_date, payload)
    complete = database.upsert_snapshot_apple_health(target_date, fields)
    if complete:
        log.info("[apple_health] snapshot complete for %s — Claude can run", target_date)
    return fields


def ingest_workouts(payload: dict, target_date: str) -> list[dict]:
    """Parse workouts payload, append raw blob, then merge into DB workouts column."""
    import database
    workouts = parse_workouts_payload(payload, target_date)
    log.info("[apple_health] workouts for %s: %d entries", target_date, len(workouts))
    database.append_raw_blob("raw_apple_health_workouts", target_date, payload)
    database.upsert_snapshot_apple_health_workouts(target_date, workouts)
    return workouts


def _detect_latest_date(payload: dict) -> str | None:
    """Return the most recent local date found across all metric entries."""
    raw_metrics = payload.get("data", {}).get("metrics") or []
    dates = set()
    for m in raw_metrics:
        for e in m.get("data") or []:
            try:
                dates.add(_local_date(e["date"]))
            except (KeyError, ValueError):
                pass
    return max(dates) if dates else None


if __name__ == "__main__":
    import glob

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    log_dir = os.path.join(os.path.dirname(__file__), "test_logs")

    metrics_files  = sorted(glob.glob(os.path.join(log_dir, "apple_health_2*.json")))
    workouts_files = sorted(glob.glob(os.path.join(log_dir, "apple_health_workouts_*.json")))

    # --- Metrics ---
    if not metrics_files:
        print("No apple_health_2*.json found in test_logs/")
    else:
        path = metrics_files[-1]
        print(f"Metrics payload : {os.path.basename(path)}")
        with open(path) as f:
            m_payload = json.load(f)

        # Use CLI arg, or auto-detect the most recent date in the payload
        if len(sys.argv) > 1:
            metrics_date = sys.argv[1]
        else:
            metrics_date = _detect_latest_date(m_payload)
            if not metrics_date:
                print("  Could not detect a date in the payload")
                metrics_date = None

        if metrics_date:
            print(f"Target date     : {metrics_date}\n")
            fields = ingest_metrics(m_payload, metrics_date)
            if fields:
                max_col = max(len(c) for c in fields)
                for col, val in sorted(fields.items()):
                    if isinstance(val, float):
                        print(f"  {col:{max_col}s}  {val:.4f}")
                    else:
                        print(f"  {col:{max_col}s}  {val}")
            else:
                print(f"  (no metrics found for {metrics_date})")

    print()

    # --- Workouts ---
    if not workouts_files:
        print("No apple_health_workouts_*.json found in test_logs/")
    else:
        path = workouts_files[-1]
        print(f"Workouts payload: {os.path.basename(path)}")
        with open(path) as f:
            w_payload = json.load(f)

        # Auto-detect the most recent date across all workouts in the payload
        raw_wkts = w_payload.get("data", {}).get("workouts") or []
        wkt_date = None
        for wkt in raw_wkts:
            if wkt.get("start"):
                try:
                    d = _local_date(wkt["start"])
                    if wkt_date is None or d > wkt_date:
                        wkt_date = d
                except ValueError:
                    pass
        wkt_date = wkt_date or (sys.argv[1] if len(sys.argv) > 1 else None)

        if wkt_date:
            print(f"Target date     : {wkt_date}\n")
            workouts = ingest_workouts(w_payload, wkt_date)
            if workouts:
                for w in workouts:
                    hr  = w.get("avg_heart_rate")
                    dis = w.get("distance_mi")
                    cal = w.get("active_calories")
                    print(
                        f"  {w['name']:25s}  {w['duration_min']:5.1f} min"
                        + (f"  HR {hr:.0f} bpm" if hr else "")
                        + (f"  {dis:.2f} mi" if dis else "")
                        + (f"  {cal:.0f} kcal" if cal else "")
                    )
            else:
                print(f"  (no workouts for {wkt_date})")
        else:
            print("  Could not determine workout date")
