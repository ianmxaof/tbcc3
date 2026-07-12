# Perchance → TBCC post-gen sinks

Perchance replaces the **Gemini image model call**. Downstream contracts stay the same.

## Promo / X flywheel

```text
Perchance (tbcc-aof-gen or stock T2I)
  → TBCC Perchance Suite: apply job → generate
  → TBCC extension canvas capture (perchance-aware)
  → Gallery download / export
  → py -3.13 scripts/upload_x_promo_pool.py   # or generate_aof_promo_gemini.py --upload path for R2
  → app/data/aof_x_promo_image_pool.json
  → Buffer native refill / flywheel (image_url)
```

Operator tips:

1. Apply a **promo** job in the suite panel (Gemini-parity prompt).
2. Set shape closest to aspect hint (Portrait for 9:16 / 3:4).
3. Generate → use TBCC overlay/capture on winning canvases.
4. Upload winners into the X promo pool (existing R2/ImgBB scripts).

## Loot tier cards

```text
Perchance loot tier job
  → capture/download PNG
  → save as tbcc/backend/app/data/loot_tier_cards/tier-N.png
  → loot bot key-roll reveal (loot_tier_card_assets / loot_preview_delivery)
```

Use jobs labeled `Loot tier N` or preset `loot-tier-0N-*`.

## Gemini fallback

If QR / pills / tier text are mangled:

```powershell
cd tbcc\backend
py -3.13 scripts\generate_aof_promo_gemini.py --preset martyrs-ma07-10 --execute
py -3.13 scripts\generate_aof_loot_card_gemini.py --tier 7 --execute
```

Do not delete Gemini scripts; Perchance is primary $0 lane only.

## Regenerate prompt packs / jobs

```powershell
cd tbcc\backend
py -3.13 scripts\export_perchance_prompt_packs.py
cd ..\userscripts
npm run build
```

Then Tampermonkey → Check for updates (`npm run serve` on :8765).
