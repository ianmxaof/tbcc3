# Storage Hub → AOF Forum (R2 path) + local personal dumps

## Path 1 — TBCC exports bytes to R2 on the island (preferred)

Telethon runs **on the island**, uploads once to `aof-media` under `library/hub/{id}/…`,
and stores the key in `media.classification_json.r2`. The forum only indexes keys.

### On the island (or local with admin.session + R2 env)

```bash
cd /opt/tbcc/backend-src   # or tbcc/backend locally
python scripts/export_storage_hub_to_r2.py --limit 10
python scripts/export_storage_hub_to_r2.py --drain --limit 20
```

Celery (telegram queue):

```text
POST /media/export/r2/tick?since_id=0&limit=10&async_celery=true
```

(with `X-TBCC-Internal-Key`)

### On the forum (home PC)

Point `TBCC_API_URL` at the island and use the **same** R2/B2 bucket as TBCC (`aof-media`):

```powershell
cd aof-forum
npm run ingest:storage-hub:manifest
```

This polls `GET /media/export?origin=storage_hub&has_r2=true` and inserts `media_items`
with `b2_key = object_key` (no `/media/{id}/file` download).

---

## Path 3 — Personal media already on disk

Browser upload: daily **file count is unlimited** (`UPLOAD_DAILY_FILE_LIMIT=0`); still
capped at **5 GB/day** and **500 MB/file**, **100 files/batch**.

Local inbox (unlimited, no browser quota):

1. Set `INGEST_LOCAL_INBOX=C:/aof-media/inbox` in `aof-forum/.env.local`
2. Configure `B2_*` to the `aof-media` bucket (same as TBCC R2)
3. Run:

```powershell
cd aof-forum
npm run ingest:watch
```

4. Copy/drag files into `C:/aof-media/inbox` (top level only), then double-click
   `! AOF INGEST.cmd` (runs `npm run ingest:inbox:watch`). Worker uploads to R2,
   inserts forum rows, and **permanently deletes** successes from the inbox. Failures stay.
   After **5 minutes idle** (no new media), the process exits to free CPU/RAM.
   One-shot without watch: `npm run ingest:inbox`.

---

## Do not use (for Storage Hub corpus)

`npm run ingest:storage-hub:full` — pulls every file through Cloudflare → Telethon and
times out (502/524). Kept only as a fallback for rows without R2 keys.
