#!/usr/bin/env bash
# Styx agent removal. Safe to run repeatedly.
# Usage: bash uninstall.sh   (or: python3 ~/.local/share/styx-agent/styx_agent.py uninstall)
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/styx-agent"

if [[ -f "$INSTALL_DIR/styx_agent.py" ]]; then
  python3 "$INSTALL_DIR/styx_agent.py" uninstall
else
  systemctl --user disable --now styx-agent.service 2>/dev/null || true
  rm -f "$HOME/.config/systemd/user/styx-agent.service"
  systemctl --user daemon-reload 2>/dev/null || true
  rm -rf "$INSTALL_DIR" "$HOME/.config/styx-agent"
  echo "Styx agent removed (agent script was missing; cleaned up files directly)."
fi
