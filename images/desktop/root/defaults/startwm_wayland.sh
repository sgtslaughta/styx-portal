#!/usr/bin/env bash

# Wayland DE startup — XFCE 4.20 official Wayland session via labwc
ulimit -c 0
export XCURSOR_THEME=breeze
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

# Launch labwc as the nesting Wayland compositor + window manager. labwc connects
# to Pixelflux's parent socket (WAYLAND_DISPLAY=wayland-1 in /config/.XDG) as a
# Wayland client, so Pixelflux captures it. The stock `startxfce4 --wayland` path
# uses `wlheadless-run -c labwc`, which would create a SEPARATE headless display
# Pixelflux can't see — we launch labwc directly to nest instead. labwc then runs
# xfce4-session (panel, xfdesktop, settings daemon) and provides WM + cursor.
export XDG_SESSION_TYPE=wayland
export XDG_CURRENT_DESKTOP=XFCE
# Force GTK apps onto Xwayland (X11). XFCE has no working native-Wayland GTK
# backend yet; with WAYLAND_DISPLAY set, GTK would auto-pick Wayland and
# xfce4-panel crashes ("cannot open display"), which xfce4-session then respawns
# in a tight loop. GDK_BACKEND=x11 routes XFCE + apps through the Xwayland server
# labwc provides (DISPLAY=:1). labwc itself is wlroots, unaffected by this.
export GDK_BACKEND=x11
exec labwc -s xfce4-session
