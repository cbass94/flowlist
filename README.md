# FlowList

AI-powered personal task manager that schedules your backlog as time blocks on Google Calendar.

---

## Tech stack decisions

| Layer | Choice | Why |
|---|---|---|
| **Backend** | Python 3.12 + FastAPI | Best-in-class Anthropic & Google API SDKs; async-native; strong typing via Pydantic; easy Docker containerisation |
| **Database** | PostgreSQL 16 | Full SQL power; native `ARRAY` type for `scheduled_blocks`; identical to Supabase (cloud migration = connection string swap) |
| **Caching / queue** | Redis 7 | Dual-purpose: signed session storage + ARQ job queue — one service does both |
| **Background jobs** | ARQ | Async-native Python, runs in the same codebase, no separate Celery infrastructure; supports both enqueued jobs and cron |
| **Frontend** | React 18 + Vite + TypeScript + Tailwind | Fast DX, great mobile-responsive story, dnd-kit for drag-to-reorder |
| **Reverse proxy** | Caddy 2 | Zero-config TLS (auto cert on a real domain), simple one-file config, trivially swapped for nginx in prod |
| **Auth** | Authlib (OAuth 2.0) | Handles Google's entire OAuth dance; integrates cleanly with FastAPI |

Cloud portability: swap `DATABASE_URL` to Supabase/Cloud SQL, `REDIS_URL` to Redis Cloud / Elasticache, push Docker images to GCR/ECR, done.

---

## Prerequisites

- Docker Desktop for Windows (with WSL2 backend recommended)
- Git

---

## 1 — Get Google OAuth credentials (TWO accounts)

FlowList needs an OAuth app for each Google account you want to connect.

### Work account (primary login)

