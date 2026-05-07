"""
Volume calculation and muscle group resolution for Hevy workout data.

Phase 1: pure calculation logic only — no DB reads.
Phase 3: add get_muscle_groups(exercise_template_id) that queries SQLite
         exercise_templates and enrich exercises before calling compute_exercise_volume.
"""

import json
import logging
import os
from datetime import datetime

log = logging.getLogger(__name__)

SECONDARY_VOLUME_MULTIPLIER = 0.4

EXCLUDED_PRIMARY = frozenset({"cardio", "neck", "other"})

# Exercises where primary_muscle_group == "full_body".
# Keyed by title (stable and readable; template IDs aren't).
# Percentages must sum to 1.0 per exercise.
FULL_BODY_SPLITS: dict[str, dict[str, float]] = {
    "Burpee": {
        "quadriceps": 0.20, "chest": 0.15, "glutes": 0.12, "shoulders": 0.10,
        "abdominals": 0.10, "triceps": 0.08, "hamstrings": 0.08, "calves": 0.07,
        "lower_back": 0.05, "traps": 0.03, "forearms": 0.02,
    },
    "Ball Slam": {
        "lats": 0.20, "abdominals": 0.18, "shoulders": 0.15, "traps": 0.10,
        "glutes": 0.10, "quadriceps": 0.08, "lower_back": 0.07, "triceps": 0.05,
        "hamstrings": 0.04, "calves": 0.03,
    },
    "Battle Ropes": {
        "shoulders": 0.25, "abdominals": 0.18, "traps": 0.12, "forearms": 0.10,
        "upper_back": 0.10, "glutes": 0.08, "quadriceps": 0.07, "lower_back": 0.05,
        "biceps": 0.03, "calves": 0.02,
    },
    "Kettlebell Swing": {
        "glutes": 0.28, "hamstrings": 0.22, "lower_back": 0.15, "abdominals": 0.10,
        "quadriceps": 0.08, "traps": 0.06, "forearms": 0.05, "shoulders": 0.04,
        "calves": 0.02,
    },
    "Power Clean (Barbell)": {
        "quadriceps": 0.20, "glutes": 0.18, "hamstrings": 0.14, "traps": 0.12,
        "lower_back": 0.10, "calves": 0.08, "shoulders": 0.06, "forearms": 0.05,
        "upper_back": 0.04, "abdominals": 0.03,
    },
    "Thruster (Barbell)": {
        "quadriceps": 0.25, "shoulders": 0.20, "glutes": 0.15, "triceps": 0.12,
        "upper_back": 0.08, "abdominals": 0.07, "hamstrings": 0.05, "traps": 0.04,
        "lower_back": 0.04,
    },
    "Box Jump": {
        "quadriceps": 0.28, "glutes": 0.22, "calves": 0.15, "hamstrings": 0.14,
        "abdominals": 0.08, "lower_back": 0.07, "traps": 0.03, "shoulders": 0.03,
    },
    "Bear Crawl": {
        "shoulders": 0.20, "abdominals": 0.18, "quadriceps": 0.15, "triceps": 0.10,
        "glutes": 0.10, "chest": 0.08, "lower_back": 0.07, "traps": 0.05,
        "forearms": 0.04, "calves": 0.03,
    },
    "Mountain Climbers": {
        "abdominals": 0.25, "shoulders": 0.18, "quadriceps": 0.15, "chest": 0.10,
        "glutes": 0.10, "triceps": 0.08, "lower_back": 0.07, "hamstrings": 0.04,
        "calves": 0.03,
    },
    "Turkish Get Up": {
        "shoulders": 0.20, "abdominals": 0.18, "glutes": 0.14, "quadriceps": 0.12,
        "lower_back": 0.10, "upper_back": 0.08, "traps": 0.06, "triceps": 0.05,
        "forearms": 0.04, "hamstrings": 0.03,
    },
    "Deadlift (Conventional)": {
        "glutes": 0.22, "hamstrings": 0.20, "lower_back": 0.18, "quadriceps": 0.12,
        "traps": 0.10, "forearms": 0.07, "lats": 0.05, "abdominals": 0.04,
        "upper_back": 0.02,
    },
    "Farmer's Carry": {
        "traps": 0.20, "forearms": 0.18, "abdominals": 0.15, "glutes": 0.12,
        "quadriceps": 0.10, "lower_back": 0.10, "calves": 0.06, "hamstrings": 0.05,
        "upper_back": 0.04,
    },
}


def get_muscle_groups(exercise_template_id: str, conn) -> dict:
    """Look up primary and secondary muscle groups from the SQLite exercise_templates table.

    Returns {"primary": str, "secondary": list[str]}.
    Falls back to {"primary": "unknown", "secondary": []} if id not found.
    conn must be a sqlite3.Connection (from database.get_sqlite()).
    """
    import json as _json
    row = conn.execute(
        "SELECT primary_muscle_group, secondary_muscle_groups, type "
        "FROM exercise_templates WHERE id = ?",
        (exercise_template_id,),
    ).fetchone()
    if not row:
        log.warning("exercise_template_id not found in DB: %s", exercise_template_id)
        return {"primary": "unknown", "secondary": [], "type": "weight_reps"}
    try:
        secondary = _json.loads(row["secondary_muscle_groups"] or "[]")
    except (ValueError, TypeError):
        secondary = []
    return {
        "primary": row["primary_muscle_group"],
        "secondary": secondary,
        "type": row["type"],
    }


