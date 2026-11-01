#!/bin/sh
# Extract ```mermaid blocks from README/docs (rewriting them to SVG links), then .mmd -> .excalidraw -> SVGs.
# Overwrites existing .excalidraw for the named (or all) .mmd files.
. "$(dirname "$0")/lib.sh"
mkdir -p "$ROOT/docs/assets/diagrams"
dnode extract.mjs /src /src/docs/assets/diagrams
dnode run.mjs convert /src/docs/assets/diagrams "$@" && "$(dirname "$0")/render.sh" "$@"
