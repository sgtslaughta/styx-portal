#!/usr/bin/env bash
# GNOME Wayland session — nested gnome-shell inside Pixelflux's Smithay compositor
ulimit -c 0
export XKB_DEFAULT_LAYOUT=us
export XKB_DEFAULT_RULES=evdev
export WAYLAND_DISPLAY=wayland-1
export XDG_SESSION_TYPE=wayland
export XCURSOR_THEME=Yaru
export XCURSOR_SIZE=24
export GTK_THEME=Yaru

# First-run: seed default dconf into the persisted volume
if [ ! -f /config/.config/.gnome-seeded ]; then
    mkdir -p /config/.config
    dconf load / < /defaults/dconf/00-ubuntu-defaults || true
    touch /config/.config/.gnome-seeded
fi

# NVIDIA / GPU acceleration (verbatim from XFCE image)
if command -v nvidia-smi &> /dev/null && [ -e /dev/dri ]; then
    export LIBGL_KOPPER_DRI2=1
    export MESA_LOADER_DRIVER_OVERRIDE=zink
    export GALLIUM_DRIVER=zink
fi

# Launch GNOME Shell nested as a Wayland client of Pixelflux's compositor.
exec dbus-run-session -- gnome-shell --wayland --nested
