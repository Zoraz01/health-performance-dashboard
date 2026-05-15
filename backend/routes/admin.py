import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query

import database
from config import settings
from deps import require_admin

log = logging.getLogger(__name__)
router = APIRouter()

_TS = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")


@router.get("/api/admin/me")
async def admin_me(user: dict = Depends(require_admin)):
    return {"is_admin": True, "email": user.get("email"), "id": user.get("id")}


@router.get("/api/admin/logs")
async def get_admin_logs(
    lines: int = Query(default=300, ge=1, le=2000),
    _: dict = Depends(require_admin),
):
    """Return the last N lines from the backend log files, sorted by timestamp."""
    entries = []
    for path, stream in [
        (settings.log_dir / "launchd.err.log", "stderr"),
        (settings.log_dir / "launchd.out.log", "stdout"),
    ]:
        if path.exists():
            for raw_line in path.read_text(errors="replace").splitlines():
                line = raw_line.strip()
                if line:
                    entries.append({"stream": stream, "line": line})

    last_ts = "0000-00-00 00:00:00"
    last_idx = 0
    for e in entries:
        m = _TS.match(e["line"])
        if m:
            last_ts = e["line"][:19]
            last_idx = 0
        else:
            last_idx += 1
        e["_sort"] = f"{last_ts}_{last_idx:06d}"

    entries.sort(key=lambda e: e["_sort"])
    for e in entries:
        del e["_sort"]
    return entries[-lines:]


@router.get("/api/admin/users")
async def list_admin_users(_: dict = Depends(require_admin)):
    return database.list_users()


@router.post("/api/admin/users/{email}/promote")
async def promote_user(email: str, actor: dict = Depends(require_admin)):
    updated = database.set_user_admin(email, True)
    if not updated:
        raise HTTPException(status_code=404, detail=f"No user found with email {email!r}")
    log.info("[admin] %s promoted %s to admin", actor.get("email"), email)
    return {"status": "ok", "email": email, "is_admin": True}


@router.post("/api/admin/users/{email}/demote")
async def demote_user(email: str, actor: dict = Depends(require_admin)):
    if email.lower().strip() == actor.get("email", "").lower().strip():
        raise HTTPException(status_code=400, detail="Cannot demote yourself")
    updated = database.set_user_admin(email, False)
    if not updated:
        raise HTTPException(status_code=404, detail=f"No user found with email {email!r}")
    log.info("[admin] %s demoted %s from admin", actor.get("email"), email)
    return {"status": "ok", "email": email, "is_admin": False}
