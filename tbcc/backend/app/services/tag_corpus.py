"""First-party, versioned tag corpus — parent/child hierarchy + aliases + lane binding.

Single source of truth for lane cue vocabulary (vision-LLM prompt cues, and — via
the merge helpers called from ``aof_lane_tag_map.py`` / ``clip_slug_lane_map.py`` —
the caption-fragment and CLIP-slug maps too, so all three stay aligned instead of
diverging as separately hand-maintained lists).

Not a live scrape. Hand-curated data file at ``app/data/tag_corpus.json``; refresh
by editing that file and re-running the app (the loader is cached per-process via
``lru_cache`` — call ``load_tag_corpus.cache_clear()`` after edits in a long-running
process, or just restart).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "tag_corpus.json"


@dataclass(frozen=True)
class TagNode:
    slug: str
    display_name: str
    parent_slug: str | None
    aliases: tuple[str, ...]
    lane_keys: tuple[str, ...]


@dataclass(frozen=True)
class TagCorpus:
    version: str
    nodes: tuple[TagNode, ...]
    alias_to_slug: dict[str, str]
    slug_to_node: dict[str, TagNode]


def _normalize_alias(raw: str) -> str:
    return " ".join((raw or "").strip().lower().split())


def _validate_and_build(data: dict[str, Any]) -> TagCorpus:
    from app.services.aof_lane_tag_map import CANONICAL_LANE_KEYS

    version = str(data.get("schema_version") or "0.0.0")
    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list):
        raise ValueError("tag_corpus.json: 'nodes' must be a list")

    slug_to_node: dict[str, TagNode] = {}
    alias_to_slug: dict[str, str] = {}
    nodes: list[TagNode] = []

    for raw in raw_nodes:
        if not isinstance(raw, dict):
            raise ValueError(f"tag_corpus.json: node entries must be objects, got {type(raw)}")
        slug = str(raw.get("slug") or "").strip().lower()
        if not slug:
            raise ValueError("tag_corpus.json: node missing required 'slug'")
        if slug in slug_to_node:
            raise ValueError(f"tag_corpus.json: duplicate slug '{slug}'")

        lane_keys = tuple(str(k).strip().lower() for k in (raw.get("lane_keys") or []) if k)
        bad_lanes = [k for k in lane_keys if k not in CANONICAL_LANE_KEYS]
        if bad_lanes:
            raise ValueError(
                f"tag_corpus.json: node '{slug}' has lane_keys outside CANONICAL_LANE_KEYS: {bad_lanes}"
            )

        parent_raw = raw.get("parent_slug")
        parent_slug = str(parent_raw).strip().lower() if parent_raw else None

        aliases: list[str] = []
        seen_alias: set[str] = set()
        for a in raw.get("aliases") or []:
            na = _normalize_alias(str(a))
            if na and na not in seen_alias:
                seen_alias.add(na)
                aliases.append(na)

        node = TagNode(
            slug=slug,
            display_name=str(raw.get("display_name") or slug),
            parent_slug=parent_slug,
            aliases=tuple(aliases),
            lane_keys=lane_keys,
        )
        slug_to_node[slug] = node
        nodes.append(node)

    # Parent references must resolve to a real node (fail fast on typos).
    for node in nodes:
        if node.parent_slug and node.parent_slug not in slug_to_node:
            raise ValueError(f"tag_corpus.json: node '{node.slug}' has unknown parent_slug '{node.parent_slug}'")

    # Second pass: build alias -> slug, dedup rule = first-registered canonical slug wins.
    for node in nodes:
        alias_to_slug.setdefault(node.slug, node.slug)
        for alias in node.aliases:
            existing = alias_to_slug.get(alias)
            if existing and existing != node.slug:
                logger.debug(
                    "tag_corpus alias collision: '%s' already -> '%s', keeping over '%s'",
                    alias,
                    existing,
                    node.slug,
                )
                continue
            alias_to_slug[alias] = node.slug

    return TagCorpus(
        version=version,
        nodes=tuple(nodes),
        alias_to_slug=alias_to_slug,
        slug_to_node=slug_to_node,
    )


@lru_cache(maxsize=1)
def load_tag_corpus() -> TagCorpus:
    raw = json.loads(_CORPUS_PATH.read_text(encoding="utf-8"))
    return _validate_and_build(raw)


def expand_alias_to_slug(alias: str) -> str | None:
    """Alias/token -> canonical corpus slug, or None if unknown."""
    corpus = load_tag_corpus()
    return corpus.alias_to_slug.get(_normalize_alias(alias))


def resolve_lane_keys_for_alias(alias: str) -> list[str]:
    """Alias/token -> ordered unique lane_keys, inheriting from the parent chain."""
    corpus = load_tag_corpus()
    slug = corpus.alias_to_slug.get(_normalize_alias(alias))
    if not slug:
        return []
    node = corpus.slug_to_node.get(slug)
    if not node:
        return []
    lanes: list[str] = list(node.lane_keys)
    seen_slugs = {node.slug}
    parent_slug = node.parent_slug
    while parent_slug and parent_slug not in seen_slugs:
        parent = corpus.slug_to_node.get(parent_slug)
        if not parent:
            break
        for lk in parent.lane_keys:
            if lk not in lanes:
                lanes.append(lk)
        seen_slugs.add(parent_slug)
        parent_slug = parent.parent_slug
    return lanes


def aliases_for_lane(lane_key: str) -> list[str]:
    """All aliases (across every node bound to this lane) — ordered, deduped."""
    corpus = load_tag_corpus()
    key = (lane_key or "").strip().lower()
    out: list[str] = []
    seen: set[str] = set()
    for node in corpus.nodes:
        if key not in node.lane_keys:
            continue
        for alias in node.aliases:
            if alias not in seen:
                seen.add(alias)
                out.append(alias)
    return out


def cue_bullet_for_lane(lane_key: str, *, max_terms: int = 48) -> str:
    """Comma-joined cue vocabulary for a lane, for embedding in a vision-LLM prompt line."""
    terms = aliases_for_lane(lane_key)
    return ", ".join(terms[:max_terms])


def clip_slug_aliases_for_lane(lane_key: str) -> dict[str, tuple[str, ...]]:
    """Corpus aliases reshaped as hyphenated CLIP-slug-style keys -> (lane_key,).

    For merging into ``CLIP_SLUG_TO_LANE`` — space-joined aliases become
    hyphen-joined slugs (``"step mom"`` -> ``"step-mom"``) to match that map's
    existing key style.
    """
    out: dict[str, tuple[str, ...]] = {}
    for alias in aliases_for_lane(lane_key):
        slug_form = alias.replace(" ", "-")
        out.setdefault(slug_form, (lane_key,))
    return out


def lane_tag_map_aliases_for_lane(lane_key: str) -> dict[str, tuple[str, ...]]:
    """Corpus aliases reshaped for merging into ``LANE_TAG_MAP`` (space-joined keys, as-is)."""
    out: dict[str, tuple[str, ...]] = {}
    for alias in aliases_for_lane(lane_key):
        out.setdefault(alias, (lane_key,))
    return out
