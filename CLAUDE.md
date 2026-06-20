You are helping me build a personal AI-powered task manager called FlowList.
This is a solo-user web application (just for me) that manages a prioritized task
backlog and automatically schedules tasks as time blocks on my Google Calendar using AI.

## Core Concept
I maintain a prioritized backlog of tasks. When I add or reprioritize a task, the app
automatically estimates the time required (using AI), finds the next available slot on
my Google Calendar, and books it. Reprioritizing tasks triggers a full reschedule of
all future auto-created calendar blocks.

## User Profile
- Solo user (just me), co-founder/COO of a startup
- Fluid, non-traditional schedule for both work and personal time
- Uses Google Calendar exclusively
- Two separate Google accounts:
  - WORK account: has full access to both Work and Personal Google Calendars
  - PERSONAL account: has view-only access to Work Calendar, full access to Personal Calendar
- App auth: Sign in with Google (work account as primary login, with ability to connect
  personal account as secondary OAuth connection)

## Task Model
Each task has:
- title: natural language input
- type: Work | Personal (maps to different Google Calendars)
- priority: position in ordered backlog (drag-to-reorder)
- status: Backlog | Scheduled | Done | Delegated
- estimated_duration_minutes: AI-generated, user-overridable
- optional_user_estimate: optional time estimate in hours entered by the user 
  (in 0.5 hour increments, e.g. 0.5, 1, 1.5, 2). When provided, the AI uses 
  this as a strong signal but may adjust based on historical estimation accuracy.
- optional_deadline: date field
- scheduled_blocks: array of Google Calendar event IDs created by this app
- actual_duration_minutes: filled in on completion, used for AI learning
- created_at, completed_at
- is_off_hours_allowed: boolean (work tasks only) — allows scheduling outside 8am-5pm
- is_workday_allowed: boolean (personal tasks only) — allows scheduling during work hours
- part_of_task_id: reference to parent task (for "Part 2" continuations)
- procrastination_flag: boolean, set by system watchdog

## Scheduling Rules
- Work tasks default to Mon-Fri, 8:00am-5:00pm in user's timezone
- Personal tasks default to outside work hours, unless is_workday_allowed = true
- Absolute hard limits: nothing before 7:00am or after 10:00pm (any day)
- Weekend scheduling: per-day (Saturday/Sunday) configurable hour ranges,
  independently settable for work and personal task types. Each day can be
  enabled/disabled with its own start/end times (default 9am–5pm when
  first enabled). Hard limits still apply as a ceiling. Null start/end
  means that day is disabled for that task type.
- Buffer rule: 30 minutes of clear calendar time REQUIRED before any auto-scheduled block.
  No buffer required after — it's fine if another event (manual or auto) starts immediately
  after an auto-block ends.
- Max single block size: 2 hours
- Min single block size (for split tasks): 1 hour
- Tasks estimated over 2 hours get split into multiple sessions of 1-2 hours each
- All sessions for a split task are scheduled consecutively by priority (not back-to-back
  in time, but in order in the queue)
- The app only moves/deletes calendar events it created. It never touches manually
  created events.

## Scheduling Philosophy
- Cap auto-scheduled blocks at 2 work blocks and 2 personal blocks per day maximum
- This creates natural breathing room and reduces calendar noise
- When a priority change occurs, only reschedule the next 72 hours of auto-blocks 
  (not all future blocks)
- A full reschedule of all future blocks runs automatically once per day
  (overnight, 09:00 UTC ≈ 4am America/Chicago) and can also be triggered
  manually by the user
- This daily full reschedule consolidates any gaps that have built up and 
  re-optimizes the entire backlog order against the real calendar, catching up
  anything left behind by 72h windowed (priority-change) reschedules. It runs
  overnight so it never shifts upcoming blocks while the user is mid-day.
- The manual "Reschedule Now" button in Settings triggers a full reschedule 
  immediately for cases where the user has made major backlog changes

## AI Behavior
- Natural language task entry: AI parses and suggests category, priority placement,
  and time estimate
