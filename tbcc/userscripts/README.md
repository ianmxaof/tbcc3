# TBCC Userscripts

CI-built Tampermonkey suites. **FetLife** and **Perchance** suites ship from this tree.

## Layout

```text
packages/
  shared/              # storage, flags, SPA, observer bus, settings shell
  fetlife-suite/       # FetLife features
  perchance-suite/     # Perchance ads + Gemini-parity jobs + TBCC capture bridge
inbox/<site>/          # drop candidate scripts before merging
dist/*.user.js         # built artifacts (install these in Tampermonkey)
docs/                  # TM hygiene, Perchance fork + post-gen sinks
```

## Commands

```powershell
cd tbcc\userscripts
npm run ci      # lint headers + unit tests + build
npm run build   # write dist/*.user.js (all suites)
```

Regenerate Perchance Gemini prompt packs (from `tbcc/backend`):

```powershell
py -3.13 scripts\export_perchance_prompt_packs.py
```

## Install (FetLife)

**Skip “Track from disk” on Brave/Chrome** — it often does nothing even with file-URL access on.

### Reliable local update loop

1. Build (bumps patch + writes dist):
   ```powershell
   cd tbcc\userscripts
   npm run build
   ```
2. Serve dist (leave this terminal open):
   ```powershell
   npm run serve
   ```
3. **First install:** open `http://127.0.0.1:8765/fetlife-suite.user.js` in Brave → Tampermonkey install prompt.  
   Or drag `dist\fetlife-suite.user.js` onto the Tampermonkey dashboard.
4. Confirm script **Settings → Update URL** is:
   `http://127.0.0.1:8765/fetlife-suite.user.js`
5. After each rebuild: Tampermonkey → script → **Check for updates** (or wait for Check Interval).  
   Keep `npm run serve` running when you check.

Also set Tampermonkey global **Check Interval** to something other than Never (e.g. Every 6 Hours).

### Feature flags (defaults)

| Flag | Default | Source |
|------|---------|--------|
| `homeFeed` | on | FetLife Suite – Home Feed (RYSTA, MIT) |
| `storyFilter` | on | client-side hide/show (local) |
| `mute` | on | fetlife-mute-button (brighid) |
| `newestDiscussions` | on | Newest Discussions redirect |
| `loginRedirect` | on | `/` + `/home` → San Jose kinksters |
| `genderFilter` | on | Hide Male (M) list cards |
| `autoFollow` | on | Follow + scroll loop; opens on `/kinksters` |

Toggle via the right-edge **FL** chevron overlay (paginated: Features / Auto-follow / Gender / Stories / Mute).

## Install (Perchance)

Same serve loop; install `http://127.0.0.1:8765/perchance-suite.user.js`.

| Flag | Default | Role |
|------|---------|------|
| `adsBypass` | on | Fuck Ads port |
| `lazyQueue` | on | Staggered iframe activation |
| `jobsPanel` | on | Gemini-parity promo/loot presets |
| `promptBridge` | on | `window.__tbccPerchanceLastPrompt` for TBCC capture |
| `promptHistory` | on | Reuse recent prompts |
| `sendWinners` | on | Alt-click picks + tag for capture |

Docs: [TAMPERMONKEY_HYGIENE.md](docs/TAMPERMONKEY_HYGIENE.md), [PERCHANCE_FORK.md](docs/PERCHANCE_FORK.md), [PERCHANCE_POSTGEN.md](docs/PERCHANCE_POSTGEN.md).

Disable GreasyFork duplicates of Fuck Ads / Prompt History once this suite is installed.

## Adding a new script later

1. Drop into `inbox/fetlife/` (or `inbox/<site>/`)
2. Decide keep / merge / drop / TBCC-port
3. Add `packages/<suite>/features/<name>.js` + flag (default **off**)
4. List the file in `packages/<suite>/manifest.json`
5. PR → `npm run ci`

## TBCC bridge

Pure logic that may move into the Chrome extension should stay free of DOM (see `story-filter-core.mjs`). DOM glue stays in `features/*`.
