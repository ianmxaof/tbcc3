#!/usr/bin/env python3
"""Run ops checklist: goon deposit, erome status/upload test, ledger seed + view sync."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()


def step_goon_deposit(limit: int = 5) -> dict:
    from app.database.session import SessionLocal
    from app.services.storage_topic_deposit import (
        await_deposit_import_job,
        await_celery_task_async,
        queue_storage_topic_deposit,
        _mirror_task_ids,
    )

    goon_thread = 2934
    db = SessionLocal()
    try:
        report = queue_storage_topic_deposit(
            db,
            message_thread_id=goon_thread,
            limit=limit,
            media_types="videos",
        )
    finally:
        db.close()

    if not report.get("ok"):
        return {"step": "goon_deposit", "ok": False, "report": report}

    job_id = str(report.get("job_id") or "")
    print(f"[deposit] queued job={job_id} pool={report.get('pool_name')}", flush=True)

    job_body = asyncio.run(await_deposit_import_job(job_id, limit=limit, timeout_s=900))
    out = {
        "step": "goon_deposit",
        "ok": bool(job_body and job_body.get("status") == "done"),
        "job_id": job_id,
        "job": job_body,
        "mirror": report.get("topic_mirror"),
    }

    if job_body and job_body.get("status") == "done":
        result = job_body.get("result") or {}
        stored = int(result.get("stored") or 0)
        print(f"[deposit] stored={stored} scanned={result.get('messages_scanned')}", flush=True)
        mirror_ids = _mirror_task_ids(report) if stored > 0 else []
        if mirror_ids:
            print(f"[deposit] waiting for mirror task…", flush=True)
            mirror_body = asyncio.run(
                await_celery_task_async(mirror_ids[0], timeout_s=1200)
            )
            out["mirror_result"] = mirror_body
            print(f"[deposit] mirror={mirror_body}", flush=True)
    elif job_body:
        print(f"[deposit] status={job_body.get('status')} error={job_body.get('error')}", flush=True)
    else:
        print("[deposit] import poll timed out", flush=True)
        out["ok"] = False

    return out


def step_erome_status() -> dict:
    from app.services.erome_upload_provision import (
        auth_state_path,
        load_flow_config,
        selectors_ready,
    )
    from app.services.playwright_browser import describe_launch_mode, resolve_launch_mode

    auth = auth_state_path()
    cfg = load_flow_config()
    launch = resolve_launch_mode(storage_state=auth)
    return {
        "step": "erome_status",
        "auth_exists": auth.is_file(),
        "auth_path": str(auth),
        "selectors_ready": selectors_ready(cfg),
        "launch_mode": describe_launch_mode(storage_state=auth),
        "launch": launch,
    }


def step_erome_staging_setup() -> Path:
    staging = Path(__file__).resolve().parents[1] / "erome_test_staging"
    staging.mkdir(parents=True, exist_ok=True)
    params = {
        "title": "Vietnamese MILF jiggly big boobs ready for sex",
        "tags": ["milf", "webcam", "big tits", "latina", "full body"],
        "network_key": "milf",
        "content_notes": "ops checklist test — single photo album",
        "source": "ops_checklist",
    }
    (staging / "erome.params.json").write_text(
        json.dumps(params, indent=2) + "\n", encoding="utf-8"
    )
    return staging


def step_erome_dry_run(folder: Path) -> dict:
    from app.services.erome_upload_provision import load_flow_config, scan_staging_folder

    cfg = load_flow_config()
    scan = scan_staging_folder(folder, allowed_extensions=cfg.allowed_extensions, max_files=3)
    return {
        "step": "erome_dry_run",
        "folder": str(folder),
        "files": [p.name for p in scan.files],
        "ok": scan.ok,
    }


def step_erome_execute(folder: Path) -> dict:
    from app.services.erome_upload_analytics import EromeUploadParams, merge_sidecar_params
    from app.services.erome_telegram_ingest import upload_staged_folder

    params = merge_sidecar_params(
        folder,
        EromeUploadParams(source="ops_checklist", file_count=1, force_policy=True),
    )
    result = upload_staged_folder(
        folder,
        title=params.title,
        tags=params.tags,
        source="ops_checklist",
        skip_watermark=True,
        force_policy=True,
        max_files=2,
    )
    body = result.to_dict()
    body["step"] = "erome_execute"
    body["ok"] = bool(result.ok)
    return body


def step_seed_ledger() -> dict:
    from app.services.erome_upload_analytics import EromeUploadParams, record_erome_upload
    from app.services.erome_upload_policy import append_ledger_row

    seeds = [
        {
            "title": "Vietnamese MILF jiggly big boobs ready for sex",
            "tags": ["milf", "webcam", "big tits", "latina", "full body"],
            "album_url": "https://www.erome.com/a/placeholder_goon_winner",
            "network_key": "goon",
            "staging_meta": {
                "format_hint": "single_video",
                "primary_duration_sec": 134,
                "video_count": 1,
            },
            "views_latest": 822,
        },
        {
            "title": "Mom's big tits make my penis fully yolked",
            "tags": ["milf", "big tits", "taboo", "webcam"],
            "album_url": "https://www.erome.com/a/placeholder_goon_2",
            "network_key": "goon",
            "staging_meta": {"format_hint": "single_video", "primary_duration_sec": 120},
            "views_latest": 456,
        },
    ]
    for row in seeds:
        append_ledger_row(
            {
                "ok": True,
                "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "title": row["title"],
                "tags": row["tags"],
                "album_url": row["album_url"],
                "network_key": row["network_key"],
                "staging_meta": row["staging_meta"],
                "views_latest": row["views_latest"],
                "source": "ops_checklist_seed",
            }
        )

    params = EromeUploadParams(
        title=seeds[0]["title"],
        tags=seeds[0]["tags"],
        source="ops_checklist_seed",
        network_key="goon",
    )
    manifest = record_erome_upload(
        params,
        {"ok": True, "album_url": seeds[0]["album_url"], "title": seeds[0]["title"], "file_count": 1},
        staging_meta=seeds[0]["staging_meta"],
    )
    return {"step": "seed_ledger", "ok": True, "manifest": str(manifest), "rows": len(seeds)}


def step_view_sync() -> dict:
    from app.services.erome_view_sync import sync_ledger_views

    report = sync_ledger_views(max_albums=5)
    report["step"] = "view_sync"
    return report


def main() -> int:
    results: list[dict] = []

    print("=== 1. GOON DEPOSIT ===", flush=True)
    results.append(step_goon_deposit(5))

    print("\n=== 2. EROME STATUS ===", flush=True)
    status = step_erome_status()
    results.append(status)
    print(json.dumps(status, indent=2), flush=True)

    print("\n=== 3. EROME STAGING + DRY RUN ===", flush=True)
    folder = step_erome_staging_setup()
    dry = step_erome_dry_run(folder)
    results.append(dry)
    print(json.dumps(dry, indent=2), flush=True)

    print("\n=== 4. EROME UPLOAD (if auth ready) ===", flush=True)
    if status.get("auth_exists") and status.get("selectors_ready") and dry.get("ok"):
        try:
            exe = step_erome_execute(folder)
            results.append(exe)
            print(json.dumps({k: exe.get(k) for k in ("ok", "album_url", "title", "error")}, indent=2), flush=True)
        except Exception as e:
            results.append({"step": "erome_execute", "ok": False, "error": str(e)[:300]})
            print(f"execute skipped/failed: {e}", flush=True)
    else:
        results.append(
            {
                "step": "erome_execute",
                "ok": False,
                "skipped": True,
                "reason": "auth or selectors or media missing — run: py scripts/erome_upload_local.py --login --headed",
            }
        )
        print("skipped execute — run --login --headed manually if auth missing", flush=True)

    print("\n=== 5. SEED LEDGER + VIEW SYNC ===", flush=True)
    results.append(step_seed_ledger())
    results.append(step_view_sync())

    out_path = folder / "ops_checklist_result.json"
    out_path.write_text(json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nWrote {out_path}", flush=True)
    failed = [r for r in results if r.get("ok") is False and not r.get("skipped")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
