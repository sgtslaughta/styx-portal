import json
from pathlib import Path
from types import SimpleNamespace

from app.services.k8s_instance_objects import refuse_reason

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


def _refused() -> dict[str, str | None]:
    out = {}
    for f in sorted(TEMPLATES.glob("*.json")):
        d = json.loads(f.read_text())
        out[f.stem] = refuse_reason(SimpleNamespace(
            dind=d.get("dind", False), privileged=d.get("privileged", False),
            cap_add=d.get("cap_add", [])))
    return out


def test_only_dind_seed_is_refused_on_k8s():
    r = _refused()
    assert set(r) == {"blank", "dev-desktop", "gaming", "workstation", "xfce-desktop"}
    assert [k for k, v in r.items() if v] == ["dev-desktop"]
    assert "DinD" in r["dev-desktop"]
