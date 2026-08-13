"""Tests for creative prompt catalog v3."""

from __future__ import annotations

from app.services.creative_prompt_catalog import (
    CreativePromptCatalog,
    MasterTemplate,
    PromptVariation,
    build_variation_prompt,
)
from app.services.prompt_gate_lookup import hash_prompt_body


def test_build_variation_prompt_master_plus_delta():
    catalog = CreativePromptCatalog(
        campaign="test",
        master_template=MasterTemplate(
            style_anchors="neon noir",
            negative_prompt="cartoon",
        ),
        variations=[
            PromptVariation(key="v1", subject_delta="woman in doorway, explicit tease"),
        ],
    )
    body = build_variation_prompt(catalog, catalog.variations[0])
    assert "neon noir" in body
    assert "woman in doorway" in body
    assert "AVOID: cartoon" in body


def test_prompt_body_hash_stable():
    body = "STYLE ANCHORS: test\n\nscene delta"
    h1 = hash_prompt_body(body)
    h2 = hash_prompt_body(body + "\n")
    assert h1 == h2
