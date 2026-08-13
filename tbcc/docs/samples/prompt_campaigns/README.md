# Prompt campaigns — index

| File | Purpose |
|------|---------|
| `ENGAGEMENT_DOCTRINE.md` | TBCC rules: serial arcs, X vs Telegram, anti-patterns |
| `LV_MANUAL_MANIFEST.md` | Auto-generated LV titles, bodies, Telegram HTML |
| `SOCIAL_ROLLOUT.md` | Auto-generated X copy + rollout calendar + optional TTS |
| `lv_urls.template.json` | Fill slugs after manual LV create → re-export |

**Catalog source:** `backend/app/data/prompt_gate_catalog_*.json` (schema v2)

**Regenerate:**
```powershell
cd tbcc\backend
py -3.13 scripts/export_prompt_gate_lv_manifest.py --include-tts
py -3.13 scripts/export_prompt_gate_lv_manifest.py --write-catalog-urls ../docs/samples/prompt_campaigns/lv_urls.json
```

**Campaigns:**
- `he_coming_horror` — `docs/samples/he_coming_horror/`
- `jackal_tapes` — `docs/samples/jackal_tapes/`
