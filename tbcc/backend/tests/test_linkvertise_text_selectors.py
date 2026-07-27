"""Linkvertise Text wizard selector readiness."""

from app.services.linkvertise_dashboard_provision import (
    FlowConfig,
    load_flow_config,
    selectors_ready,
    text_selectors_ready,
)


def test_link_selectors_ready_from_local_flow():
    cfg = load_flow_config()
    if cfg.flow_mode != "wizard":
        return
    # Local flow should satisfy link wizard when destination_input is set.
    if not cfg.locators.get("destination_input"):
        return
    assert selectors_ready(cfg)


def test_text_selectors_ready_requires_text_keys():
    cfg = FlowConfig(
        publisher_login_url="https://example.com/login",
        post_earn_url="https://example.com/post",
        selectors={},
        locators={
            "wizard_start": {"method": "get_by_role", "args": ["button", {"name": "Next"}]},
            "asset_type_text_option": {"method": "get_by_role", "args": ["button", {"name": "Text"}]},
            "text_body_input": {"method": "locator", "args": ["textarea"]},
            "wizard_next_after_url": {"method": "get_by_role", "args": ["button", {"name": "Next"}]},
            "wizard_next_after_settings": {"method": "get_by_role", "args": ["button", {"name": "Next"}]},
            "submit_button": {"method": "get_by_role", "args": ["button", {"name": "Publish"}]},
        },
        slug_url_pattern="link-target.net/1/",
        wait_after_submit_ms=4000,
        link_title_default="Test",
        flow_mode="wizard",
    )
    assert text_selectors_ready(cfg)
    assert not selectors_ready(cfg)


def test_text_selectors_ready_from_local_when_configured():
    cfg = load_flow_config()
    if cfg.flow_mode != "wizard":
        return
    if not cfg.locators.get("asset_type_text_option"):
        return
    assert text_selectors_ready(cfg)
