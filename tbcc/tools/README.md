# TBCC local tools

## Tray supervisor (recommended for daily use)

```powershell
cd tbcc\tools
.\tbcc-supervisor.ps1
```

Right-click the notification-area icon:

- **Start full stack (cold)** - runs `start.ps1 -Full -WtTabs -NoOpen`
- **Restart full stack (stop all + cold start)** - kills prior TBCC Windows Terminal tabs, Backend, Celery, bots started by the stack, then cold-starts (use after `database is locked` / duplicate :8000)
- **Telegram session (admin.session)** submenu:
  - **Stop scraper + admin bots** - kills standalone `scraper_bot` / `admin_bot` (not managed as stack tabs; they fight the API on `admin.session`)
  - **Restart Celery worker** - clears stuck import/Telegram tasks without restarting the API
- **Services** — Extensity-style toggles: **white** = enabled, **gray** = disabled (no `[up]`/`[down]`). Click to enable/disable; **Ctrl+click** to restart. Disabled services are skipped on cold start. State saved in `.tbcc-run/service-toggles.json`.
- **Cleanup orphan API workers (port 8000)** - when multiple uvicorn children are listening
- **Open system health (browser)** - `GET /health/system` shows scraper/admin_bot conflicts and shared-session warnings
- **Restart API + Payment bot** - same as `restart-api-payment.ps1`

### Session lock recovery (typical order)

1. **Restart full stack (stop all + cold start)** — one action; closes duplicate `TBCC-*` terminal tabs and stack processes.
2. **Telegram session → Stop scraper + admin bots** — if you ran scraper/admin manually outside the stack.
3. **Telegram session → Restart Celery** — if error hub still shows import/Telethon noise after (1).
4. **Open system health** — confirm no `telethon_shared_session` / `scraper_running` warnings.
5. One-time in `tbcc/.env`: `TBCC_POSTER_TELEGRAM_SESSION=admin_poster` and `TBCC_POSTER_AUTO_COPY_ADMIN_SESSION=1`, then **Restart full stack** again.

See `docs/TELEGRAM_OPS.md` for `.env` details and avoiding heavy imports while the media library warms thumbnails.

Optional logon shortcut:

```powershell
.\register-supervisor-autostart.ps1
```

## Extension cold start (HTTP)

Leave this running for **Launch full stack** in the browser extension:

```powershell
.\tbcc-launch-daemon.ps1
```

Listens on `http://127.0.0.1:8765`:

- `POST /launch-full` - cold start (`start.ps1 -Full -WtTabs`)
- `POST /launch-supervisor` - tray icon (restart menu)

Extension sidebar (Tools / popup): **Start tray supervisor** and **Launch full stack (cold)**.
