# PowerChat

**Smarter Power Monitoring. Timely Communication.**

PowerChat is an outage management and customer communication prototype for mini-grid operators, designed to integrate with MicroPowerManager (MPM). Its main purpose is to **warn customers before planned interruptions** such as maintenance, upgrades and load shedding. It also **detects unexpected outages** from smart-meter readings and helps operators respond.

> **Status.** PowerChat runs in **mock mode by default**: WhatsApp messages are simulated and no real phone is contacted.
> The WhatsApp Business Cloud API channel, its webhook, and the MicroPowerManager REST integration are **implemented and tested against mocked services**, but have **not yet been run against Meta or a live MPM instance**.
> Live sending needs explicit configuration and an allowlist.
> The demo data (customers, meters, locations) is fictional.
> How MPM handles notifications today, and why this architecture was chosen: [docs/MPM_WHATSAPP_INTEGRATION.md](docs/MPM_WHATSAPP_INTEGRATION.md).

| Part | Stack | Folder |
|---|---|---|
| Web app | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, Recharts, Lucide | [`frontend/`](frontend/) |
| API, scheduler, detection, WhatsApp and MPM integration | Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, httpx; SQLite for development, MySQL in production | [`backend/`](backend/) |

---

## Run it locally on Windows with VS Code

**Prerequisites:** Python 3.11+, Node.js 18+ (LTS) and VS Code.

1. Open the `mpm-smart-outage` folder (this repository) in VS Code (**File → Open Folder…**).
2. Open a terminal (**Terminal → New Terminal**, PowerShell) and start the API:
   ```powershell
   .\start-backend.ps1
   ```
   The first run creates `backend\.venv` and installs the dependencies. On first start the API creates `backend\powerchat.db` and loads the demo data. It then serves:
   - API: http://127.0.0.1:8000
   - Interactive API documentation: **http://127.0.0.1:8000/docs**
3. Open a **second** terminal (the **+** button) and start the web app:
   ```powershell
   .\start-frontend.ps1
   ```
4. Open **http://localhost:5173**.

If PowerShell blocks the scripts, run `Set-ExecutionPolicy -Scope Process Bypass` in that terminal first.

You can also run the steps by hand:

```powershell
# Terminal 1: backend
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# Terminal 2: frontend
cd frontend
npm install
npm run dev
```

**Configuration (optional):** copy `backend\.env.example` to `backend\.env`.
No credentials are needed for the demo.
Secrets are read only by the backend, never by the frontend.
The database schema is created and upgraded automatically at startup by Alembic migrations (`backend\migrations`).

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Default SQLite file. Production: `mysql+pymysql://user:pass@host:3306/powerchat` |
| `WHATSAPP_MODE` | `mock` (default) or `cloud` |
| `WHATSAPP_LIVE_SEND_ENABLED` | Must be `true` before any real message is sent |
| `WHATSAPP_ALLOWED_RECIPIENTS` / `WHATSAPP_ALLOWLIST_DISABLED` | Only listed numbers receive live messages unless the allowlist is disabled |
| `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_BUSINESS_ACCOUNT_ID` | WhatsApp Cloud API credentials |
| `WHATSAPP_VERIFY_TOKEN`, `META_APP_SECRET` | Webhook handshake and `X-Hub-Signature-256` verification |
| `WHATSAPP_API_VERSION`, `WHATSAPP_TEMPLATE_LANGUAGE` | Default `v26.0` (current Graph API version) and `en` |
| `MPM_BASE_URL`, `MPM_EMAIL`, `MPM_PASSWORD` | MPM service account (REST API, JWT) |
| `MPM_DEFAULT_COUNTRY_CODE`, `MPM_SMS_ENABLED`, `MPM_SYNC_INTERVAL_MINUTES` | Phone normalisation, SMS through MPM, periodic sync |
| `TELEMETRY_API_KEY` | Enables `POST /api/telemetry/readings` |

