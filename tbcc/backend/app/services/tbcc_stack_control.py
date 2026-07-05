"""TBCC Windows tray supervisor — single process control plane for API, flywheel, dashboard."""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BOT_SERVICE_IDS: dict[str, str] = {
    "payment_bot": "payment",
    "loot_bot": "loot",
    "secretary_bot": "secretary",
}

SERVICE_TITLE_TO_ID: dict[str, str] = {
    "tbcc-backend": "backend",
    "tbcc-dashboard": "dashboard",
    "tbcc-celery": "celery",
    "tbcc-celery-post": "celery_post",
    "tbcc-celery-post-scheduler": "celery_post_scheduler",
    "tbcc-beat": "beat",
    "tbcc-paymentbot": "payment",
    "tbcc-lootbot": "loot",
    "tbcc-secretarybot": "secretary",
    "tbcc-macrosearchbot": "macro_search",
    "tbcc-albumcomposer": "album_composer",
    "tbcc-companionbot": "companion",
    "tbcc-llmchatbot": "llm_chat",
    "tbcc-watchorganizer": "watch",
    "tbcc-nsfw-detect": "nsfw",
    "tbcc-lustpress": "lustpress",
    "tbcc-clip-categorize": "clip",
}

SCHEDULING_SERVICE_IDS = ("beat", "celery", "celery_post", "celery_post_scheduler")