- User sees AI suggestions and confirms or adjusts before saving
- AI learns from actual vs estimated duration over time (per task type/category)
- Tasks that remain unscheduled/incomplete for 2+ weeks get flagged with
  procrastination_flag and surface in a dashboard watchdog widget

## Calendar Scheduling Logic
- Scan calendar for free slots respecting all buffer and hour rules
- Schedule highest priority tasks in earliest available slots
- Lower priority tasks get later slots
- Each task's scheduled start date is visible in the backlog list view

## Missed/Overdue Block Flow
When a task's scheduled block START time passes and the task is still in
Scheduled status (not Done or Delegated):

**Visual indicator:** The scheduled time label on the collapsed task card
switches from green to a muted gray with a small clock icon — subtle, not
a banner or aggressive highlight.

**Two equal action buttons** appear in the expanded card:
1. **Reschedule** — Cancels all existing calendar blocks for the task
   (GCal + DB soft-delete), then enqueues a full reschedule. The task keeps
   its current backlog priority; the scheduler finds the next available slot
   from now. No prompts, no priority changes.
2. **I Have More Work To Do** — Cancels all existing calendar blocks for the
   original task, creates a "Part 2" continuation task at the same priority,
   increments the original's priority by 1 (so Part 2 slots in ahead), then
   enqueues a full reschedule. Both the original and Part 2 get new blocks.

**Rules:**
- Both buttons appear only when status=Scheduled AND start time has passed.
- Neither button appears on upcoming tasks.
- The calendar event is moved only on explicit user action — never automatically.
- Trigger is the block START time, not end time.

## Procrastination Watchdog
- Background job checks daily for tasks unscheduled or incomplete for 14+ days
- Surfaces these in a dedicated UI widget
- User can: Confirm Done | Reschedule (re-enters backlog) | Mark as Delegated | Delete

## Tech Stack
- Frontend: React + Vite + TypeScript + Tailwind + dnd-kit + TanStack Query
- Backend: Python 3.12 + FastAPI
- Database: PostgreSQL 16 (plain container, migrate to Supabase managed when moving to cloud)
- Caching + job queue: Redis 7 + ARQ
- Reverse proxy: Caddy 2
- Auth: Google OAuth 2.0 (primary work account + secondary personal account connection)
- AI: Anthropic Claude API (claude-sonnet-4-20250514)
- Calendar: Google Calendar API v3

## Development Workflow
- After making code changes to frontend or backend files, always rebuild and restart
  the affected Docker containers so changes take effect:
  `cd /c/Projects/flowlist && docker compose up -d --build frontend backend worker`
- The worker container shares the backend image, so rebuild it whenever backend changes.
- Frontend and backend run in Docker — there are no local node_modules or Python venv.
- Adding a new npm package requires two steps (the anonymous node_modules volume must
  be renewed so the container picks up the newly installed package):
  1. `docker compose run --rm --no-deps frontend npm install`  ← updates package-lock.json
  2. `docker compose up -d --build -V frontend`               ← rebuilds image + renews volume

## Design Principles
- Mobile-responsive web app (no native mobile app)
- Minimal friction task entry (natural language first, optional fields hidden by default)
- Clean, fast UI — this is a daily driver tool
- Solo user — no multi-tenancy needed, but don't hardcode credentials
- Security: OAuth tokens stored securely, no sensitive data exposed client-side
- Built for portability: Docker Compose setup from day one

## Decisions Made
- App name: FlowList
- Project folder: C:\Projects\flowlist
- Hosting: Docker on home Windows machine initially, cloud-portable design
- Internet exposure: Cloudflare Tunnel or ngrok (free tier)
- Account setup: Two separate Google accounts (work + personal)
- No voice input in v1
- No email/digest summaries in v1
- Mobile-responsive web app only (no native mobile app)
- Backend: Python 3.12 + FastAPI
- Database: PostgreSQL 16 (plain container, migrate to Supabase managed when moving to cloud)
- Caching + job queue: Redis 7 + ARQ
- Frontend: React + Vite + TypeScript + Tailwind + dnd-kit + TanStack Query
- Reverse proxy: Caddy 2
- scheduled_blocks normalized into calendar_blocks table (not stored on tasks)
- Soft-delete pattern used on calendar_blocks (is_deleted + deleted_at)
- Alembic used for database migrations
- Seed data script at scripts/seed.py
- Token encryption: Fernet (AES-128-CBC + HMAC-SHA256)
- Session management: itsdangerous signed cookies (stateless)
- OAuth state anti-CSRF: Redis nonce with 5-minute TTL
- FlowList calendar events identified by: [FlowList] in description 
  + extendedProperties.private.flowlist = "true"
