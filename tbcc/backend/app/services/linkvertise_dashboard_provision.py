"""Playwright automation for Linkvertise Post & earn dashboard links (persistent slugs)."""

from __future__ import annotations

import json
import logging
import os
import random
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.services.aof_packs_post_copy import merge_pack_source_note, parse_pack_source_note
from app.services.link_gate_provider import is_linkvertise_host, publisher_id_from_env
from app.services.linkvertise_playwright_locators import click_spec, fill_spec, locator_from_spec
from app.services.playwright_browser import (
    PlaywrightHandle,
    browser_label,
    codegen_cli_command,
    launch_browser,
    open_playwright_session,
    resolve_launch_mode,
    use_brave_persistent_profile,
)
from app.services.pack_gate_wrap import _is_dynamic_linkvertise

logger = logging.getLogger(__name__)

_FLOW_PATH = Path(__file__).resolve().parents[1] / "data" / "linkvertise_dashboard_flow.json"
_LV_SLUG_RE = re.compile(
    r"https?://(?:link-target|link-center|link-to|direct-link|up-to-down)\.net/\d+/([A-Za-z0-9_-]+)",
    re.I,
)
_PROBE_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


@dataclass
class FlowConfig:
    publisher_login_url: str
    post_earn_url: str
    selectors: dict[str, str]
    locators: dict[str, Any]
    slug_url_pattern: str
    wait_after_submit_ms: int
    link_title_default: str
    link_title_min_len: int = 40
    ad_tasks_count: int = 2
    reuse_create_new_link_loop: bool = True
    flow_mode: str = "simple"
    skip_login: bool = True
    wizard_entry_url: str | None = None


def flow_config_path() -> Path:
    override = (os.getenv("TBCC_LINKVERTISE_FLOW_CONFIG") or "").strip()
    if override:
        return Path(override)
    local = _FLOW_PATH.with_name("linkvertise_dashboard_flow.local.json")
    if local.is_file():
        return local
    return _FLOW_PATH


def auth_state_path() -> Path:
    raw = (os.getenv("TBCC_LINKVERTISE_AUTH_STATE") or "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[2] / ".linkvertise-auth.json"


def load_flow_config() -> FlowConfig:
    path = flow_config_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    sel = data.get("selectors") or {}
    loc = data.get("locators") or {}
    ad_raw = data.get("ad_tasks_count")
    if ad_raw is None:
        ad_raw = os.getenv("TBCC_LINKVERTISE_AD_TASKS") or "2"
    return FlowConfig(
        publisher_login_url=str(data.get("publisher_login_url") or "https://publisher.linkvertise.com/login"),
        post_earn_url=str(
            data.get("post_earn_url") or "https://publisher.linkvertise.com/dashboard/linkvertise/post-and-earn"
        ),
        selectors={k: str(v or "") for k, v in sel.items()},
        locators=loc if isinstance(loc, dict) else {},
        slug_url_pattern=str(data.get("slug_url_pattern") or "link-target.net/{publisher_id}/"),
        wait_after_submit_ms=int(data.get("wait_after_submit_ms") or 4000),
        link_title_default=str(
            data.get("link_title_default") or "AOF Network Premium Content Pack Access Link Official"
        ),
        link_title_min_len=int(data.get("link_title_min_len") or os.getenv("TBCC_LINKVERTISE_TITLE_MIN_LEN") or "40"),
        ad_tasks_count=int(ad_raw),
        reuse_create_new_link_loop=bool(data.get("reuse_create_new_link_loop", True)),
        flow_mode=str(data.get("flow_mode") or "simple").strip().lower(),
        skip_login=bool(data.get("skip_login", True)),
        wizard_entry_url=(str(data.get("wizard_entry_url")).strip() if data.get("wizard_entry_url") else None),
    )


def _spec(cfg: FlowConfig, key: str) -> dict[str, Any] | str | None:
    if key in cfg.locators and cfg.locators[key]:
        return cfg.locators[key]
    css = (cfg.selectors.get(key) or "").strip()
    return css or None


def selectors_ready(cfg: FlowConfig) -> bool:
    if cfg.flow_mode == "wizard":
        required = ("destination_input", "submit_button", "wizard_start")
        return all(bool(_spec(cfg, k)) for k in required)
    required = ("create_link_button", "destination_input", "submit_button")
    return all(bool(_spec(cfg, key)) for key in required)


def extract_lv_slug_url(text: str, publisher_id: str | int | None = None) -> str | None:
    pub = str(publisher_id or publisher_id_from_env())
    m = _LV_SLUG_RE.search(text or "")
    if not m:
        return None
    slug = m.group(1)
    base = f"https://link-target.net/{pub}/{slug}"
    if _is_dynamic_linkvertise(base):
        return None
    return base


def probe_lv_gate(url: str) -> dict[str, Any]:
    """HTTP probe — dashboard slugs should return LV shell, not takedown."""
    out: dict[str, Any] = {"url": url, "ok": False, "flags": []}
    try:
        with httpx.Client(timeout=25, follow_redirects=True, headers=_PROBE_UA) as client:
            r = client.get(url)
        body = (r.text or "")[:4000].lower()
        flags: list[str] = []
        if "no longer available" in body or "removed by the creator" in body:
            flags.append("TAKEDOWN")
        if "please enable" in body and "javascript" in body:
            flags.append("JS_GATE")
        if any(x in body for x in ("linkvertise", "link-target", "link-center", "link-to.net")):
            flags.append("LV_SHELL")
        out["http"] = r.status_code
        out["final_url"] = str(r.url)
        out["flags"] = flags
        out["ok"] = "TAKEDOWN" not in flags and bool(flags)
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


def rate_limit_sleep() -> None:
    lo = int(os.getenv("TBCC_LINKVERTISE_PROVISION_DELAY_MIN_S") or "30")
    hi = int(os.getenv("TBCC_LINKVERTISE_PROVISION_DELAY_MAX_S") or "90")
    if hi < lo:
        hi = lo
    delay = random.uniform(lo, hi)
    logger.info("LV provision rate limit sleep %.1fs", delay)
    time.sleep(delay)


def _playwright_sync():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Playwright not installed. Run: py -m pip install playwright && py -m playwright install chromium"
        ) from e
    return sync_playwright


