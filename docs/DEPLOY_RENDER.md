# Deploying the PowerChat backend on Render

The repository contains a Render Blueprint, [`render.yaml`](../render.yaml).
It creates:
- `powerchat-api`, the FastAPI web service built from `backend/`
- `powerchat-db`, a managed PostgreSQL database, connected through `DATABASE_URL`

The database schema is created and upgraded automatically when the service starts (Alembic migrations).

## Before you deploy

1. **Fix the git remote.** The local remote URL embeds a GitHub personal access token. Revoke that token on GitHub, then remove it from the URL:
   ```powershell
   git remote set-url origin https://github.com/M-Pascal/mpm-smart-outage.git
   ```
   Render connects to GitHub through its own GitHub app, so it never needs that token.
2. **Commit and push** the code, including `render.yaml`. Render deploys from GitHub, not from your PC.
   `backend/.env`, `*.db` and `node_modules/` are git-ignored and are not needed.
3. **Choose plans deliberately.**
   - **Web service:** the Blueprint uses an always-on paid plan (`0.5c-512mb`). PowerChat's reminder scheduler runs inside the web process. On the `free` plan the service spins down after 15 idle minutes, so reminders would be sent late. Use `free` only for a short demo.
   - **Database:** the Blueprint uses a paid Postgres plan (`0.1c-256mb`). Free Render Postgres is deleted 30 days after creation and has no backups.
   - To change a plan, edit `plan:` in `render.yaml` or pick it in the dashboard.

## Deploy

1. In the Render Dashboard, choose **New → Blueprint** and select the `mpm-smart-outage` repository and branch.
2. Render lists the two resources and asks for the variables marked `sync: false`:
   - `CORS_ORIGINS`: the URL of the deployed frontend, for example `https://powerchat-web.onrender.com`. You can leave it empty and set it later.
   - WhatsApp and MPM credentials: leave empty for a mock-mode deployment.

   `WHATSAPP_VERIFY_TOKEN` and `TELEMETRY_API_KEY` are generated automatically.
3. Click **Apply**. Render creates the database, installs `backend/requirements.txt` with Python 3.13.5, and starts:
   ```
   uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
4. Wait for the deploy to show **Live**. The health check is `/api/health`.

## Verify

- `https://<service>.onrender.com/api/health` returns `{"data": {"status": "ok", ...}}`.
- `https://<service>.onrender.com/docs` shows the interactive API documentation.
- `https://<service>.onrender.com/api/integrations` shows `"mode": "mock"` and `"live_send_enabled": false`.
- **Logs** (service → Logs) should show the Alembic migration on the first start, then `Application startup complete`.

## Connect the frontend

The React app calls `VITE_API_BASE`, which defaults to `/api`.
When the frontend is hosted separately, for example as a Render **Static Site**:
- **Root directory:** `frontend`
- **Build command:** `npm install && npm run build`
- **Publish directory:** `dist`
- **Environment variable:** `VITE_API_BASE=https://<service>.onrender.com/api`. It is read at build time, so rebuild after changing it.
- **Rewrite rule:** `/*` → `/index.html`, so client-side routes such as `/incidents` work.

Then set `CORS_ORIGINS` on `powerchat-api` to the static site's URL and redeploy.

## Going further (after the first deploy)

- **WhatsApp webhook:** in Meta's app settings, use `https://<service>.onrender.com/api/webhooks/whatsapp` and the generated `WHATSAPP_VERIFY_TOKEN` (service → Environment). Set `META_APP_SECRET` first; in cloud mode, webhooks are rejected without it.
- **Live WhatsApp:** follow section 5 of [MPM_WHATSAPP_INTEGRATION.md](MPM_WHATSAPP_INTEGRATION.md). Start with `WHATSAPP_ALLOWED_RECIPIENTS` set to staff numbers only.
- **MicroPowerManager:** MPM must be reachable from the internet, or at least from Render, over HTTPS. Set `MPM_BASE_URL`, `MPM_EMAIL` and `MPM_PASSWORD`, then use Settings → Integrations → Test connection.
- **Production data:** set `SEED_ON_STARTUP=false` **before** the first deploy for a real tenant. It only seeds an empty database.

## Important constraints

- **Run exactly one instance.** Keep `numInstances: 1` and a single uvicorn worker, because the scheduler runs in-process. Database claims prevent duplicate messages, but two schedulers would also duplicate the simulated meter readings.
- **No login yet.** PowerChat has no authentication, so anyone with the URL can use the dashboard and the API, including demo reset and sending (simulated) notifications. That is acceptable for a demo with fictional data. **Do not connect real MPM customer data or enable live WhatsApp sending on a public URL until access control is added.** Options: add authentication, or put the service behind a restricted network.
- **Ephemeral disk.** Never point `DATABASE_URL` at SQLite on Render; the file would be lost on every deploy.
- **Demo clock.** Moving the demo clock is stored in the database. Use *Reset demo data* after a presentation.
