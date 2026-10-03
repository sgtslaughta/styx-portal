import grant


def _patch_noops(monkeypatch):
    monkeypatch.setattr(grant, "_seat_bus", lambda: "unix:path=/b")
    monkeypatch.setattr(grant, "_x_display_alive", lambda d: True)
    monkeypatch.setattr(grant, "_restart_seat_portal", lambda bus: None)
    monkeypatch.setattr(grant, "_set_activation_display", lambda bus, d: None)


def test_grant_returns_0_when_token_appears(tmp_path, monkeypatch):
    tok = tmp_path / "tok"
    _patch_noops(monkeypatch)
    monkeypatch.setattr(grant, "TOKEN_PATH", tok)
    monkeypatch.setattr(grant, "_trigger_stream", lambda cfg, hold_s=0: tok.write_text("x"))
    assert grant.grant({"port": 8443}, timeout_s=1) == 0


def test_grant_times_out_and_restores(tmp_path, monkeypatch):
    _patch_noops(monkeypatch)
    calls = []
    monkeypatch.setattr(grant, "_set_activation_display", lambda bus, d: calls.append(d))
    monkeypatch.setattr(grant, "TOKEN_PATH", tmp_path / "never")
    monkeypatch.setattr(grant, "_trigger_stream", lambda cfg, hold_s=0: None)
    assert grant.grant({"port": 8443}, timeout_s=0.3) == 1
    assert calls == [":0", ""]


def test_grant_without_display_errors(tmp_path, monkeypatch):
    _patch_noops(monkeypatch)
    monkeypatch.setattr(grant, "_x_display_alive", lambda d: False)
    monkeypatch.setattr(grant, "TOKEN_PATH", tmp_path / "never")
    assert grant.grant({"port": 8443, "display": ""}, timeout_s=0.3) == 1


def test_grant_without_seat_bus(tmp_path, monkeypatch):
    _patch_noops(monkeypatch)
    monkeypatch.setattr(grant, "_seat_bus", lambda: None)
    assert grant.grant({"port": 8443}, timeout_s=0.3) == 1


def test_restart_seat_portal_kills_only_matching(tmp_path, monkeypatch):
    bus = "unix:path=/seat"
    for pid, comm, env in [(10, "xdg-desktop-por", f"A=1\0DBUS_SESSION_BUS_ADDRESS={bus}\0"),
                           (11, "xdg-desktop-por", "DBUS_SESSION_BUS_ADDRESS=unix:path=/other\0"),
                           (12, "bash", f"DBUS_SESSION_BUS_ADDRESS={bus}\0")]:
        d = tmp_path / str(pid)
        d.mkdir()
        (d / "comm").write_text(comm + "\n")
        (d / "environ").write_bytes(env.encode())
    (tmp_path / "13").mkdir()  # no comm: FileNotFoundError ignored
    monkeypatch.setattr(grant, "PROC", tmp_path)
    killed = []
    monkeypatch.setattr(grant.os, "kill", lambda pid, sig: killed.append(pid))
    grant._restart_seat_portal(bus)
    assert killed == [10]
