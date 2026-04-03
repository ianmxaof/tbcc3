"""
Copy TBCC data from SQLite into PostgreSQL.

When you switch DATABASE_URL from SQLite to Postgres, Alembic creates empty tables;
your old rows stay in tbcc.db unless you copy them.

  cd tbcc/backend
  python scripts/sqlite_to_postgres.py
  python scripts/sqlite_to_postgres.py --dry-run

Uses tbcc/.env DATABASE_URL as the Postgres target. Override with --target-url / SQLITE_URL.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# tbcc/backend/scripts -> tbcc
_TBCC_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_TBCC_ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(_TBCC_ROOT / "backend"))

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

load_dotenv(_TBCC_ROOT / ".env")

# FK-safe insert order (parents before children)
_TABLE_ORDER = [
    "channels",
    "bots",
    "content_pools",
    "sources",
    "media",
    "subscription_plans",
    "subscriptions",
    "external_payment_orders",
    "referral_tracking",
    "referral_codes",
    "subscription_milestones",
    "scheduled_text_posts",
]


def _connect_sqlite(url: str) -> Engine:
    return create_engine(url, connect_args={"check_same_thread": False})


def _common_columns(src_insp, dst_insp, table: str) -> list[str]:
    if table not in src_insp.get_table_names():
        return []
    if table not in dst_insp.get_table_names():
        return []
    src_names = {c["name"] for c in src_insp.get_columns(table)}
    return [c["name"] for c in dst_insp.get_columns(table) if c["name"] in src_names]


def _copy_table(
    src: Engine,
    dst: Engine,
    table: str,
    columns: list[str],
    dry_run: bool,
) -> int:
    if not columns:
        return 0
    cols_sql = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(f":{c}" for c in columns)
    sel = text(f"SELECT {cols_sql} FROM {table}")
    with src.connect() as sconn:
        rows = sconn.execute(sel).mappings().all()
    if not rows:
        return 0
    if dry_run:
        return len(rows)
    ins = text(f'INSERT INTO "{table}" ({cols_sql}) VALUES ({placeholders})')
    with dst.begin() as dconn:
        for row in rows:
            dconn.execute(ins, dict(row))
    return len(rows)


def _reset_all_sequences(dst: Engine) -> None:
    insp = inspect(dst)
    for table in _TABLE_ORDER:
        if table not in insp.get_table_names():
            continue
        cols = {c["name"] for c in insp.get_columns(table)}
        if "id" not in cols:
            continue
        with dst.begin() as conn:
            try:
                conn.execute(
                    text(
                        f"""
                        SELECT setval(
                            pg_get_serial_sequence('{table}', 'id'),
                            COALESCE((SELECT MAX(id) FROM "{table}"), 0),
                            true
                        )
                        """
                    )
                )
            except Exception:
                pass


def main() -> int:
    p = argparse.ArgumentParser(description="Copy TBCC SQLite data into PostgreSQL")
    p.add_argument(
        "--sqlite-url",
        default=os.getenv("SQLITE_URL", "sqlite:///./tbcc.db"),
        help="Source SQLite URL (default: sqlite:///./tbcc.db relative to cwd)",
    )
    p.add_argument(
        "--target-url",
        default=os.getenv("DATABASE_URL"),
        help="Target Postgres URL (default: DATABASE_URL from tbcc/.env)",
    )
    p.add_argument("--dry-run", action="store_true", help="Only report row counts")
    args = p.parse_args()

    if not args.target_url or not args.target_url.startswith("postgresql"):
        print("DATABASE_URL must be a postgresql:// URL for the target.", file=sys.stderr)
        return 1

    src = _connect_sqlite(args.sqlite_url)
    dst = create_engine(args.target_url)

    src_insp = inspect(src)
    dst_insp = inspect(dst)

    if not src_insp.get_table_names():
        print(f"No tables in SQLite ({args.sqlite_url}). Wrong path or empty file.", file=sys.stderr)
        return 1

    total = 0
    for table in _TABLE_ORDER:
        cols = _common_columns(src_insp, dst_insp, table)
        if not cols:
            continue
        n = _copy_table(src, dst, table, cols, args.dry_run)
        if n:
            print(f"  {table}: {n} rows" + (" (dry-run)" if args.dry_run else ""))
        total += n

    if not args.dry_run and total > 0:
        _reset_all_sequences(dst)
        print(f"Done. Copied {total} rows total. Sequences adjusted for id columns.")
    elif args.dry_run:
        print(f"Dry-run: would copy {total} rows total.")
    else:
        print("No overlapping tables/columns to copy (or SQLite empty).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
