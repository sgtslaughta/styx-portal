from typing import Any
from pydantic import BaseModel


class TemplateCreate(BaseModel):
    name: str
    display_name: str
    image: str
    icon: str | None = None
    description: str | None = None
    env_vars: dict[str, str] = {}
    gpu_enabled: bool = False
    gpu_count: int = 0
    memory_limit: str | None = None
    cpu_limit: str | None = None
    shm_size: str | None = None
    volumes: list[dict[str, str]] = []
    internal_port: int = 3001
    internal_protocol: str = "https"
    category: str | None = None
    tags: list[str] = []
    session_config: dict[str, Any] | None = None


class TemplateUpdate(BaseModel):
    display_name: str | None = None
    image: str | None = None
    icon: str | None = None
    description: str | None = None
    env_vars: dict[str, str] | None = None
    gpu_enabled: bool | None = None
    gpu_count: int | None = None
    memory_limit: str | None = None
    cpu_limit: str | None = None
    shm_size: str | None = None
    volumes: list[dict[str, str]] | None = None
    internal_port: int | None = None
    internal_protocol: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    session_config: dict[str, Any] | None = None


class InstanceCreate(BaseModel):
    template_id: str
    name: str
    subdomain: str
    env_overrides: dict[str, str] = {}
    session_config: dict[str, Any] | None = None


class SessionConfigUpdate(BaseModel):
    idle_timeout: str | None = None
    grace_period: str | None = None
    timeout_action: str | None = None
    never_timeout: bool | None = None
    max_session_duration: str | None = None


class InstanceStatus(BaseModel):
    id: str
    status: str
    container_id: str | None
    uptime_seconds: float | None
    idle_seconds: float | None
    session_config: dict[str, Any] | None
