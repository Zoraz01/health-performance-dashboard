#!/usr/bin/env python3
"""
DEPRECATED — user creation is now handled by Clerk.

To add a user: create them in the Clerk dashboard at https://dashboard.clerk.com
They will be automatically provisioned in the local database on first sign-in.

To manually claim a Clerk user ID against a local record (e.g. migration):
  python create_user.py <clerk_user_id> [email]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
import database


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    clerk_user_id = sys.argv[1].strip()
    email = sys.argv[2].strip() if len(sys.argv) > 2 else None

    database.init_db()
    user = database.create_user_from_clerk(clerk_user_id, email)
    print(f"Created/claimed user: id={user['id']} email={user['email']}")


if __name__ == "__main__":
    main()
