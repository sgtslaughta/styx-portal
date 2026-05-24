import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Field, SQLModel, Column
from sqlalchemy import JSON


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceTemplate(SQLModel, table=True):
    __tablename__ = "service_templates"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(unique=True, index=True)
    display_name: str
    image: str
    icon: str | None = None
    description: str | None = None
    env_vars: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    gpu_enabled: bool = False
    gpu_count: int = 0
    memory_limit: str | None = None
    cpu_limit: str | None = None
    shm_size: str | None = None
    volumes: list[dict[str, str]] = Field(default_factory=list, sa_column=Column(JSON))
    internal_port: int = 3001
    internal_protocol: str = "https"
    category: str | None = None
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    session_config: dict[str, Any] = Field(
        default_factory=lambda: {
            "idle_timeout": "30m",
            "grace_period": "5m",
            "timeout_action": "stop",
            "never_timeout": False,
            "max_session_duration": None,
        },
        sa_column=Column(JSON),
    )
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Instance(SQLModel, table=True):
    __tablename__ = "instances"

    id: str = Field(default_factory=_uuid, primary_key=True)
    template_id: str = Field(foreign_key="service_templates.id")
    name: str
    subdomain: str = Field(unique=True, index=True)
    container_id: str | None = None
    status: str = "created"
    env_overrides: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    volume_names: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    last_activity: datetime | None = None
    session_config: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class SessionEvent(SQLModel, table=True):
    __tablename__ = "session_events"

    id: int | None = Field(default=None, primary_key=True)
    instance_id: str = Field(foreign_key="instances.id")
    event_type: str
    details: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=_now)
