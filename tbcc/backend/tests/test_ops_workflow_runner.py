"""Tests for ops workflow runner."""

from app.services.ops_workflow_runner import workflow_status


def test_workflow_status_loads():
    st = workflow_status()
    assert st.get("ok") is True
    wf = st.get("workflow") or {}
    assert wf.get("id") == "tbcc_ops_turn"
    assert (wf.get("step_count") or 0) >= 4
