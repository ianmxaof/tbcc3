# powercore.app — minimal static site (Wrangler Pages)

Hosts BonusArrive domain verification and a tiny landing page. **Not** the TBCC dashboard (`www.powercore.app` may stay separate).

## Prerequisites

1. **Domain on Cloudflare** — `powercore.app` must use Cloudflare nameservers (Namecheap → Custom DNS → Cloudflare NS). `www.powercore.app` already hits Cloudflare; apex may need the custom domain step below.
2. **Wrangler login** (once):

```powershell
cd tbcc\static\powercore-verify
npx wrangler login
```

## How `powercore.app` is hosted (operator note)

Apex `powercore.app` is an **R2 custom domain** on bucket **`aof-x-promo`** (not Pages). Verification file must live at bucket root:

`aof-x-promo/bonusarrive-verify-a3048e.txt`

`www.powercore.app` is separate (dashboard on Vercel/Pages IPs).

## Deploy (Wrangler Pages — optional www landing)


From repo root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tbcc\scripts\deploy-powercore-verify.ps1
```

Or manually:

```powershell
cd tbcc\static\powercore-verify
npm install
npx wrangler pages deploy . --project-name=powercore-app --branch=main
```

## Attach apex domain (after first deploy)

In [Cloudflare Dashboard](https://dash.cloudflare.com) → **Workers & Pages** → project **powercore-app** → **Custom domains** → add:

- `powercore.app`
- (optional) `www.powercore.app` only if you want this mini-site on www instead of the dashboard

Or try CLI:

```powershell
npx wrangler pages project list
npx wrangler pages domain add powercore.app --project-name=powercore-app
```

## Verify BonusArrive

```powershell
curl https://powercore.app/bonusarrive-verify-a3048e.txt
```

Expected output (only this line):

```text
ac34-5af9-6867-d27f-e170
```

Then click **Verify** in BonusArrive.

## Files

| File | Purpose |
|------|---------|
| `bonusarrive-verify-a3048e.txt` | BonusArrive domain verification token |
| `index.html` | Minimal landing (optional) |
| `package.json` | Wrangler deploy script |

## Updating the verify token

If BonusArrive issues a new file, replace `bonusarrive-verify-*.txt` in this folder and redeploy.
