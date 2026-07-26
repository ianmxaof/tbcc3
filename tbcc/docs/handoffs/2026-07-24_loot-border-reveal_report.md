# Claude Code — Loot Border Reveal — Reverse Report

**Branch:** `fix/loot-border-reveal`
**Island:** `root@5.161.53.91` (`infra-api-1`, `infra-loot_bot-1`)
**Note:** filename is `2026-07-24_loot-border-reveal_report.md` per the operative paste / `/cc-report`. The phase2-plus doc references `..._loot-border-animations_report.md` — reconcile to one going forward.

---

## Phase 1 (ops) — DONE, but READ THE HEADLINE

### ⚠️ Headline: borders are NOT live yet. The static-dud is NOT fixed.

Flipping the flag was **necessary but not sufficient**. Production still renders the old static path. Full activation is blocked on the **border code + assets being persistently deployed to the island** — which your own structure puts at **Phase 4**, and which must now carry the **single-clip** refactor (Cursor's Lane B), not the deprecated pair-model.

### What was done (durable)

- ✅ `TBCC_LOOT_BORDER_REVEAL=1` confirmed in island `/opt/tbcc/infra/.env.revenue-island` (line 44 — was already appended; env file size 7611 B, not corrupted).
- ✅ Recreated `infra-api-1` and `infra-loot_bot-1` (`up -d --pull never --force-recreate`, no rebuild). Both Started; `/health` → `{"status":"ok",...}`.
- ✅ Env var now live in containers: `env | grep TBCC_LOOT_BORDER_REVEAL` → `TBCC_LOOT_BORDER_REVEAL=1`.
- ✅ Drift-proofing (local repo): added `TBCC_LOOT_BORDER_REVEAL=1` (+ `TBCC_LOOT_REVEAL_VIDEO=1`) to `$forceKeep` in `seed-island-env-from-home.ps1`, so the exact env-drift that caused this (`.example` advanced, real env didn't) cannot recur on re-seed. `env.revenue-island.example` already documented the var.

### The catch-22 we hit (and why it's inherent, not a mistake)

The previously-working border code on the island was a **hot-patch** (`docker cp` into the running container), **not baked into the image** (`ghcr.io/ianmxaof/tbcc-worker:latest`). A running container's env is fixed at start — only `up`/recreate re-reads `env_file`; `restart` does not. So loading the flag **required** a recreate, and recreate **wipes** `docker cp` patches. "Load the flag with no rebuild" + "border code is a hot-patch" is a contradiction in the Phase-1 spec as written — it cannot light up borders by itself.

Post-recreate container state:
- `import app.services.loot_border_reveal` → `ModuleNotFoundError` (module gone with the patch).
- Image's `loot_preview_delivery.py` has **0** references to `loot_border_reveal` → it never imports the module and never reads the flag.

### Is production broken? No.

- Before: flag OFF + dormant hot-patched code → static path.
- After: flag ON + no border code → old image delivery ignores the flag → **same static path**.
- Borders were never live (flag was off the whole time), so **nothing regressed**. `/health` OK; startup didn't crash (proof the image predates border code — it neither imports the module nor reads the flag). No real roll was burned to re-confirm.

### Version / multi-agent state (important)

- **Local repo** `loot_border_reveal.py` = **431 lines**, now has single-clip `pick_border_clip()` + a compat `pick_border_pair()` — Cursor's Lane B single-clip refactor is **landing live in the working copy right now**.
- **Island `backend-src`** = **403 lines**, pair-only (older); container image = no border module (oldest).
- Per `2026-07-24_loot-border-animations-phase2-plus.md`: stasis deprecated, single clips from `borders/open/` via `pick_border_clip()`, island assets are **Phase 4**.

---

## DECISION NEEDED (STOP for ACK)

**How do you want the border code + assets deployed to the island?**

**A — HOLD (recommended).** Do the island code+assets at **Phase 4** with the **final single-clip build**, baked into the image or volume-mounted so it survives recreate. Rationale: hot-patching the deprecated pair-model now is throwaway (single-clip replaces it), non-persistent (next recreate wipes it again), and deploying stale code mid-refactor muddies the multi-agent state. Leave the flag ON (correct target state).

**B — INTERIM (only if you want borders live *now*, accepting it's throwaway).** No-rebuild path: [recreate already done] → `docker cp` the island's **own self-consistent `backend-src` pair set** (border modules + border-aware `loot_preview_delivery.py`/`loot_tier_card_assets.py` + `borders/open` **and** `borders/stasis` clips) into both containers → `docker restart` both (**NOT** recreate) → verify module present + one test encode. Uses backend-src's pair code, **not** the half-refactored local 431-line single-clip.

Flag stays ON either way.

---

## Guardrails observed

- Did **not** run `deploy-island-live.ps1` (rebuilds from stale pair-model `backend-src` + runs all seeds = OOM path).
- Committed selectively: `seed-island-env-from-home.ps1` + this report only. Did **not** `git add` the border `*.py` (Cursor editing live — would snapshot a half-refactor). `infra/.env.revenue-island` confirmed gitignored (holds real tokens).
- `/usage` could not be run from here — operator should check the quota window manually.

## Fast-path prep for Phase 4 (do once Cursor signals Phase 2/3 done)

- Confirm local tests pass on the single-clip code.
- Confirm `app/data/loot_tier_cards/borders/open/` actually holds the imported single clips.
- Then Phase 4 (bake/volume-mount + `docker cp` assets) is quick on ACK.
