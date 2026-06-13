"""Settings must tolerate unrelated keys in the shared deployment .env.

The repo-root .env is shared with docker-compose / cloudflared / authentik and
carries vars the backend Settings model does not declare (e.g. CF_TUNNEL_TOKEN,
AUTHENTIK_HOST, COMPOSE_PROFILES). Reading such a .env file must not raise
extra_forbidden — Settings should ignore unknown keys.
"""
from app.config import Settings


def test_settings_ignores_unknown_env_file_keys(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "CF_TUNNEL_TOKEN=deadbeef\n"
        "AUTHENTIK_HOST=a.example.com\n"
        "COMPOSE_PROFILES=tunnel\n"
        "DOMAIN=test.local\n"
    )
    # Without extra="ignore" this raises pydantic ValidationError(extra_forbidden).
    s = Settings(_env_file=str(env))  # type: ignore[call-arg]
    assert s.DOMAIN == "test.local"
