# Storage Hub → R2 → AOF Forum

**Date:** 2026-08-12  
**Status:** code shipped; needs island deploy + operator drain

## Why

Forum `ingest:storage-hub:full` re-downloads every file through Cloudflare → Telethon and dies on 502/524. New path: **island Telethon → R2 once**, forum indexes keys only.

## TBCC

| Piece | Path |
|-------|------|
| Service | `backend/app/services/storage_hub_r2_export.py` |
| Celery (telegram queue) | `backend/app/workers/storage_hub_r2_export_worker.py` |
| CLI | `backend/scripts/export_storage_hub_to_r2.py` |
| Export fields | `GET /media/export` → `object_key`, `direct_url`, `has_r2` |
| Tick | `POST /media/export/r2/tick` |

Keys: `library/hub/{media_id}/{file_unique_id}.{ext}` in `TBCC_R2_BUCKET` (aof-media). Meta in `classification_json.r2`.

## Forum

| Piece | Path |
|-------|------|
| Manifest indexer | `npm run ingest:storage-hub:manifest` |
| Operator doc | `aof-forum/docs/STORAGE_HUB_INGEST.md` |
| Local dumps | `INGEST_LOCAL_INBOX` + `npm run ingest:watch` |

## Operator sequence

1. Deploy island (bake new worker + API).
2. On island: `python scripts/export_storage_hub_to_r2.py --drain --limit 20`
3. On home: `npm run ingest:storage-hub:manifest` (B2_* = same aof-media bucket).
4. Personal files: drop into `C:/aof-media/inbox` with `ingest:watch`.
