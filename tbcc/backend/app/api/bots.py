from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.common import orm_to_dict
from app.services.payment_bot_settings_effective import get_effective_payment_bot_settings
from app.services.loot_bot_settings_effective import get_effective_loot_bot_settings

router = APIRouter()
_LOCAL_PROCS: dict[str, subprocess.Popen] = {}


def _backend_root() -> Path:
    # backend/app/api/bots.py -> parents: api, app, backend
    return Path(__file__).resolve().parent.parent.parent


def _proc_alive(name: str) -> bool:
    p = _LOCAL_PROCS.get(name)
    return bool(p and p.poll() is None)


def _runtime_cfg(db: Session) -> dict:
    try:
        eff = get_effective_payment_bot_settings(db)
    except Exception:
        eff = {}
    return {
        "adapter": (eff.get("runtime_adapter") or os.getenv("TBCC_BOT_RUNTIME_ADAPTER") or "local").strip().lower(),
        "start": (eff.get("runtime_cmd_start") or os.getenv("TBCC_PAYMENT_BOT_CMD_START") or "").strip(),
        "stop": (eff.get("runtime_cmd_stop") or os.getenv("TBCC_PAYMENT_BOT_CMD_STOP") or "").strip(),
        "restart": (eff.get("runtime_cmd_restart") or os.getenv("TBCC_PAYMENT_BOT_CMD_RESTART") or "").strip(),
        "reload": (eff.get("runtime_cmd_reload") or os.getenv("TBCC_PAYMENT_BOT_CMD_RELOAD") or "").strip(),
        "status": (eff.get("runtime_cmd_status") or os.getenv("TBCC_PAYMENT_BOT_CMD_STATUS") or "").strip(),
    }


def _runtime_adapter(db: Session) -> str:
    v = _runtime_cfg(db)["adapter"]
    return v if v in ("local", "command") else "local"


def _loot_runtime_cfg(db: Session) -> dict:
    try:
        eff = get_effective_loot_bot_settings(db)
    except Exception:
        eff = {}
    return {
        "adapter": (eff.get("runtime_adapter") or os.getenv("TBCC_BOT_RUNTIME_ADAPTER") or "local").strip().lower(),
        "start": (eff.get("runtime_cmd_start") or os.getenv("TBCC_LOOT_BOT_CMD_START") or "").strip(),
        "stop": (eff.get("runtime_cmd_stop") or os.getenv("TBCC_LOOT_BOT_CMD_STOP") or "").strip(),
        "restart": (eff.get("runtime_cmd_restart") or os.getenv("TBCC_LOOT_BOT_CMD_RESTART") or "").strip(),
        "reload": (eff.get("runtime_cmd_reload") or os.getenv("TBCC_LOOT_BOT_CMD_RELOAD") or "").strip(),
        "status": (eff.get("runtime_cmd_status") or os.getenv("TBCC_LOOT_BOT_CMD_STATUS") or "").strip(),
    }


def _loot_runtime_adapter(db: Session) -> str:
    v = _loot_runtime_cfg(db)["adapter"]
    return v if v in ("local", "command") else "local"


def _run_command(action: str, db: Session, cfg: dict | None = None) -> dict:
    cfg = cfg if cfg is not None else _runtime_cfg(db)
    cmd = str(cfg.get(action) or "").strip()
    if not cmd:
        raise HTTPException(status_code=400, detail=f"No command configured for action '{action}'.")
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    out = (p.stdout or "").strip()
    err = (p.stderr or "").strip()
    if p.returncode != 0:
        raise HTTPException(
            status_code=502,
            detail=f"Command failed (exit {p.returncode}): {err or out or 'no output'}",
        )
    return {"ok": True, "status": "unknown", "pid": None, "message": out or f"{action} command executed"}


def _bot_runtime_status_local(name: str) -> dict:
    p = _LOCAL_PROCS.get(name)
    if p and p.poll() is None:
        return {
            "bot_key": name,
            "status": "running",
            "pid": p.pid,
            "adapter": "local",
        }
    return {"bot_key": name, "status": "stopped", "pid": None, "adapter": "local"}


def _bot_runtime_status(name: str, db: Session) -> dict:
    adapter = _loot_runtime_adapter(db) if name == "loot_bot" else _runtime_adapter(db)
    if adapter == "local":
        return _bot_runtime_status_local(name)
    cfg = _loot_runtime_cfg(db) if name == "loot_bot" else _runtime_cfg(db)
    status_cmd = cfg.get("status") or ""
    if status_cmd:
        r = _run_command("status", db, cfg)
        msg = str(r.get("message") or "").lower()
        status = "running" if any(x in msg for x in ("running", "active", "up")) else "unknown"
        if any(x in msg for x in ("stopped", "inactive", "down")):
            status = "stopped"
        return {"bot_key": name, "status": status, "pid": None, "adapter": "command", "message": r.get("message")}
    return {"bot_key": name, "status": "unknown", "pid": None, "adapter": "command", "message": "no status command configured"}


def _start_payment_bot(db: Session) -> dict:
    if _runtime_adapter(db) == "command":
        return _run_command("start", db)
    if _proc_alive("payment_bot"):
        p = _LOCAL_PROCS["payment_bot"]
        return {"ok": True, "status": "running", "pid": p.pid, "message": "already running"}
    cwd = _backend_root()
    args = [sys.executable, "-m", "bots.payment_bot"]
    p = subprocess.Popen(args, cwd=str(cwd))
    _LOCAL_PROCS["payment_bot"] = p
    return {"ok": True, "status": "running", "pid": p.pid}


