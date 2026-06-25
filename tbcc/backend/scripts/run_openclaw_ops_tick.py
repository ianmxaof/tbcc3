#!/usr/bin/env python3
"""Deprecated alias — use run_tbcc_flywheel_tick.py (not GitHub OpenClaw)."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_target = Path(__file__).resolve().parent / "run_tbcc_flywheel_tick.py"
sys.argv[0] = str(_target)
runpy.run_path(str(_target), run_name="__main__")
