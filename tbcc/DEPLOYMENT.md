# TBCC Production Deployment

## Environment variables (no .env in version control)

Use environment variables or a secrets manager. Never commit `.env` with real values.

| Variable | Description |
|----------|-------------|
| `API_ID` | Telegram API ID (my.telegram.org) |
| `API_HASH` | Telegram API hash |
| `ADMIN_TELEGRAM_ID` | Your Telegram user ID (for admin bot) |
| `BOT_TOKEN` | Payment bot token from @BotFather |
| `DATABASE_URL` | PostgreSQL or SQLite connection string |
| `REDIS_URL` | Redis connection (e.g. `redis://redis:6379/0`) |
| `TBCC_API_URL` | Backend URL (for payment bot when not localhost) |

## Docker Compose (infra/)

```bash
cd tbcc/infra
# Create .env with API_ID, API_HASH, ADMIN_TELEGRAM_ID, BOT_TOKEN
docker compose up -d
```

Services: postgres, redis, api, worker_scrape, worker_post, worker_subscription, celery_beat.

## Payment bot (separate process)

The payment bot must run as a long-lived process. It connects to Telegram and the backend API.

```bash
cd tbcc/backend
TBCC_API_URL=https://your-backend.example.com python -m bots.payment_bot
```

Use a process manager (systemd, PM2, Docker) to keep it running.

## HTTPS

- Put the backend behind a reverse proxy (nginx, Caddy, Traefik) with TLS.
- Set `TBCC_API_URL` to the HTTPS backend URL when running the payment bot remotely.
- The dashboard (Vite dev) proxies `/api` to the backend; in production, build the dashboard and serve it from the same origin or configure CORS.

## Celery Beat

Runs scheduled tasks:
- **schedule-posts**: every 5 minutes
- **cleanup-expired-subscriptions**: daily at midnight UTC

Ensure only one Celery Beat instance runs (single scheduler).

## Process managers

### systemd (Linux)

Example unit for the payment bot:

```ini
[Unit]
Description=TBCC Payment Bot
After=network.target

[Service]
Type=simple
User=tbcc
WorkingDirectory=/opt/tbcc/backend
Environment="TBCC_API_URL=http://localhost:8000"
EnvironmentFile=/opt/tbcc/.env
ExecStart=/usr/bin/python -m bots.payment_bot
Restart=always

[Install]
WantedBy=multi-user.target
```

### PM2 (Node.js)

```bash
pm2 start "python -m bots.payment_bot" --name tbcc-payment --cwd tbcc/backend --interpreter python
```
