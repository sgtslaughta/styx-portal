FROM ghcr.io/linuxserver/baseimage-selkies:ubunturesolute

LABEL maintainer="richardsoto1010@gmail.com"
LABEL description="Minimal GNOME (Ubuntu 26.04) Wayland desktop"

ENV DEBIAN_FRONTEND=noninteractive

# ─── GNOME core (nested Wayland shell) ───────────────────────────────────────
# --no-install-recommends and NO ubuntu-desktop meta → avoids snapd.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnome-shell \
    gnome-session \
    gnome-settings-daemon \
    mutter \
    nautilus \
    gnome-control-center \
    dbus-x11 \
    at-spi2-core \
    dconf-cli \
    && rm -rf /var/lib/apt/lists/*

# ─── Stock Ubuntu 26.04 GNOME apps ───────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnome-text-editor \
    gnome-system-monitor \
    gnome-calculator \
    loupe \
    papers \
    ptyxis \
    xdg-desktop-portal-gnome \
    && rm -rf /var/lib/apt/lists/*

# ─── Ubuntu look: Yaru theme + dock + appindicator ───────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    yaru-theme-gtk \
    yaru-theme-icon \
    yaru-theme-sound \
    yaru-theme-gnome-shell \
    gnome-shell-extension-ubuntu-dock \
    gnome-shell-extension-appindicator \
    ubuntu-wallpapers \
    fonts-ubuntu \
    && rm -rf /var/lib/apt/lists/*

# ─── Firefox (deb, not snap) — Mozilla PPA, pinned over transition package ────
RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common && \
    add-apt-repository -y ppa:mozillateam/ppa && \
    printf 'Package: *\nPin: release o=LP-PPA-mozillateam\nPin-Priority: 1001\n' > /etc/apt/preferences.d/mozilla-firefox && \
    apt-get update && apt-get install -y --no-install-recommends firefox && \
    rm -rf /var/lib/apt/lists/*

# ─── Default dconf settings (theme, dock, extensions) ────────────────────────
COPY root/defaults/dconf/ /defaults/dconf/

# ─── Desktop Startup Override ────────────────────────────────────────────────
COPY root/defaults/startwm_wayland.sh /defaults/startwm_wayland.sh
RUN chmod +x /defaults/startwm_wayland.sh

ENV TITLE="GNOME Desktop"
ENV START_DOCKER=false

EXPOSE 3000 3001
VOLUME /config
