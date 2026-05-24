import json
import tempfile
import os

from sqlmodel import Session as DBSession, create_engine, SQLModel, select

from app.database import seed_templates
from app.models import ServiceTemplate


def test_seed_templates():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with tempfile.TemporaryDirectory() as tmpdir:
        template_data = {
            "name": "test-seed",
            "display_name": "Test Seed",
            "image": "test:latest",
            "internal_port": 3001,
        }
        with open(os.path.join(tmpdir, "test-seed.json"), "w") as f:
            json.dump(template_data, f)

        with DBSession(engine) as session:
            seed_templates(session, tmpdir)
            templates = session.exec(select(ServiceTemplate)).all()
            assert len(templates) == 1
            assert templates[0].name == "test-seed"


def test_seed_idempotent():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with tempfile.TemporaryDirectory() as tmpdir:
        template_data = {
            "name": "idem",
            "display_name": "Idem",
            "image": "test:latest",
            "internal_port": 3001,
        }
        with open(os.path.join(tmpdir, "idem.json"), "w") as f:
            json.dump(template_data, f)

        with DBSession(engine) as session:
            seed_templates(session, tmpdir)
            seed_templates(session, tmpdir)
            templates = session.exec(select(ServiceTemplate)).all()
            assert len(templates) == 1
