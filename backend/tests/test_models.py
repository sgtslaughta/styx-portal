import pytest
from sqlmodel import Session, create_engine, SQLModel
from app.models import ServiceTemplate, Instance, SessionEvent


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_create_service_template(db_session):
    template = ServiceTemplate(
        name="dev-desktop",
        display_name="Development Desktop",
        image="ghcr.io/linuxserver/baseimage-selkies:debiantrixie",
        description="Full Linux desktop",
        env_vars={"PUID": "1000", "PGID": "1000"},
        gpu_enabled=True,
        gpu_count=1,
        memory_limit="8g",
        cpu_limit="4.0",
        shm_size="2g",
        volumes=[{"name": "{instance_id}-home", "mount": "/config"}],
        internal_port=3001,
        category="desktop",
        tags=["development", "gpu"],
        session_config={"idle_timeout": "30m", "grace_period": "5m"},
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    assert template.id is not None
    assert template.name == "dev-desktop"
    assert template.gpu_enabled is True
    assert template.env_vars["PUID"] == "1000"
    assert template.volumes[0]["mount"] == "/config"


def test_create_instance(db_session):
    template = ServiceTemplate(
        name="test-tmpl",
        display_name="Test",
        image="test:latest",
        internal_port=3001,
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    instance = Instance(
        template_id=template.id,
        name="my-instance",
        subdomain="my-instance",
        status="created",
    )
    db_session.add(instance)
    db_session.commit()
    db_session.refresh(instance)

    assert instance.id is not None
    assert instance.template_id == template.id
    assert instance.status == "created"
    assert instance.container_id is None


def test_create_session_event(db_session):
    template = ServiceTemplate(
        name="tmpl", display_name="T", image="t:1", internal_port=3001
    )
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    instance = Instance(
        template_id=template.id, name="inst", subdomain="inst", status="running"
    )
    db_session.add(instance)
    db_session.commit()
    db_session.refresh(instance)

    event = SessionEvent(
        instance_id=instance.id,
        event_type="started",
        details={"trigger": "manual"},
    )
    db_session.add(event)
    db_session.commit()
    db_session.refresh(event)

    assert event.id is not None
    assert event.event_type == "started"


def test_template_name_unique(db_session):
    t1 = ServiceTemplate(name="unique", display_name="A", image="a:1", internal_port=3001)
    t2 = ServiceTemplate(name="unique", display_name="B", image="b:1", internal_port=3001)
    db_session.add(t1)
    db_session.commit()
    db_session.add(t2)
    with pytest.raises(Exception):
        db_session.commit()


def test_instance_subdomain_unique(db_session):
    template = ServiceTemplate(name="t", display_name="T", image="t:1", internal_port=3001)
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    i1 = Instance(template_id=template.id, name="a", subdomain="same", status="created")
    i2 = Instance(template_id=template.id, name="b", subdomain="same", status="created")
    db_session.add(i1)
    db_session.commit()
    db_session.add(i2)
    with pytest.raises(Exception):
        db_session.commit()


def test_service_template_dind_defaults_false():
    from app.models import ServiceTemplate
    t = ServiceTemplate(name="x", display_name="X", image="img:latest")
    assert t.dind is False
