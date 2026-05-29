# AOF Hub (aof-forum)

Motherless-style doom-scroll hub on top of a Stash-powered media library, fed by URL ingest + Telegram ingest from `tbcc`, stored in Backblaze B2, with a Reddit-style forum and first-class Groups on top.

Built to run **entirely locally** during iteration. Only the launch step needs a VPS.

See the active build plan at `c:\Users\ianmp\.cursor\plans\aof-forum_motherless_stash_a783052a.plan.md`.

## Stack

- **Frontend:** Next.js 14 (App Router) on `localhost:3001` -> Vercel at launch
- **DB + Auth:** Supabase Postgres (cloud free tier from day one)
- **Media library / tagging:** Stash in Docker on `localhost:9999`, synced into Supabase
- **Storage:** Backblaze B2 (S3-compatible). Cloudflare CDN added at launch only.
- **Ingest worker:** Node + TypeScript, runs locally as `npm run ingest`
- **Stash sync:** `npm run stash:sync`
- **Content firehose:** existing `tbcc` FastAPI crawler (erome / onlyfans / bunkr / generic), reused via internal API

## Local-dev quickstart

### 1. Cloud accounts (one-time, ~10 min)

**Backblaze B2:**
1. Sign up at <https://www.backblaze.com/cloud-storage>. First 10 GB free, then $0.006/GB/mo.
2. Create a **private** bucket named `aof-media-dev`.
3. **App Keys** -> Add a new application key, scoped to that bucket, with **Read + Write + Delete**.
4. Note the `keyID`, `applicationKey`, and the **S3 endpoint** shown on the bucket page (e.g. `s3.us-west-004.backblazeb2.com`).

**Supabase:**
1. Sign up at <https://supabase.com>. Free tier: 500 MB Postgres, 50k MAU.
2. Create a project `aof-forum-dev`.
3. **Project Settings -> API** -> copy `Project URL`, `anon public` key, and `service_role` key.

Drop everything into `.env.local` (copied from `.env.example`).

### 2. Stash (Docker on Windows)

```powershell
# One-time: create folders Stash will use
mkdir C:/aof-media
mkdir C:/aof-media/stash-inbox
mkdir C:/aof-media/inbox

docker run -d --name stash `
  -p 9999:9999 `
  -v $env:USERPROFILE/.stash:/root/.stash `
  -v C:/aof-media:/data `
  stashapp/stash:latest
```

Open <http://localhost:9999>:
- **Settings -> Library** -> add `/data/stash-inbox` as a Library Path.
- **Settings -> Security** -> optionally enable an API key; paste it into `STASH_API_KEY`.
- Install community plugins for auto-tagging (Settings -> Plugins): PhashAutoTagger, StashDB scrapers, FaceLook (community fork).

### 3. Install + apply schema

```powershell
cd aof-forum
npm install

# Apply migrations to your Supabase project (uses SUPABASE_SERVICE_ROLE_KEY from .env.local).
# Requires the supabase CLI: https://supabase.com/docs/guides/cli
npx supabase link --project-ref <your-project-ref>
npx supabase db push
```

### 4. Run

```powershell
# Terminal 1: Next.js
npm run dev               # http://localhost:3001

# Terminal 2: ingest worker (watches INGEST_LOCAL_INBOX, polls tbcc, processes api/ingest jobs)
npm run ingest:watch

# Terminal 3 (optional): Stash sync every 5 min
npm run stash:sync:watch
```

Drag a file into `C:/aof-media/inbox/` -> worker uploads to B2, inserts row in `media_items`, copies into `C:/aof-media/stash-inbox/` -> Stash auto-imports + tags -> stash-sync writes tags back into Supabase -> media appears in the forum feed with tags + related panel.

## What's in this repo

```
aof-forum/
  app/
    (site)/          # the actual UI (feed, media, galleries, groups, forum, profiles)
    api/             # route handlers (feed, related, ingest, vote, view, groups)
    auth/            # supabase magic link
  lib/
    supabase/        # browser + server + admin (service-role) clients
    b2.ts            # S3-compatible Backblaze client
    stash.ts         # Stash GraphQL client
    reco/            # related / feed / for-you algorithms
  workers/
    ingest/          # URL / local-folder / Telegram pipeline -> B2 + Supabase
    stash-sync/      # Stash GraphQL -> Supabase tags + media_tags
  supabase/
    migrations/      # 0001_init.sql ... (run via supabase CLI)
  middleware.ts      # Supabase auth cookie refresh
```

## Vercel (launch)

1. Import the repo (or monorepo with Root Directory = `aof-forum`).
2. Add env vars matching `.env.example`, swapping `localhost` URLs for production hosts.
3. Deploy.

Until launch: keep iterating locally. The cloud services (B2, Supabase) are the same in dev and prod; only `STASH_GRAPHQL_URL`, `TBCC_API_URL`, and `NEXT_PUBLIC_MEDIA_BASE_URL` change.
