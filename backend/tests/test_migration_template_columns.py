import sqlite3
from app.database import _ensure_template_columns


def test_ensure_template_columns_adds_missing(tmp_path):
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE service_templates (id TEXT PRIMARY KEY, name TEXT)"
    )
    conn.commit()
    _ensure_template_columns(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(service_templates)")}
    for c in ["shared", "restart_policy", "read_only_rootfs", "tmpfs",
              "extra_hosts", "ulimits", "extra_ports", "entrypoint",
              "command", "devices", "privileged", "extra_docker_args"]:
        assert c in cols
    # idempotent: second run does not raise
    _ensure_template_columns(conn)
    conn.close()
