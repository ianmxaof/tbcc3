# Tampermonkey hygiene (Perchance + TBCC)

Use this when Perchance feels slow or “conflicts” with the TBCC extension.

## Leave alone

| Setting | Action | Why |
|---------|--------|-----|
| **Trash Mode** | Leave Enabled | Only affects deleted-script recovery, not page performance |
| **Logging Level** | Error | Fine |
| **Auto reload pages** | Off | Fine |
| **Config mode** | Advanced | Unlocks knobs; no runtime cost |

## Change for smoothness

| Setting | Action | Why |
|---------|--------|-----|
| **Debug scripts** | **Off** unless debugging | Extra instrumentation on every injection |
| **Show fixed source** | Off unless debugging | Editor/dashboard cost |

## Conflict triage

1. Brave profile with only **TBCC + Tampermonkey + TBCC Perchance Suite**.
2. Disable GreasyFork duplicates once `dist/perchance-suite.user.js` is installed (double-injection = real jank).
3. TM Errors like `Cannot create item with duplicate id` / `No tab with id` are usually context-menu lifecycle noise on reload — clear and reload once; not proof of TBCC conflict.
4. Red **“This page has errors”** on a Perchance page is the generator’s own error chip — fix lists/`modelText` first, not TM.
5. Optional: disable non-essential TBCC extension modules on `perchance.org` while iterating prompts.

## Install / update loop

```powershell
cd tbcc\userscripts
npm run build
npm run serve
```

Install or update from `http://127.0.0.1:8765/perchance-suite.user.js`. Keep serve running when checking for updates.