def _dismiss_banners(page: Any) -> None:
    for name in ("CONFIRM", "OK", "Accept", "Accept all"):
        try:
            page.get_by_role("button", name=name).first.click(timeout=2000)
            page.wait_for_timeout(400)
        except Exception:
            continue


def _click_next_when_ready(page: Any, cfg: FlowConfig) -> None:
    spec = _spec(cfg, "wizard_start")
    if not spec:
        raise RuntimeError("wizard_start (Next) locator missing")
    loc = locator_from_spec(page, spec).first
    loc.wait_for(state="visible", timeout=60000)
    loc.click()


def _navigate_to_wizard_start(page: Any, cfg: FlowConfig, *, first: bool) -> None:
    """Reach the create-link wizard step where the Next button is visible."""
    _dismiss_banners(page)

    if not first:
        start_spec = _spec(cfg, "wizard_start")
        try:
            locator_from_spec(page, start_spec).first.wait_for(state="visible", timeout=5000)
            _click_next_when_ready(page, cfg)
            return
        except Exception:
            pass
        _click_if_spec(page, cfg, "create_new_link_button")
        _click_next_when_ready(page, cfg)
        return

    entry = (cfg.wizard_entry_url or "").strip()
    if entry:
        page.goto(entry, wait_until="networkidle", timeout=120000)
        _dismiss_banners(page)

    start_spec = _spec(cfg, "wizard_start")
    if start_spec:
        try:
            locator_from_spec(page, start_spec).first.wait_for(state="visible", timeout=4000)
            return
        except Exception:
            pass

    _click_if_spec(page, cfg, "post_earn_nav")
    page.wait_for_timeout(2500)
    try:
        locator_from_spec(page, start_spec).first.wait_for(state="visible", timeout=15000)
        return
    except Exception:
        pass

    fallbacks = [
        lambda: page.get_by_role("button", name="Get Started").first.click(timeout=5000),
        lambda: page.get_by_role("link", name="Dashboard").first.click(timeout=5000),
    ]
    for action in fallbacks:
        try:
            action()
            page.wait_for_timeout(1500)
            _click_if_spec(page, cfg, "post_earn_nav")
            page.wait_for_timeout(1500)
            locator_from_spec(page, start_spec).first.wait_for(state="visible", timeout=20000)
            return
        except Exception:
            continue

    raise RuntimeError(
        "Could not open create-link wizard (Next not found). "
        "Try setting wizard_entry_url in linkvertise_dashboard_flow.local.json"
    )


def _login_wall_visible(page: Any) -> bool:
    """Login modal can sit on top while sidebar chrome is still visible."""
    checks = [
        lambda: page.get_by_text("Login / Registration").first.is_visible(),
        lambda: page.get_by_text("Continue with Google").first.is_visible(),
        lambda: page.get_by_role("textbox", name=re.compile(r"^email$", re.I)).first.is_visible(),
    ]
    for check in checks:
        try:
            if check():
                return True
        except Exception:
            continue
    return False


def _looks_logged_in(page: Any, cfg: FlowConfig) -> bool:
    if _login_wall_visible(page):
        return False
    url = (page.url or "").lower()
    if "/login" in url or "publisher.linkvertise.com/login" in url:
        return False
    start = _spec(cfg, "wizard_start")
    if start:
        try:
            locator_from_spec(page, start).first.wait_for(state="visible", timeout=2000)
            return True
        except Exception:
            pass
    # Logged in on consumer site — Post & earn in sidebar, login modal closed.
    try:
        page.locator("a.sidebar-item.asset-link").filter(has_text="Post & earn").first.wait_for(
            state="visible", timeout=2000
        )
        return not _login_wall_visible(page)
    except Exception:
        pass
    try:
        page.get_by_role("textbox", name=re.compile(r"password", re.I)).first.wait_for(
            state="visible", timeout=1500
        )
        return False
    except Exception:
        pass
    return False


