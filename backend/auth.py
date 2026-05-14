"""
Clerk JWT verification using JWKS.

Verifies incoming Clerk session tokens against a pinned issuer URL fetched
from the environment. The JWKS is cached in-process with a 1-hour TTL and
re-fetched on cache miss or staleness.
"""

import json
import logging
import os
import time

import httpx
import jwt as pyjwt
from jwt.algorithms import RSAAlgorithm

log = logging.getLogger(__name__)

CLERK_SECRET_KEY = os.environ.get("CLERK_SECRET_KEY", "")
# Pinned issuer — never derived from the token itself (prevents SSRF / auth bypass)
CLERK_ISSUER = os.environ.get("CLERK_ISSUER", "")

_key_cache: dict[str, object] = {}
_cache_loaded_at: float = 0.0
_CACHE_TTL = 3600  # seconds


def _load_jwks() -> None:
    """Fetch JWKS from the pinned issuer and populate the key cache."""
    global _cache_loaded_at
    url = f"{CLERK_ISSUER}/.well-known/jwks.json"
    log.info("[auth] fetching JWKS from %s", url)
    resp = httpx.get(url, timeout=5)
    resp.raise_for_status()
    keys = resp.json().get("keys", [])
    for key_data in keys:
        _key_cache[key_data["kid"]] = RSAAlgorithm.from_jwk(json.dumps(key_data))
    _cache_loaded_at = time.monotonic()
    log.info("[auth] JWKS loaded — %d key(s) cached", len(keys))


def verify_clerk_token(token: str) -> dict:
    """Verify a Clerk JWT and return its payload. Raises jwt.InvalidTokenError on failure."""
    if not CLERK_ISSUER:
        raise pyjwt.InvalidTokenError("CLERK_ISSUER is not configured")

    header = pyjwt.get_unverified_header(token)
    kid    = header.get("kid")
    if not kid:
        raise pyjwt.InvalidTokenError("Missing kid in token header")

    cache_stale = (time.monotonic() - _cache_loaded_at) > _CACHE_TTL
    if kid not in _key_cache or cache_stale:
        reason = "stale" if cache_stale else "kid miss"
        log.debug("[auth] JWKS cache %s — reloading", reason)
        _load_jwks()

    public_key = _key_cache.get(kid)
    if not public_key:
        # One retry after a fresh fetch to handle mid-rotation races
        _load_jwks()
        public_key = _key_cache.get(kid)
    if not public_key:
        raise pyjwt.InvalidTokenError("No matching public key found in JWKS")

    return pyjwt.decode(
        token,
        public_key,
        algorithms=["RS256"],
        options={"verify_aud": False},
        issuer=CLERK_ISSUER,
    )


def get_clerk_user_email(clerk_user_id: str) -> str | None:
    """Fetch the user's primary email from the Clerk API (used on first login)."""
    if not CLERK_SECRET_KEY:
        return None
    try:
        resp = httpx.get(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {CLERK_SECRET_KEY}"},
            timeout=5,
        )
        if resp.status_code == 200:
            data       = resp.json()
            primary_id = data.get("primary_email_address_id")
            for addr in data.get("email_addresses", []):
                if addr["id"] == primary_id:
                    email = addr["email_address"]
                    log.info("[auth] resolved email for %s: %s", clerk_user_id, email)
                    return email
        else:
            log.warning("[auth] Clerk user lookup returned %d for %s", resp.status_code, clerk_user_id)
    except Exception as exc:
        log.warning("Could not fetch Clerk user email for %s: %s", clerk_user_id, exc)
    return None
