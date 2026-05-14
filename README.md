# FitPulse

Personal health performance dashboard. Aggregates Apple Health data, Hevy workout logs, sleep, HRV, and recovery metrics into a single daily readiness view — with Claude AI analysis.

![FitPulse dashboard](frontend/src/assets/hero.png)

## Stack

- **Backend**: FastAPI (Python), SQLite + DuckDB, APScheduler
- **Frontend**: React + Vite + Tailwind CSS
- **Auth**: Clerk
- **Deployment**: Cloudflare Zero Trust tunnel → `health.zorazhaseeb.com`

## Setup

### Backend

```bash
cd backend
pip install -r ../requirements.txt
# Copy and fill in your secrets:
cp .env.example .env
uvicorn main:app --host 0.0.0.0 --port 8100
```

Required `.env` vars: `APPLE_HEALTH_WEBHOOK_SECRET`, `CLERK_SECRET_KEY`, `CLERK_ISSUER`, `HEVY_API_KEY`, `FRONTEND_ORIGIN`.

### Frontend (dev)

```bash
cd frontend
npm install
npm run dev   # runs on :5173, proxies /api → localhost:8100
```

## Deploying to production

Build the frontend and restart the backend service. The built `dist/` is served directly by FastAPI on port 8100, which the Cloudflare tunnel exposes at `health.zorazhaseeb.com`.

```bash
cd frontend && npm run build

# Restart the backend launchd service
launchctl unload ~/Library/LaunchAgents/com.zoraz.health-dashboard.plist
launchctl load  ~/Library/LaunchAgents/com.zoraz.health-dashboard.plist
```

## Admin Panel

The admin log viewer is available at:

```
https://health.zorazhaseeb.com/admin/logs
```

Or locally: `http://localhost:8100/admin/logs`

Requires an account with `is_admin = 1` in the database. The `OWNER_EMAIL` from `.env` is automatically promoted on every backend startup. Non-admin users see an access denied page.

> **Note on log history**: `launchd.err.log` and `launchd.out.log` are append-only. The log viewer shows the full file history — including Python tracebacks from previous crashes (visible as `~~~^^^` caret underlines in Python 3.14's enhanced traceback format). These are historical, not current errors. The service is healthy as long as `Application startup complete.` appears near the bottom.

## Viewing live logs

The launchd service writes stdout/stderr to:

```text
backend/logs/launchd.out.log
backend/logs/launchd.err.log
```

Watch them live:

```bash
tail -f backend/logs/launchd.out.log
# or both streams together:
tail -f backend/logs/launchd.out.log backend/logs/launchd.err.log
```

To run the backend **interactively** with logs printed to your terminal (useful for debugging):

```bash
launchctl unload ~/Library/LaunchAgents/com.zoraz.health-dashboard.plist
cd backend
uvicorn main:app --host 0.0.0.0 --port 8100
# Ctrl+C to stop, then reload launchd when done:
launchctl load ~/Library/LaunchAgents/com.zoraz.health-dashboard.plist
```

## Architecture

```text
Apple Health (webhook) ──▶ POST /webhook/apple-health ──▶ SQLite daily_snapshot
Hevy (nightly cron)    ──▶ APScheduler 02:00           ──▶ SQLite daily_snapshot
Claude CLI             ──▶ APScheduler 03:00            ──▶ SQLite daily_records.analysis
Frontend               ──▶ GET /api/today               ──▶ React dashboard
```
