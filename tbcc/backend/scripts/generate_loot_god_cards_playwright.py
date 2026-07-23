"""Batch-generate Loot God tier cards via headed Playwright on Perchance.

Requires: playwright + chromium, operator logged into Perchance in the profile,
and the TBCC extension optional (script fills the prompt field directly).

  py -3.13 scripts/generate_loot_god_cards_playwright.py --url https://perchance.org/YOUR-GEN --execute
  py -3.13 scripts/generate_loot_god_cards_playwright.py --tiers 1,2,3 --dry-run

Saves PNGs to app/data/loot_tier_cards/tier-N.png (overwrites).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB = (
    ROOT.parent
    / "userscripts"
    / "packages"
    / "perchance-suite"
    / "data"
    / "loot-god-library.json"
)
OUT = ROOT / "app" / "data" / "loot_tier_cards"
SEEDS_BY_TIER = {
    1: "adult woman, 30s, dim bedroom, sealed-heat vibe, lingerie tease, phone-cam grain",
    2: "voyeur doorway peek, adult woman undressing, cool blue neon, frosted mirror edge",
    3: "locker steam, adult athletic woman towel-slip, amber light, wet tile",
    4: "adult woman pulse-red neon, sweat sheen, close heat, shallow DOF",
    5: "adult woman on wet vinyl, hot-pink neon, mid-heat club",
    6: "VIP hotel corridor, adult woman velvet rope, orange blaze neon",
    7: "vault-green spill light, adult woman latex gloves open shirt",
    8: "purple gold chrome, adult woman victory mess, no soft landing energy",
    9: "near-black ultraviolet, adult silhouette behind frosted glass",
    10: "gold chrome confetti light, adult woman godroll smirk, blood-red accents",
}


def load_lib() -> dict:
    return json.loads(LIB.read_text(encoding="utf-8"))


def compose(tier: int, subject: str, lib: dict) -> tuple[str, str]:
    meta = (lib.get("tiers") or {}).get(str(tier)) or {}
    name = str(meta.get("name") or f"T{tier}").upper()
    world = meta.get("world") or "?"
    tagline = meta.get("tagline") or ""
    neon = meta.get("neon") or ""
    mood = meta.get("mood") or ""
    prompt = "\n".join(
        [
            lib.get("outputBlock") or "",
            "",
            lib.get("borderStyle") or "",
            "",
            "TIER BLOCK (exact UI text — do not alter spelling):",
            f"TOP-RIGHT = TIER {tier} · {world}",
            f"BOTTOM NAME = {name}",
            f"TAGLINE = {tagline}",
            f"NEON / FRAME ACCENT: {neon}",
            f"MOOD CUE: {mood}",
            "",
            lib.get("qualityPrimer") or "",
            "",
            "SUBJECT (center window only — adult content allowed; keep chrome readable):",
            subject,
            "",
            "Generate now. Lock the card chrome. Put all creative variation in the center window only.",
        ]
    )
    return prompt, str(lib.get("negative") or "")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="https://perchance.org/ai-text-to-image-generator")
    p.add_argument("--tiers", default="1-10", help="e.g. 1-10 or 1,3,5")
    p.add_argument("--execute", action="store_true", help="Run browser (default dry-run prints prompts)")
    p.add_argument("--headed", action="store_true", default=True)
    p.add_argument("--wait-sec", type=int, default=90, help="Wait after Generate click")
    p.add_argument("--out-dir", type=Path, default=OUT)
    args = p.parse_args()

    if not LIB.is_file():
        print(f"missing library: {LIB}", file=sys.stderr)
        return 2
    lib = load_lib()

    tiers: list[int] = []
    raw = args.tiers.strip()
    if "-" in raw and "," not in raw:
        a, b = raw.split("-", 1)
        tiers = list(range(int(a), int(b) + 1))
    else:
        tiers = [int(x) for x in raw.split(",") if x.strip()]

    args.out_dir.mkdir(parents=True, exist_ok=True)

    if not args.execute:
        for t in tiers:
            prompt, neg = compose(t, SEEDS_BY_TIER.get(t, "adult hyperreal subject"), lib)
            print(f"\n===== TIER {t} =====\n{prompt[:400]}...\nNEGATIVE: {neg[:120]}...")
        print("\nDry-run only. Re-run with --execute when ready (headed Chromium).")
        return 0

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("pip install playwright && playwright install chromium", file=sys.stderr)
        return 2

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=80)
        context = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=120_000)
        print("Log into Perchance in the opened window if needed, then leave the generator ready.")
        print("Waiting 25s for manual login/setup...")
        time.sleep(25)

        for t in tiers:
            subject = SEEDS_BY_TIER.get(t, "adult hyperreal subject")
            prompt, neg = compose(t, subject, lib)
            print(f"\n--- Tier {t}: filling prompt ---")
            areas = page.locator("textarea")
            count = areas.count()
            if count < 1:
                print("No textarea found — abort", file=sys.stderr)
                break
            # Prefer largest / first non-negative
            areas.nth(0).fill(prompt)
            if count >= 2:
                try:
                    areas.nth(1).fill(neg)
                except Exception:
                    pass
            # Shape square if select exists
            try:
                page.get_by_text("Square", exact=False).first.click(timeout=2000)
            except Exception:
                pass
            gen = page.get_by_role("button", name=lambda n: n and "generate" in n.lower())
            if gen.count() == 0:
                page.locator("button").filter(has_text="generate").first.click()
            else:
                gen.first.click()
            print(f"Generate clicked; waiting {args.wait_sec}s...")
            time.sleep(args.wait_sec)
            # Best-effort: screenshot full page as fallback card
            out = args.out_dir / f"tier-{t}.png"
            # Try canvas screenshot
            canvases = page.locator("canvas")
            saved = False
            if canvases.count() > 0:
                try:
                    canvases.last.screenshot(path=str(out))
                    saved = True
                except Exception as e:
                    print(f"canvas shot failed: {e}")
            if not saved:
                page.screenshot(path=str(out), full_page=False)
            print(f"saved {out} ({out.stat().st_size} bytes)")

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
