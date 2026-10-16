# PowerChat ↔ MicroPowerManager ↔ WhatsApp integration

This document records how MicroPowerManager (MPM) handles notifications today, the integration approach chosen for PowerChat, and how to configure it.
Facts about MPM come from its source code (EnAccess/micropowermanager, `main` branch, inspected October 2026).
The MPM source is **not** part of this repository.

## 1. How MPM sends notifications today

MPM is a Laravel (PHP) monorepo with a Vue 2 frontend, multi-tenant MySQL (a shared database plus one database per tenant), and Redis/Horizon queues with a separate scheduler container.

**Outgoing messages (SMS):**

1. Callers use `App\Services\SmsService::sendSms($data, SmsTypes::X, SmsConfigs::class)`.
   `SmsTypes` has transaction confirmation, appliance rate, overdue appliance rate, manual SMS, and resend information.
2. A `App\Sms\Senders\SmsSender` subclass builds the text from `sms_bodies` templates (header, body, footer).
   It resolves the receiver from `addresses.phone`.
3. A row is written to the `sms` table: `status` (0 stored, 1 sent, 2 delivered, -1 failed), `attempts`, `error_message`, `gateway_id`, a polymorphic `trigger` (used for de-duplication), and `uuid`.
4. `App\Jobs\SmsProcessor` is dispatched to the Redis `sms` queue with `$tries = 1`.
   Retries are handled by the scheduled `sms:resend-rejected` command.
5. `App\Services\SmsGatewayResolverService::determineGateway()` picks **one** gateway per tenant from `main_settings.sms_gateway_id`.
6. The gateway plugin's `sendSms(body, receiver, Sms)` is called.
   The gateway plugins are `AfricasTalking`, `TextbeeSmsGateway` and `ViberMessaging`.
   Viber is a non-SMS channel with its own webhook route and falls back when the customer has no Viber contact.
7. `SmsService::markSent()` or `markFailed()` records the outcome.

**HTTP routes (`routes/api.php`, JWT guard `auth:api`):**
- `GET /api/sms`, `GET /api/sms/{id}`, `GET /api/sms/phone/{number}`, `GET /api/sms/search/{term}`
- `POST /api/sms/storeandsend` sends to `person_id` or `phone`.
- `POST /api/sms/bulk` sends to people, groups, connection types or all customers.
- `POST /api/sms` records an incoming SMS.

**Other facts relevant to PowerChat:**
- **Customers** are `people` with `is_customer = 1`. The phone number is the primary address (`addresses.is_primary = 1`). `GET /api/people` accepts the filters `is_customer`, `city_id`, `agent_id` and others.
- **Mini-grids and cities.** Cities belong to mini-grids (`cities.mini_grid_id`). Routes: `GET /api/mini-grids` and `GET /api/cities`.
- **Authentication.** `POST /api/auth/login {email, password}` returns `{access_token, expires_in, …}` for the `api` guard. An `api-key` guard exists for company integrations but protects only a few payment routes.
- **No maintenance-schedule or outage entity.** "Maintenance" in MPM means maintenance *users* (technicians).
- **No voltage telemetry.** `meter_consumptions` stores consumption and credit per reading date only.

## 2. Integration approach and why

```
MicroPowerManager ──REST (JWT service account)──► PowerChat backend ──template messages──► WhatsApp Cloud API ──► customer
   people, cities, mini-grids, devices             maintenance events, incidents,                ▲
   POST /api/sms/storeandsend ◄─── SMS customers ── scheduled reminders, delivery tracking       │
                                                                                                  └── delivery statuses (webhook)
```

**Chosen approach: a companion service with no changes to MPM.**
- **MPM stays the source of truth for customers.** PowerChat reads mini-grids, cities and customers with MPM's existing REST API, using a dedicated service account. It never connects to MPM's databases.
- **PowerChat owns what MPM does not have:** maintenance events, incident verification, scheduled WhatsApp reminders, delivery tracking and the audit trail. These live in PowerChat's own database, which is MySQL in production and SQLite only for development and tests. Alembic migrations manage the schema.
- **SMS is preserved and reused.** Customers who prefer SMS are delivered through MPM's own `POST /api/sms/storeandsend`, so MPM's gateways, `sms` table and resend command keep working unchanged.
- **WhatsApp is a new channel** behind a channel interface (`app/channels/`): mock, Cloud API, or MPM SMS.

