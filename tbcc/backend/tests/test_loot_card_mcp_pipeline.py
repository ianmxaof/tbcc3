"""Tests for loot border prompt builder and MCP pipeline helpers."""

from app.services.loot_border_prompt_builder import (
    build_border_animation_prompt,
    parse_border_variants,
    resolve_border_variant,
)
from app.services.loot_card_mcp_pipeline import (
    list_border_variants_summary,
    pipeline_spec,
    write_border_prompt_pack,
)


def test_parse_border_variants_count():
    variants = parse_border_variants()
    assert len(variants) >= 12
    assert variants[0].stem


def test_build_border_prompt_replaces_magenta_rules():
    v = resolve_border_variant("brushed_vault_steel")
    prompt = build_border_animation_prompt(v)
    assert "#FF00FF" in prompt
    assert "[VARIANT" not in prompt
    assert v.chrome[:20] in prompt


def test_write_border_prompt_pack(tmp_path, monkeypatch):
    from app.services import loot_card_mcp_pipeline as pipe

    monkeypatch.setattr(pipe, "staging_prompts_dir", lambda: tmp_path / "prompts")
    monkeypatch.setattr(pipe, "staging_root", lambda: tmp_path)
    monkeypatch.setattr(pipe, "ensure_staging_dirs", lambda: {})

    manifest = write_border_prompt_pack(variants=["brushed_vault_steel"])
    assert manifest["count"] == 1
    assert (tmp_path / "prompts" / "brushed_vault_steel.txt").is_file()


def test_pipeline_spec():
    spec = pipeline_spec()
    assert spec.magenta_matte == "#FF00FF"
    assert spec.import_size_px == 512


def test_list_border_variants_summary():
    rows = list_border_variants_summary()
    assert any(r["stem"] == "brushed_vault_steel" for r in rows)
