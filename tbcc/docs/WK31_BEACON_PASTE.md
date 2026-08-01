# Paste wk31 Linkvertise beacons (automated)

**Do not hand-edit 15 LV rows.** Run Playwright retarget (same auth as pack provisioning):

```powershell
cd tbcc/backend
py -3.13 scripts/retarget_lv_gate_beacons.py --week wk31 --dry-run
py -3.13 scripts/retarget_lv_gate_beacons.py --week wk31 --execute --headed
```

Requires `backend/.linkvertise-auth.json` or Brave profile (`TBCC_BRAVE_PROFILE_NAME`). First run: use `--headed` and watch one gate; then run without `--limit`.

Manual fallback only if automation fails — table below.

Beacon format: `https://api.powercore.app/r/{week}-lv-{key}`

Run on island to re-print this table:

```bash
cd /opt/tbcc/backend && python scripts/seed_gate_beacons.py --week wk31
```

## wk31 paste table

| Gate key | Paste this beacon URL into Linkvertise destination |
|----------|-----------------------------------------------------|
| addlist | https://api.powercore.app/r/wk31-lv-addlist |
| abg | https://api.powercore.app/r/wk31-lv-abg |
| ai | https://api.powercore.app/r/wk31-lv-ai |
| ass | https://api.powercore.app/r/wk31-lv-ass |
| big_tits | https://api.powercore.app/r/wk31-lv-big_tits |
| blowjob | https://api.powercore.app/r/wk31-lv-blowjob |
| bop | https://api.powercore.app/r/wk31-lv-bop |
| goon | https://api.powercore.app/r/wk31-lv-goon |
| loot | https://api.powercore.app/r/wk31-lv-loot |
| lootgod | https://api.powercore.app/r/wk31-lv-lootgod |
| main_group | https://api.powercore.app/r/wk31-lv-main_group |
| mainhub | https://api.powercore.app/r/wk31-lv-mainhub |
| milf | https://api.powercore.app/r/wk31-lv-milf |
| packs | https://api.powercore.app/r/wk31-lv-packs |
| taboo | https://api.powercore.app/r/wk31-lv-taboo |
| voyeur | https://api.powercore.app/r/wk31-lv-voyeur |

Full gate URL mapping: `docs/GATE_LINK_AUDIT.md`.

## Watch attribution

Dashboard → **Analytics → Gate funnel** (island API target), or:

```powershell
curl -fsS -H "X-TBCC-Internal-Key: <from tbcc/.env>" "https://api.powercore.app/analytics/gate-funnel?days=7"
```

After ~1 week of live beacon traffic, enable daily pull on island: `TBCC_LOOT_DAILY_PULL_ENABLED=1`.
