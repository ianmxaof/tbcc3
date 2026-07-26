# TBCC CI merge gates (draft)

Changelog: Initial draft — required checks, branch protection, backlog clear vs home-bandwidth myth.

## Applied (2026-07-13)

- [x] `tbcc-pr-gate.yml` on `main` (via PR #4 squash)
- [x] Ruleset **Main — TBCC PR gate** (`id=18892202`) — require check `TBCC PR gate`, no force-push
- [x] Classic branch protection on `main` also requires `TBCC PR gate` (admins enforced)
- [x] PR #4 merged: https://github.com/ianmxaof/tbcc3/pull/4 → `558d491`
- [ ] `alembic upgrade head` (092) — **blocked**: Postgres localhost:5432 connection refused (stack down)
- [ ] Tray services restart — operator choice; status was **0/12 up** after merge (good for WAN)

WIP from pre-merge dirty tree is in git stash: `wip-before-pr4-squash-merge` (FetLife 1.7 FLConsole etc. not all in the squash).

---

## Goal

Every PR into `main` must pass automated tests **before** merge. Prefer GitHub Actions (cheap, deterministic) as the merge gate; Cursor Bugbot / Cloud Agents are optional review layers, not the merge button.

## Bandwidth first (clear the backlog)

**An open GitHub PR does not eat home bandwidth.** Remote clones, Actions, and the PR page live on GitHub’s side.

Home WAN pressure almost always comes from **local runtime**, not unmerged commits:

| Likely | Unlikely |
|--------|----------|
| Tray: payment/loot/secretary + Telethon scrapes | Open PR #4 sitting on GitHub |
| Celery/beat importing/mirroring media | `feat/loot-key-roll` existing as a branch tip |
| Docker/`docker compose pull`, GHCR image pulls | Squash-merge button unused |
| R2 / Mega / CDN downloads, Buffer publishes | Cursor chat history |
| Cursor indexing + OneDrive/Dropbox syncing the repo | |

Clearing the 300-file backlog **is still right** (merge risk + ops confusion). Do it because the branch is huge and hard to reason about — not because GitHub is saturating your pipe. To free bandwidth: tray Services → pause scrapers / heavy workers; check `GET /ops/stack-status` for N/M running.

## What you already have

| Workflow | Trigger | Role |
|----------|---------|------|
| `tbcc-backend-tests.yml` | PR/push touching `tbcc/backend/**` | Lean pytest gate + full suite non-blocking |
| `tbcc-userscripts.yml` | PR/push touching `tbcc/userscripts/**` | `npm run ci` |
| `tbcc-remote-worker-ghcr.yml` | push `main` (paths) | Build/push worker image — **not** a PR gate |

Gaps today:

1. Extension-only PRs (`tbcc/extension/**`) run **no** CI.
2. Backend gate only covers growth/ops four files; loot/sale/scrape from PR #4 are **not** required.
3. Branch protection likely not requiring any check as a hard block (optional on personal repos).
4. No single “merge summary” check name for Rulesets to pin.

## Recommended gates (phased)

### Phase A — before/alongside clearing PR #4 (NOW)

1. Squash-or-merge `feat/loot-key-roll` → `main` after smoke (migration 092 + tray restart). Clearing the backlog unblocks cognition and local dirty-tree pain; it does not by itself fix WAN.
2. Enable **Ruleset / branch protection** on `main` (below).
3. Land `tbcc-pr-gate.yml` (companion draft) so **every** PR to `main` produces a stable check name: `TBCC PR gate`.

### Phase B — tighten required pytest (HIGH)

Expand the required backend job to include TEST_MAP rows for surfaces in the mega-PR:

- `tests/test_sale_public_announce.py`
- `tests/test_loot_*.py` (or a short allowlist)
- `tests/test_scrape_transport.py`, `tests/test_scrape_tag_pool_map.py`
- Keep full `tests/` as `continue-on-error: true` until green.

### Phase C — agents (OPTIONAL, cost gate)

| Layer | When | Bill |
|-------|------|------|
| GitHub Actions | Every PR | Free minutes / Actions quota |
| Cursor Bugbot | Explicit “review this PR” | Pro/API pool |
| Cloud Agent | Rare grind only (hard gate) | Max Mode — avoid as default merge agent |

Do **not** auto-spawn Cloud Agents on every push. Auto CI = Actions. AI review = on-demand.

---

## Branch protection / Ruleset (apply in GitHub UI)

Repo → **Settings → Rules → Rulesets → New branch ruleset**

| Setting | Value |
|---------|--------|
| Enforcement | Active |
| Target | `main` (include default branch) |
| Restrict deletions | On |
| Block force pushes | On |
| Require a pull request before merging | On (1 approval optional for solo) |
| Require status checks to pass | On |
| Required checks | `TBCC PR gate` (from `tbcc-pr-gate.yml`) |
| Require conversation resolution | Optional |
| Require linear history | Optional (conflicts with merge commits; OK with squash) |
| Require deployments | Off |

Classic **Branch protection** equivalent: require status checks → add `TBCC PR gate`.

CLI sketch (after workflow exists on `main`):

```powershell
# Inspect existing rulesets
gh api repos/:owner/:repo/rulesets

# Create is API-heavy; UI is faster for first setup.
# After first run of tbcc-pr-gate on a PR, the check name appears in the required-checks picker.
```

---

## Workflow design (`tbcc-pr-gate.yml`)

See `.github/workflows/tbcc-pr-gate.yml` (draft companion).

Behavior:

- Triggers on `pull_request` → `main` (all paths).
- Parallel path-filtered jobs: `backend`, `userscripts`, `extension-manifest` (lightweight).
- Final job `gate` with `needs:` + `if: always()` fails if any required job failed/skipped incorrectly.
- That final job’s name is what Rulesets pin: **`TBCC PR gate`**.

Also bump `tbcc-backend-tests.yml` required pytest list (Phase B) in the same PR as the gate, or immediately after mega-merge.

---

## Pre-merge checklist for PR #4 (operational)

```powershell
# On merge machine / after pull main:
cd tbcc/backend
alembic upgrade head   # includes 092_scrape_channel_metrics

# Tray: restart services you care about; confirm
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\tbcc-stack-cli.ps1 -Action Status
# or GET /ops/stack-status
```

Smoke: loot key roll once; one scrape transport row; extension reload if you ship extension bits.

---

## Anti-patterns

- Requiring Cloud Agent / Bugbot as a merge check (cost + flaky).
- Requiring GHCR image build on every PR (slow, burn minutes).
- Path filters so narrow that a docs+backend+extension PR skips all jobs but still “passes” — the summary `gate` job must fail if **no** path matched and changes aren’t docs-only (or allow docs-only explicitly).

---

## Done criteria for this draft

- [ ] `tbcc-pr-gate.yml` on a branch and green on a sample PR
- [ ] Ruleset on `main` requiring `TBCC PR gate`
- [ ] PR #4 merged or split; migration 092 applied
- [ ] Phase B pytest allowlist expanded (separate commit OK)
