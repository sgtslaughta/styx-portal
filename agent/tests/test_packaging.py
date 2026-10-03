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


def test_enroll_upgrade_is_atomic_and_self_restoring():
    sh = (AGENT / "enroll.sh").read_text()
    assert 'mv "$INSTALL_DIR" "$INSTALL_DIR.prev"' in sh
    assert "trap restore_prev ERR" in sh
    body = sh.split("restore_prev() {", 1)[1].split("\n}", 1)[0]
    assert 'mv "$INSTALL_DIR.prev" "$INSTALL_DIR"' in body
    assert "restore_prev; exit 1" in sh  # fail() restores too
    assert 'cp -a "$INSTALL_DIR"' not in sh.replace('"$INSTALL_DIR.prev/', "")
    step5 = sh.split('step 5/8', 1)[1].split('step 6/8', 1)[0]
    assert 'if [[ "$UPGRADE" == 1 ]]' in step5.split("install_pkgs()", 1)[0]
