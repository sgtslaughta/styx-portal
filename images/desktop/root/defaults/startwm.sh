#!/bin/bash

# Detect NVIDIA GPU for hardware acceleration
if command -v nvidia-smi &> /dev/null && [ -e /dev/dri ]; then
    export LIBGL_KOPPER_DRI2=1
    export MESA_LOADER_DRIVER_OVERRIDE=zink
    export GALLIUM_DRIVER=zink
fi

# Copy default XFCE config if not present
if [ ! -d /config/.config/xfce4 ]; then
    mkdir -p /config/.config
    cp -r /defaults/xfce4 /config/.config/xfce4
fi

# Copy default zshrc if not present
if [ ! -f /config/.zshrc ]; then
    cp /defaults/.zshrc /config/.zshrc
fi

# Install oh-my-zsh on first run
if [ ! -d /config/.oh-my-zsh ]; then
    cp -r /defaults/.oh-my-zsh /config/.oh-my-zsh
    chown -R abc:abc /config/.oh-my-zsh
fi

# Terminator config
if [ ! -d /config/.config/terminator ]; then
    mkdir -p /config/.config/terminator
    cp /defaults/terminator/config /config/.config/terminator/config
fi

# Start XFCE session under dbus
exec dbus-launch --exit-with-session xfce4-session
