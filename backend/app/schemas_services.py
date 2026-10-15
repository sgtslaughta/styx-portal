"""Service / group / preset schemas (split from schemas.py)."""
import ipaddress
import re
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

SERVICE_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED_SERVICE_SLUGS = {
    "api", "i", "w", "assets", "login", "setup", "connecting", "change-password",
    "accept-invite", "_styx",
    # Authentik (SP2) prefixes, reserved now so no slug migration later
    "if", "application", "outpost.goauthentik.io", "static", "media", "flows", "ws",
    "-", ".well-known", "source",
}


def _is_ip(host: str | None) -> bool:
    try:
        ipaddress.ip_address(host or "")
        return True
    except ValueError:
        return False


CONTAINER_NAME_RE = r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$"
MOUNT_MODES = {"path", "cookie-root"}
AUTH_MODES = {"sso", "sso-with-bypass", "app-native"}
SERVICE_KINDS = {"url", "docker-local"}


class BypassRule(BaseModel):
    path_prefix: str = Field(min_length=1, max_length=255)
    required_header: str | None = Field(default=None, max_length=64)
    header_prefix: str | None = Field(default=None, max_length=64)   # header value must start with this
    required_query: str | None = Field(default=None, max_length=64)  # query param must be present & non-empty

    @field_validator("path_prefix")
    @classmethod
    def _starts_with_slash(cls, v):
        if not v.startswith("/"):
            raise ValueError("path_prefix must start with /")
        return v

    @model_validator(mode="after")
    def _one_condition(self):
        # a rule without a condition bypasses its whole prefix, so never let a
        # half-specified rule (e.g. header_prefix alone) silently widen that
        if self.header_prefix and not self.required_header:
            raise ValueError("header_prefix requires required_header")
        if self.required_header and self.required_query:
            raise ValueError("required_header and required_query are mutually exclusive")
        return self


class _ServiceFields(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    icon: str | None = Field(default=None, max_length=400_000)   # same cap as workstation icons
    kind: str = "url"
    upstream_url: str | None = None
    container: str | None = Field(default=None, max_length=255, pattern=CONTAINER_NAME_RE)
    container_port: int | None = Field(default=None, ge=1, le=65535)
    mount_mode: str = "path"
    auth_mode: str = "sso"
    bypass_rules: list[BypassRule] = []
    allowed_groups: list[str] = []
    verify_tls: bool = True
    upstream_is_proxy: bool = False      # url kind only; send the URL hostname as Host/SNI
    health_path: str | None = Field(default=None, max_length=255)
    preset_id: str | None = None
    enabled: bool = True
    pass_identity: bool = False
    frame_ok: bool = True

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in SERVICE_KINDS:
            raise ValueError("kind must be url or docker-local")
        return v

    @field_validator("mount_mode")
    @classmethod
    def _mount(cls, v):
        if v not in MOUNT_MODES:
            raise ValueError("mount_mode must be path or cookie-root")
        return v

    @field_validator("auth_mode")
    @classmethod
    def _auth(cls, v):
        if v not in AUTH_MODES:
            raise ValueError("auth_mode must be sso, sso-with-bypass or app-native")
        return v

    @field_validator("upstream_url")
    @classmethod
    def _url(cls, v):
        if v is None:
            return v
        # http(s) only; "@" is barred from the authority part (no credentials/userinfo)
        if not re.fullmatch(r"https?://[^\s/@]+(/\S*)?", v) or re.search(r"[\x00-\x20\x7f]", v):
            raise ValueError("upstream_url must be http(s)://host[:port][/path], no credentials")
        return v.rstrip("/")

    @field_validator("health_path")
    @classmethod
    def _health(cls, v):
        if v is not None and not v.startswith("/"):
            raise ValueError("health_path must start with /")
        return v

    def _cross_check(self):
        if self.kind == "url" and not self.upstream_url:
            raise ValueError("upstream_url required for kind=url")
        if self.kind == "docker-local" and not (self.container and self.container_port):
            raise ValueError("container and container_port required for kind=docker-local")
        if self.upstream_is_proxy:
            if self.kind != "url":
                raise ValueError("upstream_is_proxy only allowed for kind=url")
            if _is_ip(urlsplit(self.upstream_url).hostname):
                raise ValueError("A reverse proxy picks the site by hostname, so the upstream "
                                 "address must use one (e.g. https://unraid.home.lan).")
        if self.bypass_rules and self.auth_mode != "sso-with-bypass":
            raise ValueError("bypass_rules only allowed with auth_mode=sso-with-bypass")
        return self


class ProxiedServiceCreate(_ServiceFields):
    slug: str

    @field_validator("slug")
    @classmethod
    def _slug(cls, v):
        if not SERVICE_SLUG_RE.match(v) or v in RESERVED_SERVICE_SLUGS:
            raise ValueError("slug is invalid or reserved")
        return v

    @model_validator(mode="after")
    def _after(self):
        return self._cross_check()


class ProxiedServiceUpdate(_ServiceFields):
    @model_validator(mode="after")
    def _after(self):
        return self._cross_check()


class ProxiedServiceOut(BaseModel):
    id: str
    slug: str
    name: str
    icon_kind: str = "auto"        # auto | emoji | image (bytes are served by GET /{id}/icon)
    icon_etag: str = ""            # cache-buster for /{id}/icon?v=
    kind: str
    upstream_url: str | None
    container: str | None
    container_port: int | None
    upstream_fallback: str | None
    mount_mode: str
    auth_mode: str
    bypass_rules: list[dict]
    allowed_groups: list[str]
    verify_tls: bool
    upstream_is_proxy: bool = False
    health_path: str | None
    health_status: str
    health_checked_at: str | None
    preset_id: str | None
    enabled: bool
    mount_managed: bool
    needs_setup: bool = False
    pass_identity: bool
    frame_ok: bool
    created_at: str
    updated_at: str


class ServiceTileOut(BaseModel):
    """What non-admins see: enough for a tile, no upstream/topology details."""
    id: str
    slug: str
    name: str
    icon_kind: str = "auto"
    icon_etag: str = ""
    mount_mode: str
    enabled: bool
    up: bool | None          # None = unknown
    frame_ok: bool = True
    needs_setup: bool = False


class ServicePresetOut(BaseModel):
    id: str
    name: str
    icon: str | None
    default_port: int | None
    mount_mode: str
    auth_mode: str
    bypass_rules: list[dict]
    health_path: str | None
    verify_tls: bool
    base_url_hint: str | None
    warnings: list[str]
    subpath: dict | None = None


class DiscoveredContainer(BaseModel):
    name: str
    image: str
    ports: list[int]
    networks: list[str]
    suggested_preset: str | None = None


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[^,]+$")  # X-Styx-Groups is comma-joined
    description: str | None = Field(default=None, max_length=255)


class GroupOut(BaseModel):
    id: str
    name: str
    description: str | None
    member_count: int = 0


class UserGroupsUpdate(BaseModel):
    group_ids: list[str]