**Why not add WhatsApp as another MPM gateway plugin (the `ViberMessaging` pattern)?**
- MPM gateways send free text. WhatsApp requires pre-approved **template** messages for business-initiated conversations; free text is allowed only within 24 hours of the customer's last message. Proactive outage alerts must therefore be templates.
- MPM has no maintenance or outage domain to trigger the messages, so that logic would have to be built inside MPM anyway.
- A PHP plugin could not be built or tested in this environment (no PHP, Composer, Docker or MySQL). MPM's contribution rules also require plan-first PRs with its quality checks.

**Possible follow-up:** a thin MPM plugin that pushes meter telemetry to `POST /api/telemetry/readings`, or one that adds a "PowerChat WhatsApp" gateway for free-text replies within the 24-hour window.

## 3. Data model added to PowerChat

Migration `backend/migrations/versions/0002_delivery_tracking_and_mpm_references.py` adds:

| Table / column | Purpose |
|---|---|
| `notification_messages.channel`, `provider`, `simulated` | Which channel and provider delivered the message (`mock`, `whatsapp_cloud` or `mpm_sms`), and whether it was simulated |
| `notification_messages.provider_message_id` (UNIQUE) | WhatsApp `wamid` or MPM SMS id. A message that has one is never sent again |
| `notification_messages.status` | `queued`, `sending`, `retry_scheduled`, `sent`, `delivered`, `read` or `failed` |
| `notification_messages.sent_at`, `delivered_at`, `read_at`, `failed_at`, `next_retry_at`, `error_code` | Delivery timeline and retry schedule |
| `delivery_attempts` | One row per provider call: outcome, HTTP status and error code. No credentials or message bodies |
| `webhook_events` (UNIQUE `event_key`) | Idempotent processing of Meta's at-least-once webhook delivery |
| `customers.source`, `mpm_person_id`, `last_synced_at` | Link to the MPM person. `demo` customers are never sent live messages |
| `customers.consent_source`, `consent_updated_at` | Consent audit: operator, WhatsApp reply, … |
| `mini_grids.mpm_id`, `service_areas.mpm_city_id`, `meters.source` | MPM references |
| `incidents.evidence_type` | `voltage` or `communication_loss` |

Existing simulated history is kept and labelled `simulated = true`. The migration is reversible.

## 4. Safety rules

1. **Mock is the default.** Live sending needs `WHATSAPP_MODE=cloud`, `WHATSAPP_LIVE_SEND_ENABLED=true` and credentials.
2. **Live sends go only to allow-listed numbers.** Add numbers to `WHATSAPP_ALLOWED_RECIPIENTS`, or set `WHATSAPP_ALLOWLIST_DISABLED=true` once you approve broad sending. Other recipients are recorded as failed with `not_allowlisted`.
3. **Demo customers are never sent to a real provider,** whatever the configuration.
4. **Consent and preference are checked when the message is queued and again just before each send.** A customer who replies **STOP** is opted out automatically; **START** opts them back in.
5. **Phone numbers must be E.164.** Local MPM numbers are converted with `MPM_DEFAULT_COUNTRY_CODE`. Invalid numbers are recorded as failed with `invalid_phone`.
6. **No duplicate alerts:**
   - Jobs and messages are claimed atomically before sending.
   - Each customer gets at most one message per job (UNIQUE).
   - Provider message ids are UNIQUE.
   - An outcome that may have reached Meta (read timeout, or a crash while sending) is never retried automatically; an operator decides.
7. **Retries follow Meta's guidance.** Retryable errors are rate limits (`4`, `80007`, `130429`, `131056`), temporary unavailability (`131016`, `133004`), HTTP 429 and 5xx, and the unknown send error `131000`. They back off at 30 s, then 60 s, up to 3 attempts. Other errors are permanent: undeliverable (`131026`), template problems (`132000`, `132001`), expired token (`190`), quality restrictions (`131048`).
8. **Logs never contain the access token or full phone numbers** (masked as `+250•••456`).

