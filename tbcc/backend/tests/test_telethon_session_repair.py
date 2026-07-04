"""Telethon session schema forward-compat repair."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.utils.telethon_session import repair_session_schema_for_installed_telethon


def test_repair_downgrades_v8_session_with_empty_tmp_auth_key(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "app.utils.telethon_session._installed_telethon_session_version",
        lambda: 7,
    )
    stem = str(tmp_path / "test_admin")
    path = stem + ".session"
    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("create table version (version integer primary key)")
    c.execute("insert into version values (8)")
    c.execute(
        """
        create table sessions (
            dc_id integer primary key,
            server_address text,
            port integer,
            auth_key blob,
            takeout_id integer,
            tmp_auth_key blob
        )
        """
    )
    c.execute(
        "insert into sessions values (?,?,?,?,?,?)",
        (1, "149.154.175.56", 443, b"x" * 256, None, None),
    )
    conn.commit()
    conn.close()

    repair_session_schema_for_installed_telethon(stem)

    conn = sqlite3.connect(path)
    c = conn.cursor()
    c.execute("select version from version")
    assert c.fetchone()[0] == 7
    c.execute("pragma table_info(sessions)")
    cols = [r[1] for r in c.fetchall()]
    assert cols == ["dc_id", "server_address", "port", "auth_key", "takeout_id"]
    c.execute("select dc_id, port, length(auth_key) from sessions")
    assert c.fetchone() == (1, 443, 256)
    conn.close()
