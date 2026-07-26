"""Erome upload preflight — rate limits, duplicate titles, spam-pattern guards."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.services.import_pipeline import tbcc_run_dir

_LEDGER_NAME = "upload_ledger.jsonl"

# Handles / auto-filename patterns that correlate with spam bans on Erome.
_DEFAULT_SPAM_TITLE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"@\w+", re.I),
    re.compile(r"^\d{8}\s*[-–—]\s*@", re.I),
    re.compile(r"@AOF[_\w]*", re.I),
    re.compile(r"platform\s*\d", re.I),
    re.compile(r"^goon\s*wall", re.I),
)

# Erome TOS: no advertising in titles/descriptions (see tbcc/docs/EROME_TOS.md).
_TME_LINK_RE = re.compile(r"t\.me/|telegram\.me/|telegram\.dog/", re.I)
_PROMO_HOST_RE = re.compile(
    r"linkvertise|link-center\.net|direct-link\.net|allmylinks|onlyfans|fansly|"
    r"linktr\.ee|beacons\.ai|cash\.app|gumroad|paypal\.me|http[s]?://",
    re.I,
)


@dataclass
class EromePolicyVerdict:
    allowed: bool
    warnings: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    wait_seconds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "warnings": list(self.warnings),
            "blocks": list(self.blocks),
            "wait_seconds": self.wait_seconds,
        }


def _analytics_dir() -> Path:
    d = tbcc_run_dir() / "erome-analytics"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ledger_path() -> Path:
    return _analytics_dir() / _LEDGER_NAME


def policy_enabled() -> bool:
    raw = (os.getenv("TBCC_EROME_POLICY_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def min_interval_minutes() -> int:
    raw = (os.getenv("TBCC_EROME_MIN_INTERVAL_MINUTES") or "25").strip()
    try:
        return max(0, min(720, int(raw)))
    except ValueError:
        return 25


def max_uploads_per_day() -> int:
    raw = (os.getenv("TBCC_EROME_MAX_UPLOADS_PER_DAY") or "8").strip()
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return 8


def max_files_soft_recommend() -> int:
    """Single-video uploads often outperform multi-file spam bursts."""
    raw = (os.getenv("TBCC_EROME_MAX_FILES_SOFT") or "3").strip()
    try:
        return max(1, min(50, int(raw)))
    except ValueError:
        return 3


def duplicate_title_hours() -> int:
    raw = (os.getenv("TBCC_EROME_DUPLICATE_TITLE_HOURS") or "72").strip()
    try:
        return max(1, min(720, int(raw)))
    except ValueError:
        return 72


def spam_title_patterns() -> tuple[re.Pattern[str], ...]:
    extra = (os.getenv("TBCC_EROME_SPAM_TITLE_REGEX") or "").strip()
    patterns = list(_DEFAULT_SPAM_TITLE_RES)
    if extra:
        for chunk in extra.split(";"):
            chunk = chunk.strip()
            if chunk:
                patterns.append(re.compile(chunk, re.I))
    return tuple(patterns)


def _read_ledger_rows(*, since: datetime | None = None) -> list[dict[str, Any]]:
    path = ledger_path()
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if since is not None:
            ts = row.get("published_at") or row.get("recorded_at")
            if ts:
                try:
                    when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if when.tzinfo is None:
                        when = when.replace(tzinfo=timezone.utc)
                    if when < since:
                        continue
                except ValueError:
                    pass
        rows.append(row)
    return rows


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip().lower())[:120]


def scan_description_for_tos(description: str) -> list[str]:
    """Erome forbids advertising / off-platform full-version mentions in album text."""
    d = (description or "").strip()
    if not d:
        return []
    issues: list[str] = []
    if _TME_LINK_RE.search(d):
        issues.append("tos_advertising:telegram_link_in_description")
    if _PROMO_HOST_RE.search(d):
        issues.append("tos_advertising:promo_link_in_description")
    if re.search(r"full (version|pack|album|set)|available (on|at|via)|subscribe|onlyfans", d, re.I):
        issues.append("tos_advertising:full_version_elsewhere")
    return issues


def scan_title_for_tos(title: str) -> list[str]:
    """Advertising patterns in album titles (e.g. t.me/aofmainhub)."""
    t = (title or "").strip()
    if not t:
        return []
    issues: list[str] = []
    if _TME_LINK_RE.search(t):
        issues.append("tos_advertising:telegram_link_in_title")
    if re.search(r"^t\.me\b|aofmainhub|@aof", t, re.I):
        issues.append("tos_advertising:hub_handle_in_title")
    return issues


def scan_title_for_spam(title: str) -> list[str]:
    """Return human-readable spam/TOS risk notes for a title."""
    t = (title or "").strip()
    if not t:
        return ["empty_title"]
    issues: list[str] = []
    if len(t) > 100:
        issues.append("title_too_long")
    if t.isupper() and len(t) > 12:
        issues.append("title_all_caps")
    for pat in spam_title_patterns():
        if pat.search(t):
            issues.append(f"spam_pattern:{pat.pattern[:40]}")
    return issues


def check_upload_policy(
    *,
    title: str | None = None,
    description: str | None = None,
    file_count: int = 1,
    tags: list[str] | None = None,
    source: str = "unknown",
    force: bool = False,
) -> EromePolicyVerdict:
    """Preflight before Playwright upload. Set force=True to bypass hard blocks (CLI --force)."""
    verdict = EromePolicyVerdict(allowed=True)
    if not policy_enabled():
        return verdict

    now = datetime.now(timezone.utc)
    day_since = now - timedelta(days=1)
    interval_min = min_interval_minutes()

    recent_ok = [
        r
        for r in _read_ledger_rows(since=day_since)
        if r.get("ok") and r.get("published_at")
    ]
    if len(recent_ok) >= max_uploads_per_day():
        verdict.blocks.append(f"daily_cap:{max_uploads_per_day()}")
        verdict.allowed = False

    if interval_min > 0 and recent_ok:
        last_ts = None
        for row in reversed(recent_ok):
            ts = row.get("published_at") or row.get("recorded_at")
            if ts:
                try:
                    last_ts = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
        if last_ts:
            elapsed = (now - last_ts).total_seconds()
            need = interval_min * 60
            if elapsed < need:
                wait = int(need - elapsed)
                verdict.wait_seconds = wait
                verdict.blocks.append(f"rate_limit:wait_{wait}s")
                verdict.allowed = False

    norm_title = _normalize_title(title or "")
    if norm_title:
        dup_since = now - timedelta(hours=duplicate_title_hours())
        for row in _read_ledger_rows(since=dup_since):
            if not row.get("ok"):
                continue
            other = _normalize_title(str(row.get("title") or ""))
            if other and other == norm_title:
                verdict.blocks.append("duplicate_title")
                verdict.allowed = False
                break

    spam = scan_title_for_spam(title or "")
    for issue in spam:
        if issue.startswith("spam_pattern:"):
            verdict.warnings.append(issue)
        else:
            verdict.warnings.append(issue)

    for issue in scan_title_for_tos(title or ""):
        verdict.warnings.append(issue)

    for issue in scan_description_for_tos(description or ""):
        verdict.warnings.append(issue)
        if issue.startswith("tos_advertising:") and not force:
            verdict.blocks.append(issue)
            verdict.allowed = False

    if file_count > max_files_soft_recommend():
        verdict.warnings.append(
            f"multi_file_burst:{file_count}>{max_files_soft_recommend()} "
            "(single trimmed videos often outperform albums on Erome)"
        )

    if not (tags or []):
        verdict.warnings.append("no_tags (Erome search visibility suffers without tags)")
    elif (os.getenv("TBCC_EROME_BROWSE_INTEL_UPLOAD_HINTS") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    ):
        try:
            hints = intel_upload_hints()
            saturated = {str(t).lower() for t in hints.get("saturated_tags") or []}
            for tag in tags or []:
                tl = str(tag).strip().lower()
                if tl and tl in saturated:
                    verdict.warnings.append(f"intel_saturated_tag:{tl}")
        except Exception:
            pass

    if source == "auto" and file_count > 1:
        verdict.warnings.append("auto_upload_album (prefer manual title/tags for auto lane)")

    if force and verdict.blocks:
        verdict.warnings.extend([f"forced_past:{b}" for b in verdict.blocks])
        verdict.blocks = []
        verdict.wait_seconds = 0
        verdict.allowed = True

    if verdict.blocks:
        verdict.allowed = False

    return verdict


def append_ledger_row(row: dict[str, Any]) -> Path:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(row)
    payload.setdefault("recorded_at", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def policy_block_message(verdict: EromePolicyVerdict) -> str:
    parts = list(verdict.blocks)
    if verdict.wait_seconds > 0:
        mins = max(1, verdict.wait_seconds // 60)
        parts.append(f"wait ~{mins} min before next upload")
    if verdict.warnings:
        parts.append("warnings: " + "; ".join(verdict.warnings[:4]))
    return "; ".join(parts) if parts else "upload blocked by policy"


def intel_upload_hints(*, top_n: int = 8) -> dict[str, Any]:
    """Actionable upload hints from browse intel (Erome market only)."""
    from app.services.erome_browse_intel import (
        aggregate_format_scores,
        aggregate_tag_scores,
        load_recent_rows,
        top_quartile_tags,
    )

    erome_rows = [r for r in load_recent_rows() if str(r.get("platform") or "erome") == "erome"]
    if not erome_rows:
        return {"ok": True, "row_count": 0, "top_tags": [], "top_quartile_tags": []}

    tag_scores = aggregate_tag_scores(erome_rows, platform="erome")
    format_scores = aggregate_format_scores(erome_rows)
    from app.services.erome_browse_intel import format_discoveries

    discoveries = format_discoveries(erome_rows, platform="erome")
    top_tags = sorted(tag_scores.items(), key=lambda x: -x[1])[:top_n]
    tq = top_quartile_tags(tag_scores)
    best_format = discoveries.get("preferred_format_bucket") or (
        max(format_scores.items(), key=lambda x: x[1])[0] if format_scores else None
    )
    saturated: list[str] = []
    buckets: dict[str, list[tuple[float, int]]] = {}
    for row in erome_rows:
        vpd = row.get("views_per_day_proxy")
        if vpd is None:
            continue
        for tag in row.get("tags") or []:
            buckets.setdefault(tag, []).append((float(vpd), int(row.get("engagement_bps") or 0)))
    for tag, vals in buckets.items():
        if len(vals) < 10:
            continue
        vpds = sorted(v for v, _ in vals)
        median_bps = sorted(b for _, b in vals)[len(vals) // 2]
        if vpds[-1] > vpds[len(vpds) // 2] * 3 and median_bps < 300:
            saturated.append(tag)
    return {
        "ok": True,
        "top_tags": [{"tag": t, "score": round(s, 1)} for t, s in top_tags],
        "top_quartile_tags": sorted(tq)[:40],
        "preferred_format_bucket": best_format,
        "suite_actions": discoveries.get("suite_actions") or [],
        "format_stats": discoveries.get("format_stats") or {},
        "saturated_tags": sorted(set(saturated))[:20],
        "row_count": len(erome_rows),
    }
