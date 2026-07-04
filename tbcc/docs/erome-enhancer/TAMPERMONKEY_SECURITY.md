# Tampermonkey security checklist (TBCC)

Apply these in Brave + Tampermonkey **before** relying on browse-intel for pool picks.

## Extension (Brave)

| Setting | Value |
|---------|-------|
| Site access | On all sites (required; use blacklist below) |
| Allow User Scripts | On |
| Allow in Private | **Off** |
| Allow access to file URLs | **Off** |
| Pin to toolbar | On (optional) |

## Tampermonkey → Settings

| Setting | Value |
|---------|-------|
| Userscript Update → Check Interval | **Never** |
| Externals → Update Interval | **Never** |
| Allow scripts to access cookies | **None** (or All but protected if a script breaks) |
| Check @connect | Ask if unknown |
| Page Filter Mode | **Blacklist** |
| Subresource Integrity | Validate if possible |

## Scripts to disable now

| Script | Action |
|--------|--------|
| Erome Enhancer (alpha) | **Disable** — duplicate of extended fork |
| Bypass All Shortlinks (pick one) | **Disable v96.5 or v96.7** — keep only one if needed |
| Bypass All Shortlinks Manual Captcha | Disable if unused |

## Scripts OK to keep (narrow `@match`)

Erome Enhancer extended fork (v4), site-specific enhancers (FetLife, Reddit++, Chaturbate, OnlyFans) if you use them.

## Blacklisted Pages (paste into Tampermonkey Security)

```
*example.org/*
*://*.paypal.com/*
*://*.paypal.me/*
*paypal.tld/*
*://*.venmo.com/*
*://*.cash.app/*
*://*.chime.com/*
*://*.chimebank.com/*
*://*.wellsfargo.com/*
*://*.wf.com/*
https://*bankofamerica.tld/*
*://*.coinbase.com/*
*://*.nowpayments.io/*
*://*.linkvertise.com/*
*://*.link-to.net/*
*://*.ssa.gov/*
*://mail.google.com/*
*://accounts.google.com/*
*://myaccount.google.com/*
*://pay.google.com/*
*://wallet.google.com/*
*stripe.com/*
*://*.chase.com/*
*://*.capitalone.com/*
*://*.americanexpress.com/*
*://*.trustwallet.com/*
*://*.binance.com/*
*://*.kraken.com/*
*://*.crypto.com/*
*://login.live.com/*
*://*.icloud.com/*
*://web.telegram.org/*
*://www.facebook.com/plugins/*
*://platform.twitter.com/widgets/*
```

## Whitelisted Pages (optional)

```
/https?:\/\/greasyfork\.org\/.*/
/https?:\/\/sleazyfork\.org\/.*/
```

## TBCC browse-intel workflow

1. Install `tbcc/tools/erome-enhancer/erome-enhancer.user.js` in Tampermonkey.
2. Browse Erome explore with **Show like counts** on (records intel).
3. Enhancer → **Export JSONL** → save as `browse-intel-drop.jsonl`.
4. Copy file to TBCC run dir: `{tbcc_run}/erome-analytics/browse-intel-drop.jsonl`
5. `POST http://127.0.0.1:8000/analytics/erome-browse-intel/sync-file`  
   Or set TBCC URL in script settings and **Push to TBCC**.
6. `GET /analytics/erome-browse-intel/summary` — top tags / formats.
7. Pool picks use intel when `TBCC_EROME_BROWSE_INTEL_RANK=1` (default).

## Env vars (TBCC backend)

| Var | Default | Meaning |
|-----|---------|---------|
| `TBCC_EROME_BROWSE_INTEL_ENABLED` | `1` | Ingest + summary |
| `TBCC_EROME_BROWSE_INTEL_LOOKBACK_DAYS` | `30` | Aggregate window |
| `TBCC_EROME_BROWSE_INTEL_RANK` | `1` | Boost `rank_pool_media` by tag overlap |
