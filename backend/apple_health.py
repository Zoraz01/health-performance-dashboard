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
log = logging.getLogger(__name__)

from scheduler import LOCAL_TZ  # single definition lives in scheduler.py

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
    ("blood_oxygen_saturation",    "mean",           "spo2"),
    ("respiratory_rate",           "mean",           "respiratory_rate"),
    ("caffeine",                   "sum",            "caffeine_mg"),
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
        return round(sum((_val(e) or 0.0) for e in todays), 1)

    if method == "mean":
        vals = [v for e in todays if (v := _val(e)) is not None]
        return round(mean(vals), 1) if vals else None

    if method == "last":
        todays.sort(key=lambda e: _parse_dt(e["date"]))
        val = _val(todays[-1])
        return round(val, 1) if val is not None else None

    if method == "count_positive":
        return sum(1 for e in todays if (_val(e) or 0) > 0)

    raise ValueError(f"unknown aggregation method: {method!r}")


def _extract_sleep_hr(
    hr_entries: list[dict],
    sleep_start_iso: str,
    sleep_end_iso: str,
) -> list[dict]:
    """
    Filter HR entries to the sleep window and return [{t, hr}, ...] sorted by time.
    Prefers RingConn readings when multiple sources share a timestamp.
    sleep_start_iso / sleep_end_iso must be tz-aware ISO strings (from isoformat()).
    """
    from datetime import datetime as _dt
    try:
        win_start = _dt.fromisoformat(sleep_start_iso)
        win_end   = _dt.fromisoformat(sleep_end_iso)
    except Exception:
        return []

    seen: dict[str, dict] = {}
    for entry in hr_entries:
        ts_raw = entry.get("start") or entry.get("date") or ""
        if not ts_raw:
            continue
        try:
            dt = _parse_dt(ts_raw)
        except Exception:
            continue
        if dt < win_start or dt > win_end:
            continue
        hr_val = entry.get("Avg") or entry.get("qty")
        if hr_val is None:
            continue
        ts_iso = dt.isoformat()
        src = entry.get("source", "")
        if ts_iso not in seen or "RingConn" in src:
            seen[ts_iso] = {"t": ts_iso, "hr": round(float(hr_val), 1)}

    return sorted(seen.values(), key=lambda x: x["t"])


def parse_sleep(
    entries: list[dict],
    target_date: str,
    hr_entries: list[dict] | None = None,
) -> dict:
    """
    Parse Apple Health sleep_analysis entries for target_date.

    Apple Health AutoExport uses short stage names:
      "Core"   / "AsleepCore"        → light sleep (counted in total)
      "Deep"   / "AsleepDeep"        → deep sleep (counted in total + deep)
      "REM"    / "AsleepREM"         → REM sleep (counted in total + rem)
      "Asleep" / "AsleepUnspecified" → unspecified sleep (counted in total)
      "In Bed" / "InBed"             → in-bed time (not counted as sleep)
      "Awake"                        → awake time during sleep window

    qty field is in hours.
    Also builds sleep_stages timeline, sleep_source, and sleep_hr (if hr_entries given).
    """
    ASLEEP  = {"Asleep", "AsleepUnspecified", "Core", "AsleepCore"}
    DEEP    = {"Deep", "AsleepDeep"}
    REM     = {"REM", "AsleepREM"}
    IN_BED  = {"In Bed", "InBed"}
    AWAKE   = {"Awake"}
    STAGE_KEY = {
        **{s: "core"  for s in ASLEEP},
        **{s: "deep"  for s in DEEP},
        **{s: "rem"   for s in REM},
        **{s: "awake" for s in AWAKE},
    }

    total_min = deep_min = rem_min = awake_min = 0.0
    segments: list[dict] = []
    sources_seen: set[str] = set()

    for entry in entries:
        ts = entry.get("date") or entry.get("startDate") or ""
        try:
            entry_date = _local_date(ts)
        except Exception:
            continue
        if entry_date != target_date:
            continue

        stage_raw = entry.get("value") or ""
        if stage_raw in IN_BED:
            continue  # In Bed overlaps all stages — skip to avoid double-counting

        raw_qty = entry.get("qty") or entry.get("Qty")
        try:
            minutes = float(raw_qty) * 60.0
        except (TypeError, ValueError):
            continue
        if minutes <= 0:
            continue

        stage_key = STAGE_KEY.get(stage_raw)
        if not stage_key:
            continue

        src = entry.get("source", "")
        if "RingConn" in src:
            sources_seen.add("ring")
        if "Apple Watch" in src:
            sources_seen.add("watch")

        if stage_key == "deep":
            total_min += minutes
            deep_min  += minutes
        elif stage_key == "rem":
            total_min += minutes
            rem_min   += minutes
        elif stage_key == "core":
            total_min += minutes
        elif stage_key == "awake":
            awake_min += minutes

        # Build tz-aware timeline segment (best-effort — totals are unaffected if this fails)
        start_raw = entry.get("start") or entry.get("startDate") or ts
        end_raw   = entry.get("end")   or entry.get("endDate")   or ts
        try:
            start_iso = _parse_dt(start_raw).isoformat()
            end_iso   = _parse_dt(end_raw).isoformat()
            segments.append({"start": start_iso, "end": end_iso, "stage": stage_key})
        except Exception:
            pass

    segments.sort(key=lambda x: x["start"])

    out: dict = {}
    if total_min > 0:
        out["sleep_total_min"] = round(total_min, 1)
    if deep_min > 0:
        out["sleep_deep_min"] = round(deep_min, 1)
    if rem_min > 0:
        out["sleep_rem_min"] = round(rem_min, 1)
    if awake_min > 0:
        out["sleep_awake_min"] = round(awake_min, 1)

    if segments:
        out["sleep_stages"] = json.dumps(segments)
        if "ring" in sources_seen and "watch" in sources_seen:
            out["sleep_source"] = "watch+ring"
        elif "ring" in sources_seen:
            out["sleep_source"] = "ring"
        elif "watch" in sources_seen:
            out["sleep_source"] = "watch"

        if hr_entries:
            sleep_hr = _extract_sleep_hr(hr_entries, segments[0]["start"], segments[-1]["end"])
            if sleep_hr:
                out["sleep_hr"] = json.dumps(sleep_hr)

    return out


