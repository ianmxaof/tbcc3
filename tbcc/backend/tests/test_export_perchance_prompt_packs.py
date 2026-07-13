"""Smoke: Gemini → Perchance prompt pack export stays in sync."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO_TBCC = BACKEND.parent
EXPORT = BACKEND / "scripts" / "export_perchance_prompt_packs.py"
JOBS = REPO_TBCC / "userscripts" / "packages" / "perchance-suite" / "data" / "jobs.json"
PACKS = REPO_TBCC / "userscripts" / "inbox" / "perchance" / "prompt-packs"
MODEL = REPO_TBCC / "userscripts" / "inbox" / "perchance" / "tbcc-aof-gen.modelText.txt"


def test_export_perchance_prompt_packs_smoke():
    assert EXPORT.is_file()
    proc = subprocess.run(
        [sys.executable, str(EXPORT)],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert JOBS.is_file()
    data = json.loads(JOBS.read_text(encoding="utf-8"))
    jobs = data.get("jobs") or []
    assert len(jobs) >= 20
    lanes = {j.get("lane") for j in jobs}
    assert "promo" in lanes and "loot" in lanes
    assert any(j.get("id") == "promo-martyrs-ma07-10" for j in jobs)
    assert any(str(j.get("id", "")).startswith("loot-tier-") for j in jobs)
    assert (PACKS / "promo" / "martyrs-ma07-10.txt").is_file()
    assert (PACKS / "loot" / "tier-07.txt").is_file()
    assert MODEL.is_file()
    text = MODEL.read_text(encoding="utf-8")
    assert "t2i-framework-plugin-v2" in text
    assert "TBCC AOF Image Lab" in text
    jobs_js = JOBS.with_name("jobs-data.js")
    assert jobs_js.is_file()
    assert "jobsData" in jobs_js.read_text(encoding="utf-8")
