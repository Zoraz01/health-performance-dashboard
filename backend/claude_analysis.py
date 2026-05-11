"""
Claude-powered daily analysis — invokes the Claude Code CLI as a subprocess.

Entrypoint: run_analysis(date, snapshot, baselines, history) -> (parsed_dict, raw_str)

Output schema (stored in daily_records.analysis):
  {
    "scores": {
      "overall":          int 1-10,
      "training_quality": int 1-10,
      "recovery":         int 1-10,
      "volume_balance":   int 1-10,
      "consistency":      int 1-10
    },
    "summary":  str,
    "critique": list[str],
    "callout":  str
  }
"""

import json
import logging
import shutil
import subprocess
from datetime import date as _date, timedelta

log = logging.getLogger(__name__)

CLAUDE_BIN = shutil.which("claude") or "/Users/zoraz/.local/bin/claude"

_PROMPT_HEADER = """\
You are a personal sports science analyst. You have access to one user's Apple Health \
and Hevy training data. Your job is to give an honest, specific daily readout — not \
generic coaching advice.

## User profile
- Training program: Push / Pull / Legs split, targeting 3–4 resistance sessions per week, supplemented by recreational sport
- Sport activity: plays basketball, volleyball, and similar court/team sports — tracked via Apple Health as cardio workouts. These count as real training load: cardiovascular stress, lower body explosive demand (quads, calves, glutes), and lateral movement. Factor sport sessions into recovery scoring and training quality accordingly.
- Data sources: Apple Health (steps, HRV, resting HR, cardio recovery, sleep, cardio \
workouts via Apple Watch) + Hevy app (resistance training: exercises, sets, reps, load in kg)
- Goal: Build strength and muscle, improve cardiovascular fitness

## What you are analyzing
This is YESTERDAY's completed data — all Apple Health syncs and Hevy workouts for the \
day are final by the time this runs (3 am nightly job).

## Output format
Respond with valid JSON only. No markdown fences. No text outside the JSON object.

{
  "scores": {
    "overall":          <int 1-10>,
    "training_quality": <int 1-10>,
    "recovery":         <int 1-10>,
    "volume_balance":   <int 1-10>,
    "consistency":      <int 1-10>
  },
  "summary": "<2-3 sentences — name the dominant signal, cite specific numbers>",
  "critique": [
    "<observation 1 — must cite an actual value from the data>",
    "<observation 2 — must cite an actual value from the data>",
    "<observation 3 — must cite an actual value from the data>"
  ],
  "callout": "<one sentence — the single highest-leverage action, specific and actionable>"
}

## Scoring rubric

overall
  Weighted composite: recovery 30% + training_quality 30% + volume_balance 20% + consistency 20%.
  Reflects readiness going into the next session. Round to nearest int.

training_quality
  1–2  No workout logged, and training frequency suggests this was not a planned rest day.
  3–4  Light incidental activity only (short walk, <15 min casual movement). No structured session.
  5    Short or low-intensity sport session (<30 min, relaxed pace) or light cardio.
  6    Moderate sport session (30–60 min basketball, volleyball, etc.) or solid cardio.
  7    Long or high-intensity sport session (60+ min, competitive pace) OR solid resistance session with normal volume for the split.
  8–9  Strong resistance session (volume above recent baseline, or high intensity) OR an unusually demanding sport session combined with other activity.
  10   Exceptional. Personal record, elite effort. Rare.
  Note: basketball and volleyball are physically demanding — a full-length game or hard session should score 6–7 minimum. Use avg HR and duration from the Apple Health entry to gauge intensity. Resistance sessions: assess based on exercises, sets, reps, and load in the Workouts section.

recovery
  Anchor at 5 (HRV and resting HR exactly at 30-day averages).
  HRV 5–10% above avg → +1. HRV >10% above avg → +2.
  HRV 5–10% below avg → −1. HRV >10% below avg → −2.
  Resting HR 3–5 bpm above avg → −1. Resting HR >5 bpm above avg → −2.
  Both metrics bad simultaneously: floor at 2.
  If User Notes mention poor sleep, illness, or alcohol — apply an additional −1 to −2 \
even if sensors look normal (alcohol suppresses HRV; the sensor may not fully capture it).

volume_balance
  Based on Muscle Recovery Status: how recently each major group was trained.
  10  All push / pull / legs groups hit within the last 7 days.
  7–8 Minor gap — one group at 8–14 days.
  4–6 Clear neglect — a full category (push, pull, or legs) at 10+ days.
  1–3 Majority of muscle groups at 14 days (detrained or just starting out).

consistency
  Based on resistance sessions in the 7-Day Training History.
  1–2  0 resistance sessions in 7 days.
  3–4  1 resistance session.
  5–6  2 resistance sessions.
  7–8  3 resistance sessions.
  9–10 4+ resistance sessions.

## Tone
You are direct, a little critical, and occasionally funny — but always earned and rooted in the data. Think of a coach who genuinely wants the user to improve and isn't afraid to call out laziness or bad decisions, but also acknowledges when things are actually going well.

- When the data is bad (skipped sessions, poor recovery, long gaps), be blunt and a little cutting. A dry comment about 14 days without legs is fair game. Make it sting just enough to be motivating.
- When the user clearly pushed hard or bounced back, acknowledge it specifically — not with empty praise, but with a concrete "this is what good looks like."
- Humour should be dry and situational, not forced. If the data doesn't call for it, skip it. Never funny at the expense of accuracy.
- The callout is the one place to be direct and a bit sharp if warranted — this is the line that should make the user want to close the app and go train.

## Rules
- Every critique point must reference a specific number from the data. No vague statements.
- If User Notes are present, weight them heavily — the user knows context sensors miss.
- If sleep data is absent, explicitly note it in the summary and do not assume good sleep.
- Callout must be one punchy, specific sentence. If the situation calls for it, make it land.
- Do not use phrases like "great job", "keep it up", or "well done" unless the data actually justifies a strong reaction.

---

Here is yesterday's data:

"""


