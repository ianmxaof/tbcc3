"""Smoke-test emoji-factory API (prerequisites + async split poll).

Run from tbcc/backend:
  python scripts/smoke_emoji_factory_api.py
  python scripts/smoke_emoji_factory_api.py --sync
  python scripts/smoke_emoji_factory_api.py --upload --dry-run
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
env_path = ROOT / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

API_BASE = (os.getenv("TBCC_API_URL") or "http://127.0.0.1:8000").rstrip("/")

# 1×1 PNG (valid, tiny — pipeline scales to grid)
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _sample_png() -> bytes:
    try:
        from PIL import Image

        im = Image.new("RGB", (64, 64), (80, 40, 120))
        buf = BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return base64.b64decode(_TINY_PNG_B64)


def _print_json(label: str, data: object) -> None:
    print(f"\n=== {label} ===", file=sys.stderr)
    print(json.dumps(data, indent=2))


def smoke_prerequisites(client: httpx.Client) -> dict:
    r = client.get(f"{API_BASE}/emoji-factory/prerequisites")
    r.raise_for_status()
    return r.json()


def smoke_sync_split(client: httpx.Client) -> dict:
    files = {"file": ("smoke_grid.png", BytesIO(_sample_png()), "image/png")}
    data = {
        "cols": "2",
        "rows": "2",
        "tile_px": "100",
        "static": "true",
        "upload_telegram": "false",
    }
    r = client.post(f"{API_BASE}/emoji-factory/create-from-upload", files=files, data=data, timeout=600.0)
    if not r.is_success:
        raise RuntimeError(r.text[:500])
    return r.json()


def smoke_async_split(
    client: httpx.Client,
    *,
    upload: bool,
    dry_run: bool,
    dividers: bool,
    preset: bool,
    timeout_s: float,
) -> dict:
    files = {"file": ("smoke_async.png", BytesIO(_sample_png()), "image/png")}
    data = {
        "cols": "2",
        "rows": "2",
        "tile_px": "100",
        "static": "true",
        "upload_telegram": "true" if upload else "false",
        "dry_run": "true" if dry_run else "false",
        "import_dividers": "true" if dividers else "false",
        "save_sketchbook_preset": "true" if preset else "false",
        "source": "smoke_script",
        "title": "Smoke emoji pack",
        "short_name": "smoke_pack",
    }
    r = client.post(f"{API_BASE}/emoji-factory/jobs/create-async", files=files, data=data, timeout=120.0)
    if not r.is_success:
        raise RuntimeError(r.text[:500])
    queued = r.json()
    job_id = queued.get("job_id")
    if not job_id:
        raise RuntimeError(f"no job_id in response: {queued}")
    deadline = time.time() + timeout_s
    last: dict = queued
    queued_since: float | None = None
    while time.time() < deadline:
        pr = client.get(f"{API_BASE}/emoji-factory/jobs/{job_id}/status", timeout=30.0)
        pr.raise_for_status()
        last = pr.json()
        print(f"poll status={last.get('status')} stage={last.get('stage')}", file=sys.stderr)
        if last.get("terminal"):
            return last
        if last.get("status") == "queued":
            if queued_since is None:
                queued_since = time.time()
            elif time.time() - queued_since >= 12.0:
                print("WARN: job still queued — running worker inline (Celery may be offline)", file=sys.stderr)
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                from app.services.emoji_factory_async import execute_emoji_factory_job

                return execute_emoji_factory_job(str(job_id))
        else:
            queued_since = None
        time.sleep(2.0)
        raise TimeoutError(f"job {job_id} did not finish within {timeout_s:.0f}s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test TBCC emoji-factory API")
    parser.add_argument("--sync", action="store_true", help="Also run blocking create-from-upload")
    parser.add_argument("--upload", action="store_true", help="Async path: upload_telegram=true")
    parser.add_argument("--dry-run", action="store_true", help="With --upload: dry_run pack create")
    parser.add_argument("--dividers", action="store_true", help="Async path: import row dividers")
    parser.add_argument("--preset", action="store_true", help="Async path: save sketchbook preset (needs upload)")
    parser.add_argument("--timeout", type=float, default=300.0, help="Async poll timeout seconds")
    args = parser.parse_args()

    out: dict = {"api_base": API_BASE}
    with httpx.Client() as client:
        try:
            prereq = smoke_prerequisites(client)
            out["prerequisites"] = prereq
            _print_json("prerequisites", prereq)
            if not prereq.get("ffmpeg"):
                print("WARN: ffmpeg not on PATH — split will fail", file=sys.stderr)

            async_result = smoke_async_split(
                client,
                upload=args.upload,
                dry_run=args.dry_run,
                dividers=args.dividers,
                preset=args.preset,
                timeout_s=args.timeout,
            )
            out["async"] = async_result
            _print_json("async job", async_result)

            if args.sync:
                sync_result = smoke_sync_split(client)
                out["sync"] = sync_result
                _print_json("sync split", sync_result)
        except httpx.ConnectError:
            print(f"Cannot reach API at {API_BASE} — start TBCC backend first.", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"FAIL: {e}", file=sys.stderr)
            return 1

    print(json.dumps(out, indent=2))
    split = (out.get("async") or {}).get("split") or {}
    tiles = split.get("tile_count")
    print(f"\nOK — async job finished, tiles={tiles}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
