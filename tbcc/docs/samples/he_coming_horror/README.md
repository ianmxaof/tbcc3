# HE'S COMING — horror promo prompt collection

Inspired by [Joel Farrelly / Thought Catalog (2014)](https://thoughtcatalog.com/joel-farrelly/2014/08/i-hacked-into-a-cam-girls-computer-and-what-i-found-truly-terrified-me/).

## Files

| Key | Scene | Prompt file |
|-----|-------|-------------|
| `he_coming_discovery` | Hidden tower / logs folder | `01_discovery.txt` |
| `he_coming_session_logs` | Dry session transcript night | `02_session_logs.txt` |
| `he_coming_window_feed` | Mask in window behind elliptical | `03_window_feed.txt` |
| `he_coming_closet_feed` | Closet cam / door banging | `04_closet_feed.txt` |
| `he_coming_backseat` | Voicemail / rearview mirror | `05_backseat.txt` |
| `he_coming_filmstrip_5x` | **Telegram scroll — all 5 stacked** | `06_filmstrip_5x_telegram.txt` |

### Telegram filmstrip

Paste `06_filmstrip_5x_telegram.txt` into Gemini for one tall 9:16 scroll post.

### LV manual manifest (all campaigns)

`docs/samples/prompt_campaigns/LV_MANUAL_MANIFEST.md` — titles, Text bodies, Telegram HTML with `PASTE_SLUG_HERE` placeholders.

Regenerate after catalog edits:

```powershell
cd tbcc\backend
py -3.13 scripts/export_prompt_gate_lv_manifest.py
```

## Gemini (image)

Paste any `*.txt` into Gemini image gen (9:16). Overlay pills/QR in Figma if baked text drifts.

## Linkvertise (gated prompt text)

Catalog JSON (import source of truth):

`backend/app/data/prompt_gate_catalog_he_coming_horror.json`

```powershell
cd tbcc\backend
py -3.13 scripts/provision_prompt_gates.py --import-json app/data/prompt_gate_catalog_he_coming_horror.json
py -3.13 scripts/provision_prompt_gates.py --dry-run
py -3.13 scripts/provision_prompt_gates.py --execute --headed
```

After `--execute`, `lv_url` values live in the `prompt_gate` table. Horror copy may hit Linkvertise guidelines — expect some rows to fail; tune body text if needed.

## X / social

Per placement doctrine: **no LV on X by default** — use generated art + clearnet CTA. LV gates are for Telegram prompt-drop lane.
