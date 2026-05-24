from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest
from sqlmodel import Session as DBSession, create_engine, SQLModel

from app.models import ServiceTemplate, Instance, SessionEvent
from app.services.session_monitor import SessionMonitor


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with DBSession(engine) as session:
        yield session


@pytest.fixture
def mock_docker():
    manager = MagicMock()
    manager.get_container_stats.return_value = {
        "networks": {"eth0": {"rx_bytes": 0, "tx_bytes": 0}}
    }
    return manager


@pytest.fixture
def template(db_session):
    t = ServiceTemplate(
        name="test",
        display_name="Test",
        image="test:1",
        internal_port=3001,
        session_config={
            "idle_timeout": "30m",
            "grace_period": "5m",
            "timeout_action": "stop",
            "never_timeout": False,
        },
    )
    db_session.add(t)
    db_session.commit()
    db_session.refresh(t)
    return t


def _make_instance(db_session, template, last_activity_minutes_ago, status="running"):
    now = datetime.now(timezone.utc)
    inst = Instance(
        template_id=template.id,
        name="test-inst",
        subdomain="test",
        container_id="container-123",
        status=status,
        last_activity=now - timedelta(minutes=last_activity_minutes_ago),
        started_at=now - timedelta(hours=1),
        session_config=template.session_config,
    )
    db_session.add(inst)
    db_session.commit()
    db_session.refresh(inst)
    return inst


def test_parse_duration():
    monitor = SessionMonitor.__new__(SessionMonitor)
    assert monitor._parse_duration("30m") == timedelta(minutes=30)
    assert monitor._parse_duration("2h") == timedelta(hours=2)
    assert monitor._parse_duration("90s") == timedelta(seconds=90)
    assert monitor._parse_duration("1h") == timedelta(hours=1)


def test_active_instance_not_flagged(db_session, mock_docker, template):
    instance = _make_instance(db_session, template, last_activity_minutes_ago=5)
    monitor = SessionMonitor(mock_docker)

    actions = monitor.check_instance(instance, db_session)

    assert actions == []
    assert instance.status == "running"


def test_idle_instance_gets_warning(db_session, mock_docker, template):
    instance = _make_instance(db_session, template, last_activity_minutes_ago=35)
    monitor = SessionMonitor(mock_docker)

    actions = monitor.check_instance(instance, db_session)

    assert "idle_warning" in actions
    assert instance.status == "idle"


def test_idle_instance_past_grace_gets_stopped(db_session, mock_docker, template):
    instance = _make_instance(db_session, template, last_activity_minutes_ago=40)
    instance.status = "idle"
    db_session.add(instance)
    db_session.commit()
    monitor = SessionMonitor(mock_docker)

    actions = monitor.check_instance(instance, db_session)

    assert "auto_stopped" in actions
    mock_docker.stop_container.assert_called_once_with("container-123")
    assert instance.status == "stopped"


def test_never_timeout_skipped(db_session, mock_docker, template):
    instance = _make_instance(db_session, template, last_activity_minutes_ago=120)
    instance.session_config = {**instance.session_config, "never_timeout": True}
    db_session.add(instance)
    db_session.commit()
    monitor = SessionMonitor(mock_docker)

    actions = monitor.check_instance(instance, db_session)

    assert actions == []
    assert instance.status == "running"


def test_stopped_instance_skipped(db_session, mock_docker, template):
    instance = _make_instance(
        db_session, template, last_activity_minutes_ago=60, status="stopped"
    )
    monitor = SessionMonitor(mock_docker)

    actions = monitor.check_instance(instance, db_session)

    assert actions == []
