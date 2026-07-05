#!/bin/sh
# Stamp the release version into the backend Python package.
#
# semantic-release computes the version from conventional commits; this script
# writes it into backend/pyproject.toml so the built image reports the real
# released version (surfaced via importlib.metadata in app/main.py).
#
# The agent (agent/styx_agent.py AGENT_VERSION) is intentionally NOT touched:
# it is an independent version stream that drives the workstation auto-update
# check (backend get_latest_agent_version parses it). Clobbering it to the repo
# release version would flag every enrolled workstation as outdated.
set -eu

V="${1:?usage: stamp-version.sh <version>}"
V="${V#v}"

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYPROJECT="$ROOT/backend/pyproject.toml"

# Only the [project] version key. tool.* tables use other keys
# (target-version, python_version) so anchoring on `^version = ` is unambiguous.
sed -i "s/^version = \".*\"/version = \"$V\"/" "$PYPROJECT"
grep -q "^version = \"$V\"\$" "$PYPROJECT" || { echo "stamp failed: $PYPROJECT" >&2; exit 1; }

echo "stamped backend version $V"
