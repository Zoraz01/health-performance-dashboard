"""
Database layer — DuckDB (raw blobs) + SQLite (normalized app state).

Both files live on NVME at /Volumes/NVME/health-dashboard/data/.

Write paths:
  upsert_snapshot_apple_health()          — Apple Health metrics
  upsert_snapshot_apple_health_workouts() — Apple Health workouts column only
  upsert_snapshot_hevy()                  — Hevy muscle volume + workouts
  append_raw_blob()                       — append-only to DuckDB (errors swallowed)
  replace_workouts_for_source()           — merge helper used by both upsert paths

Never use INSERT OR REPLACE on daily_snapshot — it drops columns not in the statement.
"""

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Generator

import duckdb

log = logging.getLogger(__name__)

DATA_DIR    = "/Volumes/NVME/health-dashboard/data"
DUCKDB_PATH = os.path.join(DATA_DIR, "health_raw.duckdb")
SQLITE_PATH = os.path.join(DATA_DIR, "health_app.sqlite")

# Columns written exclusively by each source — enforces partial-upsert discipline.
APPLE_HEALTH_COLUMNS = (
    "body_weight_kg", "steps", "active_calories", "basal_calories",
    "exercise_minutes", "stand_hours", "distance_mi", "flights_climbed",
    "hrv_ms", "resting_hr", "cardio_recovery", "avg_heart_rate",
    "walking_hr_avg", "sleep_total_min", "sleep_deep_min",
    "sleep_rem_min", "sleep_awake_min", "medications_today",
)

HEVY_COLUMNS = ("body_weight_kg", "muscle_volume", "workouts")

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

# Explicit list — avoids silent statement drops from split(";") on unterminated stmts.
_DUCKDB_DDL_STATEMENTS: list[str] = [
    "CREATE SEQUENCE IF NOT EXISTS seq_raw_apple_health",
    "CREATE SEQUENCE IF NOT EXISTS seq_raw_apple_health_workouts",
    "CREATE SEQUENCE IF NOT EXISTS seq_raw_hevy_workouts",
    """CREATE TABLE IF NOT EXISTS raw_apple_health (
    id          BIGINT PRIMARY KEY DEFAULT nextval('seq_raw_apple_health'),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    date        DATE NOT NULL,
    payload     JSON NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS raw_apple_health_workouts (
    id          BIGINT PRIMARY KEY DEFAULT nextval('seq_raw_apple_health_workouts'),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    date        DATE NOT NULL,
    payload     JSON NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS raw_hevy_workouts (
    id          BIGINT PRIMARY KEY DEFAULT nextval('seq_raw_hevy_workouts'),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    date        DATE NOT NULL,
    payload     JSON NOT NULL
)""",
    "CREATE INDEX IF NOT EXISTS idx_raw_apple_health_date ON raw_apple_health(date)",
    "CREATE INDEX IF NOT EXISTS idx_raw_apple_health_workouts_date ON raw_apple_health_workouts(date)",
    "CREATE INDEX IF NOT EXISTS idx_raw_hevy_workouts_date ON raw_hevy_workouts(date)",
    # Intraday timeseries (HR, steps per sample)
    """CREATE TABLE IF NOT EXISTS daily_timeseries (
    date         DATE        NOT NULL,
    ts           TIMESTAMPTZ NOT NULL,
    metric       VARCHAR     NOT NULL,
    value        DOUBLE,
    PRIMARY KEY (date, ts, metric)
)""",
    "CREATE INDEX IF NOT EXISTS idx_daily_ts_date ON daily_timeseries(date)",
    # Per-workout timeseries
    """CREATE TABLE IF NOT EXISTS workout_hr_samples (
    workout_id  VARCHAR NOT NULL,
    source      VARCHAR NOT NULL,
    ts          TIMESTAMPTZ NOT NULL,
    hr_avg      DOUBLE,
    hr_min      DOUBLE,
    hr_max      DOUBLE,
    calories    DOUBLE,
    steps       DOUBLE,
    PRIMARY KEY (workout_id, ts)
)""",
    """CREATE TABLE IF NOT EXISTS workout_sets (
    workout_id             VARCHAR NOT NULL,
    exercise_index         INTEGER NOT NULL,
    exercise_title         VARCHAR NOT NULL,
    exercise_template_id   VARCHAR,
    primary_muscle_group   VARCHAR,
    set_index              INTEGER NOT NULL,
    set_type               VARCHAR,
    weight_kg              DOUBLE,
    reps                   INTEGER,
    duration_seconds       INTEGER,
    rpe                    DOUBLE,
    PRIMARY KEY (workout_id, exercise_index, set_index)
)""",
]

