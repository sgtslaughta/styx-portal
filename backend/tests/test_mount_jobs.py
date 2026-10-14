import tarfile
from unittest.mock import MagicMock
import pytest
from sqlmodel import select
from app.models import MountJob, ProxiedService
from app.services.mount_jobs import MountPlan, run_job, sweep_interrupted

XML = b"<Config><UrlBase></UrlBase></Config>"
PLAN = MountPlan("config_file", "/config/config.xml", "xml", "/Config/UrlBase",
                 [{"target": "/config/config.xml", "key": "/Config/UrlBase", "old": "", "new": "/sonarr"}], True)


@pytest.fixture
def factory(session):
    class F:
        async def __aenter__(self): return session
        async def __aexit__(self, *a): return False
    return lambda: F()


async def _setup(session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.mount_jobs._settings.MOUNT_BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.mount_jobs.VERIFY_BUDGET_S", 0.2)
    monkeypatch.setattr("app.services.mount_jobs.VERIFY_INTERVAL_S", 0.05)
    svc = ProxiedService(slug="sonarr", name="Sonarr", kind="docker-local", container="sonarr",
                         container_port=8989, preset_id="sonarr")
    job = MountJob(service_id=svc.id)
    session.add_all([svc, job])
    await session.commit()
    d = MagicMock()
    d.read_file.return_value = (XML, tarfile.TarInfo("config.xml"))
    d.container_logs.return_value = "boom"
    return svc, job, d


async def test_happy_path(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    async def ok(url): return 200
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=ok)
    await session.refresh(job)
    await session.refresh(svc)
    assert job.state == "done" and [s["state"] for s in job.steps] == ["done"] * 4
    assert b"/sonarr" in d.write_file.call_args.args[2]
    assert (tmp_path / svc.id).is_dir() and svc.mount_managed is True


async def test_verify_fail_rolls_back(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    calls = []
    async def get(url):
        calls.append(url)
        return 404 if url.endswith("/sonarr/ping") else 200
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=get, verify_path="/sonarr/ping",
                  old_verify_path="/ping")
    await session.refresh(job)
    assert job.state == "rolled_back" and job.changed is True
    assert job.log_excerpt == "boom"
    assert d.write_file.call_args.args[2] == XML          # original restored
    assert d.restart_container.call_count == 2


async def test_restored_but_old_path_silent_is_rolled_back_with_note(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    async def down(url): return 503
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=down)
    await session.refresh(job)
    assert job.state == "rolled_back" and job.backup_dir and job.changed is True
    assert "restored" in job.log_excerpt.lower() and "didn't answer" in job.log_excerpt


async def test_read_failure_ends_failed(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    d.read_file.side_effect = tarfile.ReadError("bad archive")
    await run_job(job.id, svc.id, PLAN, d, factory)
    await session.refresh(job)
    assert job.state == "failed" and job.finished_at
    assert job.steps[0]["state"] == "failed" and "bad archive" in job.steps[0]["detail"]
    assert d.write_file.call_count == 0 and d.restart_container.call_count == 0


async def test_no_changes_finishes_without_restart(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    await run_job(job.id, svc.id, MountPlan("config_file", "/c", "xml", "/C/U", [], True), d, factory)
    await session.refresh(job)
    assert job.state == "done" and d.restart_container.call_count == 0


async def test_keeps_last_five_backups(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    for i in range(6):
        (tmp_path / svc.id / f"2026010{i}T000000Z").mkdir(parents=True)
    async def ok(url): return 200
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=ok)
    assert len(list((tmp_path / svc.id).iterdir())) == 5


async def test_sweep_marks_running_failed(session):
    session.add(MountJob(service_id="s", state="running", changed=True, backup_dir="/b"))
    await session.commit()
    assert await sweep_interrupted(session) == 1
    j = (await session.exec(select(MountJob))).first()
    assert j.state == "failed" and "Interrupted" in j.log_excerpt and "/b" in j.log_excerpt


async def test_sweep_clears_pending(session):
    session.add(MountJob(service_id="s", state="pending"))
    await session.commit()
    assert await sweep_interrupted(session) == 1


async def test_service_deleted_before_run_fails(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    await session.delete(svc)
    await session.commit()
    await run_job(job.id, svc.id, PLAN, d, factory)
    await session.refresh(job)
    assert job.state == "failed" and job.steps[0]["detail"]


async def test_read_none_fails(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    d.read_file.return_value = None
    await run_job(job.id, svc.id, PLAN, d, factory)
    await session.refresh(job)
    assert job.state == "failed" and d.write_file.call_count == 0


async def test_logs_raise_still_restores(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    d.container_logs.side_effect = RuntimeError("no logs")

    async def get(url):
        return 404 if url.endswith("/sonarr") else 200
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=get)
    await session.refresh(job)
    assert job.state == "rolled_back" and d.write_file.call_args.args[2] == XML


async def test_rollback_error_recorded(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    d.restart_container.side_effect = [None, RuntimeError("daemon gone")]

    async def down(url):
        return 503
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=down)
    await session.refresh(job)
    assert job.state == "failed"
    assert "Rollback failed: daemon gone" in job.log_excerpt and job.backup_dir in job.log_excerpt


async def test_edit_error_fails_without_restore(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    d.read_file.return_value = (b"not xml <<", tarfile.TarInfo("config.xml"))
    await run_job(job.id, svc.id, PLAN, d, factory)
    await session.refresh(job)
    assert job.state == "failed"
    assert d.write_file.call_count == 0 and d.restart_container.call_count == 0


async def test_write_raises_restores(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    d.write_file.side_effect = [OSError("disk"), None]

    async def ok(url):
        return 200
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=ok)
    await session.refresh(job)
    assert job.state == "rolled_back" and d.write_file.call_count == 2


async def test_default_getter_uses_probe_container(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    d.probe_http.return_value = 200
    await run_job(job.id, svc.id, PLAN, d, factory)
    await session.refresh(job)
    assert job.state == "done"
    args, kw = d.probe_http.call_args
    assert args[0] == "http://sonarr:8989/sonarr" and args[1] == "styx-services"
    assert kw["extra_hosts"] is None


async def test_probe_unavailable_rolls_back_with_note(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    calls = []

    async def broken(url):
        calls.append(url)
        return -1
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=broken)
    await session.refresh(job)
    assert len(calls) == 2                       # no waiting on a dead probe
    assert job.state == "rolled_back"
    assert "probe image unavailable" in job.steps[3]["detail"]
    assert "couldn't confirm" in job.log_excerpt
    assert d.write_file.call_args.args[2] == XML


async def test_bind_mounted_file_fails_without_restore(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    d.write_file.side_effect = OSError("rename: device or resource busy")
    await run_job(job.id, svc.id, PLAN, d, factory)
    await session.refresh(job)
    assert job.state == "failed" and "mounted on its own" in job.steps[1]["detail"]
    assert d.write_file.call_count == 1 and d.restart_container.call_count == 0
    assert "Rollback" not in (job.log_excerpt or "")
    assert job.changed is False


async def test_read_failure_changed_false(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    d.read_file.side_effect = RuntimeError("docker down")
    await run_job(job.id, svc.id, PLAN, d, factory)
    await session.refresh(job)
    assert job.state == "failed" and job.changed is False


async def test_rollback_error_sets_changed_true_and_failed(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    d.write_file.side_effect = [None, RuntimeError("disk gone")]
    async def down(url): return 503
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=down)
    await session.refresh(job)
    assert job.state == "failed" and job.changed is True and "Rollback failed" in job.log_excerpt


async def test_backup_dirs_never_collide_in_one_second(session, tmp_path, monkeypatch, factory):
    from datetime import datetime as real
    class Fixed(real):
        @classmethod
        def now(cls, tz=None): return real(2026, 1, 1, 0, 0, 0, tzinfo=tz)
    monkeypatch.setattr("app.services.mount_jobs.datetime", Fixed)
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    async def ok(url): return 200
    for _ in range(2):
        j = MountJob(service_id=svc.id)
        session.add(j)
        await session.commit()
        await run_job(j.id, svc.id, PLAN, d, factory, http_get=ok)
    assert len([p for p in (tmp_path / svc.id).iterdir() if p.is_dir()]) == 2


async def test_sweep_note_warns_file_may_hold_new_value(session):
    session.add(MountJob(service_id="s", state="running", changed=True, backup_dir="/b"))
    await session.commit()
    await sweep_interrupted(session)
    j = (await session.exec(select(MountJob))).first()
    assert "restore from the backup" in j.log_excerpt and "/b" in j.log_excerpt


async def test_sweep_note_and_steps_follow_changed(session):
    steps = [{"id": "backup", "label": "b", "state": "done", "detail": ""},
             {"id": "write", "label": "w", "state": "running", "detail": ""},
             {"id": "verify", "label": "v", "state": "pending", "detail": ""}]
    session.add_all([MountJob(service_id="a", state="running", changed=False, steps=steps),
                     MountJob(service_id="b", state="running", changed=True, backup_dir="/b", steps=steps)])
    await session.commit()
    await sweep_interrupted(session)
    rows = {j.service_id: j for j in (await session.exec(select(MountJob))).all()}
    assert "new value" not in rows["a"].log_excerpt and "Nothing was changed" in rows["a"].log_excerpt
    assert "new value" in rows["b"].log_excerpt
    for j in rows.values():
        assert [s["state"] for s in j.steps] == ["done", "failed", "pending"]


TEMPLATE = '<?xml version="1.0"?>\n<NetworkConfiguration>\n  <BaseUrl />\n</NetworkConfiguration>\n'
NEW = "/config/config/network.xml"
CPLAN = MountPlan("config_file", NEW, "xml", "/NetworkConfiguration/BaseUrl",
                  [{"target": NEW, "key": "/NetworkConfiguration/BaseUrl", "old": "",
                    "new": "/sonarr", "created": True}], True, create=True, template=TEMPLATE,
                  owner_from="/config/config/system.xml")


def _owner_docker(d):
    owner = tarfile.TarInfo("system.xml")
    owner.uid, owner.gid, owner.mode = 1000, 100, 0o600
    d.read_file.side_effect = lambda c, p: (b"<x/>", owner) if p == CPLAN.owner_from else None


async def test_create_writes_new_file_with_owner_and_mode(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    _owner_docker(d)
    async def ok(url): return 200
    await run_job(job.id, svc.id, CPLAN, d, factory, http_get=ok)
    await session.refresh(job)
    assert job.state == "done"
    d.write_file.assert_called_once()
    _, path, body, info = d.write_file.call_args.args
    assert path == NEW and b"/sonarr" in body
    assert (info.mode, info.uid, info.gid) == (0o644, 1000, 100)
    assert NEW not in [c.args[1] for c in d.read_file.call_args_list]
    assert (next((tmp_path / svc.id).iterdir()) / "network.xml").read_text() == TEMPLATE


async def test_create_verify_fail_rolls_back_to_template(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    _owner_docker(d)
    async def get(url): return 404 if url.endswith("/sonarr") else 200
    await run_job(job.id, svc.id, CPLAN, d, factory, http_get=get)
    await session.refresh(job)
    assert job.state == "rolled_back"
    assert d.write_file.call_args.args[2] == TEMPLATE.encode()


async def test_create_without_owner_fails_backup_and_writes_nothing(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    d.read_file.side_effect = lambda c, p: None
    await run_job(job.id, svc.id, CPLAN, d, factory)
    await session.refresh(job)
    assert job.state == "failed" and "system.xml" in job.steps[0]["detail"]
    d.write_file.assert_not_called()


async def test_after_done_called_only_on_done(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    seen = []

    async def after(sid):
        seen.append(sid)

    async def ok(url):
        return 200

    await run_job(job.id, svc.id, PLAN, d, factory, http_get=ok, after_done=after)
    assert seen == [svc.id]


async def test_after_done_not_called_on_rollback(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    seen = []

    async def after(sid):
        seen.append(sid)

    async def down(url):
        return 500
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=down, after_done=after)
    assert seen == []


async def test_after_done_failure_does_not_break_job(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)

    async def boom(sid):
        raise RuntimeError("x")

    async def ok(url):
        return 200
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=ok, after_done=boom)
    await session.refresh(job)
    assert job.state == "done"
