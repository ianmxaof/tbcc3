"""Wrap eligible URLs with a configured link gate provider (Linkvertise, LootLabs, Work.ink)."""



from __future__ import annotations



import json

import re

from dataclasses import dataclass

from typing import Callable

from urllib.parse import urlparse



from app.services.link_gate_provider import (

    GATE_HOST_SUFFIXES,

    gate_payout_kind,

    is_monetized_gate_host,

    pick_gate_provider,

    publisher_id_from_env,

    wrap_gate_url,

    wrap_linkvertise_url,

    linkvertise_base_from_env,

)

from app.services.link_resolver_policy import normalize_input_url



# Back-compat alias

_SKIP_HOST_SUFFIXES = GATE_HOST_SUFFIXES



_AFFILIATE_HOST_MARKERS = (

    "adultforce.com",

    "nodress.site",

    "botynude.com",

    "nutaku.net",

    "bangbrosnetwork.com",

    "digitalplaygroundnetwork.com",

    "mofosnetwork.com",

    "spicevids.com",

    "mydirtyhobby.com",

    "rk.com",

    "motionmuse.ai",

)



_URL_IN_TEXT_RE = re.compile(r"https?://[^\s\]\)<>\"']+", re.IGNORECASE)





@dataclass

class UrlWrapDecision:

    original: str

    wrapped: str | None

    action: str  # wrap | skip

    reason: str

    provider: str | None = None





def _host(url: str) -> str:

    try:

        return (urlparse(url).hostname or "").lower()

    except Exception:

        return ""





def _is_monetized_host(host: str) -> bool:

    return is_monetized_gate_host(host)





def _is_affiliate_host(host: str) -> bool:

    return any(m in host for m in _AFFILIATE_HOST_MARKERS)





def _is_telegram_internal_c(url: str, host: str) -> bool:

    if host not in ("t.me", "telegram.me"):

        return False

    path = (urlparse(url).path or "").strip("/")

    return path.startswith("c/") or "/c/" in (urlparse(url).path or "")





def _is_telegram_invite(url: str, host: str) -> bool:

    if host not in ("t.me", "telegram.me"):

        return False

    if _is_telegram_internal_c(url, host):

        return False

    path = urlparse(url).path or ""

    return path.startswith("/+") or path.startswith("/addlist/")





def _is_telegram_boost(url: str, host: str) -> bool:

    return host in ("t.me", "telegram.me") and (urlparse(url).path or "").startswith("/boost")





def _is_telegram_public_channel(url: str, host: str) -> bool:

    if host not in ("t.me", "telegram.me"):

        return False

    path = (urlparse(url).path or "").strip("/")

    if not path or path.startswith("+") or path.startswith("addlist/") or path.startswith("boost"):

        return False

    if "?" in path:

        path = path.split("?", 1)[0]

    return bool(path)





def _is_affiliate_telegram_bot(url: str, host: str) -> bool:

    if host not in ("t.me", "telegram.me"):

        return False

    q = urlparse(url).query or ""

    return "start=" in q or "ref" in q.lower()





def classify_url(

    url: str,

    *,

    include_affiliates: bool = False,

    include_public_telegram: bool = True,

    include_mega_hosts: bool = False,

) -> tuple[str, str]:

    norm, block = normalize_input_url(url.rstrip(".,;)]"))

    if not norm:

        return "skip", block or "invalid"



    host = _host(norm)

    if _is_monetized_host(host):

        return "skip", "already_gated"

    if _is_telegram_boost(norm, host):

        return "skip", "telegram_boost"

    if _is_affiliate_host(host) and not include_affiliates:

        return "skip", "affiliate_host"

    if _is_affiliate_telegram_bot(norm, host) and not include_affiliates:

        return "skip", "affiliate_bot_deeplink"



    if _is_telegram_invite(norm, host):

        return "wrap", "telegram_invite"



    if include_public_telegram and _is_telegram_public_channel(norm, host):

        return "wrap", "telegram_public"



    if include_mega_hosts:

        mega_markers = ("mega.nz", "pixeldrain.com", "gofile.io", "mediafire.com", "terabox", "dropbox.com")

        if any(m in host for m in mega_markers):

            return "wrap", "file_host"



    if host in ("t.me", "telegram.me"):

        return "skip", "telegram_other"



    return "skip", "policy_no_match"