1. Go to [Google Cloud Console](https://console.cloud.google.com) and **sign in with your work Google account**.
2. Create a new project: **FlowList**.
3. Navigate to **APIs & Services → Library** and enable:
   - **Google Calendar API**
   - **Google People API** (for profile/email)
4. Navigate to **APIs & Services → OAuth consent screen**.
   - User type: **External** (for personal projects)
   - App name: `FlowList`
   - Add your work email as a test user
   - Scopes to add: `openid`, `email`, `profile`, `https://www.googleapis.com/auth/calendar`
5. Navigate to **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
   - Application type: **Web application**
   - Authorised redirect URIs: `http://localhost/api/auth/callback/work`
     (also add your tunnel URL later, e.g. `https://flowlist.yourdomain.com/api/auth/callback/work`)
6. Copy the **Client ID** and **Client Secret** into `.env`:
   ```
   GOOGLE_WORK_CLIENT_ID=...
   GOOGLE_WORK_CLIENT_SECRET=...
   ```

### Personal account (secondary connection)

Repeat the exact same steps above but:
- Sign in with your **personal Google account**
- Create a **separate** Cloud project (or reuse the same one if personal account owns it)
- Redirect URI: `http://localhost/api/auth/callback/personal`
- Copy credentials into `.env`:
  ```
  GOOGLE_PERSONAL_CLIENT_ID=...
  GOOGLE_PERSONAL_CLIENT_SECRET=...
  ```

> **Why two separate OAuth apps?** Google OAuth tokens are scoped to the user who grants them. The work token lets the app write to your work calendar; the personal token lets it write to your personal calendar. Each account's credentials must be obtained while signed into that Google account.

### Find your Calendar IDs

1. Open [Google Calendar](https://calendar.google.com) → Settings (gear icon)
2. In the left sidebar, click each calendar name → scroll to **Calendar ID**
3. Set in `.env`:
   ```
   WORK_CALENDAR_ID=you@company.com
   PERSONAL_CALENDAR_ID=you@gmail.com
   ```

---

## 2 — Get an Anthropic API key

1. Go to [console.anthropic.com](https://console.anthropic.com) and sign up / sign in.
2. Navigate to **API Keys → Create Key**.
3. Copy the key (shown once) into `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

The default model is `claude-sonnet-4-20250514`. Update `ANTHROPIC_MODEL` in `.env` to change it.

---

## 3 — Run locally with Docker Compose (Windows)

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd flowlist

# 2. Create your .env file
cp .env.example .env
# Edit .env — fill in every value before proceeding

# 3. Build and start all services
docker compose up --build

# 4. In a separate terminal, run database migrations (first time only)
docker compose exec backend alembic upgrade head
```

Open `http://localhost` in your browser.

### Useful dev commands

```bash
# View logs for a specific service
docker compose logs -f backend

# Restart just the backend after a code change (hot-reload handles most cases)
docker compose restart backend

# Open a psql shell
docker compose exec db psql -U flowlist flowlist

# Open a Redis CLI
docker compose exec redis redis-cli -a $REDIS_PASSWORD

# Run a new Alembic migration after model changes
docker compose exec backend alembic revision --autogenerate -m "describe change"
docker compose exec backend alembic upgrade head

# Stop everything
docker compose down

# Stop and wipe all data volumes (destructive)
docker compose down -v
```

---

## 4 — Expose to the internet (for OAuth callbacks + mobile access)

Google OAuth requires a publicly reachable redirect URI. Two free options:

### Option A — Cloudflare Tunnel (recommended, permanent URL)

Cloudflare Tunnel gives you a stable subdomain at no cost with no open firewall ports.

```bash
# 1. Install cloudflared on Windows
# Download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

# 2. Log in (one-time)
cloudflared tunnel login

# 3. Create a tunnel
cloudflared tunnel create flowlist

# 4. Create config file: %USERPROFILE%\.cloudflared\config.yml
#    url: http://localhost:80
#    tunnel: <tunnel-id>
#    credentials-file: %USERPROFILE%\.cloudflared\<tunnel-id>.json

# 5. Route a hostname (requires a domain in your Cloudflare account)
cloudflared tunnel route dns flowlist flowlist.yourdomain.com

# 6. Start the tunnel (run this whenever Docker Compose is up)
cloudflared tunnel run flowlist
```

Then update `.env`:
```
APP_BASE_URL=https://flowlist.yourdomain.com
GOOGLE_WORK_REDIRECT_URI=https://flowlist.yourdomain.com/api/auth/callback/work
GOOGLE_PERSONAL_REDIRECT_URI=https://flowlist.yourdomain.com/api/auth/callback/personal
ALLOWED_ORIGINS=https://flowlist.yourdomain.com
```
And add the `https://flowlist.yourdomain.com/api/auth/callback/work` (and `/personal`) URIs
to your Google Cloud OAuth client's **Authorised redirect URIs** list.

### Option B — ngrok (quickest for testing, URL changes each restart on free tier)

```bash
# 1. Download ngrok from https://ngrok.com/download
# 2. Sign up for a free account and authenticate
ngrok config add-authtoken <your-token>

# 3. Start tunnel pointing at port 80
ngrok http 80
```

ngrok will print a URL like `https://abc123.ngrok-free.app`. Use that as `APP_BASE_URL`
and add it to your Google OAuth redirect URIs. Remember to update `.env` and restart
`docker compose up` each time the URL changes (or upgrade to ngrok paid for a static domain).

---

## Project structure

```
flowlist/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app + router registration
│   │   ├── config.py          # pydantic-settings (all env vars)
│   │   ├── database.py        # async SQLAlchemy engine + session
│   │   ├── models/            # SQLAlchemy ORM models
│   │   │   ├── user.py
│   │   │   └── task.py
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   ├── routers/           # FastAPI route handlers
│   │   │   ├── auth.py        # Google OAuth login/callback
│   │   │   ├── tasks.py       # CRUD + AI parse + reorder
│   │   │   └── calendar.py    # Calendar read endpoints
│   │   ├── services/
│   │   │   ├── ai_service.py        # Anthropic Claude integration
│   │   │   ├── calendar_service.py  # Google Calendar API wrapper
│   │   │   ├── scheduler_service.py # Slot-finding + booking engine
│   │   │   └── auth_service.py      # Session + current-user dep
│   │   └── workers/
│   │       └── tasks.py       # ARQ job definitions + cron schedule
│   ├── alembic/               # Database migrations
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/        # Reusable UI components
│   │   ├── pages/             # Route-level page components
│   │   ├── hooks/             # React Query hooks
│   │   ├── services/api.ts    # Axios client
│   │   └── types/index.ts     # TypeScript types (mirrors backend schemas)
│   ├── vite.config.ts
│   └── Dockerfile
├── caddy/Caddyfile            # Reverse proxy config
├── docker-compose.yml
├── .env.example
└── README.md
```
