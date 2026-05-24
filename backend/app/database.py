import json
import os

from sqlmodel import SQLModel, create_engine, Session, select

from app.config import Settings
from app.models import ServiceTemplate

settings = Settings()
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)


def init_db():
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed_templates(session, settings.TEMPLATES_DIR)


def get_session():
    with Session(engine) as session:
        yield session


def seed_templates(session: Session, templates_dir: str):
    if not os.path.isdir(templates_dir):
        return
    for filename in os.listdir(templates_dir):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(templates_dir, filename)
        with open(filepath) as f:
            data = json.load(f)

        existing = session.exec(
            select(ServiceTemplate).where(ServiceTemplate.name == data["name"])
        ).first()
        if existing:
            continue

        template = ServiceTemplate(**data)
        session.add(template)

    session.commit()
