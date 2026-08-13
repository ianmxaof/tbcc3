# Storage Hub Panel Manual

**For:** Storage & Bot Hangar forum lanes (`-1003812457581`)  
**Bot:** `@aof remixer` (Album Composer on island) — admin in the hangar group  
**Audience:** Operators with `TBCC_ADMIN_TELEGRAM_IDS` in `tbcc/.env`

Pin this manual **once per lane subtopic** (above the live control panel). The **lane panel** auto-reposts to the **bottom** of the thread after deposits; this manual stays pinned at the top for reference.

---

## 1. What the hangar does

| Surface | Job |
|--------|-----|
| **Lane subtopic** (e.g. AOF MILF/GILF STORAGE) | Warehouse for one content lane — forward/scrape media here first |
| **Lane control panel** | Deposit presets, auto-pipe, Loot preview, rebundle — **per lane** |
| **SENT VAULT** | Permanent archive copy after deposit (masters + emoji stamps) |
| **Loot Room subtopic** | Capped preview albums (not the full feed — schedulers own channels) |
| **Q&A master panel** | Fleet view + bulk deposit + global toggles |
| **Inbox intake panel** | Batch cadence for inbox quarantine → albums |

**Deposit flow (normal):**

1. Media lands in a lane subtopic (forward, scrape micro-pull, extension import).
2. Operator runs **Deposit** (panel button or `/deposit`).
3. Celery imports newest deduped items → **content pool** + copies to **SENT VAULT**.
4. Optional: **Loot preview** posts capped albums to the matching Loot Room subtopic.
5. **Channel schedulers** pull from the pool (album size 1 previews on public lanes).

---

## 2. Lane control panel (every content lane)

**Location:** Bottom of each mapped lane subtopic (e.g. MILF, AI, ASS).  
**Refresh:** `/hubpanel` in that topic, or tap **🔄 Refresh**.

### What the panel shows

- **Lane** — network key (`milf`, `ai`, …)
- **Deposit** — current count + media type + equivalent `/deposit` command
- **Auto-pipe** — auto-queue review when new media appears (per lane)
- **Loot preview** — whether this lane’s deposits also post to Loot Room
- **Loot subtopic** — live/dead link status for the Loot Room mirror
- **Composer status** — last SENT VAULT composer run (when applicable)

### Buttons

| Control | What it does |
|--------|----------------|
| **− / +** (count) | Adjust deposit batch size (50–200, steps of 50) |
| **− type / + type** | Cycle media filter: `video` → `image` → `both` |
| **📥 Deposit now** | Queue import for **this lane only** (uses panel presets) |
| **⏸ / ▶ Auto-pipe** | Toggle auto-pipe for **this lane only** |
| **⏸ / ▶ Loot preview** | Toggle Loot Room preview for **this lane only** |
| **🔗 Preview rebundle** | Dry-run: loose singles → albums in **this topic** |
| **✅ Rebundle (+partial)** | Queue rebundle job (partial albums OK; removes sources) |
| **🟡 Master panel** | Repost Q&A master panel at bottom of **this thread** |
| **🔄 Refresh** | Re-render panel with current Redis settings |
| **50 / 100** | Deposit count presets |

### Commands (same lane)

```text
/deposit 50 video      # import up to 50 new videos (newest-first, deduped)
/deposit 100 both       # 100 photos+videos
/depositstaged         # deposit only items you staged in this topic
/hubpanel               # refresh lane / vault / inbox / master panel
/review                 # quarantine bulk-approve panel
/rebundle               # preview loose → albums in this chat/topic
/rebundle go            # run rebundle (partial OK)
```

**Deposit ack:** Bot posts “Uploading media…” in the topic; message updates when Celery finishes.

---

## 3. Q&A master panel (fleet control)

**Canonical topic:** `Q&A | APPROVE / DENY | INTAKE`  
**Also works from:** Any hangar subtopic via **🟡 Master panel** on a lane panel.

