from dataclasses import dataclass
from typing import Any
from pydantic import BaseModel, Field


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
    dind: bool = False
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
    dind: bool | None = None
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


class InstanceUpdate(BaseModel):
    name: str | None = None
    env_overrides: dict[str, str] | None = None
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


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str | None = None
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    username: str
    password: str


class AcceptInviteRequest(BaseModel):
    token: str
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=256)


class UserOut(BaseModel):
    id: str
    username: str
    email: str | None
    role: str
    is_active: bool


class CreateInviteRequest(BaseModel):
    email: str | None = None
    role: str = "user"


class InviteOut(BaseModel):
    token: str
    expires_at: str | None


@dataclass
class OAuthIdentity:
    sub: str
    email: str | None
    email_verified: bool
    claims: dict


class ProviderCreate(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    display_label: str
    kind: str = "oidc"                       # oidc | oauth2
    issuer_url: str | None = None
    authorize_url: str | None = None
    token_url: str | None = None
    userinfo_url: str | None = None
    client_id: str
    client_secret: str                        # plaintext in; stored encrypted
    scopes: str = "openid email profile"
    role_map: dict = Field(default_factory=dict)
    enabled: bool = True


class ProviderUpdate(BaseModel):
    display_label: str | None = None
    issuer_url: str | None = None
    authorize_url: str | None = None
    token_url: str | None = None
    userinfo_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None          # if provided, re-encrypt; else unchanged
    scopes: str | None = None
    role_map: dict | None = None
    enabled: bool | None = None


class ProviderOut(BaseModel):
    id: str
    name: str
    display_label: str
    kind: str
    issuer_url: str | None
    client_id: str
    scopes: str
    role_map: dict
    enabled: bool
    has_secret: bool                          # never expose the secret itself


class PublicProvider(BaseModel):
    name: str
    display_label: str


class ConnectedIdentity(BaseModel):
    provider: str
    email: str | None
    created_at: str
