#!/usr/bin/env python3
"""Local folder / Explorer context-menu AOF promo watermark burn-in.

Examples:
  cd tbcc/backend
  py -3.13 scripts/watermark_local.py analyze "D:/staging/clips"
  py -3.13 scripts/watermark_local.py apply "D:/staging/clips"
  py -3.13 scripts/watermark_local.py apply --files clip1.mp4 photo.jpg
  py -3.13 scripts/watermark_local.py apply "D:/out" --output-dir "D:/watermarked"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.local_media_watermark import (  # noqa: E402
    collect_media_paths,
    ensure_local_watermark_defaults,
    format_scan_report,
    scan_media_folder,
)


def _configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _notify_windows(title: str, message: str, *, error: bool = False) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        icon = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(0, message, title, icon)
    except Exception:
        pass


def _print_progress(index: int, total: int, result) -> None:
    label = result.path.name
    if result.ok and result.changed:
        status = "OK"
    elif result.ok:
        status = "SKIP"
    else:
        status = "FAIL"
    detail = result.message or status
    print(f"[{index}/{total}] {status}: {label} — {detail}", flush=True)


def cmd_analyze(args: argparse.Namespace) -> int:
    scan = scan_media_folder(args.folder, recursive=not args.no_recursive, max_files=args.max_files)
    print(format_scan_report(scan, list_limit=args.list_limit))
    if scan.skipped and args.verbose:
        print("\nSkipped:")
        for item in scan.skipped[: args.list_limit]:
            print(f"  {item}")
    return 0 if scan.ok else 1


def cmd_apply(args: argparse.Namespace) -> int:
    ensure_local_watermark_defaults()

    if args.files:
        scan = collect_media_paths(args.files)
    else:
        if not args.folder:
            print("ERROR: provide a folder path or --files", file=sys.stderr)
            return 2
        scan = scan_media_folder(args.folder, recursive=not args.no_recursive, max_files=args.max_files)

    if not scan.ok:
        print("No supported media files found.", file=sys.stderr)
        if args.notify:
            _notify_windows("TBCC Watermark", "No supported image/video files found.", error=True)
        return 1

    if args.dry_run:
        print(format_scan_report(scan, list_limit=args.list_limit))
        print("\nDry run — no files modified.")
        return 0

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output: {output_dir}")
    else:
        print(f"Overwrite in place ({len(scan.files)} file(s))")

    def _dest_for(path: Path) -> Path | None:
        if output_dir is None:
            return None
        if scan.root is not None:
            return output_dir / path.relative_to(scan.root)
        return output_dir / path.name

    from app.services.local_media_watermark import WatermarkBatchResult, watermark_file

    batch = WatermarkBatchResult()
    total = len(scan.files)
    for index, path in enumerate(scan.files, start=1):
        result = watermark_file(
            path,
            output_path=_dest_for(path),
            max_video_mb=args.max_video_mb,
        )
        batch.results.append(result)
        _print_progress(index, total, result)
    print(batch.summary(), flush=True)

    if args.notify:
        _notify_windows("TBCC Watermark", batch.summary(), error=batch.failed > 0)

    return 1 if batch.failed else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Analyze or watermark local images/videos with AOF promo burn-in.")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-recursive", action="store_true", help="Only top-level files in folder")
    common.add_argument("--max-files", type=int, default=None, help="Cap number of files processed")
    common.add_argument("--list-limit", type=int, default=40, help="Rows shown in analyze output")
    common.add_argument("--verbose", action="store_true")

    analyze = sub.add_parser("analyze", parents=[common], help="List media in folder without modifying")
    analyze.add_argument("folder", type=Path)
    analyze.set_defaults(func=cmd_analyze)

    apply = sub.add_parser("apply", parents=[common], help="Watermark folder contents or explicit files")
    apply.add_argument("folder", nargs="?", type=Path, default=None, help="Folder to scan")
    apply.add_argument("--files", nargs="+", default=None, help="Explicit file/folder paths (Explorer menu)")
    apply.add_argument("--dry-run", action="store_true", help="Analyze only")
    apply.add_argument(
        "--output-dir",
        default=None,
        help="Write watermarked copies here instead of overwriting originals",
    )
    apply.add_argument("--max-video-mb", type=int, default=None, help="Override TBCC_WATERMARK_MAX_VIDEO_MB")
    apply.add_argument("--notify", action="store_true", help="Windows message box when finished")
    apply.set_defaults(func=cmd_apply)

    return p


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
