"""
Schema DDL, migrations, and database initialisation.
"""

import logging
import os
import sqlite3

from db.connection import get_sqlite, get_duckdb, _DB_DIR, SQLITE_PATH, DUCKDB_PATH

log = logging.getLogger(__name__)

# Columns written exclusively by each source — enforces partial-upsert discipline.
APPLE_HEALTH_COLUMNS = (
    "body_weight_kg", "steps", "active_calories", "basal_calories",
    "exercise_minutes", "stand_hours", "distance_mi", "flights_climbed",
    "hrv_ms", "resting_hr", "cardio_recovery", "avg_heart_rate",
    "walking_hr_avg", "sleep_total_min", "sleep_deep_min",
    "sleep_rem_min", "sleep_awake_min", "medications_today",
    "spo2", "respiratory_rate", "caffeine_mg",
)

HEVY_COLUMNS = ("body_weight_kg", "muscle_volume", "workouts")

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
    "ALTER TABLE daily_snapshot ADD COLUMN spo2 REAL",
    "ALTER TABLE daily_snapshot ADD COLUMN respiratory_rate REAL",
    "ALTER TABLE daily_snapshot ADD COLUMN caffeine_mg REAL",
    # Multi-user: per-user webhook tokens and soreness ownership
    "ALTER TABLE users ADD COLUMN webhook_token TEXT",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_webhook_token ON users(webhook_token) WHERE webhook_token IS NOT NULL",
    "ALTER TABLE soreness_log ADD COLUMN user_id INTEGER",
    "CREATE INDEX IF NOT EXISTS idx_soreness_log_user_id ON soreness_log(user_id)",
]


def init_db() -> None:
    """Create both DB files and all tables/indexes/sequences if they don't exist."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)

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
    _backfill_data_ownership()


def _backfill_data_ownership() -> None:
    """Backfill user_id on legacy rows and generate missing webhook tokens."""
    import secrets as _secrets
    owner_email = os.environ.get("OWNER_EMAIL", "").lower().strip()
    with get_sqlite() as conn:
        # Generate webhook tokens for any user that doesn't have one yet
        rows = conn.execute("SELECT id FROM users WHERE webhook_token IS NULL").fetchall()
        for (uid,) in rows:
            conn.execute(
                "UPDATE users SET webhook_token = ? WHERE id = ?",
                (_secrets.token_urlsafe(32), uid),
            )
        if rows:
            log.info("[init_db] generated webhook tokens for %d user(s)", len(rows))

        if not owner_email:
            return
        owner_row = conn.execute(
            "SELECT id FROM users WHERE email = ?", (owner_email,)
        ).fetchone()
        if not owner_row:
            return
        owner_id = owner_row[0]
        conn.execute("UPDATE daily_snapshot SET user_id = ? WHERE user_id IS NULL", (owner_id,))
        conn.execute("UPDATE daily_records SET user_id = ? WHERE user_id IS NULL", (owner_id,))
        conn.execute("UPDATE soreness_log SET user_id = ? WHERE user_id IS NULL", (owner_id,))
        log.info("[init_db] backfilled user_id=%d on legacy rows", owner_id)


def _bootstrap_owner_admin() -> None:
    """Ensure the OWNER_EMAIL user is flagged as admin on every startup."""
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
