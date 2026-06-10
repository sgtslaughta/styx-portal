from app.services import pull_progress


def setup_function():
    pull_progress.clear("i1")


def test_set_and_get():
    pull_progress.set_progress("i1", 42, "Downloading")
    assert pull_progress.get("i1") == {"percent": 42, "detail": "Downloading"}


def test_get_missing_returns_none():
    assert pull_progress.get("nope") is None


def test_clear():
    pull_progress.set_progress("i1", 10, "x")
    pull_progress.clear("i1")
    assert pull_progress.get("i1") is None


def test_overall_percent_from_layers():
    events = [
        {"id": "a", "progressDetail": {"current": 50, "total": 100}},
        {"id": "b", "progressDetail": {"current": 0, "total": 100}},
    ]
    assert pull_progress.overall_percent(events) == 25


def test_overall_percent_no_totals_is_zero():
    assert pull_progress.overall_percent([{"id": "a", "progressDetail": {}}]) == 0