**Refresh:** `/qapanel` in Q&A topic, or **🔄 Refresh** on the master panel.

### What it shows

- **Auto-pipe (all lanes)** — global + per-lane summary (▶ / ⏸ per lane in inventory)
- **Auto-approve** — deposit goes straight to **pool** vs **Q&A review** queue
- **Mode** — e.g. `Auto-pipe → pool` or `Auto-pipe → Q&A review`
- **Q&A waiting** — items in gatekeeper quarantine
- **Deposit preset** — shared count/type for master deposits
- **Lane inventory** — photos · videos · quarantine · buffer per lane (paged)
- **Intake scheduler** — global batch/interval status

### Buttons

| Control | What it does |
|--------|----------------|
| **🔄 Refresh** | Update counts and toggles |
| **📋 Review** | Open `/review` bulk-approve panel |
| **▶ Auto-pipe ALL** / **⏸ Auto-pipe ALL** | Turn auto-pipe on/off for **every content lane** |
| **✅ Auto-approve ON** / **⛔ Auto-approve OFF** | Pool direct vs quarantine review path |
| **− / +** (dep) | Adjust shared deposit count |
| **◀ type / type ▶** | Cycle deposit media type |
| **5 / 15 / 25 / 50** | Deposit count presets |
| **Lane emoji buttons** | Queue deposit for that lane (uses master preset + auto-approve mode) |
| **◀ Lanes / Lanes ▶** | Paginate lane inventory |
| **📤 Flush Q&A** | Force-flush quarantine buffers (all lanes) |
| **📦 Flush hub** | Queue hub album-buffer flush |
| **📥 Inbox now** | Run inbox intake deposit immediately |
| **🗄 Vault flush** | Post staged SENT VAULT emoji buffers |

**Auto-approve ON:** master lane deposits → pool (fast path).  
**Auto-approve OFF:** deposits → Q&A review cards → approve with `/review` or gatekeeper buttons.

---

## 4. SENT VAULT control panel

**Topic:** `SENT VAULT` (permanent master archive — do not bulk-delete).

| Control | What it does |
|--------|----------------|
| **Composer ON/OFF** | Run emoji-lane composer after deposits |
| **Loot preview ON/OFF** | Post preview albums to Loot Room from vault staging |
| **Erome ON/OFF** | Erome export side path |
| **Preview − / +** | Max Loot preview **albums per deposit** (0 = vault only) |
| **Album − / +** | Items per SENT VAULT album chunk (2–10) |
| **📦 Flush vault staging** | Post pending emoji-buffer albums |
| **🔄 Refresh** | Update panel text |

Vault items beyond the preview cap stay in SENT VAULT + pool for **channel schedulers**.

---

## 5. Inbox intake panel

**Topic:** `AOF INBOX` (forum) + optional `AOF INBOX #CHANNEL` shortcut.

Controls **global** inbox batch cadence (not per-lane):

- **Batch +5 / +10 / +25** — items per inbox run
- **Interval +5m / +15m / +30m** — schedule spacing
- **Album +1 / +2 / +3** — inbox quarantine album bundle size
- **▶ Run all due lanes** — force intake tick
- **▶ Inbox now** — immediate inbox deposit
- **📤 Flush inbox albums** / **📦 Flush hub albums** / **📦 Post vault staging**
- **▶ / ⏸ Auto-pipe** — global auto-pipe toggle

**Command:** `/intake` — same panel outside the pinned message.

---

## 6. Quarantine review (`/review`)

Use when **Auto-approve OFF** or gatekeeper quarantines bad fits.

```text
/review
```

- Shows waiting count by lane
- **Approve** → confirm → bulk approve to pool
- Per-lane filters available on the review keyboard

Review cards also post in the **Q&A** topic when items need eyes.

---

## 7. Auto-pipe (when to use)

