from app.services import health_store


def setup_function():
    health_store.reset()


def test_record_and_history():
    health_store.record(1000.0, {"docker": True, "disk": False}, {"docker": 5, "disk": 0})
    health_store.record(1060.0, {"docker": True, "disk": True}, {"docker": 4, "disk": 0})
    h = health_store.get_history("1h")
    assert h["timestamps"] == [1000.0, 1060.0]
    assert h["status"]["docker"] == [True, True]
    assert h["status"]["disk"] == [False, True]
    assert h["latency_ms"]["docker"] == [5, 4]


def test_range_slicing():
    for i in range(200):
        health_store.record(float(i), {"docker": True}, {"docker": 1})
    assert len(health_store.get_history("1h")["timestamps"]) == 120  # 1h = 120 samples


def test_get_missing_key_absent():
    health_store.record(1.0, {"docker": True}, {"docker": 1})
    h = health_store.get_history("1h")
    assert "gpu" not in h["status"]