def decide_wrap(

    url: str,

    publisher_id: str | int | None = None,

    *,

    provider: str | None = None,

    base_url: str | None = None,

    include_affiliates: bool = False,

    include_public_telegram: bool = True,

    include_mega_hosts: bool = False,

) -> UrlWrapDecision:

    original = url.rstrip(".,;)]")

    action, reason = classify_url(

        original,

        include_affiliates=include_affiliates,

        include_public_telegram=include_public_telegram,

        include_mega_hosts=include_mega_hosts,

    )

    if action != "wrap":

        return UrlWrapDecision(original=original, wrapped=None, action="skip", reason=reason)

    try:

        prov = provider

        if not prov:

            prov = pick_gate_provider(seed=original)

        if prov == "linkvertise":

            pub = publisher_id if publisher_id is not None else publisher_id_from_env()

            wrapped = wrap_linkvertise_url(pub, original, base_url=base_url)

        else:

            wrapped, prov = wrap_gate_url(original, provider=prov, seed=original)

    except (ValueError, RuntimeError) as e:

        return UrlWrapDecision(original=original, wrapped=None, action="skip", reason=str(e))

    return UrlWrapDecision(

        original=original,

        wrapped=wrapped,

        action="wrap",

        reason=reason,

        provider=prov,

    )





def wrap_urls_in_text(

    text: str,

    publisher_id: str | int | None = None,

    *,

    provider: str | None = None,

    base_url: str | None = None,

    include_affiliates: bool = False,

    include_public_telegram: bool = True,

    include_mega_hosts: bool = False,

    on_decision: Callable[[UrlWrapDecision], None] | None = None,

) -> tuple[str, list[UrlWrapDecision]]:

    decisions: list[UrlWrapDecision] = []

    replacements: dict[str, str] = {}



    for match in _URL_IN_TEXT_RE.finditer(text or ""):

        raw = match.group(0)

        if raw in replacements:

            continue

        d = decide_wrap(

            raw,

            publisher_id,

            provider=provider,

            base_url=base_url,

            include_affiliates=include_affiliates,

            include_public_telegram=include_public_telegram,

            include_mega_hosts=include_mega_hosts,

        )

        decisions.append(d)

        if on_decision:

            on_decision(d)

        if d.wrapped:

            replacements[raw] = d.wrapped



    out = text or ""

    for orig, wrapped in replacements.items():

        out = out.replace(orig, wrapped)

    return out, decisions





def decisions_to_promo_items(decisions: list[UrlWrapDecision], *, label_prefix: str = "gate") -> list[dict]:

    items: list[dict] = []

    seen: set[str] = set()

    n = 0

    for d in decisions:

        if not d.wrapped or d.original in seen:

            continue

        seen.add(d.original)

        n += 1

        slug = re.sub(r"[^a-zA-Z0-9]+", "-", d.original)[:40].strip("-").lower() or f"link-{n}"

        kind = gate_payout_kind(d.provider or "linkvertise")

        items.append(

            {

                "label": f"{label_prefix}-{slug}"[:512],

                "url": d.original,

                "short_url": d.wrapped,

                "payout_kind": kind,

                "payout_detail": (d.provider or kind)[:64],

                "priority_tier": 15,

                "active": True,

            }

        )

    return items





def wrap_scheduled_post_content(

    content: str,

    variations_json: str | None,

    publisher_id: str | int | None = None,

    **kwargs,

) -> tuple[str, str | None, list[UrlWrapDecision]]:

    new_content, dec_main = wrap_urls_in_text(content, publisher_id, **kwargs)

    all_dec = list(dec_main)

    new_var_json: str | None = variations_json

    if variations_json:

        try:

            vars_list = json.loads(variations_json)

        except json.JSONDecodeError:

            vars_list = None

        if isinstance(vars_list, list):

            out_vars: list[str] = []

            for v in vars_list:

                if not isinstance(v, str):

                    continue

                wrapped, dec_v = wrap_urls_in_text(v, publisher_id, **kwargs)

                out_vars.append(wrapped)

                all_dec.extend(dec_v)

            new_var_json = json.dumps(out_vars)

    return new_content, new_var_json, all_dec


