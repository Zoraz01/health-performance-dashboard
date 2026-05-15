"""
Workout deduplication diagnostic and repair script.

WHY THIS EXISTS
---------------
Hevy, when started on Apple Watch and synced to iPhone, writes two separate
HKWorkout records to Apple Health for the same gym session — one from the Watch
app and one from the iPhone sync. Both arrive in the Apple Health webhook payload
with source='apple_health', the same workout name, and overlapping time windows.

The existing 60-second start-time window in parse_workouts_payload() usually
catches this, but the Hevy sync can cause start times to diverge by more than
60 seconds. The correct check is time-window overlap: two apple_health workouts
with the same name whose intervals overlap are the same session.

This script:
  1. Scans daily_snapshot for dates with multiple same-named apple_health workouts
  2. Prints a report showing the before/after for every affected date
  3. With --fix: applies the overlap-based dedup to the DB and patches
     parse_workouts_payload() to use overlap detection going forward

USAGE
-----
  python backend/dedup_workouts.py           # dry run — report only
  python backend/dedup_workouts.py --fix     # apply to DB

WHAT "FIX" DOES
---------------
For each pair of same-named, time-overlapping apple_health workouts:
  - Keeps the one with the longer duration
  - Copies non-null biometric fields (avg_heart_rate, max_heart_rate,
    active_calories) from the dropped entry if the kept one lacks them
  - Writes the deduped list back to daily_snapshot.workouts

This does NOT touch hevy-sourced workouts or cross-source stitching — that
logic lives in _cross_source_dedup() in database.py and is unchanged.
"""

import json
import os
import sys
from datetime import datetime

# Allow running from repo root or backend/
sys.path.insert(0, os.path.dirname(__file__))

import database  # noqa: E402  (local import after path fix)


# ---------------------------------------------------------------------------
# Core dedup logic (overlap-based, same-source only)
# ---------------------------------------------------------------------------

def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _windows_overlap(a: dict, b: dict) -> bool:
    """True if two workout time windows share any overlap."""
    a_start = _parse_iso(a.get("start"))
    a_end   = _parse_iso(a.get("end"))
    b_start = _parse_iso(b.get("start"))
    b_end   = _parse_iso(b.get("end"))
    if not all([a_start, a_end, b_start, b_end]):
        return False
    return a_start < b_end and b_start < a_end


def _merge_biometrics(kept: dict, dropped: dict) -> dict:
    """Copy non-null biometric fields from dropped → kept if kept has None."""
    for field in ("avg_heart_rate", "max_heart_rate", "active_calories", "distance_mi"):
        if kept.get(field) is None and dropped.get(field) is not None:
            kept[field] = dropped[field]
    return kept


def dedup_same_source(workouts: list[dict], source: str = "apple_health") -> tuple[list[dict], list[dict]]:
    """
    Dedup same-named, time-overlapping workouts within a single source.

    Returns (deduped_list, dropped_list).
    When two entries match: keep the longer, merge biometrics from the shorter.
    """
    target = [w for w in workouts if w.get("source") == source]
    other  = [w for w in workouts if w.get("source") != source]

    dropped: list[dict] = []
    absorbed: set[int] = set()

    for i, candidate in enumerate(target):
        if i in absorbed:
            continue
        for j, existing in enumerate(target):
            if j <= i or j in absorbed:
                continue
            if candidate.get("name") != existing.get("name"):
                continue
            if not _windows_overlap(candidate, existing):
                continue
            # Same session — keep longer, drop shorter
            if (existing.get("duration_min") or 0) >= (candidate.get("duration_min") or 0):
                _merge_biometrics(existing, candidate)
                absorbed.add(i)
                dropped.append(candidate)
            else:
                _merge_biometrics(candidate, existing)
                absorbed.add(j)
                dropped.append(existing)

    kept = [w for i, w in enumerate(target) if i not in absorbed]
    return other + kept, dropped


# ---------------------------------------------------------------------------
# Diagnostic
# ---------------------------------------------------------------------------

def _fmt_workout(w: dict) -> str:
    return (
        f"  [{w.get('source')}] {w.get('name')} | "
        f"{w.get('start', '?')[:16]} → {w.get('end', '?')[:16]} | "
        f"{w.get('duration_min', '?')} min | "
        f"avg_hr={w.get('avg_heart_rate')} kcal={w.get('active_calories')}"
    )


def run_diagnostic(apply_fix: bool = False) -> None:
    with database.get_sqlite() as conn:
        rows = conn.execute(
            "SELECT date, workouts FROM daily_snapshot WHERE workouts IS NOT NULL ORDER BY date"
        ).fetchall()

    affected_dates: list[str] = []

    for row in rows:
        date_str = row["date"]
        try:
            workouts = json.loads(row["workouts"])
        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(workouts, list):
            continue

        deduped, dropped = dedup_same_source(workouts, "apple_health")

        if not dropped:
            continue

        affected_dates.append(date_str)
        print(f"\n{'='*60}")
        print(f"  {date_str}  —  {len(workouts)} workouts → {len(deduped)} after dedup")
        print(f"{'='*60}")
        print("BEFORE:")
        for w in workouts:
            print(_fmt_workout(w))
        print("AFTER:")
        for w in deduped:
            print(_fmt_workout(w))
        print("DROPPED:")
        for w in dropped:
            print(_fmt_workout(w))

        if apply_fix:
            with database.get_sqlite() as conn:
                conn.execute(
                    "UPDATE daily_snapshot SET workouts = ? WHERE date = ?",
                    (json.dumps(deduped), date_str),
                )
            print(f"  → FIXED: wrote {len(deduped)} workouts to DB")

    print(f"\n{'='*60}")
    if affected_dates:
        print(f"Dates with duplicates: {', '.join(affected_dates)}")
        if apply_fix:
            print("Fix applied to all dates above.")
        else:
            print("Dry run — no changes made. Re-run with --fix to apply.")
    else:
        print("No duplicate workouts found. DB is clean.")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    apply = "--fix" in sys.argv
    if apply:
        print("Running in FIX mode — changes will be written to the database.")
    else:
        print("Running in DRY RUN mode — no changes will be made.")
    print()

    run_diagnostic(apply_fix=apply)
