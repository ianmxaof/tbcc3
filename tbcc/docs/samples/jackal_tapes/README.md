# JACKAL TAPES — Far Cry 2 narrative promo collection

Inspired by the **Jackal Tapes** collectible interviews (Reuben Oluwagembi ↔ The Jackal). Themes: moral ambiguity, war-as-home philosophy, dignity vs brutality, mercenary complicity.

> Fan/promo creative — not official Ubisoft assets. Prompts use original visuals; no game character likeness.

## Quote anchor

> "You can't break a man the way you break a dog or a horse. The harder you beat a man, the taller he stands."

## Files

| Key | Scene | Prompt file |
|-----|-------|-------------|
| `jackal_tapes_interview` | Betacam interview / Tape 01 | `01_the_interview.txt` |
| `jackal_tapes_break_the_man` | Break the mind, not the body | `02_break_the_man.txt` |
| `jackal_tapes_war_is_home` | Convoy / profit cycle | `03_war_is_home.txt` |
| `jackal_tapes_mikes_bar` | Return tapes to Reuben | `04_mikes_bar.txt` |
| `jackal_tapes_monster_display` | Brutality as posture | `05_monster_display.txt` |
| `jackal_tapes_filmstrip_5x` | **Telegram scroll — all 5 stacked** | `06_filmstrip_5x_telegram.txt` |

### Telegram filmstrip (recommended)

Paste `06_filmstrip_5x_telegram.txt` into Gemini for **one** tall 9:16 scroll post with all five tapes. If baked text drifts, generate clean panels and stack in Figma.

Regenerate after catalog edits:

```powershell
cd tbcc\backend
py -3.13 scripts/export_prompt_gate_lv_manifest.py
```

## LV import

`backend/app/data/prompt_gate_catalog_jackal_tapes.json`

```powershell
cd tbcc\backend
py -3.13 scripts/provision_prompt_gates.py --import-json app/data/prompt_gate_catalog_jackal_tapes.json
py -3.13 scripts/provision_prompt_gates.py --execute --headed
```
