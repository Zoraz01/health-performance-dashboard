import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Header

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(Path(__file__).parent / "test_logs" / "server.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

app = FastAPI()

APPLE_HEALTH_WEBHOOK_SECRET = "hd-apple-x7k2q9"
LOG_DIR = Path(__file__).parent / "test_logs"
LOG_DIR.mkdir(exist_ok=True)


def verify_bearer(authorization: Optional[str]):
    if authorization != f"Bearer {APPLE_HEALTH_WEBHOOK_SECRET}":
        raise HTTPException(status_code=401, detail="Unauthorized")


def save(label: str, data: dict):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"{label}_{timestamp}.json"
    path.write_text(json.dumps(data, indent=2))
    log.info(f"[{label}] saved → {path.name}")


@app.post("/webhook/apple-health")
async def apple_health(request: Request, authorization: Optional[str] = Header(None)):
    verify_bearer(authorization)
    try:
        data = await request.json()
        save("apple_health", data)
    except Exception as e:
        log.error(f"[apple_health] failed to process payload: {e}")
        raise HTTPException(status_code=500, detail="Processing error")
    return {"status": "ok"}


@app.post("/webhook/apple-health-workouts")
async def apple_health_workouts(request: Request, authorization: Optional[str] = Header(None)):
    verify_bearer(authorization)
    try:
        data = await request.json()
        save("apple_health_workouts", data)
    except Exception as e:
        log.error(f"[apple_health_workouts] failed to process payload: {e}")
        raise HTTPException(status_code=500, detail="Processing error")
    return {"status": "ok"}


@app.post("/webhook/hevy")
async def hevy(request: Request):
    try:
        data = await request.json()
        save("hevy", data)
    except Exception as e:
        log.error(f"[hevy] failed to process payload: {e}")
        raise HTTPException(status_code=500, detail="Processing error")
    return {"status": "ok"}
