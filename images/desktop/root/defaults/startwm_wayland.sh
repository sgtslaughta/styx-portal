#!/usr/bin/env bash

# Wayland DE startup — XFCE 4.20 official Wayland session via labwc
ulimit -c 0
# Cursor theme MUST name an installed theme or X shows the ugly 'X' fallback
# cursor. Only Yaru / Adwaita / breeze_cursors exist here — "breeze" does not.
export XCURSOR_THEME=Yaru
export XCURSOR_SIZE=24
export XKB_DEFAULT_LAYOUT=us
export XKB_DEFAULT_RULES=evdev
export WAYLAND_DISPLAY=wayland-1

# First-run config setup
if [ ! -d /config/.config/xfce4 ]; then
    mkdir -p /config/.config
    cp -r /defaults/xfce4 /config/.config/xfce4
fi

if [ ! -f /config/.zshrc ]; then
    cp /defaults/.zshrc /config/.zshrc
fi

if [ ! -d /config/.oh-my-zsh ]; then
    cp -r /defaults/.oh-my-zsh /config/.oh-my-zsh
    chown -R abc:abc /config/.oh-my-zsh
fi

if [ ! -d /config/.config/terminator ]; then
    mkdir -p /config/.config/terminator
    cp /defaults/terminator/config /config/.config/terminator/config
fi

# NVIDIA GPU acceleration
if command -v nvidia-smi &> /dev/null && [ -e /dev/dri ]; then
    export LIBGL_KOPPER_DRI2=1
    export MESA_LOADER_DRIVER_OVERRIDE=zink
    export GALLIUM_DRIVER=zink
fi

# Remove saved display config — Pixelflux creates modes dynamically per-client
rm -f /config/.config/xfce4/xfconf/xfce-perchannel-xml/displays.xml

# Launch full XFCE session via official Wayland method
exec startxfce4 --wayland