def _stop_payment_bot(db: Session) -> dict:
    if _runtime_adapter(db) == "command":
        return _run_command("stop", db)
    p = _LOCAL_PROCS.get("payment_bot")
    if not p or p.poll() is not None:
        return {"ok": True, "status": "stopped", "pid": None, "message": "already stopped"}
    try:
        p.terminate()
        p.wait(timeout=8)
    except Exception:
        p.kill()
    return {"ok": True, "status": "stopped", "pid": None}


def _start_loot_bot(db: Session) -> dict:
    if _loot_runtime_adapter(db) == "command":
        return _run_command("start", db, _loot_runtime_cfg(db))
    if _proc_alive("loot_bot"):
        p = _LOCAL_PROCS["loot_bot"]
        return {"ok": True, "status": "running", "pid": p.pid, "message": "already running"}
    cwd = _backend_root()
    args = [sys.executable, "-m", "bots.loot_bot"]
    p = subprocess.Popen(args, cwd=str(cwd))
    _LOCAL_PROCS["loot_bot"] = p
    return {"ok": True, "status": "running", "pid": p.pid}


def _stop_loot_bot(db: Session) -> dict:
    if _loot_runtime_adapter(db) == "command":
        return _run_command("stop", db, _loot_runtime_cfg(db))
    p = _LOCAL_PROCS.get("loot_bot")
    if not p or p.poll() is not None:
        return {"ok": True, "status": "stopped", "pid": None, "message": "already stopped"}
    try:
        p.terminate()
        p.wait(timeout=8)
    except Exception:
        p.kill()
    return {"ok": True, "status": "stopped", "pid": None}


@router.get("/")
def list_bots(db: Session = Depends(get_db)):
    from app.models.bot import Bot
    rows = [orm_to_dict(b) for b in db.query(Bot).all()]
    runtime = _bot_runtime_status("payment_bot", db)
    if not any(str(r.get("name") or "").lower() == "payment_bot" for r in rows):
        rows.append(
            {
                "id": "runtime:payment_bot",
                "name": "payment_bot",
                "role": "payment",
                "status": runtime["status"],
                "last_seen": None,
                "pid": runtime.get("pid"),
                "adapter": runtime.get("adapter"),
            }
        )
    loot_rt = _bot_runtime_status("loot_bot", db)
    if not any(str(r.get("name") or "").lower() == "loot_bot" for r in rows):
        rows.append(
            {
                "id": "runtime:loot_bot",
                "name": "loot_bot",
                "role": "loot_overseer",
                "status": loot_rt["status"],
                "last_seen": None,
                "pid": loot_rt.get("pid"),
                "adapter": loot_rt.get("adapter"),
            }
        )
    return rows


@router.get("/{bot_id}")
def get_bot(bot_id: int, db: Session = Depends(get_db)):
    from app.models.bot import Bot
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        return {"error": "Not found"}
    return orm_to_dict(bot)


@router.get("/runtime/{bot_key}")
def get_bot_runtime(bot_key: str, db: Session = Depends(get_db)):
    key = (bot_key or "").strip().lower()
    if key not in ("payment_bot", "loot_bot"):
        raise HTTPException(status_code=404, detail="Unknown bot_key; use payment_bot or loot_bot.")
    return _bot_runtime_status(key, db)


@router.post("/runtime/{bot_key}/{action}")
def control_bot_runtime(bot_key: str, action: str, db: Session = Depends(get_db)):
    key = (bot_key or "").strip().lower()
    act = (action or "").strip().lower()
    if key not in ("payment_bot", "loot_bot"):
        raise HTTPException(status_code=404, detail="Unknown bot_key; use payment_bot or loot_bot.")
    if key == "payment_bot":
        if act == "start":
            return _start_payment_bot(db)
        if act == "stop":
            return _stop_payment_bot(db)
        if act == "restart":
            if _runtime_adapter(db) == "command":
                cmd = (_runtime_cfg(db).get("restart") or "").strip()
                if cmd:
                    return _run_command("restart", db)
            _stop_payment_bot(db)
            return _start_payment_bot(db)
        if act == "reload":
            if _runtime_adapter(db) == "command":
                cmd = (_runtime_cfg(db).get("reload") or "").strip()
                if cmd:
                    return _run_command("reload", db)
            if _proc_alive("payment_bot"):
                p = _LOCAL_PROCS["payment_bot"]
                return {"ok": True, "status": "running", "pid": p.pid, "message": "config auto-refreshes every ~30s"}
            return {"ok": True, "status": "stopped", "pid": None, "message": "bot is stopped; start it to apply config"}
        raise HTTPException(status_code=400, detail="Action must be one of: start, stop, restart, reload")

    if act == "start":
        return _start_loot_bot(db)
    if act == "stop":
        return _stop_loot_bot(db)
    if act == "restart":
        if _loot_runtime_adapter(db) == "command":
            lcfg = _loot_runtime_cfg(db)
            cmd = (lcfg.get("restart") or "").strip()
            if cmd:
                return _run_command("restart", db, lcfg)
        _stop_loot_bot(db)
        return _start_loot_bot(db)
    if act == "reload":
        if _loot_runtime_adapter(db) == "command":
            lcfg = _loot_runtime_cfg(db)
            cmd = (lcfg.get("reload") or "").strip()
            if cmd:
                return _run_command("reload", db, lcfg)
        if _proc_alive("loot_bot"):
            p = _LOCAL_PROCS["loot_bot"]
            return {"ok": True, "status": "running", "pid": p.pid, "message": "config auto-refreshes from TBCC API"}
        return {"ok": True, "status": "stopped", "pid": None, "message": "bot is stopped; start it to apply config"}
    raise HTTPException(status_code=400, detail="Action must be one of: start, stop, restart, reload")
