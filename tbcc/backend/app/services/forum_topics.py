"""Parse Telethon GetForumTopics responses for dashboard + import."""


def parse_forum_topics_response(resp) -> list[dict]:
    raw = getattr(resp, "topics", None) or []
    topics: list[dict] = []
    seen: set[int] = set()
    for t in raw:
        d = t.to_dict() if hasattr(t, "to_dict") else {}
        tid = d.get("id")
        if tid is None:
            continue
        tid = int(tid)
        if tid in seen:
            continue
        seen.add(tid)
        title = d.get("title", "")
        if isinstance(title, dict):
            title = title.get("text") or ""
        topics.append({"id": tid, "title": str(title).strip() or f"Topic {tid}"})
    return topics
