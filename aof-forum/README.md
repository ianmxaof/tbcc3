# AOF Hub (forum scaffold)

Next.js 14 (App Router) + Supabase. Intended for **Vercel** deploy and clearnet funnel from AOF / TBCC on Telegram.

## Why Vercel + Supabase (vs free VPS + Docker)

| Approach | Pros | Cons |
|----------|------|------|
| **Vercel + Supabase** (this app) | Git push deploy, edge-friendly API routes, no server patching; Supabase gives Postgres, Auth, Storage on free tier | Serverless timeouts; heavy transcoding / long workers belong elsewhere later |
| **Free VPS + Docker** (e.g. Oracle free tier) | Full control, long-running containers | You operate OS, firewall, SSL, backups |

For a forum MVP and SEO pages, Vercel + Supabase is the lower-friction path. Add a worker host only when you need tube-style transcoding or big batch jobs.

## Local dev

```bash
cd aof-forum
cp .env.example .env.local
# Fill NEXT_PUBLIC_SUPABASE_* from Supabase project settings → API

npm install
npm run dev
```

Open [http://localhost:3001](http://localhost:3001) (port avoids clash with TBCC on :8000 / dashboard :5173).

## Vercel

1. Import this repo (or monorepo with **Root Directory** = `aof-forum`).
2. Add environment variables: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
3. Deploy. Optional: assign your domain in Vercel (already on your account).

## Supabase

Create a project → copy **Project URL** and **anon public** key into Vercel + `.env.local`.

**Policies:** Read [Supabase](https://supabase.com/terms) and [Vercel](https://vercel.com/legal acceptable-use) acceptable use for your content category before relying on free tiers for production.

## TBCC integration (later)

- Public canonical URLs in Telegram: `https://your-domain.com/...?utm_source=telegram`
- Server-only: `TBCC_API_URL` + `TBCC_INTERNAL_API_KEY` in Vercel env for Route Handlers that check subscription tier (do not expose the internal key to the client).

## Structure

- `app/` — pages and `app/api/*` route handlers
- `lib/supabase/` — browser + server Supabase clients (`@supabase/ssr`)
- `middleware.ts` — refresh auth session cookies
