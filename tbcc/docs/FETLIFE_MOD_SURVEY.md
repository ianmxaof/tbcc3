# FetLife mod survey (evaluate later)

**Date:** 2026-07-14  
**Scope:** GitHub / GreasyFork / gist dice-roll — no ports this pass.  
**Suite:** TBCC FetLife Suite v1.8 (extension bundle).

## Finds worth remembering

| Source | What it does | TBCC fit | Risk |
|--------|--------------|----------|------|
| [PrincessBabyTay/FetLifeEnhancer](https://github.com/PrincessBabyTay/FetLifeEnhancer) | Broader FL UX extension + userscript | Inventory gaps vs suite Features tab | Unmaintained; ToS |
| [unnaturaldevelopment/fles](https://github.com/unnaturaldevelopment/fles) (archived) | UI customization suite; wiki has feature list | Idea mine only | Dead project |
| [fabacab/fetlife-spyscope](https://github.com/fabacab/fetlife-spyscope) | Hover profile intel (age/sex/role/activity) | Social-proof adjacent | Old DOM |
| [fabacab/better-fetlife](https://github.com/fabacab/better-fetlife) | vCard + event calendar export | Niche operator utility | Low priority |
| [gallery-dl #909](https://github.com/mikf/gallery-dl/issues/909) console IIFE | One-shot **u2000** image extract (SW headers) | Candidate: photo-page **Save u2000** button | Manual; no bulk scrape |
| Video sharer / paywall bypass scripts | Free share of paid videos | **Skip** | ToS / legal |

## Recommended next slice (separate PR)

1. **Save u2000** on `/pictures/{id}` pages only — port the gallery-dl console pattern into the suite overlay (no crawler).
2. Skim FetLife Enhancer release notes for any UI affordances we still lack (mute already covered; masonry/home feed covered).
3. Do **not** port Spyscope wholesale — rebuild hover intel against current FL markup if still desired.

## Explicit non-goals

- Bulk album downloaders / scrapers
- Paywall bypass / video sharer
- Auto-follow bots outside TBCC’s existing gated controls
