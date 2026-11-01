#!/bin/sh
# Render docs/assets/diagrams/*.excalidraw -> <name>-light.svg + <name>-dark.svg. Args: optional names.
. "$(dirname "$0")/lib.sh"
dnode run.mjs render /src/docs/assets/diagrams "$@"
