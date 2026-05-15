"""
db/ — database layer split from the original monolithic database.py.

Re-exports the full public API so existing `import database` code continues
to work after database.py becomes a thin shim pointing here.
"""

from db.connection import get_sqlite, get_duckdb, SQLITE_PATH, DUCKDB_PATH
from db.schema import APPLE_HEALTH_COLUMNS, HEVY_COLUMNS, init_db
from db.snapshots import (
    upsert_snapshot_apple_health,
    upsert_snapshot_apple_health_workouts,
    upsert_snapshot_recovery_status,
    upsert_snapshot_notes,
    upsert_snapshot_hevy,
    get_snapshot,
    get_snapshots,
    get_weekly_summary,
    get_soreness_for_date,
    replace_workouts_for_source,
    dedup_existing_workouts,
)
from db.records import (
    upsert_daily_record_snapshot,
    upsert_daily_record_analysis,
    get_daily_record,
    get_score_history,
)
from db.workouts import (
    append_raw_blob,
    upsert_workout_hr_samples,
    upsert_workout_sets,
    get_workout_hr_samples,
    get_workout_sets,
)
from db.users import (
    get_user_by_clerk_id,
    create_user_from_clerk,
    set_user_admin,
    list_users,
    get_user_by_id,
    create_user,
    get_user_by_email,
    generate_webhook_token,
    get_user_by_webhook_token,
)
from db.analytics import (
    get_metric_baselines,
    get_activity_history,
    get_muscle_volume_30d,
    get_muscle_volume_baselines,
    get_exercise_template,
    upsert_daily_timeseries,
    get_daily_timeseries,
)

__all__ = [
    # connection
    "get_sqlite", "get_duckdb", "SQLITE_PATH", "DUCKDB_PATH",
    # schema
    "APPLE_HEALTH_COLUMNS", "HEVY_COLUMNS", "init_db",
    # snapshots
    "upsert_snapshot_apple_health", "upsert_snapshot_apple_health_workouts",
    "upsert_snapshot_recovery_status", "upsert_snapshot_notes", "upsert_snapshot_hevy",
    "get_snapshot", "get_snapshots", "get_weekly_summary", "get_soreness_for_date",
    "replace_workouts_for_source", "dedup_existing_workouts",
    # records
    "upsert_daily_record_snapshot", "upsert_daily_record_analysis",
    "get_daily_record", "get_score_history",
    # workouts
    "append_raw_blob", "upsert_workout_hr_samples", "upsert_workout_sets",
    "get_workout_hr_samples", "get_workout_sets",
    # users
    "get_user_by_clerk_id", "create_user_from_clerk", "set_user_admin",
    "list_users", "get_user_by_id", "create_user", "get_user_by_email",
    "generate_webhook_token", "get_user_by_webhook_token",
    # analytics
    "get_metric_baselines", "get_activity_history",
    "get_muscle_volume_30d", "get_muscle_volume_baselines",
    "get_exercise_template", "upsert_daily_timeseries", "get_daily_timeseries",
]
