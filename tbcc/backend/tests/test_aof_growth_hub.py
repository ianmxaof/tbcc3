"""Tests for AOF growth hub footers and VIP contrast."""

from __future__ import annotations

import os
from unittest.mock import patch

from app.services.aof_growth_hub import (
    build_addlist_footer,
    build_vip_post_contrast_line_html,
    post_footer_vip_contrast_enabled,
)


def test_vip_post_contrast_line_includes_roll_and_timing():
    line = build_vip_post_contrast_line_html()
    assert "VIP rolls" in line
    assert "early" in line.lower()
    assert "/subscribe" in line
    assert "direct where mapped" in line


@patch.dict(os.environ, {"TBCC_POST_FOOTER_VIP_CONTRAST": "0"}, clear=False)
def test_addlist_footer_omits_vip_contrast_when_disabled():
    footer = build_addlist_footer({})
    assert "VIP rolls" not in footer
    assert "/subscribe" in footer


@patch.dict(os.environ, {"TBCC_POST_FOOTER_VIP_CONTRAST": "1"}, clear=False)
def test_addlist_footer_includes_vip_contrast_when_enabled():
    footer = build_addlist_footer({})
    assert "VIP rolls" in footer


def test_post_footer_vip_contrast_default_on():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TBCC_POST_FOOTER_VIP_CONTRAST", None)
        assert post_footer_vip_contrast_enabled() is True
