# Local Beta Stack — Setup and Smoke Test

This guide walks through starting the Fall-In backend locally and verifying
the critical paths before a beta session.

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.12+ |
| uv | 0.4+ (`pip install uv`) |
| SQLite | bundled with Python |
| Redis | *optional* — only for single-worker quick-match queue persistence |

---

## 1. Clone and Install

```bash
git clone https://github.com/bnbong/Fall-In.git
cd Fall-In/backend
uv sync
```

---

## 2. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env`. Minimum required values:

```dotenv
# JWT — MUST change for any shared environment
SECRET_KEY=change-me-to-a-long-random-string

# Auto-create tables on startup (dev only — use Alembic for staging/prod)
CREATE_TABLES_ON_STARTUP=true

# Logging level: INFO for normal use, DEBUG for step-through debugging
LOG_LEVEL=INFO

# Admin token — set a strong random value to enable /admin/* endpoints
# Leave empty to disable admin endpoints during local dev (safe default)
ADMIN_TOKEN=local-dev-admin-token
```

Optional Redis (leave unset for local dev — in-memory fallback is used):

```dotenv
REDIS_URL=redis://localhost:6379/0
```

---

## 3. Database Setup

### Option A — Auto-create (local dev)

With `CREATE_TABLES_ON_STARTUP=true` in `.env`, tables are created on first
startup. No migration command needed.

### Option B — Alembic (staging / production)

```bash
uv run alembic upgrade head
```

This applies all migrations in order:
- `001` — users, profiles, user_collection
- `002` — reports

---

## 4. Start the Server

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Logs are emitted as JSON to stdout:

```json
{"ts": "2026-04-06T09:00:00.000Z", "level": "INFO", "logger": "fall_in.ws", "msg": "ws_connect", "conn_id": "..."}
```

Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 5. Smoke Tests

### 5.1 Health check

```bash
curl http://localhost:8000/healthz
# → {"status":"ok"}
```

### 5.2 Register a player

```bash
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test1234!","nickname":"BravePilot"}' \
  | python3 -m json.tool
```

Expected: `201` with `access_token`, `refresh_token`, `account_type: "registered"`.

Invalid nickname example (should return `422`):

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"bad@example.com","password":"Test1234!","nickname":"admin"}'
```

### 5.3 Guest login

```bash
curl -s -X POST http://localhost:8000/auth/guest \
  -H "Content-Type: application/json" \
  -d '{"nickname":"AceRookie"}' \
  | python3 -m json.tool
```

Expected: `200` with short-lived `access_token`, no `refresh_token`.

### 5.4 Submit a report

Replace `TOKEN` with the access token from step 5.2.

```bash
TOKEN=...
curl -s -X POST http://localhost:8000/report \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reported_connection_id":"test-conn","reason_code":"emote_spam","details":"Testing report submission"}' \
  | python3 -m json.tool
```

Expected: `201` with `report_id` and `status: "open"`.

### 5.5 Admin: list reports

```bash
curl -s http://localhost:8000/admin/reports \
  -H "Authorization: Bearer local-dev-admin-token" \
  | python3 -m json.tool
```

Expected: `200` with the report from 5.4.

Filter by status: append `?status=open`  
Filter by reason: append `?reason_code=emote_spam`

### 5.6 WebSocket flow (requires wscat or Postman)

```bash
npx wscat -c ws://localhost:8000/ws
```

Then in the wscat prompt:

```json
> {"type":"WS_HELLO","data":{}}
< {"type":"WS_WELCOME","data":{"connection_id":"..."}}

> {"type":"AUTH_LOGIN","data":{"token":"<ACCESS_TOKEN>"}}
< {"type":"AUTH_OK","data":{"user_id":"...","display_name":"BravePilot","account_type":"registered"}}

> {"type":"ROOM_CREATE","data":{}}
< {"type":"ROOM_STATE","data":{"room_code":"...","seats":[...],"phase":"waiting"}}
```

---

## 6. Running the Test Suite

```bash
cd backend
uv run pytest -q
```

To run only PR-08 tests:

```bash
uv run pytest tests/test_report.py tests/test_nickname.py -v
```

Expected: all tests pass (no external services needed).

---

## 7. Beta Deployment Checklist

Before opening to beta testers:

- [ ] `SECRET_KEY` is set to a cryptographically random string (not the default).
- [ ] `ADMIN_TOKEN` is set and shared only with moderators.
- [ ] `CREATE_TABLES_ON_STARTUP=false`; run `alembic upgrade head` to apply migrations.
- [ ] `LOG_LEVEL=INFO` (not DEBUG) to avoid leaking user data to logs.
- [ ] HTTPS/WSS termination in place (nginx or cloud load balancer).
- [ ] `DATABASE_URL` points to PostgreSQL (not SQLite) for concurrent load.
- [ ] **Run only ONE uvicorn worker.** Room state, match state, connection
  tracking, and the reconnect token store are all in-process singletons.
  Running multiple workers splits this state across processes and breaks
  room broadcast, active-match lookup, and reconnect paths.
  Multi-worker support requires a future PR to move these stores to Redis/DB.
  Redis only covers the quick-match queue and reconnect token TTLs — it does
  **not** make the rest of the stack multi-worker-safe.

---

## 8. Useful Log Queries (beta debugging)

All logs are JSON. Filter with `jq` or your log aggregator.

```bash
# All WebSocket connects
cat app.log | jq 'select(.msg == "ws_connect")'

# Auth/room/WS failure events
cat app.log | jq 'select(.msg == "ws_error")'

# Match starts
cat app.log | jq 'select(.msg == "match_start")'

# Emote rate-limit hits (potential emote-spam reports)
cat app.log | jq 'select(.msg == "emote_rate_limited")'

# Report submissions
cat app.log | jq 'select(.msg == "report_submitted")'
```
