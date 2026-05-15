import logging
from typing import Optional

import httpx
import jwt as pyjwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import auth
import database
from config import settings

log = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """Verifies Clerk JWT and returns (or lazily creates) the local user row."""
    if not creds:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = auth.verify_clerk_token(creds.credentials)
    except pyjwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
    except httpx.HTTPError as exc:
        log.error("JWKS fetch failed: %s", exc)
        raise HTTPException(status_code=503, detail="Auth service temporarily unavailable")

    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(status_code=401, detail="Token missing sub claim")

    user = database.get_user_by_clerk_id(clerk_user_id)
    if user:
        if not user.get("is_active"):
            raise HTTPException(status_code=401, detail="User inactive")
    else:
        email = auth.get_clerk_user_email(clerk_user_id)
        user = database.create_user_from_clerk(clerk_user_id, email)
        log.info("[auth] first login — created user %s (clerk_id=%s)", email, clerk_user_id)

    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Only users with is_admin=1 in the DB can reach /api/admin/* routes."""
    if not user.get("is_admin"):
        log.warning("[auth] admin access denied for %s", user.get("email"))
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
