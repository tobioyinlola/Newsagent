import pytest

from app.models import Project
from app.services import state_machine as sm


def test_happy_path_and_illegal_jump():
    p = Project(state="draft")
    for s in ["script_ready", "script_approved", "rendering_anchor", "anchor_ready", "final_ready"]:
        sm.transition(p, s)
    with pytest.raises(sm.IllegalTransition):
        sm.transition(Project(state="draft"), "rendering_anchor")
    with pytest.raises(sm.IllegalTransition):
        sm.transition(p, "draft")


def test_fail_and_resume():
    p = Project(state="rendering_anchor")
    sm.fail(p, "boom", retryable=True)
    assert p.state == "failed" and p.failure_retryable
    sm.resume(p)
    assert p.state == "rendering_anchor" and p.failure_reason is None


def test_final_ready_cannot_fail():
    with pytest.raises(sm.IllegalTransition):
        sm.fail(Project(state="final_ready"), "x", retryable=False)