## 5. Configure the WhatsApp Business Cloud API

1. In Meta for Developers, create an app of type **Business** and add the **WhatsApp** product.
2. In **WhatsApp Manager → API setup**, note the **Phone number ID** and **WhatsApp Business Account ID**. Add a production number, or use Meta's test number with verified test recipients.
3. Create a **system user** in Business Settings, give it the `whatsapp_business_messaging` and `whatsapp_business_management` permissions, and generate a permanent **access token**.
4. **Register the templates.** For each template, open `GET /api/templates/{key}/whatsapp`, for example `/api/templates/maintenance_reminder/whatsapp`. It returns the body with positional `{{1}}…{{n}}` variables, in the order PowerChat sends them. Create a template in WhatsApp Manager with the **same name**, category **Utility**, and the language from `WHATSAPP_TEMPLATE_LANGUAGE`. Wait for approval.
5. **Configure the webhook.** In the app's WhatsApp → Configuration, set:
   - Callback URL: `https://<your-public-host>/api/webhooks/whatsapp`. Meta requires HTTPS; for a local test use a tunnel.
   - Verify token: the value of `WHATSAPP_VERIFY_TOKEN`.
   - Subscriptions: **messages**. This covers delivery statuses and customer replies.
6. Put the credentials in `backend/.env`:
   - `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_VERIFY_TOKEN`
   - `META_APP_SECRET` (App settings → Basic)
   - `WHATSAPP_API_VERSION=v26.0`
7. **First live test:** keep `WHATSAPP_ALLOWED_RECIPIENTS` to one or two staff numbers. Set `WHATSAPP_MODE=cloud` and `WHATSAPP_LIVE_SEND_ENABLED=true`, then restart. Settings → Integrations shows the live state.

## 6. Configure MicroPowerManager access

1. In MPM, create a dedicated user for PowerChat, with a role that can read customers (`customers` permission). Add the SMS permission only if `MPM_SMS_ENABLED=true`.
2. Set `MPM_BASE_URL`, `MPM_EMAIL`, `MPM_PASSWORD` and `MPM_DEFAULT_COUNTRY_CODE` in `backend/.env`.
3. In **Settings → Integrations**, click **Test connection**, then **Sync customers now**. Set `MPM_SYNC_INTERVAL_MINUTES` to sync periodically.
4. Synced customers start **without WhatsApp consent**. Record consent per customer in PowerChat. MPM has no consent field.

## 7. Meter telemetry (Workflow B with real meters)

MPM does not store voltage readings.
To use real data, a meter-vendor integration or an MPM plugin pushes readings for synced meters:

```http
POST /api/telemetry/readings
X-PowerChat-Key: <TELEMETRY_API_KEY>
Content-Type: application/json

{"readings": [{"meter_serial": "47000123", "voltage": 0.8, "timestamp": "2026-10-16T08:00:00Z"}]}
```

**Detection rules:**
- One near-zero reading is never enough. A status change needs consecutive readings.
- Several meters in an area going silent together become a **communication-loss** incident, which may be an outage or a network fault. These are never auto-confirmed.
- Customers are alerted only after an operator verifies the incident. Automatic confirmation exists but is off by default.

## 8. What is implemented, simulated or pending

| Item | Status |
|---|---|
| WhatsApp Cloud API client: templates, error handling, retries, idempotency | Implemented and tested against a mocked HTTP transport. **Not exercised against Meta** (no credentials here) |
| Webhook: verification, signature, statuses, STOP/START | Implemented and tested with signed sample payloads. **Not registered with Meta** |
| MPM client and sync, SMS through MPM | Implemented against MPM's source-code contracts and tested with mocked responses. **Not run against a live MPM instance**: verify response shapes on your MPM version |
| Mock messaging mode | Implemented (default) |
| Telemetry ingestion and detection for MPM meters | Implemented. **No telemetry producer exists yet** in MPM |
| Native MPM plugin (PHP) | Pending, by design (see section 2) |
