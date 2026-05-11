#!/usr/bin/env python3
"""
One-shot migration: reassign all data rows (user_id IS NULL or user_id = 1)
to the local user that has a Clerk user ID set.

Run AFTER signing in to the app at least once so the Clerk-linked user row exists.

Usage:
  python migrate_to_clerk_user.py [--dry-run]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import database

DRY_RUN = "--dry-run" in sys.argv


def main():
    database.init_db()

    with database.get_sqlite() as conn:
        # Find the user linked to Clerk
        clerk_user = conn.execute(
            "SELECT id, email, clerk_user_id FROM users WHERE clerk_user_id IS NOT NULL LIMIT 1"
        ).fetchone()

        if not clerk_user:
            print("No Clerk-linked user found. Sign in to the app first, then re-run.")
            sys.exit(1)

        new_id     = clerk_user["id"]
        email      = clerk_user["email"]
        clerk_id   = clerk_user["clerk_user_id"]
        print(f"Migrating data to user: id={new_id}, email={email}, clerk_user_id={clerk_id}")

        # Count rows that need updating
        snap_count = conn.execute(
            "SELECT COUNT(*) FROM daily_snapshot WHERE user_id IS NULL OR user_id != ?",
            (new_id,)
        ).fetchone()[0]

        rec_count = conn.execute(
            "SELECT COUNT(*) FROM daily_records WHERE user_id IS NULL OR user_id != ?",
            (new_id,)
        ).fetchone()[0]

        print(f"  daily_snapshot rows to update: {snap_count}")
        print(f"  daily_records  rows to update: {rec_count}")

        if DRY_RUN:
            print("Dry run — no changes written.")
            return

        conn.execute(
            "UPDATE daily_snapshot SET user_id = ? WHERE user_id IS NULL OR user_id != ?",
            (new_id, new_id)
        )
        conn.execute(
            "UPDATE daily_records SET user_id = ? WHERE user_id IS NULL OR user_id != ?",
            (new_id, new_id)
        )

        # Verify
        remaining_snap = conn.execute(
            "SELECT COUNT(*) FROM daily_snapshot WHERE user_id != ?", (new_id,)
        ).fetchone()[0]
        remaining_rec = conn.execute(
            "SELECT COUNT(*) FROM daily_records WHERE user_id != ?", (new_id,)
        ).fetchone()[0]

    print(f"Done. Unassigned rows remaining — snapshots: {remaining_snap}, records: {remaining_rec}")


if __name__ == "__main__":
    main()
