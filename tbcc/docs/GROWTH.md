# Growth & referrals — what each field means

## Current test setup (filled in `tbcc/.env`)

| Setting | Value | Why |
|--------|--------|-----|
| **Landing chat id** | `7787282561` | Same as `ADMIN_TELEGRAM_ID`. The bot sends the **daily bulletin** here as a **private message** so you can verify copy and timing without a public channel yet. |
| **Milestone progress chat id** | `7787282561` | The **“X / Y subscribers…”** line after new subscriptions is sent here (your DM) for testing. |
| **Send hour (UTC)** | `14` | Bulletin task runs every hour; only **14:00 UTC** actually sends. |
| **Bot username** | `aofsubscriptions_bot` | Printed as `t.me/aofsubscriptions_bot` in the bulletin. |
| **Intro** | One line in `TBCC_LANDING_BULLETIN_INTRO` | Custom opener; milestone line and bot link still append. |
| **Referrals** | invite link, AOF, 7 days, community | Bot copy for `/referral` and deep links. |

**Requirement:** You must have tapped **/start** on `aofsubscriptions_bot` so it can DM you.

## Production swap

Replace **both** numeric user ids with:

- **Landing:** your real **landing** chat — public `@YourChannel` or `-100…` (not the `t.me/+hash` invite slug).
- **Milestone (optional):** often the **main group** `-100…` so members see FOMO; can match landing or stay in DM.

Then **Save** in **Dashboard → Growth** if you use overrides, or edit `.env` and restart workers.

## Manual bulletin test

From `tbcc/backend` with venv active:

```bash
python -m celery -A app.workers.celery_app call app.workers.landing_bulletin_worker.send_aof_landing_bulletin
```

By default the task **only sends during your configured UTC hour** — otherwise it exits quietly. To **test immediately**, use **Dashboard → Growth → Post now** (queues the same forced task), or from `tbcc/backend`:

```bash
python scripts/trigger_landing_bulletin.py --force
```

Or (from `tbcc/backend`):

```bash
python -m celery -A app.workers.celery_app call app.workers.landing_bulletin_worker.send_aof_landing_bulletin --kwargs "{\"force\": true}"
```

(Use **cmd.exe** for the `celery call` line if PowerShell mangles JSON.) **Restart the Celery worker** after code pulls so it runs the latest task code.
