# Sleazy Fork community scripts (AOF)

Public Tampermonkey cuts — **no intel, no TBCC ingest**. Soft promo: Loot · `@aofsubscriptions_bot` · hub.

| Listing | Upload file | Paste kit |
|---------|-------------|-----------|
| Erome Enhancer extended sort options | `tbcc/tools/erome-enhancer/erome-enhancer-community.user.js` | `docs/erome-enhancer/SLEAZY_FORK_PUBLISH.md` |
| FetLife Enhancer | `tbcc/userscripts/community/fetlife-suite-community.user.js` | `docs/fetlife-enhancer/SLEAZY_FORK_PUBLISH.md` |
| ThisVid Enhancer | `tbcc/tools/thisvid-enhancer/thisvid-enhancer-community.user.js` | `docs/thisvid-enhancer/SLEAZY_FORK_PUBLISH.md` |

**Not published:** Motherless (retired). Operator intel builds, Perchance loot lab, X overlay, macrosearch.

Rebuild:

```powershell
py -3.13 tbcc/tools/erome-enhancer/build_community.py
py -3.13 tbcc/tools/thisvid-enhancer/build_community.py
cd tbcc/userscripts; npm run build:nobump
```