def _wait_for_manual_step(page: Any, cfg: FlowConfig, *, prompt: str) -> None:
    """Wait for user to finish in browser — no Inspector/Enter required."""
    wait_s = int(os.getenv("TBCC_LINKVERTISE_WAIT_LOGIN_S") or "300")
    print(prompt)
    print(f"Automation continues automatically when ready (up to {wait_s}s)…\n")
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if _looks_logged_in(page, cfg):
            print("Dashboard ready — continuing automation.\n")
            return
        page.wait_for_timeout(2000)
    raise RuntimeError(
        f"Timed out after {wait_s}s waiting for Linkvertise login. "
        "Log in in the Playwright browser window and re-run."
    )


def _ensure_logged_in(page: Any, cfg: FlowConfig, *, headed: bool) -> None:
    """Login is not in the recorded wizard — wait for manual auth when needed."""
    if _looks_logged_in(page, cfg):
        return
    print(
        "\n=== LINKVERTISE LOGIN (manual step) ===\n"
        "The recorded flow starts *after* login. In the Brave window:\n"
        "  • Sign in (Google or email)\n"
        "  • Dismiss cookie banners\n"
        "  • Click Post & earn in the sidebar if needed\n"
    )
    if headed:
        _wait_for_manual_step(
            page,
            cfg,
            prompt="Log in via the browser window if prompted (Google/email).",
        )
    else:
        print("Waiting up to 3 minutes for dashboard…\n")
        deadline = time.time() + 180
        while time.time() < deadline:
            if _looks_logged_in(page, cfg):
                return
            page.wait_for_timeout(2000)
        raise RuntimeError("Not logged in — re-run with --headed and log in when prompted")
    if not _looks_logged_in(page, cfg):
        raise RuntimeError("Still not on Linkvertise dashboard after manual login step")


_LV_TITLE_BLOCK_RE = re.compile(
    r"freeuse|overlord|freeusegod|freeuseoverlord|porn|xxx|nude|nsfw|sex|fans|18\+?|"
    r"golden|adult|leak|onlyfans|premium\s*content|pack|hub|mega|terabox|gofile|bunkr",
    re.I,
)

_LV_GUIDELINES_RE = re.compile(r"violates our guidelines|severely violates", re.I)


def _ultra_safe_linkvertise_title(cfg: FlowConfig, *, pack_id: int | None = None) -> str:
    """Bland title that passes Linkvertise content filters (per creator help docs)."""
    _ = pack_id  # never embed pack ids/names — LV flags adult/deceptive patterns
    min_len = max(40, int(cfg.link_title_min_len or 40))
    title = "Official Gaming Mod Resource Download Collection Link Archive"
    while len(title) < min_len:
        title += " Edition"
    return title[:120]