_SQLITE_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS exercise_templates (
    id                      TEXT PRIMARY KEY,
    title                   TEXT NOT NULL,
    type                    TEXT NOT NULL,
    primary_muscle_group    TEXT NOT NULL,
    secondary_muscle_groups TEXT NOT NULL,
    is_custom               INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS daily_snapshot (
    date                DATE PRIMARY KEY,
    body_weight_kg      REAL,
    steps               INTEGER,
    active_calories     REAL,
    basal_calories      REAL,
    exercise_minutes    REAL,
    stand_hours         INTEGER,
    distance_mi         REAL,
    flights_climbed     INTEGER,
    hrv_ms              REAL,
    resting_hr          INTEGER,
    cardio_recovery     REAL,
    avg_heart_rate      REAL,
    walking_hr_avg      REAL,
    sleep_total_min     REAL,
    sleep_deep_min      REAL,
    sleep_rem_min       REAL,
    sleep_awake_min     REAL,
    muscle_volume       TEXT CHECK (muscle_volume IS NULL OR json_valid(muscle_volume)),
    workouts            TEXT CHECK (workouts IS NULL OR json_valid(workouts)),
    recovery_status     TEXT CHECK (recovery_status IS NULL OR json_valid(recovery_status)),
    medications_today   TEXT CHECK (medications_today IS NULL OR json_valid(medications_today)),
    apple_health_at     TIMESTAMP,
    hevy_at             TIMESTAMP,
    snapshot_complete   INTEGER NOT NULL DEFAULT 0,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- WHEN guard prevents the trigger from firing on its own updated_at write (avoids recursion).
CREATE TRIGGER IF NOT EXISTS daily_snapshot_touch
AFTER UPDATE ON daily_snapshot
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE daily_snapshot SET updated_at = CURRENT_TIMESTAMP WHERE date = OLD.date;
END;

CREATE TABLE IF NOT EXISTS daily_records (
    date              DATE PRIMARY KEY,
    -- metrics snapshot (copied from daily_snapshot at analysis time)
    steps             INTEGER,
    active_calories   REAL,
    basal_calories    REAL,
    resting_hr        INTEGER,
    hrv_ms            REAL,
    cardio_recovery   REAL,
    exercise_minutes  REAL,
    stand_hours       INTEGER,
    distance_mi       REAL,
    flights_climbed   INTEGER,
    body_weight_kg    REAL,
    avg_heart_rate    REAL,
    walking_hr_avg    REAL,
    sleep_total_min   REAL,
    sleep_deep_min    REAL,
    sleep_rem_min     REAL,
    sleep_awake_min   REAL,
    -- workout summary
    workout_count     INTEGER,
    workout_names     TEXT,
    muscle_volume     TEXT CHECK (muscle_volume IS NULL OR json_valid(muscle_volume)),
    top_muscle_group  TEXT,
    total_volume_kg   REAL,
    -- muscle fatigue per muscle group (JSON: {"lats": "fatigued", ...})
    muscle_fatigue    TEXT,
    -- recovery status snapshot (JSON: {"lats": {"days_since_trained": 0, "recovery_pct": 0}, ...})
    recovery_status   TEXT CHECK (recovery_status IS NULL OR json_valid(recovery_status)),
    -- claude analysis
    score_overall     INTEGER,
    score_training    INTEGER,
    score_recovery    INTEGER,
    score_balance     INTEGER,
    score_consistency INTEGER,
    summary           TEXT,
    critique          TEXT,
    callout           TEXT,
    history_days      INTEGER,
    raw_response      TEXT,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS soreness_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    date      DATE NOT NULL,
    muscle    TEXT NOT NULL,
    soreness  INTEGER NOT NULL CHECK (soreness BETWEEN 0 AND 5),
    logged_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (date, muscle)
);

CREATE TABLE IF NOT EXISTS medications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    dosage       TEXT,
    frequency    TEXT,
    time_of_day  TEXT,
    notes        TEXT,
    active       INTEGER NOT NULL DEFAULT 1,
    started_date TEXT,
    stopped_date TEXT
);

CREATE INDEX IF NOT EXISTS idx_medications_active ON medications(active);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

@contextmanager
def get_sqlite() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(SQLITE_PATH, isolation_level=None)  # autocommit
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_duckdb() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    # Fresh connection per call — DuckDB doesn't allow concurrent write connections.
    con = duckdb.connect(DUCKDB_PATH)
    try:
        yield con
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

# Additive migrations — each runs ALTER TABLE and swallows "duplicate column" errors.
# Add new entries here whenever a column is added to an existing table.
_SQLITE_MIGRATIONS: list[str] = [
    "ALTER TABLE daily_snapshot ADD COLUMN recovery_status TEXT CHECK (recovery_status IS NULL OR json_valid(recovery_status))",
    "ALTER TABLE daily_snapshot ADD COLUMN notes TEXT",
    # Multi-user readiness: user_id on data tables.
    "ALTER TABLE daily_snapshot ADD COLUMN user_id INTEGER",
    "ALTER TABLE daily_records  ADD COLUMN user_id INTEGER",
    "CREATE INDEX IF NOT EXISTS idx_daily_snapshot_user ON daily_snapshot(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_daily_records_user  ON daily_records(user_id)",
    # Clerk auth migration
    "ALTER TABLE users ADD COLUMN clerk_user_id TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_clerk_id ON users(clerk_user_id) WHERE clerk_user_id IS NOT NULL",
    "ALTER TABLE daily_snapshot ADD COLUMN medications_today TEXT CHECK (medications_today IS NULL OR json_valid(medications_today))",
    # Admin flag — owner bootstrapped at startup via _bootstrap_owner_admin()
    "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0",
]


def init_db() -> None:
    """Create both DB files and all tables/indexes/sequences if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)

    with get_duckdb() as con:
        for stmt in _DUCKDB_DDL_STATEMENTS:
            con.execute(stmt)
        log.info("DuckDB schema ready: %s", DUCKDB_PATH)

    with get_sqlite() as conn:
        conn.executescript(_SQLITE_DDL)
        for stmt in _SQLITE_MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise
        log.info("SQLite schema ready: %s", SQLITE_PATH)

    _bootstrap_owner_admin()


def _bootstrap_owner_admin() -> None:
    """Ensure the OWNER_EMAIL user is flagged as admin on every startup.

    Safe to call repeatedly — only updates when is_admin=0 to avoid no-ops.
    Does nothing if OWNER_EMAIL is not set or no matching row exists yet
    (the row is created on first Clerk login; the next startup will promote it).
    """
    owner = os.environ.get("OWNER_EMAIL", "").lower().strip()
    if not owner:
        return
    with get_sqlite() as conn:
        cursor = conn.execute(
            "UPDATE users SET is_admin = 1 WHERE email = ? AND is_admin = 0",
            (owner,),
        )
        if cursor.rowcount:
            log.info("Bootstrapped is_admin=1 for owner %s", owner)


# ---------------------------------------------------------------------------
# Raw blob storage (DuckDB — append-only, errors swallowed)
# ---------------------------------------------------------------------------

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
    into the hevy entry and drop the apple_health entry. Hevy wins on exercise
    data; Apple Health provides the biometric envelope for the full gym session.
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
    conn: sqlite3.Connection, date: str, source: str, new_entries: list[dict]
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
        "INSERT INTO daily_snapshot (date, workouts) VALUES (?, ?) "
        "ON CONFLICT(date) DO UPDATE SET workouts = excluded.workouts",
        (date, json.dumps(merged)),
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

def upsert_snapshot_apple_health(date: str, fields: dict) -> bool:
    """Write Apple-Health-derived metric fields and set apple_health_at.

    Returns True if this write completed the snapshot (triggers Claude).
    """
    fields = {k: v for k, v in fields.items() if k in APPLE_HEALTH_COLUMNS and v is not None}
    if not fields:
        log.warning("upsert_snapshot_apple_health: no valid fields for %s", date)
        return False

    cols = list(fields.keys()) + ["apple_health_at"]
    placeholders = ", ".join("?" for _ in cols)
    update_clause = ", ".join(f"{c} = excluded.{c}" for c in cols)
    sql = (
        f"INSERT INTO daily_snapshot (date, {', '.join(cols)}) "
        f"VALUES (?, {placeholders}) "
        f"ON CONFLICT(date) DO UPDATE SET {update_clause}"
    )
    values = [date] + [fields[c] for c in cols[:-1]] + [_now_iso()]

    with get_sqlite() as conn:
        conn.execute(sql, values)
        return _maybe_complete(conn, date)


def upsert_snapshot_apple_health_workouts(date: str, workouts: list[dict]) -> None:
    """Merge Apple Health workout entries into the workouts column for date."""
    with get_sqlite() as conn:
        replace_workouts_for_source(conn, date, "apple_health", workouts)
    log.info("apple_health workouts upserted for %s (%d entries)", date, len(workouts))


def upsert_snapshot_recovery_status(date: str, recovery_status: dict) -> None:
    """Store the computed recovery status snapshot for date."""
    with get_sqlite() as conn:
        conn.execute(
            "INSERT INTO daily_snapshot (date, recovery_status) VALUES (?, ?) "
            "ON CONFLICT(date) DO UPDATE SET recovery_status = excluded.recovery_status",
            (date, json.dumps(recovery_status)),
        )
    log.info("recovery_status stored for %s", date)


def get_weekly_summary(before_date: str, days: int = 7) -> list[dict]:
    """
    Return per-day summaries for the N days immediately before before_date (exclusive).
    Used to build the 7-day training history section of the Claude prompt.
    """
    from datetime import date as _date, timedelta
    from_date = (_date.fromisoformat(before_date) - timedelta(days=days)).isoformat()
    with get_sqlite() as conn:
        rows = conn.execute(
            """SELECT date, steps, exercise_minutes, sleep_total_min, hrv_ms,
                      workouts, muscle_volume
               FROM daily_snapshot
               WHERE date >= ? AND date < ?
               ORDER BY date""",
            (from_date, before_date),
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


def upsert_snapshot_notes(date: str, notes: str) -> None:
    """Store free-text check-in notes for date."""
    with get_sqlite() as conn:
        conn.execute(
            "INSERT INTO daily_snapshot (date, notes) VALUES (?, ?) "
            "ON CONFLICT(date) DO UPDATE SET notes = excluded.notes",
            (date, notes.strip()),
        )
    log.info("notes stored for %s", date)


def get_soreness_for_date(date: str) -> dict[str, int]:
    """Return {muscle: soreness_level} for a given date from soreness_log."""
    with get_sqlite() as conn:
        rows = conn.execute(
            "SELECT muscle, soreness FROM soreness_log WHERE date = ?", (date,)
        ).fetchall()
    return {row["muscle"]: row["soreness"] for row in rows}


def upsert_snapshot_hevy(
    date: str,
    body_weight_kg: float | None,
    muscle_volume: dict | None,
    workouts: list[dict],
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
            (date, body_weight_kg, muscle_volume, hevy_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            body_weight_kg = COALESCE(daily_snapshot.body_weight_kg, excluded.body_weight_kg),
            muscle_volume  = excluded.muscle_volume,
            hevy_at        = excluded.hevy_at
    """
    with get_sqlite() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute(sql, (
                date,
                body_weight_kg,
                json.dumps(muscle_volume) if muscle_volume is not None else None,
                _now_iso(),
            ))
            replace_workouts_for_source(conn, date, "hevy", workouts)
            result = _maybe_complete(conn, date)
            conn.execute("COMMIT")
            return result
        except Exception:
            conn.execute("ROLLBACK")
            raise


# ---------------------------------------------------------------------------
# daily_records — two-phase write: snapshot first, analysis second
# ---------------------------------------------------------------------------

def upsert_daily_record_snapshot(date: str, snapshot: dict) -> None:
    """Write the metrics + workout portion of daily_records when snapshot completes.

    Called as soon as both Apple Health and Hevy data have arrived — before
    Claude runs. Claude analysis fields are NULL until upsert_daily_record_analysis()
    fills them in. Safe to call multiple times (idempotent on non-Claude fields).
    """
    snap = snapshot or {}
    workouts: list[dict] = snap.get("workouts") or []
    workout_names = [w.get("name") or w.get("title") for w in workouts
                     if w.get("name") or w.get("title")]
    muscle_volume: dict = snap.get("muscle_volume") or {}
    top_muscle = max(muscle_volume, key=muscle_volume.get) if muscle_volume else None
    total_volume = round(sum(muscle_volume.values()), 2) if muscle_volume else None

    with get_sqlite() as conn:
        conn.execute(
            """
            INSERT INTO daily_records (
                date,
                steps, active_calories, basal_calories, resting_hr, hrv_ms,
                cardio_recovery, exercise_minutes, stand_hours, distance_mi,
                flights_climbed, body_weight_kg, avg_heart_rate, walking_hr_avg,
                sleep_total_min, sleep_deep_min, sleep_rem_min, sleep_awake_min,
                workout_count, workout_names, muscle_volume, top_muscle_group,
                total_volume_kg, recovery_status
            ) VALUES (
                ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(date) DO UPDATE SET
                steps           = excluded.steps,
                active_calories = excluded.active_calories,
                basal_calories  = excluded.basal_calories,
                resting_hr      = excluded.resting_hr,
                hrv_ms          = excluded.hrv_ms,
                cardio_recovery = excluded.cardio_recovery,
                exercise_minutes = excluded.exercise_minutes,
                stand_hours     = excluded.stand_hours,
                distance_mi     = excluded.distance_mi,
                flights_climbed = excluded.flights_climbed,
                body_weight_kg  = excluded.body_weight_kg,
                avg_heart_rate  = excluded.avg_heart_rate,
                walking_hr_avg  = excluded.walking_hr_avg,
                sleep_total_min = excluded.sleep_total_min,
                sleep_deep_min  = excluded.sleep_deep_min,
                sleep_rem_min   = excluded.sleep_rem_min,
                sleep_awake_min = excluded.sleep_awake_min,
                workout_count   = excluded.workout_count,
                workout_names   = excluded.workout_names,
                muscle_volume   = excluded.muscle_volume,
                top_muscle_group = excluded.top_muscle_group,
                total_volume_kg = excluded.total_volume_kg,
                recovery_status = excluded.recovery_status
            """,
            (
                date,
                snap.get("steps"), snap.get("active_calories"), snap.get("basal_calories"),
                snap.get("resting_hr"), snap.get("hrv_ms"), snap.get("cardio_recovery"),
                snap.get("exercise_minutes"), snap.get("stand_hours"), snap.get("distance_mi"),
                snap.get("flights_climbed"), snap.get("body_weight_kg"),
                snap.get("avg_heart_rate"), snap.get("walking_hr_avg"),
                snap.get("sleep_total_min"), snap.get("sleep_deep_min"),
                snap.get("sleep_rem_min"), snap.get("sleep_awake_min"),
                len(workouts),
                json.dumps(workout_names) if workout_names else None,
                json.dumps(muscle_volume) if muscle_volume else None,
                top_muscle, total_volume,
                json.dumps(snap.get("recovery_status")) if snap.get("recovery_status") else None,
            ),
        )
    log.info("daily_records snapshot written for %s", date)


def upsert_daily_record_analysis(
    date: str,
    parsed: dict,
    raw: str,
    history_days: int | None = None,
    force: bool = False,
) -> None:
    """Fill in Claude's analysis fields on an existing daily_records row.

    force=True  — always overwrite (used by /api/analyze endpoint and 4-h cron).
    force=False — skip if score_overall is already set (used by nightly job).
    """
    scores = parsed.get("scores", {})
    where_clause = "" if force else "WHERE daily_records.score_overall IS NULL"
    with get_sqlite() as conn:
        cursor = conn.execute(
            f"""
            INSERT INTO daily_records (
                date, muscle_fatigue,
                score_overall, score_training, score_recovery,
                score_balance, score_consistency,
                summary, critique, callout, history_days, raw_response
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                muscle_fatigue    = excluded.muscle_fatigue,
                score_overall     = excluded.score_overall,
                score_training    = excluded.score_training,
                score_recovery    = excluded.score_recovery,
                score_balance     = excluded.score_balance,
                score_consistency = excluded.score_consistency,
                summary           = excluded.summary,
                critique          = excluded.critique,
                callout           = excluded.callout,
                history_days      = excluded.history_days,
                raw_response      = excluded.raw_response
            {where_clause}
            """,
            (
                date,
                json.dumps(parsed.get("muscle_fatigue")) if parsed.get("muscle_fatigue") is not None else None,
                scores.get("overall"),
                scores.get("training_quality"),
                scores.get("recovery"),
                scores.get("volume_balance"),
                scores.get("consistency"),
                parsed.get("summary"),
                json.dumps(parsed.get("critique")) if parsed.get("critique") is not None else None,
                parsed.get("callout"),
                history_days,
                raw,
            ),
        )
    if cursor.rowcount == 0:
        log.info("daily_records analysis already set for %s — skipping", date)
    else:
        log.info("daily_records analysis written for %s (force=%s)", date, force)


# ---------------------------------------------------------------------------
# Read helpers (used by REST API in main.py)
# ---------------------------------------------------------------------------

def get_snapshot(date: str) -> dict | None:
    """Return a single daily_snapshot row as a dict, or None."""
    with get_sqlite() as conn:
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


def get_snapshots(from_date: str, to_date: str) -> list[dict]:
    """Return daily_snapshot rows between from_date and to_date inclusive."""
    with get_sqlite() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_snapshot WHERE date BETWEEN ? AND ? ORDER BY date",
            (from_date, to_date),
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


def get_daily_record(date: str) -> dict | None:
    """Return a daily_records row structured with nested subfields, or None."""
    with get_sqlite() as conn:
        row = conn.execute(
            "SELECT * FROM daily_records WHERE date = ?", (date,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    for key in ("critique", "muscle_fatigue", "workout_names", "muscle_volume", "recovery_status"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return {
        "date": d["date"],
        "metrics": {k: d.get(k) for k in (
            "steps", "active_calories", "basal_calories", "resting_hr",
            "hrv_ms", "cardio_recovery", "exercise_minutes", "stand_hours",
            "distance_mi", "flights_climbed", "body_weight_kg",
            "avg_heart_rate", "walking_hr_avg",
            "sleep_total_min", "sleep_deep_min", "sleep_rem_min", "sleep_awake_min",
        )},
        "workouts": {
            "count":            d.get("workout_count"),
            "names":            d.get("workout_names"),
            "muscle_volume":    d.get("muscle_volume"),
            "top_muscle_group": d.get("top_muscle_group"),
            "total_volume_kg":  d.get("total_volume_kg"),
            "muscle_fatigue":   d.get("muscle_fatigue"),
            "recovery_status":  d.get("recovery_status"),
        },
        "analysis": {
            "scores": {
                "overall":          d.get("score_overall"),
                "training_quality": d.get("score_training"),
                "recovery":         d.get("score_recovery"),
                "volume_balance":   d.get("score_balance"),
                "consistency":      d.get("score_consistency"),
            },
            "summary":      d.get("summary"),
            "critique":     d.get("critique"),
            "callout":      d.get("callout"),
            "history_days": d.get("history_days"),
            "raw_response": d.get("raw_response"),
        },
        "created_at": d.get("created_at"),
    }


def get_score_history(days: int = 30) -> list[dict]:
    """Return the last N days of score columns for ScoreChart.jsx."""
    with get_sqlite() as conn:
        rows = conn.execute(
            """
            SELECT date,
                   score_overall     AS overall,
                   score_training    AS training_quality,
                   score_recovery    AS recovery,
                   score_balance     AS volume_balance,
                   score_consistency AS consistency
            FROM (
                SELECT date, score_overall, score_training, score_recovery,
                       score_balance, score_consistency
                FROM daily_records
                WHERE score_overall IS NOT NULL
                ORDER BY date DESC
                LIMIT ?
            )
            ORDER BY date ASC
            """,
            (days,),
        ).fetchall()
    return [dict(r) for r in rows]


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


# ---------------------------------------------------------------------------
# Workout timeseries — write
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Workout timeseries — read
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Activity / baseline helpers (used by REST API)
# ---------------------------------------------------------------------------

def get_metric_baselines(days: int = 30) -> dict:
    """Return N-day trailing averages for the four recovery metrics."""
    with get_sqlite() as conn:
        row = conn.execute(
            """
            SELECT
                AVG(hrv_ms)          AS hrv_avg,
                AVG(resting_hr)      AS resting_hr_avg,
                AVG(cardio_recovery) AS cardio_recovery_avg,
                AVG(walking_hr_avg)  AS walking_hr_baseline
            FROM daily_snapshot
            WHERE date >= date('now', ? || ' days')
              AND date < date('now')
            """,
            (f"-{days}",),
        ).fetchone()
    return dict(row) if row else {}


def get_activity_history(days: int = 30) -> list[dict]:
    """Return daily activity rows for the ActivityCharts line chart."""
    with get_sqlite() as conn:
        rows = conn.execute(
            """
            SELECT date, steps, active_calories, hrv_ms,
                   ROUND(body_weight_kg * 2.20462, 1) AS body_weight_lbs,
                   resting_hr, cardio_recovery
            FROM daily_snapshot
            WHERE date >= date('now', ? || ' days')
            ORDER BY date ASC
            """,
            (f"-{days}",),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Daily timeseries — write / read (intraday HR and step samples)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Entrypoint — schema verification
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    init_db()

    with get_sqlite() as conn:
        tables = [
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        print("SQLite tables:", tables)

    with get_duckdb() as con:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        print("DuckDB tables:", tables)

    if "--smoke" in sys.argv:
        print("\nRunning smoke write...")
        # Sentinel date — never conflicts with real health data.
        date = "1970-01-01"

        ok = upsert_snapshot_apple_health(date, {
            "steps": 10000, "active_calories": 500.0, "resting_hr": 58,
        })
        print(f"  apple_health upsert complete={ok}")

        ok = upsert_snapshot_hevy(date, 61.23, {"lats": 1837.0}, [])
        print(f"  hevy upsert complete={ok}")

        snap = get_snapshot(date)
        print(f"  snapshot: steps={snap['steps']} lats={snap['muscle_volume'].get('lats')} complete={snap['snapshot_complete']}")

        append_raw_blob("raw_hevy_workouts", date, {"test": True})
        print("  raw blob appended")


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

def create_user(email: str, password_hash: str) -> int:
    """Insert a new user and return their id."""
    with get_sqlite() as conn:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            (email.lower().strip(), password_hash),
        )
        return cur.lastrowid


def get_user_by_email(email: str) -> dict | None:
    """Return the user row for email, or None."""
    with get_sqlite() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ? AND is_active = 1",
            (email.lower().strip(),),
        ).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    """Return the user row for id, or None."""
    with get_sqlite() as conn:
        row = conn.execute(
            "SELECT id, email, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else None


def get_user_by_clerk_id(clerk_user_id: str) -> dict | None:
    """Return the local user row matching a Clerk user ID, or None."""
    with get_sqlite() as conn:
        row = conn.execute(
            "SELECT id, email, is_active, is_admin FROM users WHERE clerk_user_id = ?",
            (clerk_user_id,),
        ).fetchone()
    return dict(row) if row else None


def create_user_from_clerk(clerk_user_id: str, email: str | None) -> dict:
    """Create (or claim) a local user record on first Clerk login and return it."""
    resolved_email = (email or f"{clerk_user_id}@clerk.local").lower().strip()
    with get_sqlite() as conn:
        # If a row with this email already exists (pre-Clerk account), just stamp it.
        conn.execute(
            """INSERT INTO users (email, password_hash, clerk_user_id) VALUES (?, '', ?)
               ON CONFLICT(email) DO UPDATE SET clerk_user_id = excluded.clerk_user_id""",
            (resolved_email, clerk_user_id),
        )
        row = conn.execute(
            "SELECT id, email, is_active, is_admin FROM users WHERE clerk_user_id = ?",
            (clerk_user_id,),
        ).fetchone()
    return dict(row)


def set_user_admin(email: str, is_admin: bool) -> bool:
    """Promote or demote a user by email. Returns True if a row was updated."""
    with get_sqlite() as conn:
        cursor = conn.execute(
            "UPDATE users SET is_admin = ? WHERE email = ?",
            (1 if is_admin else 0, email.lower().strip()),
        )
    return cursor.rowcount > 0


def list_users() -> list[dict]:
    """Return all user rows (id, email, is_active, is_admin, created_at)."""
    with get_sqlite() as conn:
        rows = conn.execute(
            "SELECT id, email, is_active, is_admin, created_at FROM users ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]