def _fmt_workout_line(w: dict) -> list[str]:
    """Format a single workout entry into one or more prompt lines."""
    lines = []
    name     = w.get("title") or w.get("name") or "Workout"
    source   = w.get("source", "")
    duration = w.get("duration_min")
    volume   = w.get("volume_kg") or w.get("volume_lbs")
    vol_unit = "kg" if w.get("volume_kg") else "lbs"
    avg_hr   = w.get("avg_heart_rate")
    max_hr   = w.get("max_heart_rate")

    header_parts = [f"  · {name}"]
    if source == "apple_health":
        header_parts.append("(Apple Health)")
    if duration:
        header_parts.append(f"{int(round(duration))} min")
    if avg_hr:
        header_parts.append(f"avg HR {int(round(avg_hr))} bpm")
    if max_hr:
        header_parts.append(f"max {int(max_hr)} bpm")
    if volume:
        header_parts.append(f"{round(volume, 1)} {vol_unit} total volume")
    lines.append("  ".join(header_parts))

    exercises = w.get("exercises") or []
    for ex in exercises:
        ex_name = ex.get("title", "?")
        muscle  = ex.get("primary_muscle_group", "")
        sets    = ex.get("sets") or []
        if not sets:
            continue
        set_strs = []
        for s in sets:
            w_kg  = s.get("weight_kg")
            reps  = s.get("reps")
            if reps and w_kg:
                set_strs.append(f"{round(w_kg, 1)}kg×{reps}")
            elif reps:
                set_strs.append(f"×{reps}")
        if set_strs:
            lines.append(f"      {ex_name} ({muscle}): {', '.join(set_strs)}")

    return lines


