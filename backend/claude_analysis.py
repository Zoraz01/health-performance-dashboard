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
    "critique": list[str],   # exactly 3 items; stored under key "critique"
    "callout":  str
  }
"""

import asyncio
import json
import logging
import shutil
from datetime import date as _date, timedelta

log = logging.getLogger(__name__)

CLAUDE_BIN: str | None = shutil.which("claude")


def _get_claude_bin() -> str:
    if not CLAUDE_BIN:
        raise RuntimeError(
            "claude binary not found on PATH — install Claude Code CLI or set PATH correctly"
        )
    return CLAUDE_BIN


def _is_score(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


_PROMPT_HEADER = """\
You are a personal sports science analyst. You have access to one user's Apple Health \
and Hevy training data. Your job is to give an honest, specific daily readout — not \
generic coaching advice.

## User profile
- Training program: Push / Pull / Legs split, targeting 3–4 resistance sessions per week, supplemented by recreational sport
- Sport activity: plays basketball, volleyball, and similar court/team sports — tracked via Apple Health as cardio workouts. These count as real training load: cardiovascular stress, lower body explosive demand (quads, calves, glutes), and lateral movement. Factor sport sessions into recovery scoring and training quality accordingly.
- Data sources: Apple Health (steps, HRV, resting HR, cardio recovery, avg heart rate, \
body weight, sleep, SpO2, cardio workouts) + Hevy app (resistance training: exercises, \
sets, reps, load in kg). Apple Watch is the primary sensor; a RingConn ring supplements \
it and will eventually replace it.
- Goal: Build strength and muscle, improve cardiovascular fitness

## What you are analyzing
This is YESTERDAY's completed data — all Apple Health syncs and Hevy workouts for the \
day are final by the time this runs (3 am nightly job).

## Output format

Respond with VALID JSON ONLY.
- No markdown fences (no ```json or ```).
- No text, commentary, or explanation before or after the JSON object.
- All score values must be integers (whole numbers, never floats like 7.5).
- All score values must be in range 1–10 inclusive.
- "critique" must be an array of EXACTLY 3 strings — no more, no fewer.
- "summary" must be a single string (not an array).
- "callout" must be a single string (not an array).
- Do not add any keys not listed below.

The output must match this structure exactly:

{
  "scores": {
    "overall":          <integer 1-10, weighted composite — see rubric>,
    "training_quality": <integer 1-10 — see rubric>,
    "recovery":         <integer 1-10 — see rubric>,
    "volume_balance":   <integer 1-10 — see rubric>,
    "consistency":      <integer 1-10 — see rubric>
  },
  "summary": "<2-3 sentences — name the dominant signal, cite specific numbers from the data>",
  "critique": [
    "<observation 1 — must cite an actual value from the data>",
    "<observation 2 — must cite an actual value from the data>",
    "<observation 3 — must cite an actual value from the data>"
  ],
  "callout": "<one sentence — the single highest-leverage action, specific and actionable>"
}

## Scoring rubric

Scores must be CONSISTENT and DATA-ANCHORED. The same input numbers on different days \
must produce the same score. Apply every rubric below mechanically. \
Do NOT output your calculations — compute all scores internally, then write only the final JSON.

### overall
  If today is a PLANNED REST DAY (e.g., user is on track for ~3 strength sessions/week, or appropriately resting after heavy days):
    Formula: round(volume_balance×0.35 + consistency×0.35 + recovery×0.30)
  Otherwise (Training Day):
    Formula: round(training_quality×0.35 + volume_balance×0.25 + consistency×0.20 + recovery×0.20)
  Clamp the result to the range [1, 10] before rounding.

### training_quality
  1–2  No workout logged.
  3–4  Light incidental activity only (short walk, <15 min casual movement). No structured session.
  5    Short or low-intensity sport session (<30 min, relaxed pace) or light cardio.
  6    Moderate sport session (30–60 min basketball, volleyball, etc.) or solid cardio.
  7    Long or high-intensity sport session (60+ min, competitive pace) OR solid resistance session with normal volume for the split.
  8–9  Strong resistance session (volume above recent baseline, or high intensity) OR an unusually demanding sport session combined with other activity.
  10   Exceptional. Personal record, elite effort. Rare.
  Note: basketball and volleyball are physically demanding — a full-length game or hard \
  session should score 6–7 minimum. Use avg HR and duration from the Apple Health entry \
  to gauge intensity. Resistance sessions: assess based on exercises, sets, reps, and load \
  in the Workouts section.

