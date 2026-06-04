import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Field, SQLModel, Column
from sqlalchemy import JSON, UniqueConstraint


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str | None = Field(default=None, index=True)
    password_hash: str
    role: str = "user"  # admin | user
    is_active: bool = True
    must_change_pw: bool = False
    created_at: datetime = Field(default_factory=_now)
    last_login: datetime | None = None


class Invite(SQLModel, table=True):
    __tablename__ = "invites"

    id: str = Field(default_factory=_uuid, primary_key=True)
    token_hash: str = Field(unique=True, index=True)
    email: str | None = None
    role: str = "user"
    created_by: str = Field(foreign_key="users.id")
    expires_at: datetime | None = None
    used_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"

    jti: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    expires_at: datetime
    revoked: bool = False
    user_agent: str | None = None
    created_at: datetime = Field(default_factory=_now)


class OAuthProvider(SQLModel, table=True):
    __tablename__ = "oauth_providers"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(unique=True, index=True)        # "google" | "github" | "authentik"
    display_label: str
    kind: str = "oidc"                                 # "oidc" | "oauth2"
    issuer_url: str | None = None                      # oidc: discovery base
    authorize_url: str | None = None                   # oauth2: explicit endpoints
    token_url: str | None = None
    userinfo_url: str | None = None
    client_id: str
    client_secret_enc: str
    scopes: str = "openid email profile"
    icon_url: str | None = None                        # remote URL or base64 data URI
    trust_email: bool = False                          # treat missing email_verified as verified
    role_map: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    enabled: bool = True
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class FederatedIdentity(SQLModel, table=True):
    __tablename__ = "federated_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_provider_subject"),)

    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    provider: str = Field(index=True)
    subject: str = Field(index=True)
    email: str | None = None
    created_at: datetime = Field(default_factory=_now)


class ServiceTemplate(SQLModel, table=True):
    __tablename__ = "service_templates"

    id: str = Field(default_factory=_uuid, primary_key=True)
    owner_id: str | None = Field(default=None, foreign_key="users.id", index=True)
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
    dind: bool = False
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
    owner_id: str | None = Field(default=None, foreign_key="users.id", index=True)
    name: str
    subdomain: str = Field(unique=True, index=True)
    container_id: str | None = None
    status: str = "created"
    error_message: str | None = None
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


class PulledImage(SQLModel, table=True):
    __tablename__ = "pulled_images"

    id: str = Field(default_factory=_uuid, primary_key=True)
    image: str = Field(unique=True, index=True)
    size_mb: int | None = None
    pulled_at: datetime = Field(default_factory=_now)
