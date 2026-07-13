# Fork `tbcc-aof-gen` on Perchance (operator)

Agent cannot create your Perchance account generator. Paste the repo artifact.

## Steps

1. Log into Perchance → open https://perchance.org/as8aqt61jr **or** https://perchance.org/ai-text-to-image-generator → **edit**.
2. Duplicate / save your own copy. Set private URL to `tbcc-aof-gen` (lowercase, hyphens).
3. Replace list code with contents of [`tbcc-aof-gen.modelText.txt`](../inbox/perchance/tbcc-aof-gen.modelText.txt).
4. Save. Open `https://perchance.org/tbcc-aof-gen`.
5. Install TBCC Perchance Suite (`dist/perchance-suite.user.js`) — job bar has full multiline Gemini-parity prompts even if `modelText` options are single-line.

Regenerate modelText after preset changes:

```powershell
cd tbcc\backend
py -3.13 scripts\export_perchance_prompt_packs.py
```

## Why both modelText + userscript?

- `modelText` = native Perchance job dropdown (works without TM).
- Userscript jobs panel = full multiline prompts + history + TBCC capture metadata (preferred for ops).
