"""Upload SFW promo images → R2 or ImgBB and append aof_x_promo_image_pool.json.

Run from tbcc/backend:

  py -3.13 scripts/upload_x_promo_pool.py --folder C:\\path\\to\\images --preview
  py -3.13 scripts/upload_x_promo_pool.py --folder C:\\path\\to\\images --execute
  py -3.13 scripts/upload_x_promo_pool.py --file premium-pack-purple.jpg --execute --provider imgbb
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

from app.services.r2_promo_upload import (  # noqa: E402
    append_pool_entries,
    iter_image_paths,
    pool_json_path,
    r2_config,
    upload_promo_image,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Upload X promo images and update pool JSON")
    p.add_argument("--folder", type=Path, help="Directory of jpg/png/webp/gif files")
    p.add_argument("--file", type=Path, action="append", dest="files", help="Single image (repeatable)")
    p.add_argument("--provider", choices=("auto", "r2", "imgbb"), default="auto")
    p.add_argument("--label-prefix", default="", help="Optional label prefix for pool entries")
    p.add_argument("--preview", action="store_true", help="Dry run — no upload or JSON write")
    p.add_argument("--execute", action="store_true", help="Upload and append pool JSON")
    args = p.parse_args()

    paths: list[Path] = []
    if args.folder:
        paths.extend(iter_image_paths(args.folder))
    for f in args.files or []:
        if f.is_file():
            paths.append(f)
    if not paths:
        print("ERROR: pass --folder or --file", file=sys.stderr)
        sys.exit(1)

    cfg = r2_config()
    print("pool file:", pool_json_path(), file=sys.stderr)
    print("r2 configured:", bool(cfg), file=sys.stderr)
    if cfg:
        print(f"  bucket: {cfg['bucket']}", file=sys.stderr)
        print(f"  public base: {cfg['public_base']}", file=sys.stderr)
    print("files:", len(paths), file=sys.stderr)

    if not args.preview and not args.execute:
        print("Pass --preview or --execute", file=sys.stderr)
        sys.exit(1)

    new_entries: list[dict[str, str]] = []
    for path in paths:
        label = f"{args.label_prefix}{path.stem}".strip("-_ ")
        if args.preview:
            print(f"[preview] {path.name} → would upload via {args.provider}")
            continue
        result = upload_promo_image(path, provider=args.provider)
        entry: dict[str, str] = {
            "label": label or path.stem,
            "direct_url": result["direct_url"],
        }
        if result.get("viewer_url"):
            entry["viewer_url"] = result["viewer_url"]
        new_entries.append(entry)
        print(f"OK {path.name}")
        print(f"  direct_url: {entry['direct_url']}")

    if args.execute and new_entries:
        out = append_pool_entries(new_entries, dry_run=False)
        print(f"Updated pool ({len(new_entries)} new): {out}")


if __name__ == "__main__":
    main()
