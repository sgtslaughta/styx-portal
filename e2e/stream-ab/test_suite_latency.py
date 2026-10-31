import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ab  # noqa: E402
import latstats  # noqa: E402
import netem  # noqa: E402
import suite_latency as S  # noqa: E402


def test_latency_variants_flags():
    V = ab.VARIANTS
    for name, enc, fps in [("av1-60", "av1enc", 60), ("av1-120", "av1enc", 120),
                           ("h264-60", "h264enc", 60), ("h264-120", "h264enc", 120),
                           ("hevc-120", "h265enc", 120), ("av1-60-bp8", "av1enc", 60)]:
        codec, got_fps = S.expected(V[name])
        assert got_fps == fps and V[name][0].split("=")[1].split(",")[0] == enc and codec
    assert "--backpressure-queue-size=8" in V["av1-60-bp8"]
    assert V["h264-120"][0] == "--encoder=h264enc"       # no fallback: a decode failure shows up as invalid
    assert "av1-16" in V and "h264-16" in V              # old variants kept


def test_suite_matrix_and_quick():
    assert set(S.SUITE_VARIANTS) <= set(ab.VARIANTS) and "hevc-120" not in S.SUITE_VARIANTS
    assert set(S.SUITE_PROFILES) <= set(netem.PROFILES)
    assert S.select(False, None, None) == (S.SUITE_VARIANTS, S.SUITE_PROFILES)
    assert S.select(True, None, None) == (["av1-60", "h264-120"], ["lan", "cf-tunnel"])
    assert S.select(False, "h264-60", "lan") == (["h264-60"], ["lan"])


def test_plan_and_estimates():
    plan = S.format_plan(*S.select(True, None, None))
    assert "av1-60" in plan and "--framerate=120,8-240" in plan and "4 cells" in plan
    full, quick = S.estimate_s(S.SUITE_VARIANTS, S.SUITE_PROFILES), S.estimate_s(*S.select(True, None, None))
    assert quick < full and 10 * 60 < quick < 25 * 60 and 40 * 60 < full < 90 * 60


def _flat(n=100):
    return {k: {"n": n} for k in latstats.KINDS}


def test_problems_flags_wrong_codec_fps_and_few_samples():
    row = {"codec": "AV1 VAAPI CBR 30000", "fps": 60.0, "valid": True}
    assert S.problems(ab.VARIANTS["av1-60"], row, _flat()) == []
    assert S.problems(ab.VARIANTS["hevc-120"], {**row, "fps": 120.0}, _flat())      # fell back to AV1 != HEVC
    assert any("fps" in p for p in S.problems(ab.VARIANTS["av1-120"], row, _flat()))
    assert any("mouse" in p for p in S.problems(ab.VARIANTS["av1-60"], row, {**_flat(), "mouse": {"n": 3}}))
    assert S.problems(ab.VARIANTS["h264-60"], {"codec": "H264 CPU", "fps": 60.0, "valid": True}, _flat())
    assert S.problems(ab.VARIANTS["av1-60"], {**row, "valid": False}, _flat())


def test_override_restored(tmp_path):
    p = tmp_path / "stream-override.json"
    snap = ab.snapshot_override(p)
    assert snap is None
    p.write_text("{}")
    ab.restore_override(p, snap)
    assert not p.exists()
    p.write_text('{"args": ["--x"]}')
    snap = ab.snapshot_override(p)
    p.write_text('{"args": ["--encoder=h264enc"]}')
    ab.restore_override(p, snap)
    assert p.read_text() == '{"args": ["--x"]}'


def test_samples_option_scales_plan_and_hit_requirement():
    assert S.estimate_s(["av1-60"], ["lan"], 1, 30) < S.estimate_s(["av1-60"], ["lan"], 1, 100)
    assert "x 30 samples" in S.format_plan(["av1-60"], ["lan"], 1, 30)
    row = {"codec": "AV1 VAAPI CBR 30000", "fps": 60.0, "valid": True}
    flat = {k: {"n": 28} for k in latstats.KINDS}
    assert S.problems(ab.VARIANTS["av1-60"], row, flat, 30) == []        # 28/30 >= 90%
    assert S.problems(ab.VARIANTS["av1-60"], row, flat, 100)


def test_cell_error_is_recorded_and_suite_continues(tmp_path, monkeypatch):
    p = tmp_path / "o.json"
    p.write_text('{"args": ["--orig"]}')
    cells, restarts = [], []

    class Fake:
        VARIANTS, OVERRIDE, HERE = ab.VARIANTS, p, tmp_path
        (tmp_path / "results").mkdir()
        snapshot_override, restore_override = staticmethod(ab.snapshot_override), staticmethod(ab.restore_override)
        creds = staticmethod(lambda: ("u", "p"))
        open_workload = staticmethod(lambda: type("F", (), {"terminate": lambda s: None})())
        restart_selkies = staticmethod(lambda u, pw: restarts.append(p.read_text()))
        warm_up = staticmethod(lambda *a, **k: None)

        @staticmethod
        def run_one(v, prof, *a, **k):
            cells.append(prof)
            if prof == "lan":
                raise TimeoutError("boom")
            return {"error": "timeout"}

    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    S.run(Fake, ["av1-60"], ["lan", "cf-tunnel"])
    assert cells == ["lan", "cf-tunnel"]
    import json
    rows = json.loads(next((tmp_path / "results").glob("*-latency.json")).read_text())
    assert all(not r["valid"] and r["error"] for r in rows)
    assert p.read_text() == '{"args": ["--orig"]}' and restarts[-1] == p.read_text()


def test_run_node_kills_the_process_group_on_timeout():
    import time
    t = time.time()
    rc, out, err = ab.run_node([sys.executable, "-c", "import time; time.sleep(60)"], dict(__import__("os").environ), 1)
    assert rc is None and time.time() - t < 10
