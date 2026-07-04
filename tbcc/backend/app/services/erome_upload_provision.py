"""Playwright automation for Erome album uploads (local staging folder → album URL)."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.crawler_resolver import _EROME_ALBUM_DIRECT_RE, _normalize_erome_album_url
from app.services.linkvertise_playwright_locators import click_spec, fill_spec, locator_from_spec
from app.services.playwright_browser import (
    PlaywrightHandle,
    browser_label,
    codegen_cli_command,
    open_playwright_session,
    resolve_launch_mode,
    use_brave_persistent_profile,
)

logger = logging.getLogger(__name__)

_FLOW_PATH = Path(__file__).resolve().parents[1] / "data" / "erome_upload_flow.json"
_DEFAULT_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".mp4",
    ".mov",
    ".webm",
    ".avi",
    ".mkv",
)


@dataclass
class EromeFlowConfig:
    login_url: str
    email_login_url: str
    upload_url: str
    selectors: dict[str, str]
    locators: dict[str, Any]
    wait_after_submit_ms: int
    upload_complete_timeout_ms: int
    album_title_default: str
    allowed_extensions: tuple[str, ...]
    flow_mode: str = "simple"
    age_gate_use_popup: bool = False


@dataclass
class StagingScan:
    folder: Path
    files: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.files)


@dataclass
class UploadResult:
    ok: bool
    album_url: str | None = None
    title: str | None = None
    tags: list[str] | None = None
    description: str | None = None
    file_count: int = 0
    staging_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "album_url": self.album_url,
            "title": self.title,
            "tags": list(self.tags or []),
            "description": self.description,
            "file_count": self.file_count,
            "staging_path": self.staging_path,
            "error": self.error,
        }


def flow_config_path() -> Path:
    override = (os.getenv("TBCC_EROME_FLOW_CONFIG") or "").strip()
    if override:
        return Path(override)
    local = _FLOW_PATH.with_name("erome_upload_flow.local.json")
    if local.is_file():
        return local
    return _FLOW_PATH


def auth_state_path() -> Path:
    raw = (os.getenv("TBCC_EROME_AUTH_STATE") or "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[2] / ".erome-auth.json"


def load_flow_config() -> EromeFlowConfig:
    path = flow_config_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    sel = data.get("selectors") or {}
    loc = data.get("locators") or {}
    ext_raw = data.get("allowed_extensions") or list(_DEFAULT_EXTENSIONS)
    extensions = tuple(str(x).lower() for x in ext_raw if str(x).strip())
    if not extensions:
        extensions = _DEFAULT_EXTENSIONS
    login_url = str(data.get("login_url") or "https://www.erome.com/user/login")
    email_login = str(data.get("email_login_url") or login_url)
    return EromeFlowConfig(
        login_url=login_url,
        email_login_url=email_login,
        upload_url=str(data.get("upload_url") or "https://www.erome.com/"),
        selectors={k: str(v or "") for k, v in sel.items()},
        locators=loc if isinstance(loc, dict) else {},
        wait_after_submit_ms=int(data.get("wait_after_submit_ms") or 8000),
        upload_complete_timeout_ms=int(data.get("upload_complete_timeout_ms") or 300000),
        album_title_default=str(data.get("album_title_default") or "AOF Pack"),
        allowed_extensions=extensions,
        flow_mode=str(data.get("flow_mode") or "simple").strip().lower(),
        age_gate_use_popup=bool(data.get("age_gate_use_popup", False)),
    )


def _spec(cfg: EromeFlowConfig, key: str) -> dict[str, Any] | str | None:
    if key in cfg.locators and cfg.locators[key]:
        return cfg.locators[key]
    css = (cfg.selectors.get(key) or "").strip()
    return css or None


def selectors_ready(cfg: EromeFlowConfig) -> bool:
    return bool(_spec(cfg, "file_input")) and bool(_spec(cfg, "submit_button"))


def scan_staging_folder(
    folder: str | Path,
    *,
    allowed_extensions: tuple[str, ...] | None = None,
    max_files: int | None = None,
) -> StagingScan:
    root = Path(folder).expanduser().resolve()
    scan = StagingScan(folder=root)
    if not root.is_dir():
        scan.skipped.append(f"not_a_directory:{root}")
        return scan

    exts = allowed_extensions or _DEFAULT_EXTENSIONS
    ext_set = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in exts}
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in ext_set:
            scan.skipped.append(str(path.relative_to(root)))
            continue
        found.append(path)
    if max_files is not None and len(found) > max_files:
        scan.skipped.extend(str(p.relative_to(root)) for p in found[max_files:])
        found = found[:max_files]
    scan.files = found
    return scan


def extract_erome_album_url(text: str) -> str | None:
    m = _EROME_ALBUM_DIRECT_RE.search(text or "")
    if not m:
        return None
    return _normalize_erome_album_url(m.group(1))


def _dismiss_age_gate_inline(page: Any, cfg: EromeFlowConfig) -> None:
    spec = _spec(cfg, "age_gate_button")
    if spec:
        try:
            click_spec(page, spec, timeout_ms=3000)
            page.wait_for_timeout(400)
            return
        except Exception:
            pass
    for label in ("Enter", "I am 18", "Yes", "Continue", "I am 18 or older - enter"):
        try:
            page.get_by_text(re.compile(re.escape(label), re.I)).first.click(timeout=2000)
            page.wait_for_timeout(400)
            return
        except Exception:
            continue


def _accept_age_gate(page: Any, cfg: EromeFlowConfig) -> Any:
    """Accept age gate; returns popup page when Erome opens login in a new window."""
    if cfg.age_gate_use_popup:
        spec = _spec(cfg, "age_gate_button")
        if spec:
            try:
                loc = locator_from_spec(page, spec).first
                with page.expect_popup(timeout=10000) as popup_info:
                    loc.click(timeout=8000)
                popup = popup_info.value
                popup.wait_for_load_state("domcontentloaded")
                popup.wait_for_timeout(600)
                return popup
            except Exception:
                logger.debug("age gate popup path failed", exc_info=True)
    _dismiss_age_gate_inline(page, cfg)
    return page


def _dismiss_age_gate(page: Any, cfg: EromeFlowConfig) -> None:
    _accept_age_gate(page, cfg)


def _on_email_login_form(page: Any) -> bool:
    try:
        return page.get_by_label(re.compile(r"E-?Mail", re.I)).first.is_visible()
    except Exception:
        return False


def navigate_to_email_login(page: Any, cfg: EromeFlowConfig) -> Any:
    """Direct email login — Google OAuth is blocked in Playwright automation."""
    try:
        page.goto(cfg.email_login_url, wait_until="domcontentloaded", timeout=120000)
    except Exception as e:
        err = str(e).lower()
        if "interrupted" not in err and "navigation" not in err:
            raise
        logger.debug("login navigation interrupted (%s) — continuing on current page", e)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
    page = _accept_age_gate(page, cfg)
    if _on_email_login_form(page):
        return page
    email_spec = _spec(cfg, "email_login_link")
    if email_spec:
        try:
            click_spec(page, email_spec, timeout_ms=8000)
            page.wait_for_timeout(800)
            if _on_email_login_form(page):
                return page
        except Exception:
            pass
    for label in ("login with Email", "Login with Email"):
        try:
            page.get_by_text(re.compile(label, re.I)).first.click(timeout=5000)
            page.wait_for_timeout(800)
            if _on_email_login_form(page):
                return page
        except Exception:
            continue
    try:
        page.get_by_label(re.compile(r"E-?Mail", re.I)).first.wait_for(state="visible", timeout=15000)
    except Exception:
        logger.debug("email login form not found after navigate", exc_info=True)
    return page


def _login_wall_visible(page: Any) -> bool:
    if _on_email_login_form(page):
        return True
    checks = [
        lambda: page.get_by_text(re.compile(r"^SIGN IN$", re.I)).first.is_visible(),
        lambda: page.get_by_text(re.compile(r"login with Email", re.I)).first.is_visible(),
        lambda: page.get_by_text(re.compile(r"login with Google", re.I)).first.is_visible(),
    ]
    for check in checks:
        try:
            if check():
                return True
        except Exception:
            continue
    return False


def _looks_logged_in(page: Any, cfg: EromeFlowConfig) -> bool:
    url = (page.url or "").lower()
    if "/user/login" in url or "/register" in url:
        return False
    if _on_email_login_form(page):
        return False
    try:
        if page.get_by_text(re.compile(r"^SIGN IN$", re.I)).first.is_visible():
            return False
    except Exception:
        pass
    nav_spec = _spec(cfg, "upload_nav")
    if nav_spec:
        try:
            locator_from_spec(page, nav_spec).first.wait_for(state="visible", timeout=1500)
            return True
        except Exception:
            pass
    try:
        page.get_by_role("link", name=re.compile(r"upload", re.I)).first.wait_for(state="visible", timeout=1500)
        return True
    except Exception:
        pass
    try:
        page.get_by_role("link").filter(has_text=re.compile(r"UPLOAD", re.I)).first.wait_for(
            state="visible", timeout=1500
        )
        return True
    except Exception:
        pass
    for pattern in (r"log\s*out", r"my albums", r"my profile"):
        try:
            page.get_by_text(re.compile(pattern, re.I)).first.wait_for(state="visible", timeout=800)
            return True
        except Exception:
            continue
    try:
        if page.get_by_text(re.compile(r"login with Google", re.I)).first.is_visible():
            return False
    except Exception:
        pass
    return False


def _upload_ui_visible(page: Any, cfg: EromeFlowConfig) -> bool:
    if not _looks_logged_in(page, cfg):
        return False
    file_spec = _spec(cfg, "file_input")
    if file_spec:
        try:
            locator_from_spec(page, file_spec).first.wait_for(state="attached", timeout=2000)
            return True
        except Exception:
            pass
    nav_spec = _spec(cfg, "upload_nav")
    if nav_spec:
        try:
            locator_from_spec(page, nav_spec).first.wait_for(state="visible", timeout=2000)
            return True
        except Exception:
            pass
    try:
        page.locator('input[type="file"]').first.wait_for(state="attached", timeout=1500)
        return True
    except Exception:
        return False


def _wait_for_login(page: Any, cfg: EromeFlowConfig, *, headed: bool) -> Any:
    wait_s = int(os.getenv("TBCC_EROME_WAIT_LOGIN_S") or "300")
    if not _looks_logged_in(page, cfg):
        try:
            page = navigate_to_email_login(page, cfg)
        except Exception:
            logger.debug("navigate_to_email_login failed — waiting on current page", exc_info=True)
    print(
        "\n=== EROME LOGIN ===\n"
        f"Browser: {browser_label()}\n"
        "1. Accept the age gate if shown.\n"
        "2. Sign in with EMAIL + password (do NOT use Google — blocked in automation).\n"
        "3. Solve captcha manually if shown.\n"
        "4. After login you should see UPLOAD in the nav.\n"
        f"Automation continues automatically when ready (up to {wait_s}s)…\n",
        flush=True,
    )
    deadline = time.time() + wait_s
    while time.time() < deadline:
        page = _accept_age_gate(page, cfg)
        if _looks_logged_in(page, cfg):
            print("Erome session ready — continuing.\n", flush=True)
            return page
        page.wait_for_timeout(2000)
    raise RuntimeError(
        f"Timed out after {wait_s}s waiting for Erome login. "
        "Sign in in the Playwright browser window and re-run."
    )


def _click_if_spec(page: Any, cfg: EromeFlowConfig, key: str, *, timeout_ms: int = 15000) -> bool:
    spec = _spec(cfg, key)
    if not spec:
        return False
    try:
        click_spec(page, spec, timeout_ms=timeout_ms)
        page.wait_for_timeout(500)
        return True
    except Exception:
        return False


def _navigate_to_upload(page: Any, cfg: EromeFlowConfig) -> Any:
    page.goto(cfg.upload_url, wait_until="domcontentloaded", timeout=120000)
    page = _accept_age_gate(page, cfg)

    file_spec = _spec(cfg, "file_input")
    if file_spec and cfg.flow_mode != "edit_album":
        try:
            locator_from_spec(page, file_spec).first.wait_for(state="attached", timeout=3000)
            return page
        except Exception:
            pass

    if not _click_if_spec(page, cfg, "upload_nav"):
        try:
            page.get_by_role("link").filter(has_text=re.compile(r"UPLOAD", re.I)).first.click(timeout=15000)
            page.wait_for_timeout(1500)
        except Exception as e:
            raise RuntimeError("Could not open Erome upload (UPLOAD link missing)") from e
    else:
        page.wait_for_timeout(1500)

    _click_if_spec(page, cfg, "dismiss_close_button")

    if cfg.flow_mode == "edit_album":
        try:
            page.wait_for_url(re.compile(r"/a/[A-Za-z0-9_-]+(/edit)?"), timeout=30000)
        except Exception:
            logger.debug("edit album url wait skipped", exc_info=True)

    if not file_spec:
        raise RuntimeError("file_input locator missing in erome_upload_flow config")
    locator_from_spec(page, file_spec).first.wait_for(state="attached", timeout=60000)
    return page


def _scrape_album_url(page: Any) -> str | None:
    url = (page.url or "").strip()
    found = extract_erome_album_url(url)
    if found:
        return found
    try:
        html = page.content()
    except Exception:
        html = ""
    found = extract_erome_album_url(html)
    if found:
        return found
    try:
        js = page.evaluate(
            """() => {
              const links = Array.from(document.querySelectorAll('a[href*="/a/"]'));
              for (const a of links) {
                const h = a.href || '';
                if (/\\/a\\/[A-Za-z0-9_-]+/.test(h)) return h;
              }
              return '';
            }"""
        )
        if js:
            return extract_erome_album_url(str(js))
    except Exception:
        logger.debug("album url js scrape failed", exc_info=True)
    return None


def _editor_media_count(page: Any) -> int:
    try:
        return int(
            page.evaluate(
                """() => {
                  const uploads = document.querySelectorAll('#medias .upload').length;
                  if (uploads) return uploads;
                  return document.querySelectorAll('#medias .media-group, .media-group[data-id]').length;
                }"""
            )
        )
    except Exception:
        return 0


def _uploads_in_progress(page: Any) -> bool:
    try:
        return bool(
            page.evaluate(
                """() => {
                  if (document.querySelectorAll('#medias img.uploading-img').length) return true;
                  const txt = (document.body.innerText || '').toLowerCase();
                  return /uploading|processing|please wait/.test(txt);
                }"""
            )
        )
    except Exception:
        return False


def _erome_format_error_visible(page: Any) -> str | None:
    try:
        err = page.evaluate(
            """() => {
              const txt = (document.body.innerText || '');
              const m = txt.match(/Format error/i);
              return m ? m[0] : '';
            }"""
        )
        if err:
            return str(err)
    except Exception:
        pass
    return None


def _attach_files_to_erome_editor(page: Any, cfg: EromeFlowConfig, paths: list[str]) -> None:
    """Select local files in the Erome album editor (click drop zone when configured)."""
    file_spec = _spec(cfg, "file_input")
    if not file_spec:
        raise RuntimeError("file_input locator missing")
    drag = _spec(cfg, "drag_drop_zone")
    if drag:
        _click_if_spec(page, cfg, "drag_drop_zone")
        page.wait_for_timeout(400)
    file_loc = locator_from_spec(page, file_spec).first
    try:
        file_loc.set_input_files(paths)
    except Exception:
        file_loc = page.locator('input[type="file"]').first
        file_loc.set_input_files(paths)
    page.wait_for_timeout(600)
    fmt_err = _erome_format_error_visible(page)
    if fmt_err:
        raise RuntimeError(
            f"Erome rejected file format ({fmt_err}). "
            "Re-export media or disable watermark for that file type."
        )


def _wait_for_erome_uploads(page: Any, expected_count: int) -> None:
    """Wait until Erome editor shows all selected files finished uploading."""
    wait_s = float(os.getenv("TBCC_EROME_UPLOAD_WAIT_S") or "600")
    deadline = time.time() + wait_s
    last_count = -1
    stable = 0
    while time.time() < deadline:
        fmt_err = _erome_format_error_visible(page)
        if fmt_err:
            raise RuntimeError(
                f"Erome rejected upload ({fmt_err}). "
                "Check staged files are valid JPEG/PNG/MP4 (corrupt downloads fail here)."
            )
        count = _editor_media_count(page)
        in_progress = _uploads_in_progress(page)
        if count >= expected_count and not in_progress:
            stable += 1
            if stable >= 2:
                page.wait_for_timeout(800)
                return
        else:
            stable = 0
        if count != last_count:
            logger.info("Erome editor media count: %s/%s (in_progress=%s)", count, expected_count, in_progress)
            last_count = count
        page.wait_for_timeout(2000)
    raise RuntimeError(
        f"Timed out after {wait_s:.0f}s waiting for {expected_count} file(s) to finish uploading on Erome "
        f"(last editor count={last_count})"
    )


def _album_public_media_count(page: Any) -> int:
    try:
        return int(
            page.evaluate(
                """() => {
                  const groups = document.querySelectorAll('#medias .media-group, .media-group').length;
                  if (groups) return groups;
                  return document.querySelectorAll('#medias img[src*="erome.com/i/"], #medias video').length;
                }"""
            )
        )
    except Exception:
        return 0


def _wait_for_album_published(page: Any, cfg: EromeFlowConfig) -> str | None:
    """After SAVE, wait until we land on the public album view (not /edit)."""
    timeout_ms = cfg.upload_complete_timeout_ms
    deadline = time.time() + (timeout_ms / 1000.0)
    published_re = re.compile(r"/a/[A-Za-z0-9_-]+/?$")
    while time.time() < deadline:
        url = (page.url or "").strip()
        if published_re.search(url.split("?", 1)[0]):
            found = extract_erome_album_url(url)
            if found:
                return found
        found = _scrape_album_url(page)
        if found and "/edit" not in (page.url or ""):
            return found
        page.wait_for_timeout(1500)
    return None


def _wait_for_album_url(page: Any, cfg: EromeFlowConfig) -> str | None:
    timeout_ms = cfg.upload_complete_timeout_ms
    deadline = time.time() + (timeout_ms / 1000.0)
    last_url = ""
    while time.time() < deadline:
        found = _scrape_album_url(page)
        if found and "/edit" not in (page.url or ""):
            return found
        cur = page.url or ""
        if cur != last_url:
            last_url = cur
            logger.info("Erome post-submit url: %s", cur[:120])
        page.wait_for_timeout(1500)
    return _scrape_album_url(page)


@dataclass
class EromeUploadSession:
    cfg: EromeFlowConfig
    page: Any
    context: Any
    browser: Any
    _handle: PlaywrightHandle | None = None
    _headed: bool = False
    _auth_path: Path = field(default_factory=auth_state_path)

    def save_auth(self) -> None:
        auth_path = self._auth_path
        if self._handle is None or self._handle.persistent:
            return
        try:
            auth_path.parent.mkdir(parents=True, exist_ok=True)
            self.context.storage_state(path=str(auth_path))
        except Exception:
            logger.debug("erome storage_state export skipped", exc_info=True)

    def close(self, *, force: bool = False) -> None:
        try:
            self.save_auth()
        finally:
            if self._handle is not None:
                self._handle.close(force=force)
            elif self.browser is not None:
                self.browser.close()

    def _fill_tags(self, tags: list[str]) -> None:
        if not tags:
            return
        tags_spec = _spec(self.cfg, "tags_input")
        if not tags_spec:
            logger.debug("tags_input locator missing — skipping tags")
            return
        joined = ", ".join(t.strip() for t in tags if t.strip())[:500]
        if not joined:
            return
        try:
            fill_spec(self.page, tags_spec, joined)
        except Exception:
            logger.debug("tags fill failed — continuing", exc_info=True)

    def upload_files(
        self,
        files: list[Path],
        *,
        title: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        fresh_navigate: bool = True,
    ) -> UploadResult:
        if not files:
            return UploadResult(ok=False, error="no_files")
        album_title = (title or self.cfg.album_title_default).strip() or self.cfg.album_title_default
        staging = str(files[0].parent)
        tag_list = [t.strip() for t in (tags or []) if t and str(t).strip()]
        try:
            if fresh_navigate:
                self.page = _navigate_to_upload(self.page, self.cfg)
            paths = [str(p.resolve()) for p in files]
            _attach_files_to_erome_editor(self.page, self.cfg, paths)
            _wait_for_erome_uploads(self.page, len(files))

            title_spec = _spec(self.cfg, "title_input")
            if title_spec:
                try:
                    fill_spec(self.page, title_spec, album_title)
                except Exception:
                    logger.debug("title fill failed — continuing", exc_info=True)

            desc_spec = _spec(self.cfg, "description_input")
            if description and desc_spec:
                try:
                    fill_spec(self.page, desc_spec, description)
                except Exception:
                    logger.debug("description fill failed", exc_info=True)

            self._fill_tags(tag_list)

            submit_spec = _spec(self.cfg, "submit_button")
            if not submit_spec:
                raise RuntimeError("submit_button locator missing")
            click_spec(self.page, submit_spec, timeout_ms=60000)
            self.page.wait_for_timeout(self.cfg.wait_after_submit_ms)

            album_url = _wait_for_album_published(self.page, self.cfg) or _wait_for_album_url(
                self.page, self.cfg
            )
            if not album_url or "/edit" in (self.page.url or ""):
                return UploadResult(
                    ok=False,
                    title=album_title,
                    file_count=len(files),
                    staging_path=staging,
                    error="album_not_published",
                )
            media_count = _album_public_media_count(self.page)
            if media_count < len(files):
                logger.warning(
                    "Erome album published with %s/%s media visible at %s",
                    media_count,
                    len(files),
                    album_url,
                )
                if media_count == 0:
                    return UploadResult(
                        ok=False,
                        album_url=album_url,
                        title=album_title,
                        file_count=len(files),
                        staging_path=staging,
                        error="album_empty_after_publish",
                    )
            self.save_auth()
            return UploadResult(
                ok=True,
                album_url=album_url,
                title=album_title,
                tags=tag_list or None,
                description=description,
                file_count=len(files),
                staging_path=staging,
            )
        except Exception as e:
            logger.exception("erome upload failed")
            return UploadResult(
                ok=False,
                title=album_title,
                tags=tag_list or None,
                description=description,
                file_count=len(files),
                staging_path=staging,
                error=str(e)[:400],
            )


def login_and_save_session(*, headed: bool = True) -> Path:
    """Open Erome in Brave; export cookies for parallel runs."""
    cfg = load_flow_config()
    auth_path = auth_state_path()
    auth_path.parent.mkdir(parents=True, exist_ok=True)

    handle = open_playwright_session(headed=headed, slow_mo=80, storage_state=auth_path, force_ephemeral=True)
    try:
        page = handle.get_page()
        page = navigate_to_email_login(page, cfg)
        print(
            "\n=== EROME LOGIN ===\n"
            f"Browser: {browser_label()}\n"
            "1. Accept age gate if shown.\n"
            "2. Sign in with EMAIL + password (not Google — OAuth blocked in Playwright).\n"
            "3. Solve captcha if shown.\n"
            "3. Press Resume in Playwright Inspector when upload UI is reachable.\n"
            f"\nCookies save to {auth_path.name} for runs while daily Brave stays open.\n"
            f"\nOr record upload flow:\n  {codegen_cli_command(save_storage=auth_path, url=cfg.upload_url)}\n"
        )
        if headed:
            page.pause()
        elif sys.stdin.isatty():
            input("Press Enter after login completes… ")
        else:
            _wait_for_login(page, cfg, headed=False)
        handle.context.storage_state(path=str(auth_path))
    finally:
        handle.close()

    print(f"Saved session -> {auth_path}")
    return auth_path


def record_upload_flow(*, headed: bool = True) -> None:
    """Open upload page with Inspector — record selectors into flow.local.json."""
    cfg = load_flow_config()
    auth_path = auth_state_path()
    handle = open_playwright_session(headed=True, slow_mo=80, storage_state=auth_path)
    try:
        page = handle.get_page()
        page.goto(cfg.upload_url, wait_until="domcontentloaded", timeout=120000)
        page = _accept_age_gate(page, cfg)
        print(
            "\n=== RECORD EROME UPLOAD FLOW ===\n"
            f"Browser: {browser_label()}\n"
            "Do one full upload cycle:\n"
            "  • Open Upload\n"
            "  • Select files from disk\n"
            "  • Fill title → Publish\n"
            "  • Note album URL on success screen\n\n"
            "Copy Inspector Python into erome_upload_flow.local.json locators or a recording file.\n"
            "Press Resume when done.\n"
        )
        page.pause()
        handle.context.storage_state(path=str(auth_path))
    finally:
        handle.close()


def open_upload_session(*, headed: bool = False, keep_open: bool = False) -> EromeUploadSession:
    cfg = load_flow_config()
    if not selectors_ready(cfg):
        raise RuntimeError(
            "Erome flow not configured. Set file_input + submit_button in erome_upload_flow.local.json"
        )
    auth_path = auth_state_path()
    launch_mode = resolve_launch_mode(storage_state=auth_path)
    if launch_mode == "session" and not auth_path.is_file() and not headed:
        raise RuntimeError(
            f"Missing auth state {auth_path}. Run --login (headed) or set TBCC_BRAVE_PROFILE_NAME."
        )
    handle = open_playwright_session(
        headed=headed,
        slow_mo=int(os.getenv("TBCC_EROME_SLOW_MO") or "0"),
        storage_state=auth_path if auth_path.is_file() else None,
        keep_open=keep_open,
    )
    page = handle.get_page()
    page.set_default_timeout(60000)
    page.goto(cfg.upload_url, wait_until="domcontentloaded", timeout=120000)
    page = _accept_age_gate(page, cfg)
    if not _looks_logged_in(page, cfg):
        if headed or auth_path.is_file() or use_brave_persistent_profile():
            page = _wait_for_login(page, cfg, headed=headed)
        else:
            raise RuntimeError("Not logged in to Erome. Run --login first.")
    session = EromeUploadSession(
        cfg=cfg,
        page=page,
        context=handle.context,
        browser=handle.browser or handle.context,
        _handle=handle,
        _headed=headed,
        _auth_path=auth_path,
    )
    session.save_auth()
    return session


def upload_local_folder(
    folder: str | Path,
    *,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    headed: bool = False,
    keep_open: bool = False,
    max_files: int | None = None,
) -> UploadResult:
    cfg = load_flow_config()
    scan = scan_staging_folder(folder, allowed_extensions=cfg.allowed_extensions, max_files=max_files)
    if not scan.ok:
        return UploadResult(ok=False, staging_path=str(scan.folder), error="no_media_files")
    session = open_upload_session(headed=headed, keep_open=keep_open)
    try:
        return session.upload_files(
            scan.files,
            title=title,
            description=description,
            tags=tags,
        )
    finally:
        if not keep_open:
            session.close()



@dataclass
class AlbumUploadJob:
    folder: Path
    files: list[Path]
    title: str | None = None
    description: str | None = None
    mega_folder: str | None = None
    modifier_id: int | None = None
    label: str | None = None

    @classmethod
    def from_folder(
        cls,
        folder: str | Path,
        *,
        title: str | None = None,
        files: list[Path] | None = None,
        **kwargs: Any,
    ) -> AlbumUploadJob:
        root = Path(folder).resolve()
        return cls(folder=root, files=list(files or []), title=title, **kwargs)


def _start_next_album(page: Any, cfg: EromeFlowConfig) -> Any:
    """Open a fresh album editor for the next batch item."""
    page.goto(cfg.upload_url, wait_until="domcontentloaded", timeout=90000)
    page = _accept_age_gate(page, cfg)
    if not _click_if_spec(page, cfg, "upload_nav"):
        try:
            page.get_by_role("link").filter(has_text=re.compile(r"UPLOAD", re.I)).first.click(timeout=15000)
        except Exception as e:
            raise RuntimeError("Could not start next Erome album (UPLOAD missing)") from e
    page.wait_for_timeout(1200)
    _click_if_spec(page, cfg, "dismiss_close_button")
    file_spec = _spec(cfg, "file_input")
    if file_spec:
        locator_from_spec(page, file_spec).first.wait_for(state="attached", timeout=60000)
    return page


def upload_albums_batch(
    jobs: list[AlbumUploadJob],
    *,
    headed: bool = False,
    keep_open: bool = False,
) -> list[UploadResult]:
    if not jobs:
        return []
    session = open_upload_session(headed=headed, keep_open=keep_open)
    results: list[UploadResult] = []
    try:
        for i, job in enumerate(jobs):
            if not job.files:
                results.append(
                    UploadResult(ok=False, staging_path=str(job.folder), error="no_files", title=job.title)
                )
                continue
            if i > 0:
                session.page = _start_next_album(session.page, session.cfg)
            result = session.upload_files(
                job.files,
                title=job.title,
                description=job.description,
                tags=getattr(job, "tags", None),
                fresh_navigate=(i == 0),
            )
            results.append(result)
    finally:
        if not keep_open:
            session.close()
    return results


def upload_local_folders_batch(
    folders: list[str | Path],
    *,
    titles: list[str | None] | None = None,
    headed: bool = False,
    keep_open: bool = False,
    max_files: int | None = None,
) -> list[UploadResult]:
    cfg = load_flow_config()
    jobs: list[AlbumUploadJob] = []
    for i, folder in enumerate(folders):
        scan = scan_staging_folder(folder, allowed_extensions=cfg.allowed_extensions, max_files=max_files)
        title = (titles[i] if titles and i < len(titles) else None) or Path(folder).name
        jobs.append(AlbumUploadJob.from_folder(folder, title=title, files=scan.files))
    return upload_albums_batch(jobs, headed=headed, keep_open=keep_open)


def save_upload_manifest(result: UploadResult, path: str | Path) -> Path:
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    payload["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return out
