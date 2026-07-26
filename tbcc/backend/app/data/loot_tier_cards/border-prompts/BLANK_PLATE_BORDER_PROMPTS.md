# AOF LOOT — blank-plate border generation kit

Goal: generate loot-card **border frames only** that our code composites over an NSFW
center still and stamps with dynamic TIER / name / flavor text. The frame art must carry
**zero baked text** and a **cleanly removable** window + exterior.

---

## Why the last batch failed (articulate this so Gemini stops doing it)

Two defects made ~90 of 101 generated frames unusable:

1. **Baked text.** Gemini rendered actual words/numbers into the border art — "TIER 5",
   "DRIP", "AOF LOOT", "RESTRICTED", "ADULT LANE", world coords like "2-1-2", and flavor
   lines. Our engine draws the *real* tier/name/flavor at composite time from the roll.
   When a frame with a baked "TIER 3" is used for a Tier 5 pull, the card shows **two
   contradictory tier labels**. Baked text in the top-right plate also collides with the
   dynamic TIER badge we stamp there. **The frame must be a blank chrome shell.**

2. **Fake transparency = baked checkerboard.** Instead of a real alpha hole, Gemini
   painted the window and the area outside the border as an **opaque grey Photoshop-style
   checkerboard** (the "transparency" pattern, flattened into real pixels). That looks
   like a literal checker grid on the final card and can't be keyed out reliably. **Do
   not draw a checkerboard. Do not imply transparency with a checker pattern.**

The fix for #2 is to stop relying on transparency at all: fill the removable regions with
one **flat, pure chroma color** we can key out deterministically.

---

## PRIMARY PROMPT — 10-card sheet, blank plates, chroma-keyed (copy-paste)

> Generate a single image: a **2 rows × 5 columns grid of 10 square trading-card BORDER
> FRAMES** for a neon cyberpunk "loot card" game. Follow these rules exactly.
>
> **Each card is a FRAME ONLY — an empty ornate border ring, no card face.**
> - The border/chrome occupies only the outer ~20% ring of each card.
> - The large central window (about 60% of the card, centered) must be filled with
>   **flat, solid PURE MAGENTA (#FF00FF)** — one uniform color, no texture, no gradient,
>   no pattern, no checkerboard, no shading.
> - The area **outside** each card's border (the gutters between cards and the sheet
>   margins) must also be **flat solid PURE MAGENTA (#FF00FF)**. Leave a generous magenta
>   gutter (at least 8% of a card's width) between adjacent cards so they can be cut apart.
>
> **Empty plates (raised chrome bezels with NOTHING written on them):**
> - a small empty rectangular plate in the **top-left** corner of the frame,
> - a small empty badge plate in the **top-right** corner,
> - a wide empty nameplate along the **bottom** edge.
> These plates are part of the metal border. They must be **completely blank** —
> recessed/beveled metal surfaces with no letters, numbers, words, glyphs, logos,
> symbols, or icons of any kind.
>
> **Absolutely NO text anywhere in the image.** No "TIER", no numbers, no "AOF LOOT",
> no card names, no flavor text, no watermark, no signature, no UI labels. If you are
> tempted to write a word, leave the plate empty instead.
>
> **Do NOT draw a checkerboard or any transparency-grid pattern anywhere.** The magenta
> regions are flat solid color.
>
> **Border style: make all 10 cards visibly DIFFERENT materials/themes**, one per cell,
> e.g.: (1) brushed steel + cyan neon, (2) carbon fiber + electric blue, (3) corroded
> industrial iron + amber, (4) polished gold luxe + white glow, (5) holographic iridescent
> chrome, (6) black obsidian + magenta neon, (7) riveted gunmetal + green LED, (8) frosted
> glass + ice-blue, (9) rusted copper + orange ember, (10) matte black + violet ultra.
> Keep the **layout identical** across all 10 (same window size/position, same three empty
> plates) — only the material and accent color change.
>
> Square 1:1 cards. Sharp, high-detail, game-ready. Flat magenta window + flat magenta
> background. No people, no photos, no text.

---

## MORE-ROBUST ALTERNATIVE — one card per generation

Spritesheet splitting is fragile (tight grids mis-cut). If sheet cards come out uneven,
generate **one card per image** instead, reusing the single-card block below and just
changing the style line each run. One high-res card per image removes the splitting step
entirely — most reliable path.

> Generate one square image: a single neon cyberpunk loot-card **BORDER FRAME only**.
> Ornate metal/chrome border in the outer ~20% ring. Central window (~60%, centered) =
> flat solid PURE MAGENTA #FF00FF. Everything outside the border = flat solid PURE MAGENTA
> #FF00FF. Three EMPTY beveled plates (top-left, top-right badge, bottom nameplate) with
> **no text of any kind**. NO words, numbers, "TIER", "AOF LOOT", flavor, watermark. NO
> checkerboard. Style: **<brushed steel + cyan neon>**. 1:1, sharp, game-ready.

---

## Clever approach ideas (now that we know the problem)

1. **Chroma-key instead of transparency.** Flat #FF00FF window+exterior is trivially and
   deterministically keyable — no rembg, no checker ambiguity, no AI segmentation guesswork.
   Magenta is chosen because it never appears in metal/cyan/green-neon chrome, so keying
   won't eat the border. (Add a ~5-line magenta keyer beside the existing green one.)
2. **One card per image > sheets.** Kills the splitter (our #1 mechanical failure). Slower
   per card but ~100% clean yield.
3. **Fixed layout, varied skin.** Ask for identical window/plate geometry across all cards
   so `_window_bbox` and stamp placement stay stable; only material/color varies. This also
   makes a per-tier mapping (border N → tier N) trivial if we want deterministic skins.
4. **Generate 10 styles = instant pool variety.** One good sheet ≈ our whole current clean
   pool, all badge-free, all keyable.
5. **Belt-and-suspenders acceptance.** Run every new card through
   `audit_loot_card_frames.py` AND a quick "no baked text" eyeball before promoting to
   `clean/` — the audit is structural and blind to text, so the human gate stays.
6. **If Gemini still bakes text**, add "the plates are blank metal, like an unengraved
   award trophy plate" — describing the *object* (blank plate) beats negative-listing
   every word.
