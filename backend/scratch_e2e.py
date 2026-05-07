"""
End-to-end smoke test — ingests from test_logs/ and verifies both write paths.

Apple Health data in test_logs is from 2026-04-30.
Hevy data in test_logs is from 2026-05-02/03.
No single date has both sources, so snapshot_complete is verified separately
via database.py --smoke. This test verifies each write path end-to-end.

Run from backend/: python3.14 scratch_e2e.py
"""
import asyncio
import glob
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from database import init_db, upsert_snapshot_hevy, get_snapshot, get_sqlite
from apple_health import ingest_metrics, ingest_workouts, _detect_latest_date
from muscle_map import aggregate_daily_volume, get_muscle_groups

def _latest(pattern: str) -> str:
    matches = sorted(glob.glob(f"test_logs/{pattern}"))
    if not matches:
        raise FileNotFoundError(f"No files matching test_logs/{pattern}")
    return matches[-1]


async def main():
    init_db()

    # --- Apple Health metrics ---
    print("\n=== Apple Health metrics ===")
    with open(_latest("apple_health_2*.json")) as f:
        m_payload = json.load(f)

    ah_date = _detect_latest_date(m_payload)
    print(f"Auto-detected date: {ah_date}")

    fields = ingest_metrics(m_payload, ah_date)
    print(f"Fields written ({len(fields)}):")
    for k, v in sorted(fields.items()):
        print(f"  {k:25s} {v}")

    snap = get_snapshot(ah_date)
    assert snap is not None, "Apple Health snapshot row missing"
    assert snap["steps"] is not None, "steps not written"
    assert snap["apple_health_at"] is not None, "apple_health_at not set"
    print(f"Snapshot row OK — steps={snap['steps']}, hrv={snap['hrv_ms']}")

    # --- Apple Health workouts ---
    print("\n=== Apple Health workouts ===")
    with open(_latest("apple_health_workouts_*.json")) as f:
        w_payload = json.load(f)

    # auto-detect date from first workout
    raw_wkts = w_payload.get("data", {}).get("workouts") or []
    from apple_health import _local_date
    wkt_date = _local_date(raw_wkts[0]["start"]) if raw_wkts else ah_date
    ah_workouts = ingest_workouts(w_payload, wkt_date)
    print(f"Workouts written for {wkt_date}: {len(ah_workouts)}")
    snap = get_snapshot(wkt_date)
    assert snap["workouts"], "workouts column empty after apple_health ingest"
    print(f"Workouts column OK — {len(snap['workouts'])} entries")

    # --- Hevy workouts ---
    hevy_path = _latest("hevy_workouts_*.json")
    with open(hevy_path) as f:
        hevy_workouts_raw: list[dict] = json.load(f)

    # Auto-detect the most recent date across all workouts in the file
    from zoneinfo import ZoneInfo
    from datetime import datetime
    LOCAL_TZ = ZoneInfo("America/Toronto")

    all_dates = sorted({
        datetime.fromisoformat(w["start_time"].replace("Z", "+00:00"))
        .astimezone(LOCAL_TZ).date().isoformat()
        for w in hevy_workouts_raw if w.get("start_time")
    })
    hevy_date = all_dates[-1] if all_dates else None
    assert hevy_date, "No workout dates found in hevy file"
    print(f"\n=== Hevy workouts ({hevy_date}) ===")

    hevy_workouts = []
    with get_sqlite() as conn:
        for w in hevy_workouts_raw:
            start_local = datetime.fromisoformat(
                w["start_time"].replace("Z", "+00:00")
            ).astimezone(LOCAL_TZ).date().isoformat()
            if start_local != hevy_date:
                continue
            enriched_exercises = []
            for ex in w.get("exercises", []):
                tid = ex.get("exercise_template_id")
                if tid:
                    mg = get_muscle_groups(tid, conn)
                    ex = {**ex,
                          "primary_muscle_group":    mg["primary"],
                          "secondary_muscle_groups": mg["secondary"],
                          "type":                    mg["type"]}
                enriched_exercises.append(ex)
            hevy_workouts.append({**w, "exercises": enriched_exercises})

    body_weight_kg = 61.235042773811365
    muscle_volume = aggregate_daily_volume(hevy_workouts, body_weight_kg)
    print(f"Muscle volume ({len(muscle_volume)} groups):")
    for muscle, vol in sorted(muscle_volume.items(), key=lambda x: -x[1]):
        print(f"  {muscle:20s} {vol:>8.1f}")

    upsert_snapshot_hevy(hevy_date, body_weight_kg, muscle_volume, hevy_workouts)
    snap = get_snapshot(hevy_date)
    assert snap is not None, "Hevy snapshot row missing"
    assert snap["muscle_volume"], "muscle_volume empty"
    assert snap["hevy_at"] is not None, "hevy_at not set"
    assert snap["workouts"], "workouts empty after hevy upsert"
    print(f"Hevy snapshot OK — {len(snap['muscle_volume'])} muscle groups, {len(snap['workouts'])} workouts")

    # --- get_muscle_groups DB lookup ---
    print("\n=== get_muscle_groups DB lookup ===")
    with get_sqlite() as conn:
        # Pull Up template ID from the saved workouts
        pull_up_id = None
        for w in hevy_workouts_raw:
            for ex in w.get("exercises", []):
                if "pull up" in ex.get("title", "").lower():
                    pull_up_id = ex.get("exercise_template_id")
                    break
        if pull_up_id:
            mg = get_muscle_groups(pull_up_id, conn)
            print(f"Pull Up ({pull_up_id}): primary={mg['primary']} secondary={mg['secondary']}")
            assert mg["primary"] == "lats", f"expected lats, got {mg['primary']}"
        else:
            print("No Pull Up exercise found in test data — skipping lookup check")

    print("\n=== All checks passed ===")

asyncio.run(main())