### recovery
  Computed deterministically from % deviation of today's HRV and resting HR versus \
  the 30-day baselines in the "30-day Baselines" section.
  Start at 5. Apply each adjustment below independently, then sum, then clamp to [1, 10].

  HRV adjustments (% vs baseline):
    HRV 5–10% above baseline  → +1
    HRV >10% above baseline   → +2
    HRV 5–10% below baseline  → −1
    HRV >10% below baseline   → −2

  Resting HR adjustments — READ THE MEDICATION RULE BELOW FIRST:
    Resting HR 3–5 bpm above baseline → −1
    Resting HR >5 bpm above baseline  → −2

  MEDICATION RULE (check the "Medications Logged Today" section before scoring resting HR):
    If a stimulant medication (Adderall, amphetamine, methylphenidate, or similar) is \
    listed in "Medications Logged Today", the resting HR elevation is pharmacological, \
    NOT a recovery signal. In that case: skip both resting HR adjustments entirely. \
    The HRV adjustments still apply as normal.

  Compounding penalty:
    If BOTH HRV is below baseline AND resting HR is above baseline (and no stimulant \
    medication exemption applies) → apply an additional −1.

  User-note penalties:
    User Notes mention poor sleep, illness → −1 additional.
    User Notes mention alcohol → −2 additional (alcohol suppresses HRV; sensors may \
    underreport the impact).

  This formula is strict — do not adjust recovery based on narrative judgement or \
  training context. Only the inputs listed above move the score.

### volume_balance
  Based on the Muscle Recovery Status section: how recently each major group was trained.
  10  All push / pull / legs groups trained within the last 7 days.
  7–8 Minor gap — one group at 8–14 days.
  4–6 Clear neglect — a full category (push, pull, or legs) at 10+ days.
  1–3 Majority of muscle groups untrained for 14+ days (detrained or just starting out).

### consistency
  Count resistance sessions AND substantial/intense Apple Health cardio workouts (>30 min duration or high HR) in the 7-Day Training History. Short or light incidental cardio does NOT count.
  1–2  0 valid sessions.
  3–4  1 valid session.
  5–6  2 valid sessions.
  7–8  3 valid sessions.
  9–10 4+ valid sessions.

## Tone
You are direct, a little critical, and occasionally funny — but always earned and rooted \
in the data. Think of a coach who genuinely wants the user to improve and isn't afraid to \
call out laziness or bad decisions, but also acknowledges when things are actually going well.

- When the data is bad (skipped sessions, poor recovery, long gaps), be blunt and a little \
  cutting. Make it sting just enough to be motivating, citing specific gaps from the data.
- When the user clearly pushed hard or bounced back, acknowledge it specifically. Do not use generic AI praise.
- Humour should be dry and situational, not forced. If the data doesn't call for it, skip it. \
  Never funny at the expense of accuracy.
- The callout is the one place to be direct and a bit sharp if warranted — this is the line \
  that should make the user want to close the app and go train.

## Rules
- Every critique point must reference a specific number from the data. No vague statements.
- If User Notes are present, weight them heavily — the user knows context sensors miss.
- If sleep data is absent, explicitly note it in the summary and do not assume good sleep.
- Callout must be one punchy, specific sentence. If the situation calls for it, make it land.
- Do not use phrases like "great job", "keep it up", or "well done" unless the data \
  actually justifies a strong reaction.