def tbcc_root() -> Path:
    env = (os.getenv("TBCC_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    # backend/app/services -> tbcc
    return Path(__file__).resolve().parents[3]


def stack_cli_script() -> Path:
    return tbcc_root() / "scripts" / "tbcc-stack-cli.ps1"


def default_runtime_adapter() -> str:
    raw = (os.getenv("TBCC_BOT_RUNTIME_ADAPTER") or "").strip().lower()
    if raw in ("local", "command"):
        return raw
    if platform.system() == "Windows":
        return "command"
    return "local"


def stack_control_available() -> bool:
    return platform.system() == "Windows" and stack_cli_script().is_file()


def _powershell_cli_args(action: str, service_id: str = "") -> list[str]:
    root = str(tbcc_root())
    script = str(stack_cli_script())
    args = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        script,
        "-TbccRoot",
        root,
        "-Action",
        action,
    ]
    if service_id:
        args.extend(["-Service", service_id])
    return args


def invoke_stack_cli(action: str, service_id: str = "", *, timeout: int = 90) -> dict[str, Any]:
    if not stack_control_available():
        return {"ok": False, "error": "stack CLI unavailable (Windows + tbcc-stack-cli.ps1 required)"}
    try:
        proc = subprocess.run(
            _powershell_cli_args(action, service_id),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as e:
        logger.exception("stack cli %s %s failed", action, service_id)
        return {"ok": False, "error": str(e)[:300]}
    raw = (proc.stdout or "").strip()
    if not raw:
        return {
            "ok": False,
            "error": (proc.stderr or "empty stdout")[:300],
            "returncode": proc.returncode,
        }
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "ok": proc.returncode == 0,
            "message": raw[:500],
            "returncode": proc.returncode,
        }
    if proc.returncode != 0 and data.get("ok") is not False:
        data["ok"] = False
        data["returncode"] = proc.returncode
    return data


def get_stack_status() -> dict[str, Any]:
    return invoke_stack_cli("Status")


def restart_stack_service(service_id: str) -> dict[str, Any]:
    return invoke_stack_cli("Restart", service_id)


def start_stack_service(service_id: str) -> dict[str, Any]:
    return invoke_stack_cli("Start", service_id)


def stop_stack_service(service_id: str) -> dict[str, Any]:
    return invoke_stack_cli("Stop", service_id)


def bot_service_id(bot_key: str) -> str | None:
    return BOT_SERVICE_IDS.get((bot_key or "").strip().lower())


def bot_control_shell(action: str, bot_key: str) -> str:
    """Shell command for dashboard command adapter."""
    sid = bot_service_id(bot_key)
    if not sid:
        raise ValueError(f"unknown bot_key: {bot_key}")
    act = action.strip().lower()
    if act == "reload":
        act = "restart"
    ps_act = act[:1].upper() + act[1:]
    if ps_act not in ("Start", "Stop", "Restart", "Status"):
        raise ValueError(f"unsupported action: {action}")
    root = str(tbcc_root())
    script = str(stack_cli_script())
    return (
        f'powershell -NoProfile -ExecutionPolicy Bypass -File "{script}" '
        f'-TbccRoot "{root}" -Action {ps_act} -Service {sid}'
    )


def resolve_bot_runtime_commands(bot_key: str, cfg: dict[str, Any]) -> dict[str, str]:
    """Fill missing command adapter hooks with tray supervisor CLI."""
    out = {
        "start": str(cfg.get("start") or "").strip(),
        "stop": str(cfg.get("stop") or "").strip(),
        "restart": str(cfg.get("restart") or "").strip(),
        "reload": str(cfg.get("reload") or "").strip(),
        "status": str(cfg.get("status") or "").strip(),
    }
    if not stack_control_available():
        return out
    for action in ("start", "stop", "restart", "reload", "status"):
        key = "restart" if action == "reload" else action
        if not out[action]:
            try:
                out[action] = bot_control_shell(key if key != "reload" else "restart", bot_key)
            except ValueError:
                pass
    if not out["reload"]:
        out["reload"] = out.get("restart") or ""
    return out


def runtime_status_from_stack(bot_key: str) -> dict[str, Any] | None:
    sid = bot_service_id(bot_key)
    if not sid or not stack_control_available():
        return None
    data = invoke_stack_cli("Status", sid)
    if not data.get("ok"):
        return {
            "bot_key": bot_key,
            "status": "unknown",
            "pid": None,
            "adapter": "command",
            "message": data.get("error") or data.get("message"),
        }
    running = bool(data.get("running"))
    return {
        "bot_key": bot_key,
        "status": "running" if running else "stopped",
        "pid": None,
        "adapter": "command",
        "message": f"{data.get('title') or sid}: {data.get('status') or ('up' if running else 'down')}",
        "service_id": sid,
    }


def infer_service_id_from_event(event: dict[str, Any]) -> str | None:
    """Map error-hub / inbox service tag to tray service id."""
    meta = event.get("meta") or {}
    for raw in (
        meta.get("service_id"),
        meta.get("service"),
        event.get("service"),
        event.get("title"),
        (event.get("message") or "")[:200],
    ):
        if not raw:
            continue
        s = str(raw).strip()
        if s in BOT_SERVICE_IDS.values() or s in {
            "backend",
            "dashboard",
            "celery",
            "celery_post",
            "beat",
            "forum",
            "payment",
            "loot",
            "secretary",
        }:
            return s
        norm = re.sub(r"[^a-z0-9]", "", s.lower())
        # Rank match quality so an exact title always beats a partial containment:
        # exact (2) > needle contained in event text (1) > event text contained in a
        # longer needle (0). Without the tier, "TBCC-Celery-Post" would score the longer
        # "celery_post_scheduler" needle higher purely on length and mis-route.
        best: tuple[int, int, str] | None = None
        for needle, sid in SERVICE_TITLE_TO_ID.items():
            needle_norm = re.sub(r"[^a-z0-9]", "", needle.lower())
            if norm == needle_norm:
                tier = 2
            elif needle_norm in norm:
                tier = 1
            elif norm in needle_norm:
                tier = 0
            else:
                continue
            score = (tier, len(needle_norm))
            if best is None or score > best[:2]:
                best = (tier, len(needle_norm), sid)
        if best:
            return best[2]
    body = str(event.get("body") or event.get("message") or "").lower()
    if "celery-post" in body or "celery_post" in body:
        return "celery_post"
    if "tbcc-beat" in body or "celery beat" in body:
        return "beat"
    if "tbcc-celery" in body:
        return "celery"
    if "tbcc-backend" in body or ":8000" in body:
        return "backend"
    if "payment" in body:
        return "payment"
    if "loot" in body:
        return "loot"
    if "secretary" in body:
        return "secretary"
    return None


def restart_scheduling_stack() -> dict[str, Any]:
    script = tbcc_root() / "scripts" / "_start-scheduling-stack.ps1"
    if not script.is_file():
        results = []
        for sid in SCHEDULING_SERVICE_IDS:
            results.append(restart_stack_service(sid))
        return {"ok": all(r.get("ok") for r in results), "results": results}
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(tbcc_root()),
        )
        return {
            "ok": proc.returncode == 0,
            "stdout": (proc.stdout or "")[-500:],
            "stderr": (proc.stderr or "")[-500:],
            "returncode": proc.returncode,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def force_restart_scheduling_stack() -> dict[str, Any]:
    """Stop+start Beat, Celery-Post, Celery-Post-Scheduler even when PIDs exist (Windows tray)."""
    script = tbcc_root() / "scripts" / "_force-restart-scheduling-stack.ps1"
    if not script.is_file():
        order = ("beat", "celery_post", "celery_post_scheduler")
        results = [restart_stack_service(sid) for sid in order]
        return {"ok": all(r.get("ok") for r in results), "results": results, "mode": "fallback"}
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(tbcc_root()),
        )
        return {
            "ok": proc.returncode == 0,
            "mode": "force",
            "stdout": (proc.stdout or "")[-500:],
            "stderr": (proc.stderr or "")[-500:],
            "returncode": proc.returncode,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def execute_flywheel_stack_action(action: str, event: dict[str, Any], *, reg: dict[str, Any]) -> dict[str, Any]:
    if action == "restart_scheduling_stack":
        return restart_scheduling_stack()
    if action == "restart_stack_service":
        sid = str(reg.get("service_id") or "").strip() or infer_service_id_from_event(event)
        body = str(event.get("body") or event.get("message") or "").lower()
        svc = str(event.get("service") or "").lower()
        if not sid and ("409" in body or "getupdates" in body or "conflict" in body):
            if "loot" in svc or "loot" in body:
                sid = "loot"
            elif "secretary" in svc or "secretary" in body:
                sid = "secretary"
            elif "payment" in svc or "payment" in body:
                sid = "payment"
        if not sid:
            return restart_scheduling_stack()
        return restart_stack_service(sid)
    return {"ok": False, "error": f"unknown stack action: {action}"}
