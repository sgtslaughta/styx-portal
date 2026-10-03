"""Every local module the agent imports at runtime must be served by the backend."""
import ast
import re
from pathlib import Path

AGENT = Path(__file__).resolve().parents[1]
BACKEND_LIST = AGENT.parent / "backend/app/services/workstations.py"
ENTRY = ["styx_agent", "engine", "gateway", "seat_gnome", "seat_labwc",
         "grant", "health", "portal_api"]


def _local_imports(path: Path) -> set[str]:
    local = {p.stem for p in AGENT.glob("*.py")}
    mods = set()
    for n in ast.walk(ast.parse(path.read_text())):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            mods.add(n.module.split(".")[0])
    return mods & local


def test_all_imported_local_modules_are_served():
    text = BACKEND_LIST.read_text()
    block = text.split("AGENT_UPDATE_FILES = [", 1)[1].split("]", 1)[0]
    served = set(re.findall(r'\("[^"]+", "([^"]+)"\)', block))
    for name in ENTRY:
        for mod in _local_imports(AGENT / f"{name}.py"):
            assert f"{mod}.py" in served, f"{name} imports {mod}, not served"
    assert "selkies_launcher.py" not in served
