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

**Services** — toggle any process on/off; Ctrl+click to restart. Full catalog (spicy bot, remixer, LLM chat, etc.) even on lean.

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