def _parse_sleep_from_payload(payload: dict, target_date: str) -> dict:
    """Extract sleep + HR fields from any payload containing sleep_analysis."""
    by_name = {
        m["name"]: m.get("data") or []
        for m in payload.get("data", {}).get("metrics") or []
        if isinstance(m, dict) and "name" in m
    }
    sleep_entries = by_name.get("sleep_analysis")
    if not sleep_entries:
        return {}
    return parse_sleep(sleep_entries, target_date, hr_entries=by_name.get("heart_rate"))


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
        out.update(parse_sleep(sleep_entries, target_date, hr_entries=by_name.get("heart_rate")))

    # RingConn sends weight as weight_body_mass in lbs; convert to kg as fallback
    if "body_weight_kg" not in out:
        rc_weight_entries = by_name.get("weight_body_mass")
        if rc_weight_entries:
            val = aggregate_metric(rc_weight_entries, "last", target_date)
            if val is not None:
                out["body_weight_kg"] = round(val * 0.453592, 2)

    return out


def parse_workouts_payload(payload: dict, target_date: str) -> list[dict]:
    """
    Extract Apple Health workouts for target_date.

    Payload shape: {data: {workouts: [...]}}
    Each returned dict has source='apple_health' — no muscle-group volume
    (that comes from Hevy only). All scalars are pulled from {qty, units} wrappers.

    Deduplication: Apple Health can log the same session twice — most commonly from
    Hevy's Watch→iPhone sync, which writes one HKWorkout from the Watch side and one
    from the iPhone sync. When two workouts share the same name and their time windows
    overlap, only the longer one is kept. Non-null biometric fields are merged from
    the shorter entry into the longer one before it is dropped.
    """
    raw = payload.get("data", {}).get("workouts") or []
    out = []
    for w in raw:
        start = w.get("start")
        if not start:
            continue
        try:
            workout_date = _local_date(start)
            start_dt = _parse_dt(start)
        except ValueError:
            log.warning("unparseable workout start: %s", start)
            continue
        if workout_date != target_date:
            continue

        end_raw = w.get("end")
        try:
            end_dt = _parse_dt(end_raw) if end_raw else None
        except ValueError:
            end_dt = None

        out.append({
            "source":          "apple_health",
            "id":              w.get("id"),
            "name":            w.get("name"),
            "start":           start,
            "_start_dt":       start_dt,
            "end":             end_raw,
            "_end_dt":         end_dt,
            "duration_min":    round((w.get("duration") or 0) / 60, 1),
            "active_calories": _qty(w, "activeEnergyBurned"),
            "avg_heart_rate":  _qty(w, "avgHeartRate"),
            "max_heart_rate":  _qty(w, "maxHeartRate"),
            "distance_mi":     _qty(w, "distance"),
            "intensity":       _qty(w, "intensity"),
        })

    # Dedup same-named sessions whose time windows overlap (Hevy Watch→iPhone sync
    # can create two Apple Health records for the same gym session with start times
    # that differ by more than the old 60-second proximity check could catch).
    # Keep the longer entry; copy non-null biometrics from the shorter one.
    deduped: list[dict] = []
    for candidate in out:
        absorbed = False
        for i, existing in enumerate(deduped):
            if existing["name"] != candidate["name"]:
                continue
            c_end = candidate.get("_end_dt")
            e_end = existing.get("_end_dt")
            if not (c_end and e_end):
                continue
            overlaps = (existing["_start_dt"] < c_end) and (candidate["_start_dt"] < e_end)
            if overlaps:
                if candidate["duration_min"] > existing["duration_min"]:
                    # Merge biometrics from the shorter (existing) into the longer (candidate)
                    for field in ("avg_heart_rate", "max_heart_rate", "active_calories"):
                        if candidate.get(field) is None and existing.get(field) is not None:
                            candidate[field] = existing[field]
                    deduped[i] = candidate
                else:
                    # Kept entry is existing — merge biometrics from candidate into it
                    for field in ("avg_heart_rate", "max_heart_rate", "active_calories"):
                        if existing.get(field) is None and candidate.get(field) is not None:
                            existing[field] = candidate[field]
                absorbed = True
                break
        if not absorbed:
            deduped.append(candidate)

    for w in deduped:
        w.pop("_start_dt", None)
        w.pop("_end_dt", None)

    if len(deduped) < len(out):
        log.info("[apple_health] dedup removed %d duplicate workout(s) for %s",
                 len(out) - len(deduped), target_date)

    return deduped


