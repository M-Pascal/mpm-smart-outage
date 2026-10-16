# PowerChat

**Smarter Power Monitoring. Timely Communication.**

PowerChat is an outage management and customer communication prototype for mini-grid operators, designed to integrate with MicroPowerManager (MPM). Its main purpose is to **warn customers before planned interruptions** such as maintenance, upgrades and load shedding. It also **detects unexpected outages** from smart-meter readings and helps operators respond.

> **Prototype status.** Meters, customers and locations are fictional. WhatsApp messages are **simulated**: no real phone is ever contacted. PowerChat is **not connected to MPM or to the WhatsApp Business Cloud API**. Both integrations are prepared but unverified (see [Not yet implemented](#not-yet-implemented)).

| Part | Stack | Folder |
|---|---|---|
| Web app | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, Recharts, Lucide | [`frontend/`](frontend/) |
| API, scheduler, detection | Python 3.11+, FastAPI, SQLAlchemy 2, SQLite (PostgreSQL-ready) | [`backend/`](backend/) |

---

## Run it locally on Windows with VS Code

**Prerequisites:** Python 3.11+, Node.js 18+ (LTS) and VS Code.

1. Open the `powerchat` folder in VS Code (**File → Open Folder…**).
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

**Configuration (optional):** copy `backend\.env.example` to `backend\.env`. No credentials are needed for the demo. Secrets are read only by the backend, never by the frontend.

### Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q    # 32 tests: detection, scheduling, the three demo scenarios, API
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
4. **Collect confirming readings.** The incident is auto-confirmed after the verification period, and a simulated *Unexpected outage* WhatsApp alert is sent.
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
| **Unexpected outage detection** | Simulated meters report voltage, current, power and connection status. Configurable rules use consecutive readings, a verification period, hysteresis on restore, and a minimum number of meters for an area outage. A **single meter never triggers a community-wide alert**. **Missing data is classified as a communication problem**, not an outage. Voltage loss in an area under an in-progress planned outage raises no incident. |
| **Incident management** | Acknowledge, investigate, confirm (manual or automatic), reject, resolve. Severity is calculated, and affected customers are estimated (some customers have no smart meter). A chronological timeline and the notification history are shown. Operators can send an extended outage update with an ETA. A restoration announcement is **optional and operator-initiated**. |
| **Notifications** | Queue, history and per-recipient message log; compose with recipients by service area; send now, schedule or draft; live preview; cancel; retry failed messages; editable templates with placeholders. Statuses are Draft, Scheduled, Processing, Simulated sent, Failed and Cancelled. A message is **never labelled "delivered"**. |
| **WhatsApp Channels** | Generates Channel-ready public text with no names or numbers, for the operator to copy and post manually. No unofficial automation is used. |
| **Customers** | Search, filter, add, edit and view, with consent, preference, account status and linked meter. Only active customers who have opted in and prefer WhatsApp are messaged. |
| **Power monitoring** | Area health cards, meter table with filters, online and offline devices, incident and planned-outage indicators, and per-meter historical readings. |
| **Analytics** (labelled simulated) | Planned and unexpected counts, durations, detection and confirmation time, notification preparation time, advance-notice lead time, failure rate, and most-affected areas. |
| **Settings** | Preferences and time zone, notification timing, detection thresholds, templates, service areas, integration status (read from the environment), and demo controls. |
| **UX** | Light and dark mode, collapsible sidebar, mobile navigation drawer, global search, operator alert bell, live clock, skeleton loading states, empty states, toasts, confirmation dialogs for destructive or outward-facing actions, and keyboard-accessible Radix components. |

---

## Architecture

```
frontend (React)  ──/api──►  FastAPI routers ──► services ──► SQLAlchemy models ──► SQLite
                                   ▲                 │
                  scheduler tick (every 3 s, background task)
                  1. planned-outage statuses (scheduled → in progress → completed)
                  2. simulated meter readings → debounced detection → incidents
                  3. due notification jobs → simulated WhatsApp sending
```

- **Persistent scheduling with no duplicate sends.** Notification jobs are rows in the database, so the schedule survives restarts. A job is *claimed* with a conditional `UPDATE … WHERE status='scheduled'`. Each recipient message is protected by `UNIQUE(job_id, customer_id)`, so a job interrupted mid-send resumes without sending duplicates. The detector state is also persisted.
- **Demo clock.** All backend time comes from `app/clock.py`. The offset is stored in the settings table.
- **Consistent API format.** Success returns `{"data": …, "meta"?: …}`. Errors return `{"error": {"code", "message", "details": [{field, message}]}}` with status codes 404, 409 (invalid state transition), 422 (validation) and 500.
- **PostgreSQL later.** Only portable column types are used. Set `DATABASE_URL=postgresql+psycopg://…`, install `psycopg`, and add Alembic migrations.

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
  integrations/        mpm.py (REST adapter), whatsapp_cloud.py (Cloud API client). Both inactive.
  api/                 core.py, outages.py, comms.py (routers)
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
| `GET /api/integrations`, `POST /api/integrations/mpm/test` | Integration status |

---

## Not yet implemented

- **WhatsApp Business Cloud API.** `integrations/whatsapp_cloud.py` builds template-message requests but is **not wired into sending**. Going live requires template approval in WhatsApp Manager, customer opt-in records, a delivery-status webhook with signature verification, and replacing the simulated outcome in `services/notifications.send_job`.
- **MPM.** `integrations/mpm.py` is a REST adapter skeleton. Its endpoint paths are placeholders that must be verified against the target MPM version, and no data synchronisation runs. The *Test connection* button only checks reachability. Packaging PowerChat as an MPM Laravel plugin is future work.
- **SMS.** Customers can prefer SMS, but no SMS channel exists, so they are excluded from messaging.
- **Production concerns.** There is no authentication or role-based access (a single administrator is assumed), no Alembic migrations, and no message queue. The scheduler runs in the API process, so run a single API instance.
- **Demo clock caveat.** Moving the demo clock forward and then resetting it leaves some records dated in the "future". Use **Reset demo data** to start clean.
