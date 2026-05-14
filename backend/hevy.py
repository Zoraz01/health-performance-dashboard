import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

log = logging.getLogger(__name__)

HEVY_API_KEY = os.getenv("HEVY_API_KEY")
if not HEVY_API_KEY:
    raise RuntimeError("HEVY_API_KEY not set — check backend/.env")

HEVY_BASE_URL = "https://api.hevyapp.com"
PAGE_SIZE = 10
TEMPLATE_PAGE_SIZE = 100


async def _get_json(client: httpx.AsyncClient, url: str, **kwargs) -> dict:
    """GET with up to 3 attempts on 5xx responses."""
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = await client.get(url, **kwargs)
            if resp.status_code < 500:
                resp.raise_for_status()
                return resp.json()
            last_exc = httpx.HTTPStatusError(
                f"server error {resp.status_code}", request=resp.request, response=resp
            )
        except httpx.HTTPStatusError:
            raise
        except Exception as e:
            last_exc = e
        wait = 2 ** attempt
        log.warning("Hevy API transient error on %s (attempt %d/3), retrying in %ds", url, attempt + 1, wait)
        await asyncio.sleep(wait)
    raise last_exc  # type: ignore[misc]


async def fetch_exercise_templates() -> dict[str, dict]:
    """Returns all exercise templates keyed by id."""
    templates = {}
    page = 1

    async with httpx.AsyncClient(base_url=HEVY_BASE_URL, timeout=30) as client:
        while True:
            data = await _get_json(
                client,
                "/v1/exercise_templates",
                headers={"api-key": HEVY_API_KEY},
                params={"page": page, "pageSize": TEMPLATE_PAGE_SIZE},
            )

            for t in data["exercise_templates"]:
                templates[t["id"]] = {
                    "title": t["title"],
                    "type": t["type"],
                    "primary_muscle_group": t["primary_muscle_group"],
                    "secondary_muscle_groups": t.get("secondary_muscle_groups", []),
                    "is_custom": t.get("is_custom", False),
                }

            if page >= data["page_count"]:
                break
            page += 1

    return templates


async def fetch_latest_body_weight() -> float | None:
    """Returns the most recent body weight in kg, or None if no measurements exist."""
    async with httpx.AsyncClient(base_url=HEVY_BASE_URL, timeout=30) as client:
        data = await _get_json(
            client,
            "/v1/body_measurements",
            headers={"api-key": HEVY_API_KEY},
            params={"page": 1, "pageSize": 10},
        )
        measurements = data.get("body_measurements", [])
        if not measurements:
            log.info("[hevy] no body measurements found")
            return None
        # API returns newest-first; take the first entry
        weight = measurements[0].get("weight_kg")
        log.info("[hevy] latest body weight: %.2f kg (%.1f lbs)", weight, weight * 2.20462 if weight else 0)
        return weight


async def fetch_workouts_since(since: datetime | None = None) -> list[dict]:
    """
    Fetch workouts with start_time >= since. Defaults to the past 24 hours.
    Assumes the API returns workouts newest-first, so stops paginating once
    start_time drops below the cutoff.
    """
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=24)

    workouts = []
    page = 1

    async with httpx.AsyncClient(base_url=HEVY_BASE_URL, timeout=30) as client:
        while True:
            data = await _get_json(
                client,
                "/v1/workouts",
                headers={"api-key": HEVY_API_KEY},
                params={"page": page, "pageSize": PAGE_SIZE},
            )

            batch = data["workouts"]
            if not batch:
                break

            for workout in batch:
                start = datetime.fromisoformat(
                    workout["start_time"].replace("Z", "+00:00")
                )
                if start < since:
                    log.debug("pagination cutoff reached at %s — stopping early", start.date())
                    return workouts
                workouts.append(workout)

            if page >= data["page_count"]:
                break
            page += 1

    log.info("[hevy] fetch_workouts_since(%s): %d workout(s) found", since.date(), len(workouts))
    return workouts


async def _test():
    print(f"API key loaded: {'yes' if HEVY_API_KEY else 'NO — check .env'}\n")

    log_dir = os.path.join(os.path.dirname(__file__), "test_logs")
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("--- Body Weight ---")
    body_weight_kg = await fetch_latest_body_weight()
    if body_weight_kg:
        print(f"  Latest: {body_weight_kg} kg  ({round(body_weight_kg * 2.20462, 1)} lbs)")
    else:
        print("  No measurements found")
    print()

    print("--- Exercise Templates ---")
    templates = await fetch_exercise_templates()
    print(f"Total templates fetched: {len(templates)}")

    templates_path = os.path.join(log_dir, f"hevy_templates_{ts}.json")
    with open(templates_path, "w") as f:
        json.dump(templates, f, indent=2)
    print(f"Saved → {templates_path}\n")

    # Widen the window for testing so we see existing workouts
    test_since = datetime.now(timezone.utc) - timedelta(days=7)
    print(f"--- Workouts since {test_since.date()} (7-day test window; nightly cron uses 24h) ---")
    workouts = await fetch_workouts_since(since=test_since)
    print(f"Found {len(workouts)} workout(s)\n")

    enriched = []
    for w in workouts:
        print(f"  [{w['start_time'][:10]}] {w['title']}")
        enriched_exercises = []
        for ex in w.get("exercises", []):
            tid = ex.get("exercise_template_id")
            t = templates.get(tid, {})
            mg = t.get("primary_muscle_group", "unknown")
            secondary = t.get("secondary_muscle_groups", [])
            sets = ex.get("sets", [])

            total_volume = 0.0
            for s in sets:
                reps = s.get("reps") or 0
                weight = s.get("weight_kg")
                if weight is None and body_weight_kg:
                    weight = body_weight_kg
                if weight:
                    total_volume += reps * weight
                else:
                    total_volume += reps  # reps-only fallback

            print(f"    - {ex['title']}  → {mg}  ({len(sets)} sets, {round(total_volume)} vol)")
            enriched_exercises.append({
                **ex,
                "primary_muscle_group": mg,
                "secondary_muscle_groups": secondary,
                "volume": round(total_volume, 2),
            })
        enriched.append({**w, "exercises": enriched_exercises})
        print()

    workouts_path = os.path.join(log_dir, f"hevy_workouts_{ts}.json")
    with open(workouts_path, "w") as f:
        json.dump(enriched, f, indent=2)
    print(f"Saved → {workouts_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")
    asyncio.run(_test())