def extract_hr_samples(workout: dict) -> list[dict]:
    """
    Merge heartRateData, activeEnergy, stepCount by timestamp into per-minute rows.

    Apple Health gives each series as a list of {date, Avg/qty, Min, Max, units, source}.
    Timestamps across series are aligned to the same 60-second buckets so we can
    join on the date string directly.
    """
    by_ts: dict[str, dict] = {}

    for entry in workout.get("heartRateData") or []:
        ts = entry.get("date")
        if not ts:
            continue
        by_ts.setdefault(ts, {}).update({
            "hr_avg": entry.get("Avg"),
            "hr_min": entry.get("Min"),
            "hr_max": entry.get("Max"),
        })

    for entry in workout.get("activeEnergy") or []:
        ts = entry.get("date")
        if not ts:
            continue
        v = _val(entry)
        if v is not None:
            by_ts.setdefault(ts, {})["calories"] = v

    for entry in workout.get("stepCount") or []:
        ts = entry.get("date")
        if not ts:
            continue
        v = _val(entry)
        if v is not None:
            by_ts.setdefault(ts, {})["steps"] = v

    result = []
    for ts_str, data in sorted(by_ts.items()):
        try:
            ts_iso = _parse_dt(ts_str).isoformat()
        except ValueError:
            continue
        result.append({"ts": ts_iso, **data})
    return result


