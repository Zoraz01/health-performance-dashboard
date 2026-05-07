"""
One-time seed script — populates the exercise_templates table from Hevy API.

Run once after database.py has created the schema:
    cd backend && python3.14 seed_exercise_templates.py

Safe to re-run: INSERT OR IGNORE means no duplicates.
Re-run manually if Hevy ships new exercises.
"""

import asyncio
import json
import logging
import sqlite3

from database import SQLITE_PATH, init_db
from hevy import fetch_exercise_templates

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)


async def seed() -> None:
    init_db()

    log.info("Fetching exercise templates from Hevy API...")
    templates = await fetch_exercise_templates()
    log.info("Fetched %d templates", len(templates))

    conn = sqlite3.connect(SQLITE_PATH)
    inserted = 0
    skipped = 0

    for tid, t in templates.items():
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO exercise_templates
                (id, title, type, primary_muscle_group, secondary_muscle_groups, is_custom)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                tid,
                t["title"],
                t["type"],
                t["primary_muscle_group"],
                json.dumps(t["secondary_muscle_groups"]),
                int(t["is_custom"]),
            ),
        )
        if cur.rowcount:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM exercise_templates").fetchone()[0]
    conn.close()

    log.info("Done — inserted %d new, skipped %d existing, %d total in DB", inserted, skipped, total)

    # Print a sample so it's easy to verify
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    samples = conn.execute(
        "SELECT title, primary_muscle_group, type FROM exercise_templates "
        "ORDER BY primary_muscle_group, title LIMIT 10"
    ).fetchall()
    conn.close()
    print("\nSample rows:")
    for r in samples:
        print(f"  {r['title']:40s}  {r['primary_muscle_group']:15s}  {r['type']}")


if __name__ == "__main__":
    asyncio.run(seed())
