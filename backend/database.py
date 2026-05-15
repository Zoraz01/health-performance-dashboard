"""
Compatibility shim — all database logic now lives in backend/db/.

Existing code that does `import database` and calls `database.get_snapshot()` etc.
continues to work without any changes.
"""

from db import *  # noqa: F401, F403
from db import (
    get_sqlite, get_duckdb, SQLITE_PATH, DUCKDB_PATH,
    APPLE_HEALTH_COLUMNS, HEVY_COLUMNS, init_db,
    upsert_snapshot_apple_health, upsert_snapshot_apple_health_workouts,
    upsert_snapshot_recovery_status, upsert_snapshot_notes, upsert_snapshot_hevy,
    get_snapshot, get_snapshots, get_weekly_summary, get_soreness_for_date,
    replace_workouts_for_source, dedup_existing_workouts,
    upsert_daily_record_snapshot, upsert_daily_record_analysis,
    get_daily_record, get_score_history,
    append_raw_blob, upsert_workout_hr_samples, upsert_workout_sets,
    get_workout_hr_samples, get_workout_sets,
    get_user_by_clerk_id, create_user_from_clerk, set_user_admin,
    list_users, get_user_by_id, create_user, get_user_by_email,
    generate_webhook_token, get_user_by_webhook_token,
    get_metric_baselines, get_activity_history,
    get_muscle_volume_30d, get_muscle_volume_baselines,
    get_exercise_template, upsert_daily_timeseries, get_daily_timeseries,
)