def _aggregate_all_blobs_for_date(target_date: str) -> dict | None:
    """
    Re-aggregate metrics for target_date from ALL raw blobs stored in DuckDB.

    Apple Health sends incremental payloads (only data since last sync). Each
    4-hour sync therefore only contains a slice of the day. Re-aggregating from
    all stored blobs — deduplicating entries by exact timestamp — gives the true
    full-day totals without needing to track running deltas.

    Returns None if the DuckDB read fails so callers can abort rather than
    silently writing empty data.
    """
    import database
    try:
        with database.get_duckdb() as con:
            rows = con.execute(
                "SELECT payload::text FROM raw_apple_health WHERE date = ? ORDER BY id",
                (target_date,),
            ).fetchall()
    except Exception:
        log.exception("[apple_health] DuckDB read failed for %s — aborting re-aggregation", target_date)
        return None

    if not rows:
        # append_raw_blob must have failed silently — no data to aggregate.
        log.error("[apple_health] no blobs in DuckDB for %s after append — DuckDB write likely failed", target_date)
        return None

    # Merge all metric entries across blobs, deduplicating by (metric, timestamp).
    # When two blobs share the same timestamp for a metric, the later blob wins.
    by_name: dict[str, dict[str, dict]] = {}
    all_medications: list[str] = []
    for (payload_str,) in rows:
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            continue
        data = payload.get("data") or {}
        for m in data.get("metrics") or []:
            name = m.get("name")
            if not name:
                continue
            bucket = by_name.setdefault(name, {})
            for entry in (m.get("data") or []):
                # Use the full entry as the deduplication key to avoid dropping overlapping records
                # like 'Core' and 'In Bed' sleep stages that start at the exact same timestamp.
                dedup_key = json.dumps(entry, sort_keys=True)
                if dedup_key not in bucket:
                    bucket[dedup_key] = entry
        # Collect medication names logged for this date.
        for med in data.get("medications") or []:
            name = med.get("name") or med.get("title") or ""
            if not name:
                continue
            date_str = med.get("date") or med.get("startDate") or ""
            try:
                med_date = _local_date(date_str) if date_str else target_date
            except Exception:
                med_date = target_date
            if med_date == target_date and name not in all_medications:
                all_medications.append(name)

    merged: dict[str, list] = {name: list(entries.values()) for name, entries in by_name.items()}

    out: dict = {}
    for metric_name, method, column in METRIC_RULES:
        entries = merged.get(metric_name)
        if entries is None:
            continue
        value = aggregate_metric(entries, method, target_date)
        if value is not None:
            out[column] = value

    sleep_entries = merged.get("sleep_analysis")
    if sleep_entries:
        out.update(parse_sleep(sleep_entries, target_date, hr_entries=merged.get("heart_rate")))

    # RingConn sends weight as weight_body_mass in lbs; convert to kg as fallback
    if "body_weight_kg" not in out:
        rc_weight_entries = merged.get("weight_body_mass")
        if rc_weight_entries:
            val = aggregate_metric(rc_weight_entries, "last", target_date)
            if val is not None:
                out["body_weight_kg"] = round(val * 0.453592, 2)

    if all_medications:
        out["medications_today"] = json.dumps(all_medications)

    return out


def ingest_metrics(payload: dict, target_date: str, user_id: int | None = None) -> dict:
    """
    Append raw blob, then re-aggregate ALL blobs for target_date and write to DB.

    Re-aggregation from all stored blobs (instead of just the current payload)
    ensures cumulative accuracy across the 4-hour incremental syncs Apple Health
    sends — each sync only contains data since the last, so processing them
    individually would reset metrics to the latest window's values.
    """
    import database
    database.append_raw_blob("raw_apple_health", target_date, payload)
    fields = _aggregate_all_blobs_for_date(target_date)
    if fields is None:
        raise RuntimeError(f"DuckDB re-aggregation failed for {target_date} — raw blob stored but snapshot not updated")
    log.info("[apple_health] metrics for %s: %d fields extracted (all blobs)", target_date, len(fields))
    complete = database.upsert_snapshot_apple_health(target_date, fields, user_id=user_id)
    if complete:
        log.info("[apple_health] snapshot complete for %s — Claude can run", target_date)
    return fields


def ingest_workouts(payload: dict, target_date: str, user_id: int | None = None) -> list[dict]:
    """Parse workouts payload, append raw blob, merge into DB, store HR timeseries."""
    import database
    workouts = parse_workouts_payload(payload, target_date)
    log.info("[apple_health] workouts for %s: %d entries", target_date, len(workouts))
    database.append_raw_blob("raw_apple_health_workouts", target_date, payload)
    database.upsert_snapshot_apple_health_workouts(target_date, workouts, user_id=user_id)

    for raw_w in payload.get("data", {}).get("workouts") or []:
        workout_id = raw_w.get("id")
        start = raw_w.get("start")
        if not workout_id or not start:
            continue
        try:
            if _local_date(start) != target_date:
                continue
        except ValueError:
            continue
        samples = extract_hr_samples(raw_w)
        if samples:
            database.upsert_workout_hr_samples(workout_id, "apple_health", samples)
            log.info("[apple_health] %d HR samples stored for workout %s", len(samples), workout_id)

    return workouts


def _detect_all_dates(payload: dict) -> set[str]:
    """Return all local dates found across all metric entries."""
    raw_metrics = payload.get("data", {}).get("metrics") or []
    dates: set[str] = set()
    for m in raw_metrics:
        for e in m.get("data") or []:
            try:
                dates.add(_local_date(e["date"]))
            except (KeyError, ValueError):
                pass
    return dates


def _detect_latest_date(payload: dict) -> str | None:
    """Return the most recent local date found across all metric entries."""
    dates = _detect_all_dates(payload)
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
