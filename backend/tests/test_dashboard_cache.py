from types import SimpleNamespace

from market.api import main


def test_dashboard_cached_until_latest_job_changes(monkeypatch):
    job = SimpleNamespace(id=1, status="ok", finished_at="t1")
    builds = []
    monkeypatch.setattr(main, "_latest_job", lambda session: job)
    monkeypatch.setattr(main, "_build_dashboard", lambda store, j: builds.append(j.id) or {"job": j.id})
    monkeypatch.setattr(main, "_dashboard_cache", {"key": None, "data": None})
    store = SimpleNamespace(session=None)

    assert main.cached_dashboard(store) == {"job": 1}
    assert main.cached_dashboard(store) == {"job": 1}
    assert builds == [1]  # second call served from cache

    job = SimpleNamespace(id=2, status="ok", finished_at="t2")  # a new job finished
    assert main.cached_dashboard(store) == {"job": 2}
    assert builds == [1, 2]
