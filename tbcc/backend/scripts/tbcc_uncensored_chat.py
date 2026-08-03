#!/usr/bin/env python3
"""
Free-only OpenRouter uncensored / low-alignment chat CLI (TBCC llm_completions).

Default path is $0 cloud only:
  provider=openrouter + models ending in :free (or openrouter/free)

Uses your existing TBCC_OPENROUTER_API_KEY. Featherless/Venice paid hosts are
opt-in via --allow-paid (not the default).

Examples (from tbcc/backend):

  py -3.13 scripts/tbcc_uncensored_chat.py
  py -3.13 scripts/tbcc_uncensored_chat.py --list-free
  py -3.13 scripts/tbcc_uncensored_chat.py -m nousresearch/hermes-3-llama-3.1-405b:free
  py -3.13 scripts/tbcc_uncensored_chat.py --once "Write a filthy one-liner for a loot roll"
  py -3.13 scripts/tbcc_uncensored_chat.py --verify

REPL: /quit /clear /model <id> /models /system <text> /help
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils.load_tbcc_dotenv import load_tbcc_dotenv

load_tbcc_dotenv()

DEFAULT_SYSTEM = (
    "You are a direct, capable assistant. Prefer honest, uncensored answers for adult "
    "creative and technical work. Refuse only: sexual content involving minors, "
    "real-world violent crime assistance, or non-consensual intimate imagery of real people."
)


def _build_runtime(args: argparse.Namespace):
    from app.services.llm_completions import (
        FREE_OPENROUTER_CHAT_MODELS,
        assert_free_only_runtime,
        resolve_text_llm_runtime,
    )

    provider = args.provider
    if not provider and not args.allow_paid:
        provider = "openrouter"
    model = args.model
    if not model and not args.allow_paid:
        model = FREE_OPENROUTER_CHAT_MODELS[0]

    runtime = resolve_text_llm_runtime(
        provider=provider,
        model=model,
        api_key=args.api_key,
        base_url=args.base_url,
    )
    if not args.allow_paid:
        assert_free_only_runtime(runtime)
    return runtime


def _with_model(runtime, model: str):
    from app.services.llm_completions import TextLlmRuntime

    return TextLlmRuntime(
        provider=runtime.provider,
        api_key=runtime.api_key,
        model=model,
        base_url=runtime.base_url,
        referer=runtime.referer,
        title=runtime.title,
    )


def _chat_once(runtime, messages: list[dict], *, max_tokens: int, temperature: float, timeout: float) -> str:
    from app.services.llm_completions import complete_chat_text_sync

    return complete_chat_text_sync(
        messages,
        model=runtime.model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        runtime=runtime,
    )


def _chat_with_free_fallback(
    runtime,
    messages: list[dict],
    *,
    max_tokens: int,
    temperature: float,
    timeout: float,
    allow_paid: bool,
) -> tuple[object, str]:
    """Try current model; on 429/rate-limit, walk free OpenRouter chain."""
    from app.services.llm_completions import free_openrouter_fallback_models

    if allow_paid or runtime.provider != "openrouter":
        return runtime, _chat_once(
            runtime,
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
        )

    chain = free_openrouter_fallback_models(runtime.model)
    last_err: Exception | None = None
    for mid in chain:
        rt = _with_model(runtime, mid)
        try:
            out = _chat_once(
                rt,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
            )
            if mid != runtime.model:
                print(f"(fallback model={mid})", file=sys.stderr)
            return rt, out
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "429" in msg or "rate" in msg or "temporarily" in msg:
                print(f"(rate-limited on {mid}; trying next free model)", file=sys.stderr)
                continue
            raise
    raise last_err or RuntimeError("all free OpenRouter models failed")


def _print_banner(runtime, *, free_only: bool) -> None:
    from app.services.llm_completions import chat_completions_url

    url = chat_completions_url(runtime)
    mode = "free-only" if free_only else "allow-paid"
    print(f"provider={runtime.provider}  model={runtime.model}  [{mode}]")
    print(f"endpoint={url}")
    print("Commands: /quit  /clear  /model <id>  /models  /system <text>  /help")
    print("—")


def _list_free() -> int:
    from app.services.llm_completions import FREE_OPENROUTER_CHAT_MODELS

    print("Curated free OpenRouter chat models (TBCC default order):")
    for mid in FREE_OPENROUTER_CHAT_MODELS:
        note = ""
        if "dolphin" in mid:
            note = "  # use tbcc-dolphin-lab.ps1 — Dolphin is paid on OpenRouter now"
        elif "hermes" in mid:
            note = "  # less aligned than stock Llama; good post-Dolphin fallback"
        elif mid == "openrouter/free":
            note = "  # OpenRouter auto-picks any free model"
        print(f"  {mid}{note}")
    print()
    print("Live catalog tip: any OpenRouter id ending in :free is $0 (rate-limited).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="TBCC free-only OpenRouter chat CLI (uncensored when the free model allows)"
    )
    ap.add_argument(
        "-p",
        "--provider",
        default=None,
        help="default openrouter (free-only). Paid hosts need --allow-paid",
    )
    ap.add_argument("-m", "--model", default=None, help="Model id (prefer *:free)")
    ap.add_argument("--api-key", default=None, help="Override API key (prefer env)")
    ap.add_argument("--base-url", default=None, help="Override OpenAI-compatible base URL")
    ap.add_argument("--system", default=None, help="System prompt override")
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--temperature", type=float, default=0.85)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--once", default=None, help="Single prompt (non-interactive) then exit")
    ap.add_argument("--verify", action="store_true", help="Ping with a tiny hello and exit")
    ap.add_argument(
        "--list-free",
        action="store_true",
        help="Print curated free OpenRouter models and exit",
    )
    ap.add_argument(
        "--allow-paid",
        action="store_true",
        help="Allow Featherless/Venice/paid OpenRouter models (not free-only)",
    )
    ap.add_argument(
        "--no-fallback",
        action="store_true",
        help="Do not walk the free model chain on 429",
    )
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")

    if args.list_free:
        return _list_free()

    try:
        runtime = _build_runtime(args)
    except RuntimeError as e:
        print(f"Config error: {e}", file=sys.stderr)
        print(
            "Free path: set TBCC_OPENROUTER_API_KEY (already in tbcc/.env for most TBCC installs). "
            "Run --list-free for $0 model ids. Featherless is paid now — not the default.",
            file=sys.stderr,
        )
        return 2

    system = (args.system or "").strip() or DEFAULT_SYSTEM
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    free_only = not args.allow_paid

    def _ask(prompt: str) -> str:
        nonlocal runtime
        msgs = [*messages, {"role": "user", "content": prompt}]
        if args.no_fallback:
            return _chat_once(
                runtime,
                msgs,
                max_tokens=min(256, args.max_tokens) if args.verify else args.max_tokens,
                temperature=args.temperature,
                timeout=args.timeout,
            )
        runtime, out = _chat_with_free_fallback(
            runtime,
            msgs,
            max_tokens=min(256, args.max_tokens) if args.verify else args.max_tokens,
            temperature=args.temperature,
            timeout=args.timeout,
            allow_paid=args.allow_paid,
        )
        return out

    if args.verify or args.once is not None:
        prompt = args.once if args.once is not None else "Reply with exactly: ok"
        try:
            print(_ask(prompt))
        except Exception as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        return 0

    _print_banner(runtime, free_only=free_only)
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not user:
            continue
        if user in ("/quit", "/exit", "/q"):
            return 0
        if user == "/help":
            print(" /quit /clear /model <id> /models /system <text> /help")
            continue
        if user == "/models":
            _list_free()
            continue
        if user == "/clear":
            messages = [{"role": "system", "content": system}]
            print("(history cleared)")
            continue
        if user.startswith("/model "):
            new_m = user[len("/model ") :].strip()
            if not new_m:
                print(f"model={runtime.model}")
                continue
            from app.services.llm_completions import assert_free_only_runtime, is_openrouter_free_model

            candidate = _with_model(runtime, new_m)
            if free_only:
                try:
                    assert_free_only_runtime(candidate)
                except RuntimeError as e:
                    print(f"ERROR: {e}", file=sys.stderr)
                    continue
            elif not is_openrouter_free_model(new_m) and runtime.provider == "openrouter":
                print("(warning: model is not :free — may bill OpenRouter credits)", file=sys.stderr)
            runtime = candidate
            print(f"model={runtime.model}")
            continue
        if user.startswith("/system "):
            system = user[len("/system ") :].strip() or DEFAULT_SYSTEM
            messages = [{"role": "system", "content": system}]
            print("(system updated; history cleared)")
            continue

        messages.append({"role": "user", "content": user})
        try:
            if args.no_fallback:
                out = _chat_once(
                    runtime,
                    messages,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                    timeout=args.timeout,
                )
            else:
                runtime, out = _chat_with_free_fallback(
                    runtime,
                    messages,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                    timeout=args.timeout,
                    allow_paid=args.allow_paid,
                )
        except Exception as e:
            messages.pop()
            print(f"ERROR: {e}", file=sys.stderr)
            continue
        messages.append({"role": "assistant", "content": out})
        print()
        print(out)
        print()


if __name__ == "__main__":
    raise SystemExit(main())