- Both calendars queried via single freebusy call through work account
- slot_finder.py is pure (no I/O) — all logic testable without DB or API
- User time estimate: hours only, 0.5 increment numeric input (no story points, 
  t-shirt, or pomodoros)
- AI forced tool-use (tool_choice) to guarantee structured JSON output — 
  no parsing fragility
- AI graceful degradation: all 3 Anthropic error types caught, returns 
  ai_available=False with sensible defaults
- Task input UI: 5-phase state machine (idle → loading → confirming → saving → idle)
  with optimistic skeleton loading
- Scheduler: 72-hour windowed reschedule for priority changes, full reschedule 
  for all other triggers
- Debounce: Redis token pattern, 2-second delay on priority change jobs
- Cron jobs: procrastination_watchdog (daily 8am UTC), daily_full_reschedule (daily 09:00 UTC ≈ 4am America/Chicago)
- Rollback: best-effort GCal event deletion on scheduler failure
- Scheduling cap: 2 work blocks + 2 personal blocks per day maximum
- Database migration fix: alembic.ini uses static placeholder URL, env.py
  overrides via set_main_option() from os.environ
- Redis/Postgres passwords: alphanumeric only (no special characters in URLs)
- Docker volumes must be cleared (down -v) when passwords change
- SQLAlchemy relationship overlap warning on Task.continuation_tasks — 
  minor, to be cleaned up
- All API responses use consistent envelope: { data, error, meta }
- next_scheduled_start added to TaskRead schema (batch query, no N+1)
- get_optional_user() returns None instead of 401 for optional auth checks
- All routers registered in main.py with global HTTPException handler
- Domain: taskflowlist.com (registered on Cloudflare)
- Internet exposure: Cloudflare Tunnel (not ngrok)
- Auth hardening: Cloudflare Access (email whitelist) as outer layer + 
  Google OAuth as inner layer
- Registration: invite-only (admin generates invite codes/links)
- Multi-user: designed for 2-5 trusted users before cloud migration
- Priority labels: removed — backlog order is the only priority signal
- robots.txt: Disallow all crawlers (private app)
- Mixpanel: planned for Prompt 11 — instrument all sensible user actions
  (deferred, not forgotten)
- Rate limiting: shared rate_limit.py service using existing Redis pool;
  auth login/connect = 10 req/min per IP; invites = 5 req/min per IP
- Request logging middleware: logs method, path, status, ms, IP, user_id;
  skips /api/auth/me, /health, /api/healthz
- Invite system: invites table, admin-only CRUD at /api/invites, gate in
  callback_work (first user exempt), friendly HTML error for uninvited
- Admin = user_id 1; UserRead.is_admin computed_field; frontend checks user.is_admin
- Health endpoint: GET /health (Cloudflare/Docker) + GET /api/healthz (existing)
- GET /api/auth/logout added (navigation link) alongside POST (API callers)
- Cloudflare Tunnel: cloudflared container in docker-compose using token from env
- Caddy: trusted_proxies for Cloudflare IPs; HSTS; CSP; forwards CF-Connecting-IP
- security.txt at /security.txt (served from frontend/public/)
- Overdue handling: ReviewPromptBanner and review-prompts API removed;
  overdue/missed blocks handled entirely via in-card flow in TaskRow
  (gray clock icon + Reschedule / "I Have More Work To Do" buttons).
  tentatively_done status kept in DB enum but not surfaced as a distinct
  UI state — treated the same as scheduled-and-overdue.