- Do NOT re-analyse or re-score the previous day. The Previous Day Context section is \
  provided only so you can write continuity-aware prose \
  (e.g. "bounced back from yesterday's 96 bpm RHR"). \
  Today's scores are derived solely from today's data and the rubric above.

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
    prev_analysis: dict | None = None,
    muscle_volume_30d: dict | None = None,
) -> str:
    lines = [f"Date: {date}", ""]

    # --- Activity ---
    lines.append("=== Activity ===")
    for key, label, unit, decimals in [
        ("steps",            "Steps",            "",     0),
        ("active_calories",  "Active Calories",  "kcal", 0),
        ("avg_heart_rate",   "Avg Heart Rate",   "bpm",  0),
        ("caffeine_mg",      "Caffeine",         "mg",   0),
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
        ("hrv_ms",            "HRV",              "ms",     1),
        ("resting_hr",        "Resting HR",       "bpm",    0),
        ("cardio_recovery",   "Cardio Recovery",  "bpm",    0),
        ("walking_hr_avg",    "Walking HR Avg",   "bpm",    0),
        ("body_weight_kg",    "Body Weight",      "kg",     1),
        ("spo2",              "Blood Oxygen",     "%",      1),
        ("respiratory_rate",  "Respiratory Rate", "br/min", 1),
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
            ("spo2_avg",            "SpO2 Avg",       "%"),
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

    # --- 30-day muscle volume totals ---
    if muscle_volume_30d:
        lines += ["", "=== 30-Day Muscle Volume (kg·reps, Hevy only) ==="]
        for muscle, vol in sorted(muscle_volume_30d.items(), key=lambda x: -x[1]):
            lines.append(f"  {muscle}: {round(vol):,}")

    # --- Previous day context ---
    # Positioned here — before 7-Day History — so Claude has continuity context
    # while it reads the week's sessions, avoiding end-of-prompt anchoring.
    if prev_analysis:
        prev_scores  = prev_analysis.get("analysis", {}).get("scores", {})
        prev_summary = (prev_analysis.get("analysis", {}).get("summary") or "").strip()[:300]
        prev_date    = prev_analysis.get("date", "")
        if any(_is_score(v) for v in prev_scores.values()):
            lines += ["", f"=== Previous Day Context ({prev_date}) ===",
                      "  (For continuity-aware prose only — do NOT re-score or re-analyse this day.)"]
            score_parts = []
            for key, label in [
                ("overall", "overall"), ("training_quality", "training"),
                ("recovery", "recovery"), ("volume_balance", "vol_balance"),
                ("consistency", "consistency"),
            ]:
                v = prev_scores.get(key)
                if _is_score(v):
                    score_parts.append(f"{label}={v}")
            if score_parts:
                lines.append(f"  Scores: {', '.join(score_parts)}")
            if prev_summary:
                lines.append(f"  Summary: {prev_summary}")

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

    # --- Medications ---
    meds_raw = snapshot.get("medications_today")
    if meds_raw:
        if isinstance(meds_raw, str):
            try:
                meds_raw = json.loads(meds_raw)
            except Exception:
                meds_raw = None
        if meds_raw:
            lines += ["", "=== Medications Logged Today ==="]
            for med in meds_raw:
                lines.append(f"  · {med}")
            lines.append("  Note: stimulant medications (e.g. Adderall) raise resting HR pharmacologically — see rubric.")

    # --- User notes ---
    notes = (snapshot.get("notes") or "").strip()
    if notes:
        lines += ["", "=== User Notes (context sensors cannot capture) ==="]
        lines.append(f"  {notes}")

    return _PROMPT_HEADER + "\n".join(lines)


async def run_analysis(
    date: str,
    snapshot: dict,
    baselines: dict | None = None,
    history: list[dict] | None = None,
    prev_analysis: dict | None = None,
    muscle_volume_30d: dict | None = None,
    timeout: int = 180,
) -> tuple[dict, str]:
    prompt = _build_prompt(date, snapshot, baselines, history, prev_analysis, muscle_volume_30d)
    log.info("[claude_analysis] invoking claude CLI for %s (~%d chars)", date, len(prompt))

    proc = await asyncio.create_subprocess_exec(
        _get_claude_bin(), "--print", "--output-format", "text",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(input=prompt.encode()),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        log.error("[claude_analysis] claude CLI timed out after %ds for %s", timeout, date)
        raise RuntimeError(f"claude CLI timed out after {timeout}s")

    if proc.returncode != 0:
        err = stderr_bytes.decode().strip()
        log.error("[claude_analysis] claude CLI exited %d: %s", proc.returncode, err[:300])
        raise RuntimeError(f"claude CLI failed (exit {proc.returncode}): {err[:200]}")

    raw = stdout_bytes.decode().strip()
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

    # --- Post-parse schema validation ---
    # Log warnings for any deviation so drift is visible in logs immediately.
    _SCORE_KEYS = {"overall", "training_quality", "recovery", "volume_balance", "consistency"}
    scores = parsed.get("scores", {})
    for sk in _SCORE_KEYS:
        v = scores.get(sk)
        if v is None:
            log.warning("[claude_analysis] missing score key '%s' for %s", sk, date)
        elif not isinstance(v, int) or isinstance(v, bool):
            log.warning(
                "[claude_analysis] score '%s' is not an integer (got %r) for %s — coercing",
                sk, v, date,
            )
            scores[sk] = int(round(float(v)))
        elif not (1 <= v <= 10):
            log.warning(
                "[claude_analysis] score '%s' = %r out of range [1,10] for %s — clamping",
                sk, v, date,
            )
            scores[sk] = max(1, min(10, v))

    critique = parsed.get("critique")
    if not isinstance(critique, list):
        log.warning("[claude_analysis] 'critique' is not a list for %s (got %r)", date, type(critique))
    elif len(critique) != 3:
        log.warning(
            "[claude_analysis] 'critique' has %d items (expected 3) for %s",
            len(critique), date,
        )

    for str_key in ("summary", "callout"):
        if not isinstance(parsed.get(str_key), str):
            log.warning("[claude_analysis] '%s' is not a string for %s", str_key, date)

    return parsed, raw
