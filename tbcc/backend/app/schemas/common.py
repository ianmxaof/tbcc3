from datetime import datetime
from pydantic import BaseModel


def orm_to_dict(obj):
    """Turn a SQLAlchemy model instance into a JSON-serializable dict."""
    if obj is None:
        return None
    d = {}
    for c in obj.__table__.columns:
        v = getattr(obj, c.name)
        if isinstance(v, datetime):
            v = v.isoformat()
        d[c.name] = v
    return d
