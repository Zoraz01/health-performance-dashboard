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
    "sleep_rem_min", "sleep_awake_min",
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

CREATE TABLE IF NOT EXISTS claude_responses (
    date              DATE PRIMARY KEY,
    score_overall     INTEGER,
    score_training    INTEGER,
    score_recovery    INTEGER,
    score_balance     INTEGER,
    score_consistency INTEGER,
    summary           TEXT,
    critique          TEXT,
    callout           TEXT,
    muscle_fatigue    TEXT,
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

def init_db() -> None:
    """Create both DB files and all tables/indexes/sequences if they don't exist."""
    os.makedirs(DATA_DIR, exist_ok=True)

    with get_duckdb() as con:
        for stmt in _DUCKDB_DDL_STATEMENTS:
            con.execute(stmt)
        log.info("DuckDB schema ready: %s", DUCKDB_PATH)

    with get_sqlite() as conn:
        conn.executescript(_SQLITE_DDL)
        log.info("SQLite schema ready: %s", SQLITE_PATH)


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
# Workout merge helper
# ---------------------------------------------------------------------------

def replace_workouts_for_source(
    conn: sqlite3.Connection, date: str, source: str, new_entries: list[dict]
) -> list[dict]:
    """Read the current workouts JSON for date, drop entries from source,
    append new_entries, write back. Returns the merged list.

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
# Claude response storage
# ---------------------------------------------------------------------------

def upsert_claude_response(date: str, parsed: dict, raw: str) -> None:
    """Write Claude's structured response for date.

    Idempotent — the ON CONFLICT WHERE clause prevents overwriting a row
    that already has a valid score_overall, atomically and without a
    separate SELECT round-trip.
    """
    scores = parsed.get("scores", {})
    sql = """
        INSERT INTO claude_responses
            (date, score_overall, score_training, score_recovery,
             score_balance, score_consistency, summary, critique,
             callout, muscle_fatigue, raw_response)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            score_overall     = excluded.score_overall,
            score_training    = excluded.score_training,
            score_recovery    = excluded.score_recovery,
            score_balance     = excluded.score_balance,
            score_consistency = excluded.score_consistency,
            summary           = excluded.summary,
            critique          = excluded.critique,
            callout           = excluded.callout,
            muscle_fatigue    = excluded.muscle_fatigue,
            raw_response      = excluded.raw_response
        WHERE claude_responses.score_overall IS NULL
    """
    with get_sqlite() as conn:
        cursor = conn.execute(sql, (
            date,
            scores.get("overall"),
            scores.get("training_quality"),
            scores.get("recovery"),
            scores.get("volume_balance"),
            scores.get("consistency"),
            parsed.get("summary"),
            json.dumps(parsed.get("critique")) if parsed.get("critique") is not None else None,
            parsed.get("callout"),
            json.dumps(parsed.get("muscle_fatigue")) if parsed.get("muscle_fatigue") is not None else None,
            raw,
        ))
    if cursor.rowcount == 0:
        log.info("claude_responses already populated for %s — skipping", date)
    else:
        log.info("claude_responses written for %s", date)


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
    for key in ("muscle_volume", "workouts"):
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


def get_claude_response(date: str) -> dict | None:
    """Return a claude_responses row as a dict, or None."""
    with get_sqlite() as conn:
        row = conn.execute(
            "SELECT * FROM claude_responses WHERE date = ?", (date,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    for key in ("critique", "muscle_fatigue"):
        if d.get(key):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def get_score_history(days: int = 30) -> list[dict]:
    """Return the last N days of score columns for ScoreChart.jsx."""
    with get_sqlite() as conn:
        rows = conn.execute(
            """
            SELECT date, score_overall, score_training, score_recovery,
                   score_balance, score_consistency
            FROM (
                SELECT date, score_overall, score_training, score_recovery,
                       score_balance, score_consistency
                FROM claude_responses
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

        print("Smoke test passed.")
