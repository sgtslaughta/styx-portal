import re
import ipaddress
from dataclasses import dataclass
from typing import Any
from pydantic import BaseModel, Field, field_validator

SUBDOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED_SUBDOMAINS = {"api", "traefik", "www", "admin", "auth", "portal"}


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
    cap_add: list[str] = []
    security_opt: list[str] = []
    tls_skip_verify: bool = False
    volumes: list[dict[str, str]] = []
    internal_port: int = 3001
    internal_protocol: str = "https"
    category: str | None = None
    tags: list[str] = []
    session_config: dict[str, Any] | None = None
    shared: bool = False
    restart_policy: str = "no"
    read_only_rootfs: bool = False
    tmpfs: list[str] = []
    extra_hosts: dict[str, str] = {}
    ulimits: list[dict] = []
    extra_ports: list[dict] = []
    entrypoint: list[str] | None = None
    command: list[str] | None = None
    devices: list[str] = []
    privileged: bool = False
    extra_docker_args: dict = {}


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
    cap_add: list[str] | None = None
    security_opt: list[str] | None = None
    tls_skip_verify: bool | None = None
    volumes: list[dict[str, str]] | None = None
    internal_port: int | None = None
    internal_protocol: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    session_config: dict[str, Any] | None = None
    shared: bool | None = None
    restart_policy: str | None = None
    read_only_rootfs: bool | None = None
    tmpfs: list[str] | None = None
    extra_hosts: dict[str, str] | None = None
    ulimits: list[dict] | None = None
    extra_ports: list[dict] | None = None
    entrypoint: list[str] | None = None
    command: list[str] | None = None
    devices: list[str] | None = None
    privileged: bool | None = None
    extra_docker_args: dict | None = None


class InstanceCreate(BaseModel):
    template_id: str
    name: str
    subdomain: str
    env_overrides: dict[str, str] = {}
    session_config: dict[str, Any] | None = None

    @field_validator("subdomain")
    @classmethod
    def _valid_subdomain(cls, v: str) -> str:
        if not SUBDOMAIN_RE.match(v):
            raise ValueError(
                "subdomain must be 1-63 chars: lowercase letters, digits, "
                "hyphens (no leading/trailing hyphen)"
            )
        if v in RESERVED_SUBDOMAINS:
            raise ValueError(f"'{v}' is a reserved name")
        return v


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
    pull_percent: int | None = None
    pull_detail: str | None = None


class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str | None = None
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    username: str
    password: str


class AcceptInviteRequest(BaseModel):
    token: str
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)


class UserOut(BaseModel):
    id: str
    username: str
    email: str | None
    role: str
    is_active: bool
    last_login: str | None = None
    locked_until: str | None = None
    failed_count: int = 0


class CreateInviteRequest(BaseModel):
    email: str | None = None
    role: str = "user"


class InviteOut(BaseModel):
    token: str
    expires_at: str | None


class TempPasswordOut(BaseModel):
    temp_password: str


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
    icon_url: str | None = None
    trust_email: bool = False
    allow_signup: bool = False
    auto_promote_admins: bool = True


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
    icon_url: str | None = None
    trust_email: bool | None = None
    allow_signup: bool | None = None
    auto_promote_admins: bool | None = None


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
    icon_url: str | None
    trust_email: bool
    allow_signup: bool
    auto_promote_admins: bool
    redirect_uri: str                         # register this in the IdP (login flow)
    test_redirect_uri: str                    # register this too to use "Test login"


class ProviderTestCheck(BaseModel):
    label: str
    ok: bool
    detail: str = ""


class ProviderTestResult(BaseModel):
    ok: bool
    checks: list[ProviderTestCheck]


class PublicProvider(BaseModel):
    name: str
    display_label: str
    icon_url: str | None = None


class ConnectedIdentity(BaseModel):
    provider: str
    email: str | None
    created_at: str


class WorkstationOut(BaseModel):
    id: str
    name: str
    subdomain: str
    hostname: str
    lan_ip: str
    port: int
    status: str
    display_server: str
    gpu_info: dict[str, Any]
    os_info: dict[str, Any]
    agent_version: str
    agent_outdated: bool = False
    stream_settings: dict[str, Any]
    all_users: bool
    last_heartbeat: str | None
    last_error: str | None
    created_at: str
    allowed_user_ids: list[str] = []
    in_use: bool = False
    in_use_by: str | None = None     # username, never id
    in_use_self: bool = False


class EnrollTokenOut(BaseModel):
    token: str
    expires_at: str
    lan_command: str | None        # None when no LAN URL configured or detected
    public_command: str
    lan_url_source: str            # env | detected | none


class WorkstationRegisterRequest(BaseModel):
    token: str
    hostname: str = Field(min_length=1, max_length=255)
    lan_ip: str = Field(min_length=1, max_length=64)
    display_server: str = "virtual"       # virtual (own desktop) | x11 | wayland
    gpu_info: dict[str, Any] = {}
    os_info: dict[str, Any] = {}
    agent_version: str = ""
    port: int | None = None

    @field_validator("lan_ip")
    @classmethod
    def _valid_lan_ip(cls, v: str) -> str:
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError("lan_ip must be a valid IPv4 or IPv6 address")
        return v

    @field_validator("display_server")
    @classmethod
    def _valid_display(cls, v: str) -> str:
        if v not in ("virtual", "x11", "wayland"):
            raise ValueError("display_server must be 'virtual', 'x11', or 'wayland'")
        return v


class WorkstationRegisterResponse(BaseModel):
    workstation_id: str
    agent_token: str
    subdomain: str
    selkies_user: str
    selkies_password: str
    port: int
    stream_settings: dict[str, Any]
    heartbeat_interval_s: int


class WorkstationHeartbeatRequest(BaseModel):
    status: str = "online"                # online | error
    lan_ip: str | None = None
    last_error: str | None = None
    health: dict[str, Any] = {}

    @field_validator("lan_ip")
    @classmethod
    def _valid_lan_ip(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError("lan_ip must be a valid IPv4 or IPv6 address")
        return v


class WorkstationHeartbeatResponse(BaseModel):
    state: str                            # ok | revoked
    stream_settings: dict[str, Any]
    heartbeat_interval_s: int
    # One-shot: when True the agent restarts its gateway, dropping live stream
    # clients (set by logout-with-active-session teardown).
    disconnect_clients: bool = False


class WorkstationUpdate(BaseModel):
    name: str | None = None
    all_users: bool | None = None
    stream_settings: dict[str, Any] | None = None


class WorkstationAccessUpdate(BaseModel):
    user_ids: list[str]


class WorkstationConnectOut(BaseModel):
    url: str


class WorkstationUpdateCommandOut(BaseModel):
    latest_version: str
    current_version: str
    lan_command: str | None
    public_command: str
    lan_url_source: str            # env | detected | none


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=256)
