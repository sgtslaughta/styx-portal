FROM ghcr.io/linuxserver/baseimage-selkies:ubunturesolute

LABEL maintainer="richardsoto1010@gmail.com"
LABEL description="Full XFCE Wayland desktop with dev tools"

# Prevent interactive prompts during install
ENV DEBIAN_FRONTEND=noninteractive

# ─── XFCE Desktop Environment ───────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    xfce4 \
    xfce4-goodies \
    xfce4-terminal \
    xfce4-whiskermenu-plugin \
    thunar-archive-plugin \
    thunar-volman \
    tumbler \
    mousepad \
    ristretto \
    xfce4-screenshooter \
    xfce4-taskmanager \
    xfce4-clipman-plugin \
    xfce4-notifyd \
    dbus-x11 \
    at-spi2-core \
    && rm -rf /var/lib/apt/lists/*

# ─── Browsers (deb packages, not snap) ───────────────────────────────────────
# Firefox from Mozilla's official PPA
RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common && \
    add-apt-repository -y ppa:mozillateam/ppa && \
    printf 'Package: *\nPin: release o=LP-PPA-mozillateam\nPin-Priority: 1001\n' > /etc/apt/preferences.d/mozilla-firefox && \
    apt-get update && apt-get install -y --no-install-recommends firefox && \
    rm -rf /var/lib/apt/lists/*

# Chromium from debian/upstream deb (not snap)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gnupg ca-certificates && \
    curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# ─── Terminal & Shell ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    terminator \
    zsh \
    zsh-autosuggestions \
    zsh-syntax-highlighting \
    fzf \
    fd-find \
    ripgrep \
    bat \
    eza \
    htop \
    ncdu \
    tmux \
    && rm -rf /var/lib/apt/lists/*

# ─── Development Tools ───────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    git-lfs \
    build-essential \
    cmake \
    ninja-build \
    pkg-config \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    curl \
    wget \
    unzip \
    jq \
    && rm -rf /var/lib/apt/lists/*

# ─── Node.js 22 + npm (NodeSource deb, not snap) ─────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# ─── VSCode (Microsoft apt repo, deb) ────────────────────────────────────────
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list && \
    apt-get update && apt-get install -y --no-install-recommends code && \
    rm -rf /var/lib/apt/lists/* && \
    sed -i 's|/usr/share/code/code|/usr/share/code/code --no-sandbox|g' /usr/share/applications/code.desktop /usr/share/applications/code-url-handler.desktop 2>/dev/null || true

# ─── CLI utils + Yaru dark theme ─────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    nano \
    btop \
    yaru-theme-gtk \
    yaru-theme-icon \
    && rm -rf /var/lib/apt/lists/*

# ─── Squared GTK theme (EliverLara) ──────────────────────────────────────────
# Single dark GTK theme (the theme IS dark; no -dark variant). The repo root holds
# the theme dirs + index.theme, alongside non-theme dirs (Art/assets/src) we skip.
# Its bundled xfwm4 theme is NOT used: the session runs labwc (Wayland), which
# themes window borders from openbox-3, not xfwm4 — borders use Breeze-ob (set at
# session start). Icon theme stays Yaru-dark.
RUN git clone --depth=1 https://github.com/EliverLara/Squared.git /tmp/squared && \
    mkdir -p /usr/share/themes/Squared && \
    cp -r /tmp/squared/gtk-2.0 /tmp/squared/gtk-3.0 /tmp/squared/gtk-4.0 \
          /tmp/squared/xfwm4 /tmp/squared/metacity-1 /tmp/squared/index.theme \
          /usr/share/themes/Squared/ && \
    rm -rf /tmp/squared

# ─── MesloLGS NF font (Nerd Font; default terminal font) ─────────────────────
# All four styles so terminals render bold/italic. URLs use %20 literals (Docker
# RUN is /bin/sh = dash, which lacks bash ${var// /} substitution).
RUN mkdir -p /usr/share/fonts/truetype/meslolgs && \
    cd /usr/share/fonts/truetype/meslolgs && \
    b="https://github.com/romkatv/powerlevel10k-media/raw/master" && \
    curl -fsSL "$b/MesloLGS%20NF%20Regular.ttf"     -o "MesloLGS NF Regular.ttf" && \
    curl -fsSL "$b/MesloLGS%20NF%20Bold.ttf"        -o "MesloLGS NF Bold.ttf" && \
    curl -fsSL "$b/MesloLGS%20NF%20Italic.ttf"      -o "MesloLGS NF Italic.ttf" && \
    curl -fsSL "$b/MesloLGS%20NF%20Bold%20Italic.ttf" -o "MesloLGS NF Bold Italic.ttf" && \
    fc-cache -f

# ─── PyCharm Community (JetBrains tarball, bundles JBR runtime) ───────────────
RUN set -eux; \
    url="$(curl -fsSL 'https://data.services.jetbrains.com/products/releases?code=PCC&latest=true&type=release' | jq -r '.PCC[0].downloads.linux.link')"; \
    curl -fsSL "$url" -o /tmp/pycharm.tar.gz; \
    mkdir -p /opt/pycharm; \
    tar -xzf /tmp/pycharm.tar.gz -C /opt/pycharm --strip-components=1; \
    rm /tmp/pycharm.tar.gz; \
    ln -sf /opt/pycharm/bin/pycharm.sh /usr/local/bin/pycharm
COPY root/defaults/applications/pycharm.desktop /usr/share/applications/pycharm.desktop

# ─── UV (Python package manager) ────────────────────────────────────────────
RUN curl -LsSf https://astral.sh/uv/install.sh | env HOME=/root sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && mv /root/.local/bin/uvx /usr/local/bin/uvx

# ─── Oh My Zsh (pre-download for first-run install) ─────────────────────────
RUN git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git /defaults/.oh-my-zsh

# ─── Zsh Configuration ──────────────────────────────────────────────────────
COPY root/defaults/.zshrc /defaults/.zshrc

# ─── Desktop Startup Override ────────────────────────────────────────────────
COPY root/defaults/startwm.sh /defaults/startwm.sh
COPY root/defaults/startwm_wayland.sh /defaults/startwm_wayland.sh
COPY root/defaults/autostart /defaults/autostart
RUN chmod +x /defaults/startwm.sh /defaults/startwm_wayland.sh /defaults/autostart

# ─── XFCE Default Config ────────────────────────────────────────────────────
COPY root/defaults/xfce4/ /defaults/xfce4/

# ─── Terminator Config ──────────────────────────────────────────────────────
COPY root/defaults/terminator/ /defaults/terminator/

# ─── Wallpaper & Power Management stub ───────────────────────────────────────
RUN mkdir -p /usr/share/xfce4/backdrops && \
    python3 -c "import struct,zlib;raw=b''.join(b'\x00'+bytes([0x2e,0x34,0x40])*1920 for _ in range(1080));c=lambda t,d:struct.pack('>I',len(d))+t+d+struct.pack('>I',zlib.crc32(t+d)&0xffffffff);open('/usr/share/xfce4/backdrops/xubuntu-wallpaper.png','wb').write(b'\x89PNG\r\n\x1a\n'+c(b'IHDR',struct.pack('>IIBBBBB',1920,1080,8,2,0,0,0))+c(b'IDAT',zlib.compress(raw))+c(b'IEND',b''))" && \
    printf '#!/bin/sh\nexit 1\n' > /usr/bin/pm-is-supported && chmod +x /usr/bin/pm-is-supported

# ─── Environment ─────────────────────────────────────────────────────────────
ENV TITLE="Desktop"
ENV SHELL=/bin/zsh
ENV START_DOCKER=false

# Default user shell to zsh
RUN usermod -s /bin/zsh abc 2>/dev/null || true

EXPOSE 3000 3001
VOLUME /config