| Setting | Behavior |
|--------|-----------|
| **Global ON** + **Lane ON** | New media in topic → debounced deposit/review queue |
| **Auto-approve ON** | Auto-pipe deposits → **pool** |
| **Auto-approve OFF** | Auto-pipe deposits → **Q&A review** |
| **Lane OFF** | Manual deposit only for that lane |

Debounce default ~30s (env `TBCC_STORAGE_AUTO_PIPE_DEBOUNCE_S`).

---

## 8. Rebundle (loose → albums)

When forwards arrive as **single messages** instead of Telegram albums:

1. **🔗 Preview rebundle** — alert with loose count → full/partial album plan
2. **✅ Rebundle (+partial)** — Celery packs loose media in **the same subtopic**
3. Or: `/rebundle` / `/rebundle go` anywhere remixer is admin in that topic

Photos and videos batch separately. Leftover singles stay loose until the next batch.

---

## 9. Operator checklist

### Daily

- [ ] Skim **Q&A master** inventory — quarantine not stalling
- [ ] Confirm thin lanes get a **Deposit** or master-panel lane button
- [ ] Loot Room previews firing when expected (lane **Loot preview ON**)

### After bulk import / scrape

- [ ] Run **Deposit** or tap lane on master panel
- [ ] Wait for Celery ack (“deposit complete”)
- [ ] **Refresh** lane panel — check composer line
- [ ] `/review` if auto-approve OFF

### After deploy / panel drift

```powershell
# From tbcc/backend on island or via docker exec api
python scripts/bootstrap_storage_hub_panels.py
# or
python scripts/repost_storage_hub_panels.py
# Pin lane manual (top of each subtopic)
python scripts/pin_storage_hub_lane_manuals.py
```

Or per topic: `/hubpanel`

### If deposit fails

- Remixer must be **admin** in Storage Hub
- Celery **worker** + Redis must be running (island stack)
- Telethon **admin_import** session logged in
- Check flood control — wait and retry

---

## 10. Pin copy (Telegram HTML)

Post once per lane subtopic with **@aof remixer** (Parse Mode: HTML). Replace `{LANE}` with the lane name (e.g. `MILF/GILF`).

```html
<b>📖 Storage Hub — lane manual</b>

<b>Lane:</b> AOF {LANE} STORAGE
<b>Bot:</b> @aof remixer (admin only)

<b>Quick start</b>
1. Forward / scrape media into this topic
2. Tap <b>📥 Deposit now</b> on the panel below (or <code>/deposit 50 video</code>)
3. Wait for “deposit complete” in this thread
4. Channel schedulers pull from the pool · Loot preview is capped

<b>Lane panel (bottom of thread)</b>
• <b>− / +</b> — deposit count (50–200)
• <b>− type / + type</b> — video / image / both
• <b>Auto-pipe</b> — auto-queue on new media (this lane)
• <b>Loot preview</b> — capped albums to Loot Room subtopic
• <b>Rebundle</b> — pack loose singles into albums here

<b>Commands</b>
<code>/deposit 50 video</code> · <code>/depositstaged</code>
<code>/hubpanel</code> · <code>/review</code>
<code>/rebundle</code> · <code>/rebundle go</code>

<b>Fleet control</b>
Open <b>Q&A | APPROVE / DENY | INTAKE</b> or tap <b>🟡 Master panel</b> on the lane panel.
Master panel: deposit any lane · auto-pipe ALL · auto-approve · flush buffers.

<b>Also see</b>
• <b>SENT VAULT</b> — permanent archive + composer
• <b>AOF INBOX</b> — batch intake panel (<code>/intake</code>)

<i>Panels repost to the bottom after deposits. This pin stays for reference.</i>
```

---

## 11. Related docs

- `docs/MEDIA_GATEKEEPER.md` — quarantine / approve / deny
- `docs/LOOT_LANE_ECONOMY.md` — Loot preview vs channel schedulers
- `backend/app/data/aof_storage_hub_map.py` — topic IDs and lane keys
- `docs/TELEGRAM_OPS.md` — Telethon sessions (`admin_import`, `admin_poster`)
