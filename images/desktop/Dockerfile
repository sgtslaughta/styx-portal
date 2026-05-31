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
    rm -rf /var/lib/apt/lists/*

# ─── CLI utils + Yaru dark theme ─────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    nano \
    btop \
    yaru-theme-gtk \
    yaru-theme-icon \
    && rm -rf /var/lib/apt/lists/*

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
