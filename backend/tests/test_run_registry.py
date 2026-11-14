from app.runtracker import RunRegistry


def test_run_registry_claims_each_thread_once_until_cleared():
    registry = RunRegistry()

    assert registry.claim("thread-1") is True
    assert registry.claim("thread-1") is False

    registry.clear("thread-1")

    assert registry.claim("thread-1") is True
