# TBCC local tools

## Tray supervisor (recommended for daily use)

```powershell
cd tbcc\tools
.\tbcc-supervisor.ps1
```

Right-click the notification-area icon:

- **Start full stack (cold)** - runs `start.ps1 -Full -WtTabs -NoOpen`
- **Restart service** - one click per service (Backend, Celery, etc.)
- **Restart API + Payment bot** - same as `restart-api-payment.ps1`

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