Setup steps for the WhatsApp Cloud API and MPM: [docs/MPM_WHATSAPP_INTEGRATION.md](docs/MPM_WHATSAPP_INTEGRATION.md#5-configure-the-whatsapp-business-cloud-api).

### Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q    # 70 tests: detection, scheduling, demo scenarios, API, channels,
                                       # delivery/retries, webhook, MPM client/sync, telemetry
cd ..\frontend
npm run build                          # TypeScript type-check and production build
```

---

## Guided demo (for presentations)

Click **Guided demo** (amber button, bottom left). Every step performs a real backend action.

**Demo clock.** Use **+1 hour / +6 hours / +1 day** or **Jump to next scheduled notification** to fire scheduled messages without waiting.

**Live meter feed.** The simulated meters report every 3 seconds. The feed can be paused.

### Scenario A: planned maintenance

1. **Open scheduling form.** The form opens pre-filled: Sector B, tomorrow 9:00–11:00, a 1-hour reminder.
2. Review the **"When messages will be sent"** list and the WhatsApp preview, which includes recipient counts and consent exclusions.
3. Click **Schedule & queue notifications**. The initial notice is sent in simulation.
4. Click **Jump to the reminder time**. The demo clock moves forward and the scheduler sends the reminder.
5. Click **Open notification history** to see each recipient and their simulated outcome.

### Scenario B: unexpected outage

1. Reset to normal supply.
2. **Simulate voltage loss** in Sector D.
3. A **potential** incident appears after consecutive near-zero readings.
4. **Collect readings & verify.** More near-zero readings arrive, and the operator verifies (confirms) the incident. Only then is the simulated *Unexpected outage* WhatsApp alert sent. Automatic confirmation exists but is off by default.
5. **Restore power.** The incident closes internally **without** a customer message. An optional restoration announcement is suggested because many customers were affected.

### Scenario C: rescheduling

1. Pick an announced event and click **Quick: move +1 day**, or use the reschedule form.
2. Pending reminders are **re-timed, cancelled or re-created**, and a **rescheduling notice** is sent to customers who were already notified.
3. The change is recorded in the notification history.

**Reset demo data** (in the demo panel or Settings → Demo) restores the original state. Use it after a presentation, or after moving the demo clock a long way, so dates line up again.

---

## Features

| Area | What works |
|---|---|
| **Overview** | Six summary cards, consumption and voltage charts (1 h / 6 h / 24 h / 7 d), upcoming maintenance with notification status, active incidents, recent activity. All are computed from backend data and refresh automatically. |
| **Scheduled outages** | Create (draft or publish), edit, reschedule, cancel. Validation covers end after start, start in the future, areas within the chosen mini-grid, and a 7-day maximum. Reminder options are 24 h, 6 h, 1 h or custom, with an exact send-time preview. An advance warning is **never** scheduled or sent after the start. Changing the start time recalculates pending reminders automatically. Rescheduling or cancelling an announced event sends an update. A month calendar shows status colours. Each event has a notification timeline. |
| **Unexpected outage detection** | Simulated meters, or real MPM meters through `POST /api/telemetry/readings`, report voltage, current and power. Configurable rules use consecutive readings, hysteresis on restore, and a minimum number of meters for an area outage. A **single meter never triggers a community-wide alert**. One missing reading is never an outage. Many meters going silent together create a **communication-loss** incident that always needs operator verification. **Customers are alerted only after verification.** Voltage loss in an area under an in-progress planned outage raises no incident. |
| **Incident management** | Acknowledge, investigate, confirm (manual or automatic), reject, resolve. Severity is calculated, and affected customers are estimated (some customers have no smart meter). A chronological timeline and the notification history are shown. Operators can send an extended outage update with an ETA. A restoration announcement is **optional and operator-initiated**. |
| **Notifications** | Queue, history, per-recipient message log and a **Failed** view. Compose with recipients by service area; send now, schedule or draft; live preview; cancel; operator retry. Each message shows its channel (WhatsApp, or SMS through MPM), provider, attempts, provider message ID and delivery timeline (queued → sent → delivered → read, or failed). Delivery statuses come from the WhatsApp webhook; in mock mode they are simulated. Simulated messages are always labelled as simulated. |
| **WhatsApp Channels** | Generates Channel-ready public text with no names or numbers, for the operator to copy and post manually. No unofficial automation is used. |
| **Customers** | Search, filter, add, edit and view, with consent (and how it was given), preference, account status and linked meter. Customers synced from MPM are marked: their name, phone and area are read-only, since MPM is the source of truth. WhatsApp requires consent; SMS-preference customers are reached through MPM. Replying STOP opts a customer out automatically. |
| **Power monitoring** | Area health cards, meter table with filters, online and offline devices, incident and planned-outage indicators, and per-meter historical readings. |
| **Analytics** (labelled simulated) | Planned and unexpected counts, durations, detection and confirmation time, notification preparation time, advance-notice lead time, failure rate, and most-affected areas. |
| **Settings** | Preferences and time zone, notification timing, detection thresholds, templates, service areas, integration status (read from the environment), and demo controls. |
| **UX** | Light and dark mode, collapsible sidebar, mobile navigation drawer, global search, operator alert bell, live clock, skeleton loading states, empty states, toasts, confirmation dialogs for destructive or outward-facing actions, and keyboard-accessible Radix components. |

---

## Architecture

```
                         MicroPowerManager (REST, JWT service account)
                           ▲ people / cities / mini-grids      ▲ POST /api/sms/storeandsend (SMS customers)
frontend (React) ──/api──► FastAPI ──► services ──► channels ──┬─► WhatsApp Cloud API (templates) ──► customer
                              ▲            │                   ├─► MPM SMS
     WhatsApp webhook ────────┘            ▼                   └─► mock (default)
     (statuses, STOP/START)    SQLAlchemy + Alembic ──► SQLite (dev) / MySQL (prod)
                  scheduler tick (every 3 s): planned-outage statuses → simulated readings → detection
                  → due jobs → due retries → interrupted sends → mock delivery receipts
```

- **Persistent scheduling with no duplicate sends.**
  - Jobs, messages and retry times are database rows, so nothing depends on in-memory timers.
  - Jobs and messages are *claimed* with conditional updates.
  - Each customer gets at most one message per job (`UNIQUE(job_id, customer_id)`), and provider message IDs are unique.
  - A send whose outcome is unknown (a timeout after the request left, or a crash) is never retried automatically.
- **Demo clock.** All backend time comes from `app/clock.py`. The offset is stored in the settings table.
- **Consistent API format.** Success returns `{"data": …, "meta"?: …}`. Errors return `{"error": {"code", "message", "details": [{field, message}]}}` with status codes 404, 409 (invalid state transition), 422 (validation) and 500.
- **Database.** SQLite for development; MySQL in production through `DATABASE_URL` (driver `pymysql` included). Alembic migrations live in `backend/migrations` and run at startup.

```
backend/app/
  main.py              app factory, scheduler loop, error handlers, demo reset
  models.py            customers, meters, service areas, mini-grids, scheduled outages, incidents (+events),
                       meter & area readings, templates, notification jobs & messages, activity log, settings
  services/
    scheduled_outages.py   planning, validation, publish / reschedule / cancel, status lifecycle
    notifications.py       recipients & consent, rendering, claim-and-send, retries, preview
    monitoring.py          meter simulator, detection rules, incident engine
    incidents.py           operator actions
    analytics.py, templates.py, settings_store.py, engine.py (tick), timefmt.py
    mpm_sync.py            mirror MPM mini-grids, cities, customers and meters (consent untouched)
    webhooks.py            WhatsApp status callbacks and STOP/START handling
  channels/            base.py (contract), mock.py, whatsapp_cloud.py, mpm_sms.py, router.py (consent and safety rules)
  integrations/mpm.py  MicroPowerManager REST client (JWT login, pagination, SMS store-and-send)
  phone.py             E.164 normalisation and masking
  api/                 core.py, outages.py, comms.py, integrations.py (routers)
backend/migrations/    Alembic: 0001 baseline, 0002 delivery tracking and MPM references
  seed.py              fictional demo data (36 customers, 31 meters, 2 mini-grids, 60 days of history)
frontend/src/
  pages/               Overview, Monitoring, ScheduledOutages (+ OutageForm), Incidents, Customers,
                       Notifications (+ TemplateEditor), Analytics, Settings
  components/ui/       shadcn/ui primitives        components/shared/   charts, previews, dialogs
  components/layout/   sidebar, top bar, guided demo panel
```

### Main API endpoints

The full, interactive list is at `/docs`.

| Method & path | Purpose |
|---|---|
| `GET /api/dashboard` | Summary cards, areas, upcoming maintenance, active incidents, activity |
| `GET /api/meters`, `GET /api/meters/{id}/readings?range=` | Meter status and history |
| `GET /api/monitoring/series?range=&area_id=` | Consumption and voltage trend |
| `GET/POST /api/customers`, `PATCH /api/customers/{id}` | Customer management |
| `GET /api/outages` | Planned and unexpected outages together |
| `GET/POST /api/outages/scheduled`, `PATCH /api/outages/scheduled/{id}` | Planned interruptions (PATCH recalculates reminders) |
| `POST /api/outages/scheduled/preview` | Exact send times and rendered messages, without saving |
| `POST /api/outages/scheduled/{id}/publish`, `…/cancel` | Lifecycle actions |
| `GET /api/incidents`, `GET /api/incidents/{id}` | Incidents with timeline and notifications |
| `POST /api/incidents/{id}/acknowledge`, `investigate`, `confirm`, `reject`, `resolve` | Incident workflow |
| `POST /api/incidents/{id}/send-update`, `announce-restoration` | Optional customer updates |
| `GET /api/notifications`, `GET /api/notifications/{id}`, `GET /api/notifications/messages` | Queue, history, message log |
| `POST /api/notifications/preview`, `POST /api/notifications`, `POST /api/notifications/simulate` | Preview, create (draft / schedule / send now), send immediately |
| `POST /api/notifications/{id}/cancel`, `retry`, `schedule` | Queue management |
| `GET /api/templates`, `PUT /api/templates/{key}`, `POST /api/templates/{key}/reset` | Message templates |
| `POST /api/channels/announcement` | WhatsApp Channel-ready text |
| `POST /api/simulation/outage`, `restore`, `normal`, `tick` | Outage simulation |
| `GET /api/analytics?days=` | Analytics (simulated) |
| `GET /api/settings`, `PUT /api/settings/{section}` | Settings |
| `GET /api/demo/clock`, `POST /api/demo/advance`, `POST /api/demo/reset` | Demo mode |
| `GET /api/integrations` | WhatsApp mode, live-send state and MPM status (no secrets) |
| `POST /api/integrations/mpm/test`, `POST /api/integrations/mpm/sync` | Test MPM credentials; sync customers from MPM |
| `GET /api/webhooks/whatsapp` | Meta webhook verification (`hub.challenge`) |
| `POST /api/webhooks/whatsapp` | Delivery statuses and STOP/START replies (requires a valid `X-Hub-Signature-256`) |
| `POST /api/telemetry/readings` | Meter readings for MPM meters (`X-PowerChat-Key`) |
| `GET /api/templates/{key}/whatsapp` | Template text with `{{1}}…{{n}}` variables, to register in WhatsApp Manager |
| `GET /api/audience?area_ids=&detail=true` | Which customers an event reaches, their channel, and why others are excluded |

---

## Implemented, simulated or pending

| Item | Status |
|---|---|
| Mock messaging (default) | Implemented |
| WhatsApp Cloud API channel (templates, retries, idempotency, logging without secrets) | Implemented and tested against a mocked HTTP transport. **Not yet exercised against Meta** |
| Webhook (verification, signature check, delivery statuses, STOP/START) | Implemented and tested with signed sample payloads. **Not yet registered with Meta** |
| MPM REST client, customer sync, SMS through MPM | Implemented to MPM's source-code contracts and tested with mocked responses. **Not yet run against a live MPM instance** |
| Telemetry ingestion for MPM meters | Implemented. **No telemetry producer exists yet**: MPM stores consumption, not voltage |
| Native MPM plugin (PHP) | Pending by design; see the integration document |

**Known limitations:**
- **Templates.** WhatsApp templates must be created and approved in WhatsApp Manager before live use; `GET /api/templates/{key}/whatsapp` gives the exact text.
- **Access control.** There is no authentication or role-based access in PowerChat yet (a single administrator is assumed). Put it behind your network or SSO before deployment.
- **Scheduler.** It runs inside the API process, so run a single API instance. Database claims prevent duplicates, but there is no separate worker yet.
- **Demo clock.** Moving the demo clock forward and then resetting it leaves some records dated in the "future". Use **Reset demo data** to start clean.