def log_unmapped_full_body(title: str) -> None:
    """Append unmapped full_body exercise titles to a log for later review."""
    log_dir = os.path.join(os.path.dirname(__file__), "test_logs")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "unmapped_full_body.txt")
    with open(path, "a") as f:
        f.write(f"{datetime.now().isoformat()} — {title}\n")
    log.warning("full_body exercise not in FULL_BODY_SPLITS, skipping volume: %s", title)


def compute_exercise_volume(
    exercise: dict, body_weight_kg: float | None
) -> dict[str, float]:
    """
    Compute volume distributed across muscle groups for a single exercise.

    exercise must have: title, type, primary_muscle_group,
                        secondary_muscle_groups (list), sets (list)
    Each set may have: weight_kg, reps, duration_seconds

    Volume units:
      weight_reps / reps_only  → kg-reps (sets × reps × weight)
      duration                 → minutes  (sum duration_seconds / 60)

    Returns {muscle_group: volume} or {} for excluded/unmapped exercises.
    Bodyweight sets with no body_weight_kg supplied return {} silently.
    """
    sets    = exercise.get("sets") or []
    ex_type = exercise.get("type") or "weight_reps"
    primary = exercise.get("primary_muscle_group") or ""
    title   = exercise.get("title") or ""

    if primary in EXCLUDED_PRIMARY:
        return {}

    raw_volume = 0.0
    for s in sets:
        reps     = s.get("reps") or 0
        weight   = s.get("weight_kg")
        duration = s.get("duration_seconds")

        if ex_type == "duration" and duration:
            raw_volume += duration / 60.0
        elif weight is not None:
            raw_volume += reps * weight
        elif body_weight_kg is not None:
            raw_volume += reps * body_weight_kg
        # else: bodyweight set, body weight unknown — skip silently

    if raw_volume == 0:
        return {}

    if primary == "full_body":
        split = FULL_BODY_SPLITS.get(title)
        if not split:
            log_unmapped_full_body(title)
            return {}
        return {muscle: round(raw_volume * pct, 2) for muscle, pct in split.items()}

    secondary = [
        m for m in (exercise.get("secondary_muscle_groups") or [])
        if m and m not in EXCLUDED_PRIMARY
    ]

    result: dict[str, float] = {primary: raw_volume}
    for muscle in secondary:
        result[muscle] = result.get(muscle, 0.0) + raw_volume * SECONDARY_VOLUME_MULTIPLIER

    return {k: round(v, 2) for k, v in result.items()}


def aggregate_daily_volume(
    workouts: list[dict], body_weight_kg: float | None
) -> dict[str, float]:
    """
    Sum compute_exercise_volume across all exercises in all Hevy workouts for a day.
    Skips Apple Health workout entries (source='apple_health') — they carry no
    muscle-group volume data.
    """
    totals: dict[str, float] = {}
    for workout in workouts:
        if workout.get("source") == "apple_health":
            continue
        for exercise in workout.get("exercises") or []:
            for muscle, vol in compute_exercise_volume(exercise, body_weight_kg).items():
                totals[muscle] = totals.get(muscle, 0.0) + vol
    return {k: round(v, 2) for k, v in totals.items()}


if __name__ == "__main__":
    import glob

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    log_dir = os.path.join(os.path.dirname(__file__), "test_logs")

    workouts_files  = sorted(glob.glob(os.path.join(log_dir, "hevy_workouts_*.json")))
    templates_files = sorted(glob.glob(os.path.join(log_dir, "hevy_templates_*.json")))

    if not workouts_files:
        print("No hevy_workouts_*.json found in test_logs/")
        raise SystemExit(1)

    workouts_path = workouts_files[-1]
    print(f"Workouts : {os.path.basename(workouts_path)}")
    with open(workouts_path) as f:
        workouts = json.load(f)

    # In production, type/muscle_group come from DB lookup (Phase 3).
    # For Phase 1 testing, join from the template JSON which hevy.py already saved.
    templates: dict = {}
    if templates_files:
        templates_path = templates_files[-1]
        print(f"Templates: {os.path.basename(templates_path)}")
        with open(templates_path) as f:
            templates = json.load(f)
        for w in workouts:
            for ex in w.get("exercises", []):
                if "type" not in ex:
                    t = templates.get(ex.get("exercise_template_id"), {})
                    ex["type"] = t.get("type", "weight_reps")
    else:
        print("No hevy_templates_*.json found — exercise type defaults to weight_reps")

    body_weight_kg = 61.235042773811365  # most recent measurement from Hevy API
    print(f"\nBody weight: {body_weight_kg:.3f} kg  ({body_weight_kg * 2.20462:.1f} lbs)\n")

    # Per-exercise breakdown
    for w in workouts:
        date = w.get("start_time", "")[:10]
        print(f"Workout: {w['title']}  [{date}]")
        for ex in w.get("exercises", []):
            by_muscle = compute_exercise_volume(ex, body_weight_kg)
            sets_count = len(ex.get("sets", []))
            ex_type = ex.get("type", "?")
            primary = ex.get("primary_muscle_group", "?")
            if by_muscle:
                muscle_str = ", ".join(f"{m}: {v:.0f}" for m, v in by_muscle.items())
            else:
                muscle_str = "(excluded or unmapped)"
            print(f"  {ex['title']:38s} [{ex_type:12s}] {sets_count} sets  →  {muscle_str}")
        print()

    # Daily totals
    totals = aggregate_daily_volume(workouts, body_weight_kg)
    if totals:
        print("Daily muscle volume totals (kg-reps):")
        for muscle, vol in sorted(totals.items(), key=lambda x: -x[1]):
            bar = "█" * int(vol / 200)
            print(f"  {muscle:20s}  {vol:>8.1f}  {bar}")
    else:
        print("No muscle volume computed (rest day or all exercises excluded).")
