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
    assert job.state == "rolled_back" and job.log_excerpt == "boom"
    assert d.write_file.call_args.args[2] == XML          # original restored
    assert d.restart_container.call_count == 2


async def test_rollback_failure_marks_failed(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    async def down(url): return 503
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=down)
    await session.refresh(job)
    assert job.state == "failed" and job.backup_dir


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
    session.add(MountJob(service_id="s", state="running", backup_dir="/b"))
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
