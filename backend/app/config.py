import json
import logging
import os
import secrets as _secrets
from pathlib import Path

from pydantic_settings import BaseSettings

logger = logging.getLogger("styx-portal")

PLACEHOLDER_SECRETS = {
    "change-me-to-a-long-random-string-min-32-bytes",
    "dev-insecure-secret-do-not-use-in-prod",
}


class Settings(BaseSettings):
    DOMAIN: str = "localhost"
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/styx-portal.db"
    DOCKER_SOCKET: str = "unix:///var/run/docker.sock"
    DOCKER_NETWORK: str = "styx-portal"
    SELKIES_DEFAULT_PORT: int = 3001
    TEMPLATES_DIR: str = "/app/templates"
    SCREENSHOT_CACHE_DIR: str = "/app/data/screenshots"
    SCREENSHOT_INTERVAL_SECONDS: int = 30
    TRAEFIK_DYNAMIC_DIR: str = "/app/traefik-dynamic"
    AUTHENTIK_MIDDLEWARE: str = "authentik@file"
    JWT_SECRET: str = ""
    ACCESS_TTL: int = 900          # 15 minutes
    REFRESH_TTL: int = 604800      # 7 days
    COOKIE_SECURE: bool = True
    COOKIE_DOMAIN: str | None = None
    RATE_LIMIT_AUTH: str = "5/60"        # 5 requests per 60s on /auth/*
    RATE_LIMIT_DEFAULT: str = "120/60"   # 120 requests per 60s otherwise
    OAUTH_REDIRECT_BASE: str = ""   # e.g. https://s.jmolabs.dev ; defaults to https://{DOMAIN}
    SECRETS_FILE: str = "/app/data/secrets.json"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def jwt_secret_or_raise(self) -> str:
        if self.JWT_SECRET:
            if self.JWT_SECRET in PLACEHOLDER_SECRETS:
                raise RuntimeError(
                    "JWT_SECRET is a placeholder value. Generate a real one: "
                    "openssl rand -base64 48"
                )
            if len(self.JWT_SECRET) < 32:
                raise RuntimeError(
                    f"JWT_SECRET must be at least 32 characters (got {len(self.JWT_SECRET)}). "
                    "Generate one: openssl rand -base64 48"
                )
            return self.JWT_SECRET
        return self._load_or_create_secret()

    def _load_or_create_secret(self) -> str:
        path = Path(self.SECRETS_FILE)
        data: dict = {}
        if path.exists():
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning("Secrets file %s unreadable/corrupt — regenerating", path)
                data = {}
            secret = data.get("jwt_secret")
            if isinstance(secret, str) and len(secret) >= 32:
                return secret
        secret = _secrets.token_urlsafe(48)
        data["jwt_secret"] = secret
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(data, indent=2))
        path.chmod(0o600)  # belt-and-suspenders if file pre-existed with wider mode
        logger.warning(
            "JWT_SECRET not set — generated one and saved to %s. "
            "Back this file up; losing it logs everyone out and invalidates "
            "stored OAuth client secrets.", path,
        )
        return secret

    def oauth_redirect_base(self) -> str:
        return self.OAUTH_REDIRECT_BASE or f"https://{self.DOMAIN}"
