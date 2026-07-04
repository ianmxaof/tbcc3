"""AOF network pools for extension context menu (cherry-pick → pending in target pool)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db

router = APIRouter()


def _short_label(display_name: str) -> str:
    s = (display_name or "").strip()
    if s.upper().startswith("AOF "):
        s = s[4:].strip()
    return s or display_name


@router.get("")
def list_aof_pools_for_extension(db: Session = Depends(get_db)) -> dict:
    """
    Map AOF network channel pools to DB ids for the extension context submenu.
    Skips MAIN hub pool — cherry-picks go to niche lanes only.
    """
    from app.data.aof_network import AOF_NETWORK_CHANNELS
    from app.models.content_pool import ContentPool

    by_name: dict[str, int] = {}
    for row in db.query(ContentPool.id, ContentPool.name).all():
        name = (row.name or "").strip()
        if name:
            by_name[name] = int(row.id)

    pools: list[dict] = []
    for ch in AOF_NETWORK_CHANNELS:
        if ch.key == "main":
            continue
        pid = by_name.get(ch.pool_name)
        if not pid:
            continue
        pools.append(
            {
                "id": pid,
                "key": ch.key,
                "name": ch.pool_name,
                "display_name": ch.display_name,
                "short_label": _short_label(ch.display_name),
            }
        )
    return {"pools": pools}
