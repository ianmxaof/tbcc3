"""Playwright browser launch — Brave by default; optional real Brave profile (password manager)."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

LaunchMode = Literal["persistent", "session"]

_BRAVE_CANDIDATES: tuple[str, ...] = (
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
)


def _expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path)))


def brave_user_data_root() -> Path | None:
    override = (os.getenv("TBCC_BRAVE_USER_DATA_DIR") or "").strip()
    if override:
        p = _expand(override)
        return p if p.is_dir() else None
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return None
    root = Path(local) / "BraveSoftware/Brave-Browser/User Data"
    return root if root.is_dir() else None


def _read_brave_profile_map(user_data: Path) -> dict[str, str]:
    """Display name -> profile folder (e.g. freeusegod -> Profile 1)."""
    state_path = user_data / "Local State"
    if not state_path.is_file():
        return {}
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        cache = (data.get("profile") or {}).get("info_cache") or {}
        out: dict[str, str] = {}
        for folder, info in cache.items():
            if isinstance(info, dict):
                name = str(info.get("name") or "").strip()
                if name:
                    out[name.lower()] = folder
            out[str(folder).lower()] = folder
        return out
    except Exception:
        logger.debug("brave Local State read failed", exc_info=True)
        return {}


# Display names never used for Playwright automation (daily-driver profiles).
_BRAVE_PROFILE_BLOCKLIST: frozenset[str] = frozenset({"freeusegod"})

# Default automation profile on this machine (Profile 5) — override via TBCC_BRAVE_PROFILE_NAME.
_DEFAULT_AUTOMATION_PROFILE = "new"


def list_brave_profiles() -> list[tuple[str, str]]:
    """Return (display_name, folder) for each Brave profile, e.g. ('Personal', 'Default')."""
    root = brave_user_data_root()
    if not root:
        return []
    state_path = root / "Local State"
    if not state_path.is_file():
        return []
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        cache = (data.get("profile") or {}).get("info_cache") or {}
        out: list[tuple[str, str]] = []
        for folder, info in cache.items():
            if isinstance(info, dict):
                name = str(info.get("name") or folder).strip()
                out.append((name, str(folder)))
        return sorted(out, key=lambda x: x[0].lower())
    except Exception:
        return []


def default_brave_profile_name() -> str:
    """Automation profile — never freeusegod unless explicitly set in env."""
    explicit = (os.getenv("TBCC_BRAVE_PROFILE_NAME") or "").strip()
    if explicit:
        return explicit.lower()

    root = brave_user_data_root()
    if not root:
        return _DEFAULT_AUTOMATION_PROFILE

    by_name = {n.lower(): folder for n, folder in list_brave_profiles()}
    for prefer in (_DEFAULT_AUTOMATION_PROFILE, "personal", "sss"):
        if prefer in by_name and prefer not in _BRAVE_PROFILE_BLOCKLIST:
            return prefer

    for name, _folder in list_brave_profiles():
        if name.lower() not in _BRAVE_PROFILE_BLOCKLIST:
            return name.lower()

    return _DEFAULT_AUTOMATION_PROFILE


def resolve_brave_profile_directory(profile_name: str | None = None) -> str | None:
    direct = (os.getenv("TBCC_BRAVE_PROFILE_DIRECTORY") or "").strip()
    if direct:
        return direct
    root = brave_user_data_root()
    if not root:
        return None
    name = (profile_name or default_brave_profile_name()).strip().lower()
    folder = _read_brave_profile_map(root).get(name)
    if folder:
        return folder
    return None


def resolve_brave_profile_path() -> Path | None:
    root = brave_user_data_root()
    folder = resolve_brave_profile_directory()
    if not root or not folder:
        return None
    path = root / folder
    return path if path.is_dir() else None


def brave_process_running() -> bool:
    if sys.platform == "win32":
        try:
            import subprocess

            r = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq brave.exe", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return "brave.exe" in (r.stdout or "").lower()
        except Exception:
            logger.debug("tasklist check failed", exc_info=True)
    try:
        import psutil  # type: ignore[import-untyped]

        return any(p.info.get("name", "").lower() == "brave.exe" for p in psutil.process_iter(["name"]))
    except Exception:
        return False


def brave_profile_locked() -> bool:
    root = brave_user_data_root()
    if not root:
        return False
    for name in ("SingletonLock", "lockfile", "LOCK"):
        if (root / name).exists():
            return True
    folder = resolve_brave_profile_directory()
    if folder:
        profile = root / folder
        for name in ("lockfile", "LOCK"):
            if (profile / name).exists():
                return True
    return brave_process_running()


def playwright_profile_mode() -> str:
    return (os.getenv("TBCC_PLAYWRIGHT_PROFILE_MODE") or "auto").strip().lower()


def use_brave_persistent_profile() -> bool:
    mode = playwright_profile_mode()
    if mode in ("session", "storage", "cookies", "off", "0"):
        return False
    if mode in ("persistent", "profile", "1"):
        return resolve_brave_profile_path() is not None
    raw = (os.getenv("TBCC_PLAYWRIGHT_USE_BRAVE_PROFILE") or "1").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return resolve_brave_profile_path() is not None


def resolve_launch_mode(*, storage_state: str | Path | None = None) -> LaunchMode:
    """persistent = dedicated Brave profile; session = cookie file (parallel with daily Brave)."""
    mode = playwright_profile_mode()
    if mode in ("session", "storage", "cookies"):
        return "session"
    if mode in ("persistent", "profile"):
        return "persistent"

    want_persistent = use_brave_persistent_profile()
    if not want_persistent:
        return "session"

    if brave_profile_locked():
        auth = Path(storage_state) if storage_state else None
        if auth and auth.is_file():
            return "session"
    return "persistent"


def describe_launch_mode(*, storage_state: str | Path | None = None) -> str:
    mode = resolve_launch_mode(storage_state=storage_state)
    name = default_brave_profile_name()
    if mode == "persistent":
        folder = resolve_brave_profile_directory() or "?"
        return f"persistent ({name} / {folder}) — freeusegod stays free for daily use"
    if brave_profile_locked():
        return "session (parallel — uses .linkvertise-auth.json while Brave is open)"
    return "session (uses .linkvertise-auth.json)"


def resolve_browser_executable() -> Path | None:
    override = (os.getenv("TBCC_PLAYWRIGHT_BROWSER_EXECUTABLE") or "").strip()
    if override:
        p = _expand(override)
        if p.is_file():
            return p
        raise FileNotFoundError(f"TBCC_PLAYWRIGHT_BROWSER_EXECUTABLE not found: {p}")

    pref = (os.getenv("TBCC_PLAYWRIGHT_BROWSER") or "brave").strip().lower()
    if pref in ("chromium", "chrome", "bundled"):
        return None

    local = os.environ.get("LOCALAPPDATA", "")
    candidates = list(_BRAVE_CANDIDATES)
    if local:
        candidates.insert(0, str(Path(local) / "BraveSoftware/Brave-Browser/Application/brave.exe"))
    if sys.platform == "darwin":
        candidates = [
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            *candidates,
        ]
    for raw in candidates:
        p = Path(raw)
        if p.is_file():
            return p
    return None


def launch_kwargs(*, headless: bool = False, slow_mo: int | None = None) -> dict[str, Any]:
    kw: dict[str, Any] = {"headless": headless}
    if slow_mo is not None:
        kw["slow_mo"] = slow_mo
    exe = resolve_browser_executable()
    if exe is not None:
        kw["executable_path"] = str(exe)
    return kw


def persistent_context_kwargs(*, headless: bool = False, slow_mo: int | None = None) -> dict[str, Any]:
    kw = launch_kwargs(headless=headless, slow_mo=slow_mo)
    kw["no_viewport"] = True
    folder = resolve_brave_profile_directory()
    if folder:
        existing = list(kw.get("args") or [])
        kw["args"] = [*existing, f"--profile-directory={folder}"]
    return kw


def launch_browser(playwright: Any, *, headless: bool = False, slow_mo: int | None = None) -> Any:
    return playwright.chromium.launch(**launch_kwargs(headless=headless, slow_mo=slow_mo))


@dataclass
class PlaywrightHandle:
    playwright: Any
    context: Any
    browser: Any | None
    persistent: bool
    profile_path: Path | None = None
    launch_mode: LaunchMode = "session"
    keep_open: bool = False

    def get_page(self) -> Any:
        if self.context.pages:
            return self.context.pages[0]
        return self.context.new_page()

    def close(self, *, force: bool = False) -> None:
        if self.keep_open and not force:
            return
        try:
            self.context.close()
            if self.browser is not None:
                self.browser.close()
        finally:
            self.playwright.stop()

    def wait_until_user_closes(self) -> None:
        """Block until the user closes all browser tabs/windows."""
        print("\nBrowser left open — close the Playwright Brave window when you are done.\n")
        try:
            while True:
                pages = list(getattr(self.context, "pages", []) or [])
                if not pages:
                    break
                if all(getattr(p, "is_closed", lambda: True)() for p in pages):
                    break
                pages[0].wait_for_timeout(500)
        except Exception:
            logger.debug("wait_until_user_closes ended", exc_info=True)


def open_playwright_session(
    *,
    headed: bool = True,
    slow_mo: int | None = 50,
    storage_state: str | Path | None = None,
    force_ephemeral: bool = False,
    keep_open: bool = False,
) -> PlaywrightHandle:
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    user_data_root = brave_user_data_root()
    profile_folder = resolve_brave_profile_directory()
    profile_name = default_brave_profile_name()
    launch_mode = "session" if force_ephemeral else resolve_launch_mode(storage_state=storage_state)

    if launch_mode == "persistent" and user_data_root is not None and profile_folder:
        if not headed:
            print(
                f"\nNote: Brave profile '{profile_name}' requires a visible window — enabling headed mode.\n"
            )
            headed = True
        print(
            f"\nOpening Brave profile: {profile_name} ({profile_folder})\n"
            "Automation profile — your freeusegod daily browser can stay open.\n"
            f"Close other windows using the '{profile_name}' profile if launch fails.\n"
        )
        try:
            context = pw.chromium.launch_persistent_context(
                str(user_data_root),
                **persistent_context_kwargs(headless=False, slow_mo=slow_mo),
            )
            return PlaywrightHandle(
                playwright=pw,
                context=context,
                browser=None,
                persistent=True,
                profile_path=user_data_root / profile_folder,
                launch_mode="persistent",
                keep_open=keep_open,
            )
        except Exception as e:
            err = str(e).lower()
            auth = Path(storage_state) if storage_state else None
            if auth and auth.is_file() and any(x in err for x in ("lock", "in use", "profile", "singleton")):
                print(
                    f"\nCould not open profile {profile_name} ({e}).\n"
                    "Falling back to saved session (.linkvertise-auth.json).\n"
                )
                launch_mode = "session"
            else:
                pw.stop()
                raise

    browser = launch_browser(pw, headless=not headed, slow_mo=slow_mo)
    ctx_kwargs: dict[str, Any] = {}
    auth = Path(storage_state) if storage_state else None
    if auth and auth.is_file():
        ctx_kwargs["storage_state"] = str(auth)
        if brave_profile_locked():
            print(
                "\nBrave is already running — opening Playwright with saved Linkvertise cookies.\n"
                "Your daily browser profiles are unaffected.\n"
                "Re-run --login if Linkvertise asks you to sign in again.\n"
            )
        else:
            print(f"\nOpening Brave with saved Linkvertise cookies ({auth.name}).\n")
    else:
        print(
            "\nOpening Brave without a saved session — log in when prompted.\n"
            "Run --login once to export cookies for future runs.\n"
        )
    context = browser.new_context(**ctx_kwargs)
    return PlaywrightHandle(
        playwright=pw,
        context=context,
        browser=browser,
        persistent=False,
        profile_path=None,
        launch_mode="session",
        keep_open=keep_open,
    )


def browser_label() -> str:
    name = default_brave_profile_name()
    folder = resolve_brave_profile_directory() or "?"
    if use_brave_persistent_profile() and not brave_profile_locked():
        return f"brave ({name} / {folder})"
    exe = resolve_browser_executable()
    if exe is None:
        return "Chromium (bundled) + session cookies"
    return f"brave + session cookies (parallel)"


def codegen_cli_command(*, save_storage: str | Path | None = None, url: str | None = None) -> str:
    save = f' --save-storage "{Path(save_storage)}"' if save_storage else ""
    start_url = f' "{url}"' if url else ""
    return f"py -3.13 scripts/linkvertise_codegen.py{save}{start_url}"
