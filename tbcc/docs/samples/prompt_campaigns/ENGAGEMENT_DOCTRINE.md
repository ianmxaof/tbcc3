# Prompt campaigns — engagement doctrine (TBCC)

Maximize **depth** (scroll, gate completion, return visits) without breaking placement law.

## Surface ladder

| Surface | Job | Link type | Copy shape |
| ------- | --- | --------- | ---------- |
| **X / Buffer** | Hook + philosophy + curiosity | **Clearnet** hub / bot (`@aofmainhub`, `@aof_lootgod_bot`) — **no LV** when `TBCC_X_USE_LINKVERTISE=0` | Quote → reframe → hub CTA |
| **Telegram** | Serial drops + one gate per message | **LV Text** slug OR channel gate — never both | `AOF PROMPT DROP` + teaser + single `Unlock prompt` |
| **Mainhub pin** | Top-of-funnel | Checkout pin separate from prompt arc | Don't stack checkout on same post as prompt drop |

## Serial arc rules (tapes / logs)

1. **Number everything** — Tape 01–05, Log 01–05. Completionists collect; lurkers FOMO mid-arc.
2. **Quote hook on X** — one line that stands alone in the timeline (no context required).
3. **Reframe in body** — one sentence that flips the obvious read (Jackal: cruelty ≠ point; He's Coming: logs ≠ erotica).
4. **Tease next drop** — end Telegram posts with "Tape 03 drops Thursday" (cadence in `rollout_day`).
5. **Filmstrip = hub moment** — post the 5× scroll once singles have aired; "full archive on the hub."
6. **LV gate = depth reward** — teaser on TG; full Gemini prompt behind one ad. X sends to hub, not the gate.

## Catalog JSON fields (v2)

Campaign-level:

- `style_anchors` — unified visual string appended to every `prompt_body` generation
- `negative_prompt` — model negatives (cartoon, glossy, wrong AR)
- `engagement.cadence_days` — default spacing between serial drops

Per item:

- `engagement.tape_number` / `episode`
- `engagement.narrative_tension` — one-line tension label for schedulers
- `engagement.quote_hook` — X-first line
- `engagement.x_copy` — `{ hook, body, cta }` clearnet-safe
- `engagement.telegram_teaser` — short TG line (also in LV manifest)
- `engagement.tts_script` — optional VO hook (future pipeline; not required)
- `engagement.rollout_day` — suggested day offset from arc start

## TTS / audio (future)

`tts_script` is **optional metadata only** today. When wired:

- 15–30s cassette VO under filmstrip posts
- Same original-fiction boundary as visuals
- Export via `export_prompt_gate_lv_manifest.py --include-tts`

No auto-TTS in TBCC until operator picks a voice provider env.

## Anti-patterns

- LV on X + LV on Telegram for same SKU (cannibalization)
- Dumping all 5 prompts in one TG message (no serial tension)
- Quote hooks that require NSFW context to land on X
- Double affiliate wrap (LV on AdultForce / nodress links)

See also: `docs/AOF_PLACEMENT_DOCTRINE.md`, `prompt_gate_placement.py`.
