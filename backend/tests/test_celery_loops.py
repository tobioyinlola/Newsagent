from app.integrations import registry
from app.pipeline import celery_app


def test_each_worker_task_gets_fresh_providers(monkeypatch):
    """Vendor clients are bound to the event loop that made them; a task must never reuse one from an earlier task."""
    seen = []

    async def fake_run_step(step, payload):
        seen.append(registry.get_email())

    monkeypatch.setattr("app.pipeline.runner.run_step", fake_run_step)
    celery_app.run_step_task.run("x", {})
    celery_app.run_step_task.run("x", {})
    assert len(seen) == 2 and seen[0] is not seen[1]
