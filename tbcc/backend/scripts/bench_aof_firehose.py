"""Bench: local lane-hub firehose timing — a lane folder (e.g. Unsorted) -> Storage Hub.

Exercises the real pipeline (``deposit_local_files_batch``) so numbers reflect actual
Telethon I/O under the batched single-session path (I1/I4), not a synthetic stand-in.
Wraps ``_do_upload`` with a stopwatch to report a true per-item median even though the
whole run shares one Telethon session.

Usage (from tbcc/backend, with the operator's local AOF NETWORK tree + Telegram admin
session available — same session the local lane-hub daemon uses):
    py -3.13 scripts/bench_aof_firehose.py --count 10 --lane inbox
    py -3.13 scripts/bench_aof_firehose.py --count 10 --lane ass --dry-run

Not for CI / cloud — requires real local media + a live admin.session.
"""
from __future__ import annotations

import argparse
import statistics
import time


def main() -> int:
    p = argparse.ArgumentParser(description="Time N lane-folder -> Storage Hub uploads")
    p.add_argument("--count", type=int, default=10, help="max files to upload")
    p.add_argument("--lane", default="inbox", help="network_key, e.g. inbox (Unsorted), ass, ...")
    p.add_argument("--dry-run", action="store_true", help="Prep only (stability+hash), no Telegram upload")
    p.add_argument("--stable-wait-s", type=float, default=0.5, help="matches TBCC_WATCH_AOF_FAST default")
    args = p.parse_args()

    from app.services import local_lane_hub_deposit as lld
    from app.services.local_lane_hub_map import lane_watch_targets

    targets = {t.network_key: t for t in lane_watch_targets()}
    target = targets.get(args.lane.strip().lower())
    if not target:
        print(f"lane '{args.lane}' not found -- available: {sorted(targets)}")
        return 2
    if not target.folder_path.is_dir():
        print(f"lane folder missing: {target.folder_path}")
        return 2

    entries = [e for e in sorted(target.folder_path.rglob("*")) if e.is_file()][: args.count]
    if not entries:
        print(f"no files found under {target.folder_path}")
        return 2

    timings: list[float] = []
    orig_do_upload = lld._do_upload

    async def _timed_do_upload(storage, **kwargs):
        t0 = time.monotonic()
        try:
            return await orig_do_upload(storage, **kwargs)
        finally:
            timings.append(time.monotonic() - t0)

    lld._do_upload = _timed_do_upload
    try:
        t_start = time.monotonic()
        results = lld.deposit_local_files_batch(
            entries,
            stable_wait_s=args.stable_wait_s,
            dry_run=args.dry_run,
            target=target,
        )
        wall_s = time.monotonic() - t_start
    finally:
        lld._do_upload = orig_do_upload

    ok = sum(1 for r in results if r[0])
    skipped = [r for r in results if not r[0]]
    print(
        f"lane={args.lane} files={len(entries)} uploaded_ok={ok} skipped_or_errored={len(skipped)} "
        f"wall_s={wall_s:.2f} wall_seconds_per_file={wall_s / max(1, len(entries)):.2f}"
    )
    if timings:
        median = statistics.median(timings)
        print(
            f"per_upload_seconds: median={median:.2f} min={min(timings):.2f} "
            f"max={max(timings):.2f} n={len(timings)}"
        )
        print(f"median_seconds_per_upload={median:.2f}")
        if median > 5.0:
            print("FAIL: median_seconds_per_upload above 5.0s target")
            return 1
        print("PASS: median_seconds_per_upload <= 5.0s target")
    else:
        print("no uploads timed (all skipped/dry-run/already-uploaded) -- rerun against fresh files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