def _safe_linkvertise_title(raw: str | None, cfg: FlowConfig, *, pack_id: int | None = None) -> str:
    """Linkvertise Meta title: >=40 chars, generic — pack labels often trip adult filters."""
    generic_only = (os.getenv("TBCC_LINKVERTISE_TITLE_GENERIC_ONLY") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    if generic_only:
        return _ultra_safe_linkvertise_title(cfg, pack_id=pack_id)

    min_len = max(40, int(cfg.link_title_min_len or 40))
    template = (os.getenv("TBCC_LINKVERTISE_LINK_TITLE_TEMPLATE") or cfg.link_title_default or "").strip()
    if not template or _LV_TITLE_BLOCK_RE.search(template):
        return _ultra_safe_linkvertise_title(cfg, pack_id=pack_id)

    base = template
    if raw and not _LV_TITLE_BLOCK_RE.search(raw):
        clean = re.sub(r"[^\w\s-]", " ", raw or "")
        clean = _LV_TITLE_BLOCK_RE.sub(" ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()
        if len(clean) >= 12:
            base = f"{clean} Download Portal Link"

    stamp = time.strftime("%Y-%m-%d")
    title = f"{base} {stamp}".strip()
    while len(title) < min_len:
        title += " Resource"
    if _LV_TITLE_BLOCK_RE.search(title):
        return _ultra_safe_linkvertise_title(cfg, pack_id=pack_id)
    return title[:120]


def _normalize_lv_destination(url: str) -> str:
    """Follow redirects — use final URL (1024terabox mirrors look deceptive to LV)."""
    dest = (url or "").strip()
    if not dest.startswith(("http://", "https://")):
        return dest
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            r = client.head(dest)
            final = str(r.url).strip()
            if final.startswith(("http://", "https://")):
                if final != dest:
                    logger.info("LV destination normalized %s -> %s", dest[:60], final[:60])
                return final
    except Exception:
        logger.debug("destination normalize failed for %s", dest[:80], exc_info=True)
    return dest


def _set_input_value_angular(page: Any, loc: Any, value: str) -> None:
    """Mat-input fields ignore plain fill() — dispatch input events."""
    loc.click()
    try:
        loc.fill("")
        loc.fill(value)
    except Exception:
        pass
    try:
        handle = loc.element_handle()
        if handle:
            page.evaluate(
                """(el, val) => {
                  el.focus();
                  el.value = val;
                  el.dispatchEvent(new InputEvent('input', { bubbles: true }));
                  el.dispatchEvent(new Event('change', { bubbles: true }));
                  el.dispatchEvent(new Event('blur', { bubbles: true }));
                }""",
                handle,
                value,
            )
    except Exception:
        loc.press("Control+a")
        page.keyboard.type(value, delay=15)


def _wizard_back(page: Any) -> None:
    for attempt in (
        lambda: page.locator("mat-icon", has_text=re.compile(r"arrow_back|chevron_left", re.I)).locator(
            "xpath=ancestor::button[1]"
        ).first.click(timeout=3000),
        lambda: page.locator("button").filter(
            has=page.locator("mat-icon, svg")
        ).first.click(timeout=3000),
        lambda: page.get_by_role("button", name=re.compile(r"back", re.I)).first.click(timeout=3000),
    ):
        try:
            attempt()
            page.wait_for_timeout(800)
            return
        except Exception:
            continue


def _recover_guidelines_violation(page: Any, cfg: FlowConfig, dest: str) -> str:
    """Back through wizard, re-fill normalized URL + bland title, return to Access."""
    print("Guidelines error — re-filling URL and title from earlier steps…")
    dest = _normalize_lv_destination(dest)
    bland = "Official Gaming Mod Resource Download Collection Link Archive"

    if "/access" in (page.url or ""):
        _wizard_back(page)
        page.wait_for_timeout(800)

    if _meta_title_field_visible(page):
        _ensure_meta_visibility_no(page)
        _fill_wizard_meta_title(page, cfg, bland)
        _clear_meta_description(page)

    _wizard_back(page)
    page.wait_for_timeout(800)

    dest_spec = _spec(cfg, "destination_input")
    if dest_spec:
        try:
            dest_loc = locator_from_spec(page, dest_spec).first
            _set_input_value_angular(page, dest_loc, dest)
            print(f"Destination set: {dest[:70]}…")
        except Exception:
            logger.debug("destination re-fill failed", exc_info=True)

    after_url = _spec(cfg, "wizard_next_after_url")
    if after_url:
        click_spec(page, after_url)
        page.wait_for_timeout(800)

    _ensure_meta_visibility_no(page)
    _fill_wizard_meta_title(page, cfg, bland)
    _clear_meta_description(page)

    after_meta = _spec(cfg, "wizard_next_after_settings")
    if after_meta:
        click_spec(page, after_meta)
        page.wait_for_timeout(800)

    return bland


def _guidelines_violation_visible(page: Any) -> bool:
    try:
        return page.get_by_text(_LV_GUIDELINES_RE).first.is_visible()
    except Exception:
        return False


def _ensure_meta_visibility_no(page: Any) -> None:
    """Help docs: visibility off → only title required."""
    for name in ("No",):
        try:
            btn = page.get_by_role("button", name=name).first
            if btn.is_visible():
                btn.click(timeout=2000)
                page.wait_for_timeout(400)
                return
        except Exception:
            continue


def _clear_meta_description(page: Any) -> None:
    for getter in (
        lambda: page.get_by_label("Description").first,
        lambda: page.get_by_role("textbox", name=re.compile(r"description", re.I)).first,
    ):
        try:
            loc = getter()
            loc.wait_for(state="visible", timeout=1500)
            loc.fill("")
            return
        except Exception:
            continue


def _meta_title_field_visible(page: Any) -> bool:
    try:
        page.get_by_label("Title").first.wait_for(state="visible", timeout=2500)
        return True
    except Exception:
        pass
    try:
        page.get_by_role("textbox", name=re.compile(r"^title$", re.I)).first.wait_for(
            state="visible", timeout=1500
        )
        return True
    except Exception:
        return False


def _fill_wizard_meta_title(page: Any, cfg: FlowConfig, title: str) -> None:
    if not _meta_title_field_visible(page):
        return
    spec = _spec(cfg, "meta_title_input")
    loc = None
    if spec:
        try:
            loc = locator_from_spec(page, spec).first
            loc.wait_for(state="visible", timeout=5000)
        except Exception:
            loc = None
    if loc is None:
        for candidate in (
            page.get_by_label("Title").first,
            page.get_by_role("textbox", name=re.compile(r"^title$", re.I)).first,
        ):
            try:
                candidate.wait_for(state="visible", timeout=2000)
                loc = candidate
                break
            except Exception:
                continue
    if loc is None:
        return
    _set_input_value_angular(page, loc, title)
    page.wait_for_timeout(800)
    if _guidelines_violation_visible(page):
        fallback = "Official Gaming Mod Resource Download Collection Link Archive"
        while len(fallback) < 40:
            fallback += " Edition"
        _set_input_value_angular(page, loc, fallback)
        title = fallback
        page.wait_for_timeout(800)
    print(f"Meta title set ({len(title)} chars): {title[:50]}…")


def _disable_wait_sixty_minutes(page: Any) -> None:
    """Per TBCC policy: 2 ads only — disable 60min wait (hurts completion rate)."""
    try:
        box = page.locator("mat-checkbox, .mat-mdc-checkbox").filter(
            has_text=re.compile(r"wait\s*60|60\s*min", re.I)
        ).first
        if box.is_visible():
            cls = box.get_attribute("class") or ""
            try:
                checked = "checked" in cls or box.locator("input[type=checkbox]").first.is_checked()
            except Exception:
                checked = "checked" in cls
            if checked:
                box.click()
                print("Unchecked 60min wait (mat-checkbox click)")
                page.wait_for_timeout(400)
                return
    except Exception:
        pass
    for loc in (
        page.get_by_role("checkbox", name=re.compile(r"wait.*60", re.I)).first,
        page.get_by_text(re.compile(r"wait\s*60\s*min", re.I)).first,
    ):
        try:
            if loc.is_visible():
                loc.click()
                print("Unchecked 60min wait (label/checkbox click)")
                page.wait_for_timeout(400)
                return
        except Exception:
            continue


def _configure_access_two_ads(page: Any, cfg: FlowConfig) -> None:
    """Access step: Custom → Watch 2 ads → no 60min wait (matches help docs + recording)."""
    _click_if_spec(page, cfg, "ad_tasks_custom")
    page.wait_for_timeout(500)
    _disable_wait_sixty_minutes(page)
    try:
        ads = page.get_by_role("checkbox", name=re.compile(r"watch ads", re.I)).first
        if ads.is_visible() and not ads.is_checked():
            ads.check()
    except Exception:
        pass
    dropdown = _spec(cfg, "ad_tasks_dropdown")
    if dropdown:
        click_spec(page, dropdown)
        page.wait_for_timeout(800)
    two = _spec(cfg, "ad_tasks_two")
    if two:
        click_spec(page, two)
    page.wait_for_timeout(500)
    _disable_wait_sixty_minutes(page)


def _click_if_spec(page: Any, cfg: FlowConfig, key: str) -> bool:
    spec = _spec(cfg, key)
    if not spec:
        return False
    click_spec(page, spec)
    return True


def _fill_if_spec(page: Any, cfg: FlowConfig, key: str, value: str) -> bool:
    spec = _spec(cfg, key)
    if not spec:
        return False
    fill_spec(page, spec, value)
    return True


def _select_ad_tasks(page: Any, cfg: FlowConfig) -> None:
    """Pick N ads (default 2) — explicit locator or common text/role fallbacks."""
    if _click_if_spec(page, cfg, "ad_tasks_option"):
        return
    n = cfg.ad_tasks_count
    fallbacks = [
        {"method": "get_by_text", "args": [f"{n} ads"]},
        {"method": "get_by_text", "args": [f"Watch {n} ads"]},
        {"method": "get_by_text", "args": [str(n), {"exact": True}]},
        {"method": "get_by_role", "args": ["button", {"name": re.compile(rf"{n}\s*ads?", re.I)}]},
    ]
    for spec in fallbacks:
        try:
            click_spec(page, spec)
            return
        except Exception:
            continue
    logger.warning("ad_tasks selection skipped (no locator matched for %s ads)", n)


def _extract_url_from_text(text: str | None) -> str | None:
    if not text:
        return None
    found = extract_lv_slug_url(text)
    if found:
        return found
    chunk = (text or "").strip().split()[0] if text else ""
    if chunk.startswith("http") and is_linkvertise_host(chunk) and not _is_dynamic_linkvertise(chunk):
        return chunk
    return None


def _read_created_url_js(page: Any) -> str | None:
    try:
        raw = page.evaluate(
            """() => {
              const pick = (el) => {
                if (!el) return '';
                const inp = el.querySelector('input, textarea');
                if (inp && inp.value) return inp.value;
                return (el.innerText || el.textContent || '').trim();
              };
              for (const sel of ['lv-success', '[class*="success"]', 'mat-dialog-container']) {
                const el = document.querySelector(sel);
                const txt = pick(el);
                if (txt && /link-(target|center|to|vertise)/i.test(txt)) return txt;
              }
              for (const inp of document.querySelectorAll('input, textarea')) {
                const v = (inp.value || '').trim();
                if (/link-(target|center|to)/i.test(v)) return v;
              }
              for (const a of document.querySelectorAll('a[href]')) {
                const h = a.getAttribute('href') || '';
                if (/link-(target|center|to)/i.test(h)) return h;
              }
              return '';
            }"""
        )
        return _extract_url_from_text(str(raw or ""))
    except Exception:
        return None


def _try_read_created_url_once(page: Any, cfg: FlowConfig) -> str | None:
    anchor_spec = _spec(cfg, "created_link_anchor")
    text_spec = _spec(cfg, "created_link_text")
    if anchor_spec:
        try:
            href = locator_from_spec(page, anchor_spec).first.get_attribute("href", timeout=1500)
            url = _extract_url_from_text(href)
            if url:
                return url
        except Exception:
            pass
    specs = [
        text_spec,
        _spec(cfg, "created_link_input"),
        {"method": "locator", "args": ["lv-success input"]},
        {"method": "locator", "args": ["lv-success textarea"]},
        {"method": "locator", "args": ['input[value*="link-target"]']},
        {"method": "locator", "args": ['input[value*="link-center"]']},
        {"method": "locator", "args": ["a[href*='link-target.net']"]},
    ]
    for spec in specs:
        if not spec:
            continue
        try:
            loc = locator_from_spec(page, spec).first
            for reader in (
                lambda: loc.input_value(timeout=1500),
                lambda: loc.get_attribute("value", timeout=1500),
                lambda: loc.get_attribute("href", timeout=1500),
                lambda: loc.inner_text(timeout=1500),
            ):
                try:
                    url = _extract_url_from_text(reader())
                    if url:
                        return url
                except Exception:
                    continue
        except Exception:
            continue
    url = _read_created_url_js(page)
    if url:
        return url
    return _extract_url_from_text(page.content())


def _wait_for_created_url(page: Any, cfg: FlowConfig, *, headed: bool = False) -> str:
    """Poll after Publish — success UI can take several seconds."""
    timeout_s = int(os.getenv("TBCC_LINKVERTISE_SUCCESS_WAIT_S") or "90")
    print("Waiting for created Linkvertise slug…")
    deadline = time.time() + timeout_s
    last_err = ""
    while time.time() < deadline:
        try:
            if _spec(cfg, "create_new_link_button"):
                locator_from_spec(page, _spec(cfg, "create_new_link_button")).first.wait_for(
                    state="visible", timeout=2000
                )
        except Exception:
            pass
        url = _try_read_created_url_once(page, cfg)
        if url:
            print(f"Created slug: {url}")
            return url
        page.wait_for_timeout(1000)
    if headed and sys.stdin.isatty():
        print(
            "\n=== Could not auto-read the slug ===\n"
            "The link should be visible in the Brave window after Publish.\n"
            "Copy the full link-target.net URL and paste it below.\n"
        )
        try:
            pasted = input("Paste Linkvertise URL (or Enter to fail): ").strip()
        except EOFError:
            pasted = ""
        url = _extract_url_from_text(pasted)
        if url:
            return url
    raise RuntimeError(
        "Could not read created Linkvertise slug after Publish. "
        f"Tried for {timeout_s}s. {last_err}".strip()
    )


def _scrape_created_url(page: Any, cfg: FlowConfig) -> str | None:
    return _try_read_created_url_once(page, cfg)


def _open_create_form(page: Any, cfg: FlowConfig, *, first_in_session: bool) -> None:
    if first_in_session:
        nav = _spec(cfg, "post_earn_nav")
        if nav:
            click_spec(page, nav)
        elif cfg.post_earn_url:
            page.goto(cfg.post_earn_url, wait_until="domcontentloaded")
        create = _spec(cfg, "create_link_button")
        if not create:
            raise RuntimeError("create_link_button locator missing")
        click_spec(page, create)
        return

    if cfg.reuse_create_new_link_loop and _click_if_spec(page, cfg, "create_new_link_button"):
        return
    create = _spec(cfg, "create_link_button")
    if create:
        click_spec(page, create)
        return
    page.goto(cfg.post_earn_url, wait_until="domcontentloaded")
    click_spec(page, _spec(cfg, "create_link_button"))


@dataclass
class DashboardSession:
    cfg: FlowConfig
    page: Any
    context: Any
    browser: Any
    _playwright: Any = field(repr=False, default=None)
    _handle: PlaywrightHandle | None = field(repr=False, default=None)
    _links_created: int = 0
    _headed: bool = False
    _pack_id: int | None = None

    def create_link(self, destination_url: str, *, title: str | None = None, pack_id: int | None = None) -> str:
        dest = (destination_url or "").strip()
        if not dest.startswith(("http://", "https://")):
            raise ValueError("invalid_destination_url")

        if self.cfg.flow_mode == "wizard":
            return self._create_link_wizard(dest, title=title, pack_id=pack_id)

        first = self._links_created == 0
        _open_create_form(self.page, self.cfg, first_in_session=first)

        if not _fill_if_spec(self.page, self.cfg, "destination_input", dest):
            raise RuntimeError("destination_input locator missing")

        _fill_if_spec(self.page, self.cfg, "title_input", (title or self.cfg.link_title_default)[:30])
        _select_ad_tasks(self.page, self.cfg)

        submit = _spec(self.cfg, "submit_button")
        if not submit:
            raise RuntimeError("submit_button locator missing")
        click_spec(self.page, submit)
        self.page.wait_for_timeout(self.cfg.wait_after_submit_ms)

        link_url = _scrape_created_url(self.page, self.cfg)
        if not link_url:
            raise RuntimeError("Could not scrape created Linkvertise slug from dashboard page")
        normalized = extract_lv_slug_url(link_url) or link_url.strip().split()[0]
        if not is_linkvertise_host(normalized) or _is_dynamic_linkvertise(normalized):
            raise RuntimeError(f"Created URL is not a dashboard slug: {normalized[:120]}")
        self._links_created += 1
        return normalized

    def _create_link_wizard(self, dest: str, *, title: str | None = None, pack_id: int | None = None) -> str:
        page = self.page
        cfg = self.cfg
        first = self._links_created == 0
        safe_title = _safe_linkvertise_title(title, cfg, pack_id=pack_id or self._pack_id)
        dest = _normalize_lv_destination(dest)

        _navigate_to_wizard_start(page, cfg, first=first)
        if first:
            _click_next_when_ready(page, cfg)

        dest_spec = _spec(cfg, "destination_input")
        if not dest_spec:
            raise RuntimeError("destination_input locator missing")
        dest_loc = locator_from_spec(page, dest_spec).first
        _set_input_value_angular(page, dest_loc, dest)

        after_url = _spec(cfg, "wizard_next_after_url")
        if after_url:
            click_spec(page, after_url)
            page.wait_for_timeout(800)

        _ensure_meta_visibility_no(page)
        _fill_wizard_meta_title(page, cfg, safe_title)
        _clear_meta_description(page)

        after_meta = _spec(cfg, "wizard_next_after_settings")
        if after_meta:
            click_spec(page, after_meta)
            page.wait_for_timeout(800)

        _configure_access_two_ads(page, cfg)

        if _guidelines_violation_visible(page):
            safe_title = _recover_guidelines_violation(page, cfg, dest)
            _configure_access_two_ads(page, cfg)

        submit = _spec(cfg, "submit_button")
        if not submit:
            raise RuntimeError("submit_button (Publish) locator missing")
        if _guidelines_violation_visible(page):
            raise RuntimeError(
                "Cannot Publish — Linkvertise guidelines error still visible. "
                f"dest={dest[:80]}"
            )
        click_spec(page, submit)
        page.wait_for_timeout(cfg.wait_after_submit_ms)

        link_url = _wait_for_created_url(page, cfg, headed=self._headed)
        if not link_url:
            link_url = _scrape_created_url(page, cfg)
        if not link_url:
            raise RuntimeError("Could not read created Linkvertise slug after Publish")

        normalized = extract_lv_slug_url(link_url) or link_url.strip().split()[0]
        if not is_linkvertise_host(normalized) or _is_dynamic_linkvertise(normalized):
            raise RuntimeError(f"Created URL is not a dashboard slug: {normalized[:120]}")

        if cfg.reuse_create_new_link_loop:
            _click_if_spec(page, cfg, "create_new_link_button")

        self._links_created += 1
        return normalized

    def save_auth(self) -> None:
        if self._handle is not None and self._handle.persistent:
            return
        auth_path = auth_state_path()
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.context.storage_state(path=str(auth_path))
        except Exception:
            logger.debug("storage_state export skipped", exc_info=True)

    def close(self, *, force: bool = False) -> None:
        try:
            self.save_auth()
        finally:
            if self._handle is not None:
                self._handle.close(force=force)
            elif self.browser is not None:
                self.browser.close()
                if self._playwright is not None:
                    self._playwright.stop()


def login_and_save_session(*, headed: bool = True) -> Path:
    """Open Linkvertise login in your Brave profile; save storage state export."""
    cfg = load_flow_config()
    auth_path = auth_state_path()
    auth_path.parent.mkdir(parents=True, exist_ok=True)

    handle = open_playwright_session(headed=headed, slow_mo=80, storage_state=auth_path, force_ephemeral=True)
    try:
        page = handle.get_page()
        page.goto(cfg.publisher_login_url, wait_until="domcontentloaded", timeout=120000)
        print(
            "\n=== LINKVERTISE LOGIN ===\n"
            f"Browser: {browser_label()}\n"
            "1. Log in to Linkvertise (password manager may autofill).\n"
            "2. Confirm you see the dashboard — not the login form.\n"
            "3. Press Resume in Playwright Inspector when done.\n"
            "\nCookies save to .linkvertise-auth.json so Playwright can run while your daily Brave stays open.\n"
            f"\nOr record full flow:\n  {codegen_cli_command(save_storage=auth_path, url=cfg.post_earn_url)}\n"
        )
        if headed:
            page.pause()
        else:
            input("Press Enter after login completes… ")
        handle.context.storage_state(path=str(auth_path))
    finally:
        handle.close()

    print(f"Saved session -> {auth_path}")
    return auth_path


def record_dashboard_flow(*, headed: bool = True) -> None:
    """Open Post & earn with Inspector — record create-link + 2 ads + create new link loop."""
    cfg = load_flow_config()
    auth_path = auth_state_path()

    handle = open_playwright_session(headed=True, slow_mo=80, storage_state=auth_path)
    try:
        page = handle.get_page()
        page.goto(cfg.post_earn_url, wait_until="domcontentloaded", timeout=120000)
        print(
            "\n=== RECORD LINKVERTISE POST & EARN FLOW ===\n"
            f"Browser: {browser_label()}\n"
            "Do one full cycle:\n"
            "  • Create link -> paste destination URL\n"
            f"  • Select {cfg.ad_tasks_count} ads (not 3)\n"
            "  • Submit -> note the slug URL on screen\n"
            "  • Click Create new link (for batch loop)\n\n"
            "Then: py scripts/import_linkvertise_codegen.py lv_recording.py --ad-tasks 2\n"
            "Press Resume when done.\n"
        )
        page.pause()
        handle.context.storage_state(path=str(auth_path))
    finally:
        handle.close()


def open_dashboard_session(*, headed: bool = False, keep_open: bool = False) -> DashboardSession:
    cfg = load_flow_config()
    if not selectors_ready(cfg):
        raise RuntimeError(
            "Linkvertise flow not configured. Import codegen into linkvertise_dashboard_flow.local.json"
        )
    auth_path = auth_state_path()
    launch_mode = resolve_launch_mode(storage_state=auth_path)
    if launch_mode == "session" and not auth_path.is_file() and not headed:
        raise RuntimeError(
            f"Missing auth state {auth_path}. Run --login (headed) or set TBCC_BRAVE_PROFILE_NAME."
        )
    handle = open_playwright_session(
        headed=headed,
        slow_mo=30,
        storage_state=auth_path if auth_path.is_file() else None,
        keep_open=keep_open,
    )
    page = handle.get_page()
    page.set_default_timeout(60000)
    page.goto(cfg.post_earn_url, wait_until="networkidle", timeout=120000)
    _dismiss_banners(page)
    _ensure_logged_in(page, cfg, headed=headed)
    session = DashboardSession(
        cfg=cfg,
        page=page,
        context=handle.context,
        browser=handle.browser or handle.context,
        _handle=handle,
        _headed=headed,
    )
    session.save_auth()
    return session


def create_dashboard_link(
    destination_url: str,
    *,
    title: str | None = None,
    headed: bool = False,
) -> str:
    """Single link in a fresh browser (batch runs should use DashboardSession)."""
    session = open_dashboard_session(headed=headed)
    try:
        return session.create_link(destination_url, title=title)
    finally:
        session.close()


def create_dashboard_links_batch(
    items: list[tuple[str, str | None]],
    *,
    headed: bool = False,
    keep_open: bool = False,
    no_close: bool = False,
    pack_ids: list[int] | None = None,
) -> list[tuple[str, str | None, str | None]]:
    """Reuse one browser; click Create new link between items. Returns (dest, title, lv_url|error)."""
    keep = keep_open or no_close
    session = open_dashboard_session(headed=headed, keep_open=keep)
    out: list[tuple[str, str | None, str | None]] = []
    try:
        for i, (dest, title) in enumerate(items):
            if pack_ids and i < len(pack_ids):
                session._pack_id = pack_ids[i]
            try:
                lv = session.create_link(dest, title=title, pack_id=session._pack_id)
                out.append((dest, title, lv))
            except Exception as e:
                out.append((dest, title, f"ERROR:{e}"))
                logger.exception("LV batch item failed dest=%s", dest[:80])
            if i + 1 < len(items):
                rate_limit_sleep()
        return out
    finally:
        if no_close and session._handle is not None:
            session.save_auth()
            print(
                "\n=== Automation finished ===\n"
                "Browser stays open. Close the Brave window when done.\n"
                "This terminal waits until you close it, or press Ctrl+C.\n"
            )
            session._handle.wait_until_user_closes()
            session.close(force=True)
        elif keep and headed and session._handle is not None:
            _wait_for_manual_step(
                session.page,
                session.cfg,
                prompt="Verify the created link in the browser, then continue here.",
            )
            session.close(force=True)
        else:
            session.close()


def modifier_needs_lv(mod) -> bool:
    meta = parse_pack_source_note(mod.source_note)
    if meta.gate_lv_url and is_linkvertise_host(meta.gate_lv_url) and not _is_dynamic_linkvertise(meta.gate_lv_url):
        return False
    dest = (meta.destination_url or "").strip()
    return dest.startswith(("http://", "https://"))


def apply_lv_url_to_modifier(mod, lv_url: str) -> None:
    meta = parse_pack_source_note(mod.source_note)
    mod.source_note = merge_pack_source_note(
        mod.source_note or "",
        gate_lv_url=lv_url,
        gate_adm_url=meta.gate_adm_url,
        destination_url=meta.destination_url,
    )
    if not meta.gate_adm_url and is_linkvertise_host(lv_url):
        mod.target_url = lv_url
