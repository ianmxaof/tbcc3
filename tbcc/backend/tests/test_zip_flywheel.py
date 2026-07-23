"""Zip flywheel host router + destination filename helpers."""

from __future__ import annotations

from app.services.zip_flywheel import choose_host, r2_max_bytes


def test_choose_host_hybrid() -> None:
    small = r2_max_bytes() - 1000
    large = r2_max_bytes() + 1000
    assert choose_host(size=small, host="auto") == "r2"
    assert choose_host(size=large, host="auto") == "pixeldrain"
    assert choose_host(size=large, host="auto", prefer_r2=True) == "r2"
    assert choose_host(size=small, host="pixeldrain") == "pixeldrain"
    assert choose_host(size=large, host="r2") == "r2"


def test_flywheel_result_shape() -> None:
    from app.services.zip_flywheel import FlywheelResult

    r = FlywheelResult(
        ok=True,
        host="r2",
        destination_url="https://example.com/a.zip",
        primary_url="https://gate.example/x",
        gate_adm_url="https://gate.example/x",
        filename="pack.zip",
        bytes=12,
    )
    d = r.as_dict()
    assert d["ok"] is True
    assert d["primary_url"].startswith("https://")
    assert d["modifier_id"] is None
