# SPICY REVEAL DROPS — companion promo + LV prompt packs

Owned-bot flywheel: **Gemini poster** (X/TG tease) → **Linkvertise Text gate** (prompt pack unlock) → **@aof_spicybot_bot** (trial → refer / Stars).

> SFW on posters and LV copy. Reveal-first language — no BUY on poster; monetization at bot paywall.

## Files

| Key | Poster | LV pack (unlock body) |
|-----|--------|------------------------|
| `spicy_reveal_01_trial_photo` | `01_trial_photo_tease_poster.txt` | `packs/01_trial_photo_reveal_pack.txt` |
| `spicy_reveal_02_chat_persona` | `02_chat_persona_poster.txt` | `packs/02_chat_persona_pack.txt` |
| `spicy_reveal_03_referral_earn` | `03_referral_earn_poster.txt` | `packs/03_referral_earn_pack.txt` |
| `spicy_reveal_04_scene_builder` | `04_scene_builder_poster.txt` | `packs/04_scene_builder_pack.txt` |
| `spicy_reveal_05_filmstrip_5x` | `05_filmstrip_5x_poster.txt` | `packs/05_full_bundle_pack.txt` |

Catalogs:

- `backend/app/data/creative_prompt_catalog/spicy_reveal_drops.json` — poster prompts (v3)
- `backend/app/data/prompt_gate_catalog_spicy_reveal_drops.json` — LV Text bodies (packs)

## Generate Drop 01 poster

```powershell
cd tbcc\backend
py -3.13 -c "
from pathlib import Path
from app.utils.load_tbcc_dotenv import load_tbcc_dotenv
load_tbcc_dotenv()
from app.services.creative_prompt_catalog import load_catalog_file, build_variation_prompt
from app.services.gemini_promo_generate import generate_image_bytes
root = Path('..')
cat = load_catalog_file(root / 'backend/app/data/creative_prompt_catalog/spicy_reveal_drops.json')
prompt = build_variation_prompt(cat, cat.variations[0])
out = root / 'docs/samples/spicy_reveal_drops/images/01_trial_photo_tease.png'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(generate_image_bytes(prompt=prompt, aspect_ratio='9:16'))
print('saved', out)
"
```

## LV manifest + provision

```powershell
cd tbcc\backend
py -3.13 scripts/export_prompt_gate_lv_manifest.py
py -3.13 scripts/provision_prompt_gates.py --import-json app/data/prompt_gate_catalog_spicy_reveal_drops.json
py -3.13 scripts/provision_prompt_gates.py --dry-run
# py -3.13 scripts/provision_prompt_gates.py --execute --headed
```

Doctrine: `docs/samples/prompt_campaigns/ENGAGEMENT_DOCTRINE.md` — X clearnet to bot/hub; TG serial drops; one LV gate per message.
