"""Smoke test: health, tags, LLM status, suggest (if key), subscription plan tag_ids round-trip.

Run from repo root:  python tbcc/tools/smoke_llm_shop.py
Requires API at http://127.0.0.1:8000 (override with TBCC_SMOKE_API).

Postgres: run `cd tbcc/backend && python -m alembic upgrade head` so `plan_tag_ids_json` exists
(revision 025_plan_tag_ids_json). SQLite dev auto-adds the column on startup.

LLM suggest returns 503 without OPENAI_API_KEY / TBCC_OPENAI_API_KEY (still counts as PASS).
With a key set on the API process, expect 200 from POST /llm/suggest-shop-product.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("TBCC_SMOKE_API", "http://127.0.0.1:8000").rstrip("/")


def req(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    url = f"{BASE}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            code = resp.status
            if not raw:
                return code, None
            return code, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {"detail": str(e)}
        except json.JSONDecodeError:
            parsed = {"detail": raw or str(e)}
        return e.code, parsed


def main() -> int:
    ok = True

    code, health = req("GET", "/health")
    print(f"GET /health -> {code}", health)
    if code != 200 or not isinstance(health, dict) or health.get("status") != "ok":
        print("FAIL: health")
        ok = False

    code, tags = req("GET", "/tags/")
    print(f"GET /tags/ -> {code} ({len(tags) if isinstance(tags, list) else 'n/a'} tags)")
    if code != 200 or not isinstance(tags, list) or not tags:
        print("FAIL: need at least one tag in DB for full smoke (create via POST /tags/)")
        ok = False
        tag_ids_sample: list[int] = []
    else:
        tag_ids_sample = [int(tags[0]["id"]), int(tags[1]["id"])] if len(tags) >= 2 else [int(tags[0]["id"])]

    code, st = req("GET", "/llm/status")
    print(f"GET /llm/status -> {code}", st)
    if code != 200:
        ok = False

    code, sug = req(
        "POST",
        "/llm/suggest-shop-product",
        {"name": "Smoke Test Product", "product_type": "bundle", "description": "Round-trip smoke."},
    )
    print(f"POST /llm/suggest-shop-product -> {code}", sug if code == 200 else sug)
    if code == 503:
        print("  (expected without OPENAI_API_KEY / TBCC_OPENAI_API_KEY)")
    elif code != 200:
        print("FAIL: unexpected suggest response")
        ok = False

    if not tag_ids_sample:
        print("SKIP: create/patch plan (no tag ids)")
        return 0 if ok else 1

    plan_name = "smoke-llm-shop-plan"
    code, plans = req("GET", "/subscription-plans/")
    existing_id = None
    if code == 200 and isinstance(plans, list):
        for p in plans:
            if isinstance(p, dict) and p.get("name") == plan_name:
                existing_id = p.get("id")
                break

    if existing_id is not None:
        code, patched = req(
            "PATCH",
            f"/subscription-plans/{existing_id}",
            {
                "description": "Smoke patch " + str(tag_ids_sample[0]),
                "tag_ids": tag_ids_sample,
                "description_variations": ["Variant A smoke", "Variant B smoke"],
            },
        )
        print(f"PATCH /subscription-plans/{existing_id} -> {code}", patched)
        if code != 200:
            ok = False
        elif isinstance(patched, dict):
            tid = patched.get("tag_ids") or [t.get("id") for t in (patched.get("tags") or [])]
            if set(map(int, tid)) != set(tag_ids_sample):
                print("FAIL: tag_ids round-trip on patch", tid, "expected", tag_ids_sample)
                ok = False
    else:
        code, created = req(
            "POST",
            "/subscription-plans/",
            {
                "name": plan_name,
                "price_stars": 1,
                "duration_days": 1,
                "product_type": "subscription",
                "description": "Smoke create",
                "tag_ids": tag_ids_sample,
                "description_variations": ["v1", "v2"],
                "is_active": False,
            },
        )
        print(f"POST /subscription-plans/ -> {code}", created)
        if code != 200:
            ok = False
        elif isinstance(created, dict):
            tid = created.get("tag_ids") or [t.get("id") for t in (created.get("tags") or [])]
            if set(map(int, tid)) != set(tag_ids_sample):
                print("FAIL: tag_ids round-trip on create", tid, "expected", tag_ids_sample)
                ok = False

    print("DONE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
