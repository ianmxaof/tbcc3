# TBCC local tools

## Tray supervisor (recommended for daily use)

```powershell
cd tbcc\tools
.\tbcc-supervisor.ps1
```

Right-click the notification-area icon:

**Stack**
- **Start — lean** — fresh launch with fewer auto-started bots; saves lean as default
- **Start — full** — fresh launch with all default bots and enrichment sidecars
- **Restart all** — stop everything, then cold-start using your saved default
- **Stop all** — close all TBCC terminal tabs and processes

**Services** — each row is one process. Hover for plain-English "what it does" and "when to restart". Click toggles; Ctrl+click restarts. After API/`.env` changes restart **Backend API** (plus Beat timer / due-post / Telegram-send workers if those changed too).

**Advanced** — troubleshooting (session fixes, focus mode, port 8000 cleanup), open dashboard/health/logs/panel.

Double-click the tray icon for the live supervisor panel.

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
