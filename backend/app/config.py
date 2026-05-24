from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DOMAIN: str = "localhost"
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/selkies-hub.db"
    DOCKER_SOCKET: str = "unix:///var/run/docker.sock"
    DOCKER_NETWORK: str = "selkies-hub"
    SELKIES_DEFAULT_PORT: int = 3001
    TEMPLATES_DIR: str = "/app/templates"
    SCREENSHOT_CACHE_DIR: str = "/app/data/screenshots"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
