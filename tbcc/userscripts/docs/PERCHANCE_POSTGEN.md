# Perchance → TBCC post-gen sinks

Perchance replaces the **Gemini image model call**. Downstream contracts stay the same.

**Delivery:** TBCC Chrome extension content script (`perchance-suite.bundle.js`). No Tampermonkey.

## Promo / X flywheel

```text
Perchance (tbcc-aof-gen or stock T2I)
  → TBCC extension Perchance suite: apply job → generate
    → TBCC page overlay / capture (perchance-aware)
    → Gallery download / export
    → py -3.13 scripts/upload_x_promo_pool.py
    → app/data/aof_x_promo_image_pool.json
    → Buffer native refill / flywheel (image_url)
```

Operator tips:

1. Reload TBCC extension after `npm run build` in `tbcc/userscripts`.
2. Apply a **promo** job in the suite jobs panel (Gemini-parity prompt), or use Card Lab for loot.
3. Set shape closest to aspect hint (Portrait for 9:16 / 3:4; Square for loot 1:1).
4. Generate → capture winners → upload into the X promo pool.

## Loot tier cards (Loot God Card Lab)

```text
Perchance + FAB "Loot Cards"
  → Compose + Apply (border + hyperreal primer + subject + Δ)
  → generate / capture PNG
  → save as tbcc/backend/app/data/loot_tier_cards/tier-N.png
  → loot bot key-roll reveal
```

See [`LOOT_GOD_PROMPT_LAB.md`](LOOT_GOD_PROMPT_LAB.md).

Legacy SFW/tease jobs labeled `Loot tier N` still exist in the jobs panel if you need sealed-pack centers.

## Gemini fallback

If QR / pills / tier text are mangled:

```powershell
cd tbcc\backend
py -3.13 scripts\generate_aof_promo_gemini.py --preset martyrs-ma07-10 --execute
py -3.13 scripts\generate_aof_loot_card_gemini.py --tier 7 --execute
```

Do not delete Gemini scripts; Perchance is primary $0 lane only.

## Regenerate prompt packs / rebuild extension suite

```powershell
cd tbcc\backend
py -3.13 scripts\export_perchance_prompt_packs.py
cd ..\userscripts
npm run build
```

Then **reload the TBCC extension** in Chrome.
