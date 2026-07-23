# Fork `tbcc-aof-gen` on Perchance (operator)

Agent cannot create your Perchance account generator. Paste the repo artifact.

## Steps

1. Log into Perchance → open https://perchance.org/as8aqt61jr **or** https://perchance.org/ai-text-to-image-generator → **edit**.
2. Duplicate / save your own copy. Set private URL to `tbcc-aof-gen` (lowercase, hyphens).
3. Replace list code with contents of [`tbcc-aof-gen.modelText.txt`](../inbox/perchance/tbcc-aof-gen.modelText.txt).
4. Save. Open `https://perchance.org/tbcc-aof-gen`.
5. Use **TBCC Importer extension** (Perchance suite) — Loot Cards FAB + job bar. No Tampermonkey.

Regenerate modelText after preset changes:

```powershell
cd tbcc\backend
py -3.13 scripts\export_perchance_prompt_packs.py
```

Rebuild extension suite:

```powershell
cd tbcc\userscripts
npm run build
```

Reload the extension in Chrome.

## Why both modelText + extension suite?

- `modelText` = native Perchance job dropdown (works without any script).
- Extension suite = Loot God Card Lab, lean page (no chat/gallery), full multiline Gemini-parity prompts, capture metadata.
- Gemini CLI stays fallback when layout/QR text fidelity fails.

## Lean page (no chat / public gallery / blur)

`tbcc-aof-gen.modelText.txt` sets `socialFeatures = disabled` (plus comments/gallery off).

If you still see forum tabs or blurred “show image” tiles, the extension **Lean page** flag (on by default) hides them and auto-uncensors overlays.

## Loot God cards

See [`LOOT_GOD_PROMPT_LAB.md`](LOOT_GOD_PROMPT_LAB.md). This is **not headless** — generate in the browser, save as `tier-N.png`.
