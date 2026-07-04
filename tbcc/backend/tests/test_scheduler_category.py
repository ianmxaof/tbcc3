"""Tests for scheduler_category inference."""

from app.services.scheduler_category import infer_scheduler_category


def test_infer_scheduler_category_names():
    assert infer_scheduler_category("AOF MILF SCHEDULER") == "main_lane"
    assert infer_scheduler_category("AOF — bot commands — AOF AI") == "bot_commands"
    assert infer_scheduler_category("AOF — network liveness — heartbeat") == "liveness"
    assert infer_scheduler_category("AOF MAIN — Links Hub bulletin (pinned)") == "promo_bulletin"
    assert infer_scheduler_category("My custom job") == "manual"


def test_infer_scheduler_category_explicit():
    assert infer_scheduler_category("anything", "bot_commands") == "bot_commands"