def _build_prompt(
    date: str,
    snapshot: dict,
    baselines: dict | None,
    history: list[dict] | None = None,
) -> str:
    lines = [f"Date: {date}", ""]

    # --- Activity ---
    lines.append("=== Activity ===")
    for key, label, unit, decimals in [
        ("steps",            "Steps",            "",     0),
        ("active_calories",  "Active Calories",  "kcal", 0),
        ("exercise_minutes", "Exercise Minutes", "min",  0),
        ("stand_hours",      "Stand Hours",      "hrs",  0),
        ("distance_mi",      "Distance",         "mi",   1),
        ("flights_climbed",  "Flights Climbed",  "",     0),
    ]:
        val = snapshot.get(key)
        if val is not None:
            rounded = round(val, decimals) if decimals else int(round(val))
            lines.append(f"  {label}: {rounded}{' ' + unit if unit else ''}")

    # --- Recovery ---
    lines += ["", "=== Recovery ==="]
    for key, label, unit, decimals in [
        ("hrv_ms",          "HRV",             "ms",  1),
        ("resting_hr",      "Resting HR",      "bpm", 0),
        ("cardio_recovery", "Cardio Recovery", "bpm", 0),
        ("walking_hr_avg",  "Walking HR Avg",  "bpm", 0),
    ]:
        val = snapshot.get(key)
        if val is not None:
            rounded = round(val, decimals) if decimals else int(round(val))
            lines.append(f"  {label}: {rounded} {unit}")

    if baselines:
        lines += ["", "=== 30-day Baselines ==="]
        for key, label, unit in [
            ("hrv_avg",             "HRV Avg",        "ms"),
            ("resting_hr_avg",      "Resting HR Avg", "bpm"),
            ("cardio_recovery_avg", "Cardio Rec Avg", "bpm"),
            ("walking_hr_baseline", "Walking HR Base","bpm"),
        ]:
            val = baselines.get(key)
            if val is not None:
                lines.append(f"  {label}: {round(val, 1)} {unit}")

    # --- Sleep ---
    sleep_fields = {
        "sleep_total_min": "Total",
        "sleep_deep_min":  "Deep",
        "sleep_rem_min":   "REM",
        "sleep_awake_min": "Awake",
    }
    sleep_vals = {k: snapshot.get(k) for k in sleep_fields if snapshot.get(k) is not None}
    lines += ["", "=== Sleep ==="]
    if sleep_vals:
        for k, label in sleep_fields.items():
            if k in sleep_vals:
                mins = int(sleep_vals[k])
                lines.append(f"  {label}: {mins // 60}h {mins % 60}m")
    else:
        lines.append("  No sleep data recorded for this day.")

    # --- Workouts ---
    workouts = snapshot.get("workouts") or []
    if isinstance(workouts, str):
        try:
            workouts = json.loads(workouts)
        except Exception:
            workouts = []
    if workouts:
        lines += ["", "=== Workouts ==="]
        for w in workouts:
            lines.extend(_fmt_workout_line(w))

    # --- Muscle Recovery Status ---
    recovery_status = snapshot.get("recovery_status") or {}
    if isinstance(recovery_status, str):
        try:
            recovery_status = json.loads(recovery_status)
        except Exception:
            recovery_status = {}
    if recovery_status:
        lines += ["", "=== Muscle Recovery Status (days since last trained → recovery %) ==="]
        for muscle, info in recovery_status.items():
            pct  = info.get("recovery_pct")
            days = info.get("days_since_trained")
            if pct is not None:
                lines.append(f"  {muscle}: {days or '?'}d → {pct:.0f}%")

    # --- 7-day training history ---
    if history is not None:
        target = _date.fromisoformat(date)
        start  = target - timedelta(days=7)
        lines += ["", f"=== 7-Day Training History ({start.strftime('%b %d')} – {(target - timedelta(days=1)).strftime('%b %d')}) ==="]

        resistance_days = 0
        last_resistance = None

        # Build a lookup from the history list
        by_date = {h["date"]: h for h in history}

        for i in range(7):
            day = start + timedelta(days=i)
            day_str  = day.isoformat()
            day_snap = by_date.get(day_str)
            day_label = day.strftime("%a %b %d")

            if not day_snap:
                lines.append(f"  {day_label}: no data")
                continue

            wkts = day_snap.get("workouts") or []
            if isinstance(wkts, str):
                try:
                    wkts = json.loads(wkts)
                except Exception:
                    wkts = []

            if not wkts:
                lines.append(f"  {day_label}: rest")
                continue

            # Summarise workouts for the history line
            session_parts = []
            has_resistance = False
            for w in wkts:
                name   = w.get("title") or w.get("name") or "Workout"
                source = w.get("source", "")
                mv     = day_snap.get("muscle_volume") or {}
                if isinstance(mv, str):
                    try:
                        mv = json.loads(mv)
                    except Exception:
                        mv = {}
                muscles = ", ".join(sorted(mv.keys())) if mv else ""

                if source == "hevy" or (mv and any(v > 0 for v in mv.values())):
                    has_resistance = True
                    session_parts.append(f"{name} ({muscles})" if muscles else name)
                else:
                    dur = w.get("duration_min")
                    session_parts.append(f"{name}{f' {int(round(dur))} min' if dur else ''}")

            if has_resistance:
                resistance_days += 1
                last_resistance = day

            lines.append(f"  {day_label}: {' + '.join(session_parts)}")

        days_since = (target - last_resistance).days if last_resistance else ">7"
        lines.append(f"  Resistance sessions: {resistance_days}/7  |  Days since last resistance: {days_since}")

    # --- Self-reported soreness ---
    soreness = snapshot.get("soreness") or {}
    if isinstance(soreness, str):
        try:
            soreness = json.loads(soreness)
        except Exception:
            soreness = {}
    SORENESS_LABELS = ["none", "mild", "noticeable", "moderate", "significant", "severe"]
    if soreness:
        lines += ["", "=== Self-Reported Soreness ==="]
        for muscle, level in sorted(soreness.items()):
            label = SORENESS_LABELS[level] if 0 <= level <= 5 else str(level)
            lines.append(f"  {muscle}: {level}/5 ({label})")

    # --- User notes ---
    notes = (snapshot.get("notes") or "").strip()
    if notes:
        lines += ["", "=== User Notes (context sensors cannot capture) ==="]
        lines.append(f"  {notes}")

    return _PROMPT_HEADER + "\n".join(lines)


def run_analysis(
    date: str,
    snapshot: dict,
    baselines: dict | None = None,
    history: list[dict] | None = None,
    timeout: int = 120,
) -> tuple[dict, str]:
    prompt = _build_prompt(date, snapshot, baselines, history)
    log.info("[claude_analysis] invoking claude CLI for %s (~%d chars)", date, len(prompt))

    result = subprocess.run(
        [CLAUDE_BIN, "--print", "--output-format", "text"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        err = result.stderr.strip()
        log.error("[claude_analysis] claude CLI exited %d: %s", result.returncode, err[:300])
        raise RuntimeError(f"claude CLI failed (exit {result.returncode}): {err[:200]}")

    raw = result.stdout.strip()
    log.info("[claude_analysis] received %d chars for %s", len(raw), date)

    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:])
        if "```" in raw:
            raw = raw[: raw.rfind("```")]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("[claude_analysis] JSON parse error: %s\nRaw: %s", e, raw[:500])
        raise

    # Strip muscle_fatigue if Claude still returns it — we no longer use it
    parsed.pop("muscle_fatigue", None)

    return parsed, raw
