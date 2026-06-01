from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DOMAIN: str = "localhost"
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/selkies-hub.db"
    DOCKER_SOCKET: str = "unix:///var/run/docker.sock"
    DOCKER_NETWORK: str = "selkies-hub"
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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def jwt_secret_or_raise(self) -> str:
        if not self.JWT_SECRET:
            if self.COOKIE_SECURE:
                raise RuntimeError("JWT_SECRET must be set when COOKIE_SECURE=true")
            return "dev-insecure-secret-do-not-use-in-prod"
        return self.JWT_SECRET
