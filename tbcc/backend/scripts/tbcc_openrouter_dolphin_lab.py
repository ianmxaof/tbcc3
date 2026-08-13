#!/usr/bin/env python3
"""
OpenRouter Dolphin lab — list, probe, and interactive try-out.

Dolphin on OpenRouter is paid (cheap per token). The old :free slug 404s.

From tbcc/backend:

  py -3.13 scripts/tbcc_openrouter_dolphin_lab.py --list
  py -3.13 scripts/tbcc_openrouter_dolphin_lab.py --probe
  py -3.13 scripts/tbcc_openrouter_dolphin_lab.py --probe --compare-free
  py -3.13 scripts/tbcc_openrouter_dolphin_lab.py --repl

Requires TBCC_OPENROUTER_API_KEY in tbcc/.env.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

LAB_SYSTEM = (
    "You are Dolphin — direct, creative, low-refusal for adult marketing copy. "
    "Refuse only: minors, real-person NCIM, or violent crime how-tos."
)

LAB_CASES: tuple[tuple[str, str, str | None], ...] = (
    ("ping", "Reply with exactly: DOLPHIN_OK", "DOLPHIN_OK"),
    (
        "teaser",
        "Write one spicy teaser line for an adult Telegram VIP channel (no minors, no real names).",
        None,
    ),
    (
        "sales",
        "Draft exactly two short sentences DM-ing someone to try a free loot roll at @aof_lootgod_bot.",
        None,
    ),
)

COMPARE_HERMES = "nousresearch/hermes-3-llama-3.1-405b"


def _fetch_openrouter_models(*, api_key: str) -> list[dict]:
    import httpx

    r = httpx.get(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60.0,
    )
    r.raise_for_status()
    return list(r.json().get("data") or [])


def _dolphin_models_from_catalog(all_models: list[dict]) -> list[dict]:
    out = [m for m in all_models if "dolphin" in (m.get("id") or "").lower()]
    out.sort(key=lambda m: (m.get("id") or ""))
    return out


def _pricing_line(model_row: dict) -> str:
    pricing = model_row.get("pricing") or {}
    pin = pricing.get("prompt") or "?"
    pout = pricing.get("completion") or "?"
    return f"in=${pin}/tok out=${pout}/tok"


def cmd_list(api_key: str) -> int:
    from app.services.llm_completions import OPENROUTER_DOLPHIN_MODELS

    print("TBCC curated Dolphin slugs:")
    for mid in OPENROUTER_DOLPHIN_MODELS:
        print(f"  {mid}")
    print()
    try:
        catalog = _dolphin_models_from_catalog(_fetch_openrouter_models(api_key=api_key))
    except Exception as e:
        print(f"Live catalog fetch failed: {e}", file=sys.stderr)
        return 1
    if not catalog:
        print("OpenRouter returned 0 models matching 'dolphin'.")
        return 0
    print("OpenRouter live Dolphin catalog:")
    for row in catalog:
        mid = row.get("id") or "?"
        ctx = row.get("context_length") or "?"
        print(f"  {mid}")
        print(f"    context={ctx}  {_pricing_line(row)}")
    print()
    print("Tip: paid Dolphin is cheap — a full --probe run is usually well under $0.01.")
    return 0


def _run_probe_case(runtime, case_id: str, prompt: str, expect: str | None) -> dict:
    from app.services.llm_completions import complete_chat_text_sync

    t0 = time.perf_counter()
    messages = [
        {"role": "system", "content": LAB_SYSTEM},
        {"role": "user", "content": prompt},
    ]
    err: str | None = None
    text = ""
    try:
        text = complete_chat_text_sync(
            messages,
            model=runtime.model,
            max_tokens=256,
            temperature=0.85,
            timeout=120.0,
            runtime=runtime,
        )
    except Exception as e:
        err = str(e)
    elapsed = time.perf_counter() - t0
    ok = err is None
    if ok and expect:
        ok = expect.lower() in (text or "").lower()
    return {
        "case": case_id,
        "ok": ok,
        "elapsed_s": round(elapsed, 2),
        "error": err,
        "text": (text or "")[:500],
        "expect": expect,
    }


def _print_probe_result(model_id: str, result: dict) -> None:
    status = "PASS" if result["ok"] else "FAIL"
    print(f"  [{status}] {result['case']} ({result['elapsed_s']}s)")
    if result.get("error"):
        print(f"         error: {result['error'][:200]}")
    elif result.get("text"):
        snippet = result["text"].replace("\n", " ")[:180]
        print(f"         → {snippet}")


def cmd_probe(
    *,
    model: str,
    compare_free: bool,
    json_out: bool,
) -> int:
    from app.services.llm_completions import (
        OPENROUTER_DOLPHIN_MODELS,
        resolve_text_llm_runtime,
    )

    api_key = resolve_text_llm_runtime(provider="openrouter").api_key
    target = (model or "").strip() or OPENROUTER_DOLPHIN_MODELS[0]
    runtime = resolve_text_llm_runtime(provider="openrouter", model=target)

    report: dict = {"model": runtime.model, "cases": [], "compare": []}
    print(f"Probing model={runtime.model}")
    print(f"system={LAB_SYSTEM[:72]}…")
    print("—")
    for case_id, prompt, expect in LAB_CASES:
        res = _run_probe_case(runtime, case_id, prompt, expect)
        report["cases"].append(res)
        _print_probe_result(runtime.model, res)

    if compare_free:
        print("—")
        print(f"Compare (Hermes paid): {COMPARE_HERMES}")
        free_rt = resolve_text_llm_runtime(provider="openrouter", model=COMPARE_HERMES)
        _, teaser_prompt, _ = LAB_CASES[1]
        res = _run_probe_case(free_rt, "teaser", teaser_prompt, None)
        report["compare"].append({"model": COMPARE_HERMES, **res})
        _print_probe_result(COMPARE_HERMES, res)

    print("—")
    passed = sum(1 for c in report["cases"] if c["ok"])
    print(f"Done: {passed}/{len(report['cases'])} passed on {runtime.model}")

    if json_out:
        print(json.dumps(report, indent=2))
    return 0 if passed == len(report["cases"]) else 1


def cmd_repl(model: str | None) -> int:
    import subprocess

    from app.services.llm_completions import OPENROUTER_DOLPHIN_MODELS

    target = (model or "").strip() or OPENROUTER_DOLPHIN_MODELS[0]
    script = Path(__file__).resolve().parent / "tbcc_uncensored_chat.py"
    args = [
        sys.executable,
        str(script),
        "--allow-paid",
        "-m",
        target,
        "--system",
        LAB_SYSTEM,
    ]
    print(f"Starting REPL model={target} (Ctrl+C or /quit to exit)")
    return subprocess.call(args)


def main() -> int:
    ap = argparse.ArgumentParser(description="OpenRouter Dolphin lab (list / probe / repl)")
    ap.add_argument("--list", action="store_true", help="List Dolphin models on OpenRouter")
    ap.add_argument("--probe", action="store_true", help="Run ping + teaser + sales probes")
    ap.add_argument("--repl", action="store_true", help="Interactive chat REPL")
    ap.add_argument("-m", "--model", default=None, help="Dolphin model id override")
    ap.add_argument(
        "--compare-free",
        action="store_true",
        help="Also run teaser on Hermes (paid) for alignment contrast",
    )
    ap.add_argument("--json", action="store_true", help="Emit probe report JSON")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from app.services.llm_completions import openrouter_api_key

    if not openrouter_api_key():
        print(
            "Set TBCC_OPENROUTER_API_KEY in tbcc/.env (get one at https://openrouter.ai/keys).",
            file=sys.stderr,
        )
        return 2

    if args.list:
        return cmd_list(openrouter_api_key())
    if args.probe:
        return cmd_probe(model=args.model, compare_free=args.compare_free, json_out=args.json)
    if args.repl:
        return cmd_repl(args.model)

    # Default: list + probe (quick start)
    cmd_list(openrouter_api_key())
    print()
    return cmd_probe(model=args.model, compare_free=args.compare_free, json_out=False)


if __name__ == "__main__":
    raise SystemExit(main())
