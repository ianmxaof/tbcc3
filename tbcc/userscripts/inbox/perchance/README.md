# Perchance inbox (TBCC)

## Prompt packs

Generated from Gemini builders (source of truth remains backend JSON + layout locks):

```powershell
cd tbcc\backend
py -3.13 scripts\export_perchance_prompt_packs.py
```

- `prompt-packs/promo/*.txt` — promo presets + per-scene singles
- `prompt-packs/loot/*.txt` — loot presets + tier-01…10
- `tbcc-aof-gen.modelText.txt` — paste into Perchance edit (fork of t2i-framework)
- `packages/perchance-suite/data/jobs.json` — userscript job bar

## Operator fork

1. Open https://perchance.org/as8aqt61jr (or t2i-framework) → edit → duplicate.
2. Set private URL `tbcc-aof-gen`.
3. Replace lists with `tbcc-aof-gen.modelText.txt` (or keep stock UI and use perchance-suite job bar only).
4. Install `dist/perchance-suite.user.js` via Tampermonkey.

Gemini CLI stays fallback when layout/QR fidelity fails.
