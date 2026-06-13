"""Engine logic for the pixelflux/selkies 2.x agent — pure functions only.

mirror: attach to a live X display (XShm capture), resolution locked to the
        physical screen so selkies never xrandr-resizes the user's monitor.
seat:   pixelflux's own Wayland compositor; host apps join via WAYLAND_DISPLAY.
"""
import glob
import json
import os
import socket
import time
from pathlib import Path

HOME = Path.home()
DRI_DIR = "/dev/dri"
SEAT_SINK = "styx-seat"    # null sink so seat audio never hits the speakers
APPLICATIONS_DIRS = ["/usr/share/applications",
                     "/usr/local/share/applications",
                     str(HOME / ".local/share/applications")]


def _find_xauthority(cfg: dict) -> str | None:
    """systemd --user starts with an empty env; resolve the cookie explicitly.
    Location varies by distro/display manager."""
    uid = os.getuid()
    candidates = [
        cfg.get("xauthority"),
        os.environ.get("XAUTHORITY"),
        str(HOME / ".Xauthority"),
        f"/run/user/{uid}/.mutter-Xwaylandauth",      # GNOME Xwayland
        f"/run/user/{uid}/gdm/Xauthority",            # GDM
    ]
    candidates += [str(p) for p in sorted(HOME.glob(".vnc/*Xauthority"))]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


def pick_free_port() -> int:
    """A free loopback port for the selkies<->gateway link (race window
    between close and child bind is acceptable on loopback)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pick_dri_node() -> str:
    nodes = sorted(glob.glob(os.path.join(DRI_DIR, "renderD*")))
    return nodes[0] if nodes else ""


def query_display_geometry(display: str, xauthority: str | None) -> tuple[int, int]:
    """Screen size of a live X display, via the venv's python-xlib.

    Xlib reads XAUTHORITY from the process env at connect time; set it only
    for the duration of the query so the supervisor's env stays clean.
    """
    from Xlib import display as xdisplay  # venv dep of selkies
    saved = os.environ.get("XAUTHORITY")
    if xauthority:
        os.environ["XAUTHORITY"] = xauthority
    try:
        d = xdisplay.Display(display)
        try:
            s = d.screen()
            return s.width_in_pixels, s.height_in_pixels
        finally:
            d.close()
    finally:
        if xauthority:
            if saved is None:
                os.environ.pop("XAUTHORITY", None)
            else:
                os.environ["XAUTHORITY"] = saved


def resolve_monitor_source() -> str:
    """Monitor source of the default sink ('' = no audio server -> disable).
    selkies' baked-in default 'output.monitor' only exists in containers."""
    try:
        import pulsectl
        with pulsectl.Pulse("styx-agent") as p:
            return p.server_info().default_sink_name + ".monitor"
    except Exception:
        return ""


def ensure_seat_sink() -> str:
    """Create (idempotently) a null sink for seat audio; returns its monitor."""
    import pulsectl
    with pulsectl.Pulse("styx-agent") as p:
        if not any(s.name == SEAT_SINK for s in p.sink_list()):
            p.module_load("module-null-sink",
                          f"sink_name={SEAT_SINK} "
                          f"sink_properties=device.description={SEAT_SINK}")
    return f"{SEAT_SINK}.monitor"


MIC_SOURCE = "SelkiesVirtualMic"   # name selkies expects to find


def ensure_mic_source() -> str:
    """Pre-create the virtual microphone plumbing selkies expects.

    selkies plays browser mic audio into a sink literally named 'input' and
    needs a source 'SelkiesVirtualMic' on its monitor. It tries to create
    the source via module-virtual-source, which PipeWire's pulse shim
    accepts but never materializes — so build the equivalent here with
    modules PipeWire does implement (null-sink + remap-source). selkies
    then finds the existing source and proceeds."""
    import pulsectl
    with pulsectl.Pulse("styx-agent") as p:
        if not any(s.name == "input" for s in p.sink_list()):
            p.module_load("module-null-sink",
                          "sink_name=input "
                          "sink_properties=device.description=styx-mic-in")
        if not any(s.name == MIC_SOURCE for s in p.source_list()):
            p.module_load("module-remap-source",
                          f"master=input.monitor source_name={MIC_SOURCE} "
                          f"source_properties=device.description={MIC_SOURCE}")
    return MIC_SOURCE


def guard_default_socket(runtime_dir: str):
    """Hold the wayland-0 slot so neither seat compositor can bind it.

    wl_display_connect(NULL) falls back to literally "wayland-0" when
    WAYLAND_DISPLAY is unset — true for every GTK/Qt app in an X11 login
    session. If the seat compositor or labwc grabs wayland-0, those host
    apps silently render INTO the seat (live-seen: Ubuntu's DING desktop
    icons floating over the seat desktop). Mirror libwayland's locking
    (flock on wayland-0.lock) so wl_display_add_socket_auto skips slot 0.

    Returns the held lock file (keep referenced for the agent's lifetime),
    or None when a real Wayland session already owns the slot."""
    import fcntl
    lock_path = Path(runtime_dir) / "wayland-0.lock"
    try:
        f = open(lock_path, "a+")
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    # We own the slot: drop any stale socket file so fallback connects
    # fail fast and clients move on to X11.
    (Path(runtime_dir) / "wayland-0").unlink(missing_ok=True)
    return f


def wait_for_wayland_socket(runtime_dir: str, before: set[str],
                            since_ts: float, timeout: float = 15) -> str | None:
    """The compositor picks the first free wayland-N. A socket counts if its
    name is new OR its file was (re)created after `since_ts` — stale socket
    files survive process death, so a pure before/after name diff misses a
    compositor that rebinds the same wayland-N (seen on agent restart)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for p in sorted(Path(runtime_dir).glob("wayland-*")):
            if p.name.endswith(".lock"):
                continue
            if p.name not in before:
                return p.name
            try:
                if p.stat().st_mtime >= since_ts:
                    return p.name
            except FileNotFoundError:
                continue
        time.sleep(0.2)
    return None


TERMINALS = ("foot", "alacritty", "kitty", "kgx", "gnome-terminal",
             "konsole", "xterm")


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def _menu_item(label: str, command: str) -> str:
    return (f'  <item label="{_xml_escape(label)}">'
            f'<action name="Execute" command="{_xml_escape(command)}"/></item>')


def build_root_menu(entries, term: str, file_mgr: str, home: str) -> str:
    """labwc/openbox root menu: Files + Terminal at top, an Applications
    submenu built from `entries`, then Reconfigure/Exit."""
    apps = "\n".join(_menu_item(n, e) for n, e in entries) or \
        '  <item label="(no apps found)"><action name="Reconfigure"/></item>'
    top = []
    if file_mgr:
        top.append(_menu_item("Files", f"{file_mgr} {home}"))
    if term:
        top.append(_menu_item("Terminal", term))
    top_xml = "\n".join(top)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<openbox_menu>
<menu id="apps-menu" label="Applications">
{apps}
</menu>
<menu id="root-menu" label="Styx">
{top_xml}
  <menu id="apps-menu"/>
  <separator/>
  <item label="Reconfigure"><action name="Reconfigure"/></item>
  <item label="Exit session"><action name="Exit"/></item>
</menu>
</openbox_menu>
"""


def pick_terminal() -> str:
    import shutil
    for term in TERMINALS:
        if shutil.which(term):
            return term
    return ""


LAUNCHERS = ("nwg-drawer", "fuzzel")


def pick_launcher() -> str:
    """Full-screen app grid (nwg-drawer) preferred, then a compact search
    launcher (fuzzel). Empty string -> caller falls back to labwc root menu."""
    import shutil
    for name in LAUNCHERS:
        if shutil.which(name):
            return name
    return ""


FILE_MANAGERS = ("nautilus", "nemo", "thunar", "pcmanfm-qt", "pcmanfm", "dolphin")


def pick_file_manager() -> str:
    """First GUI file manager present on the host. Empty if none."""
    import shutil
    for name in FILE_MANAGERS:
        if shutil.which(name):
            return name
    return ""


def scan_desktop_entries(dirs=None) -> list:
    """(Name, Exec) pairs from .desktop files. Skips NoDisplay/Hidden and
    entries missing Name or Exec. Strips Exec field codes (%u %F etc.).
    De-duplicated by name, sorted. First [Desktop Entry] values win."""
    dirs = dirs if dirs is not None else APPLICATIONS_DIRS
    seen = {}
    for d in dirs:
        p = Path(d)
        if not p.is_dir():
            continue
        for f in sorted(p.glob("*.desktop")):
            name = exec_ = ""
            skip = False
            try:
                text = f.read_text(errors="ignore")
            except OSError:
                continue
            for line in text.splitlines():
                if line.startswith("[") and name:
                    break                       # past first [Desktop Entry]
                if line.startswith("Name=") and not name:
                    name = line[5:].strip()
                elif line.startswith("Exec=") and not exec_:
                    exec_ = line[5:].strip()
                elif line.startswith(("NoDisplay=true", "Hidden=true")):
                    skip = True
            if skip or not name or not exec_:
                continue
            exec_ = " ".join(t for t in exec_.split()
                             if not (len(t) == 2 and t.startswith("%")))
            seen.setdefault(name, exec_)
    return sorted(seen.items())


def _primary_ip() -> str:
    """Best-effort primary LAN IP (no packets sent — TEST-NET dest)."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


def _os_pretty() -> str:
    """PRETTY_NAME from /etc/os-release, or empty."""
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


def wave_polylines(width: int, height: int, amp: int = 90,
                   wavelength: int = 900, step: int = 16) -> list:
    """Stacked sine polylines spanning the full width, tiled top-to-bottom, each
    phase-shifted — a flowing 'river/ripple' wave field that fills the canvas
    (echoes the login RippleCanvas brand). Returns ImageMagick 'polyline' ops."""
    import math
    lines = []
    spacing = max(int(amp * 1.6), 1)
    band = 0
    y = -amp
    while y < height + amp:
        phase = band * 0.9
        pts = []
        x = 0
        while x <= width:
            yy = y + amp * math.sin(x / wavelength * 2 * math.pi + phase)
            pts.append(f"{x},{yy:.1f}")
            x += step
        lines.append("polyline " + " ".join(pts))
        y += spacing
        band += 1
    return lines


def wallpaper_convert_cmd(tool: str, out: str, title: str, subtitle: str,
                          color: str = "#1d2433",
                          size: str = "1920x1080",
                          wave_color: str = "#2b303a") -> list:
    """ImageMagick argv: dark base, a full-canvas subtle wave field (dark grey),
    then a bginfo-style label (hostname large, details small) bottom-right."""
    w, h = (int(v) for v in size.lower().split("x"))
    cmd = [tool, "-size", size, f"xc:{color}",
           "-stroke", wave_color, "-strokewidth", "5", "-fill", "none"]
    for poly in wave_polylines(w, h):
        cmd += ["-draw", poly]
    cmd += [
        "-stroke", "none", "-gravity", "SouthEast",
        "-fill", "#9aa4b8", "-pointsize", "24", "-annotate", "+60+55", subtitle,
        "-fill", "#e6e9ef", "-pointsize", "52", "-annotate", "+60+110", title,
        out,
    ]
    return cmd


def build_wallpaper(dest: Path, title: str, subtitle: str) -> bool:
    """Render the bginfo wallpaper via ImageMagick (magick/convert). Returns
    True on success; False (caller falls back to a solid colour) if the tool is
    absent or rendering fails."""
    import shutil
    import subprocess
    tool = shutil.which("magick") or shutil.which("convert")
    if not tool:
        return False
    try:
        r = subprocess.run(
            wallpaper_convert_cmd(tool, str(dest), title, subtitle),
            capture_output=True, timeout=20)
        return r.returncode == 0 and dest.is_file()
    except (OSError, subprocess.SubprocessError):
        return False


def write_seat_config(config_dir: Path) -> None:
    """Generate the full seat desktop shell. `config_dir` is the labwc config
    dir ($INSTALL_DIR/labwc); the waybar config is written to its sibling
    $INSTALL_DIR/waybar. Regenerated each shell start so newly installed tools
    are picked up on restart. Every launch line is command-v-guarded, so a host
    missing waybar/nwg-*/swaybg still gets a working (if barer) session."""
    config_dir.mkdir(parents=True, exist_ok=True)
    waybar_dir = config_dir.parent / "waybar"
    waybar_dir.mkdir(parents=True, exist_ok=True)

    import socket
    term = pick_terminal()
    launcher = pick_launcher()
    file_mgr = pick_file_manager()
    browser = pick_browser()
    entries = scan_desktop_entries()

    cfg_json, style = build_waybar_config(launcher)
    (waybar_dir / "config").write_text(cfg_json)
    (waybar_dir / "style.css").write_text(style)
    dock_json, dock_style = build_waybar_dock(launcher, term, file_mgr, browser)
    (waybar_dir / "dock-config").write_text(dock_json)
    (waybar_dir / "dock-style.css").write_text(dock_style)

    # bginfo-style wallpaper: hostname + IP + OS baked into the background.
    subtitle = "\n".join(x for x in (_primary_ip(), _os_pretty()) if x)
    wp = config_dir.parent / "wallpaper.png"
    wallpaper = str(wp) if build_wallpaper(wp, socket.gethostname(), subtitle) else ""

    auto = config_dir / "autostart"
    auto.write_text(build_autostart(str(waybar_dir / "config"),
                                    str(waybar_dir / "style.css"),
                                    str(waybar_dir / "dock-config"),
                                    str(waybar_dir / "dock-style.css"),
                                    wallpaper))
    auto.chmod(0o755)
    (config_dir / "menu.xml").write_text(
        build_root_menu(entries, term, file_mgr, str(HOME)))
    (config_dir / "rc.xml").write_text(build_labwc_rc(launcher, term))
    (config_dir / "environment").write_text(build_labwc_environment())


def build_selkies_cmd(cfg: dict, internal_port: int, control_port: int) -> tuple[list[str], dict]:
    """argv + env for the selkies process (run through selkies_launcher.py,
    which forces a loopback bind). Secrets travel via env, never argv.

    internal_port: dynamically allocated loopback port for selkies<->gateway.
    control_port: dynamically allocated control port (independent of internal_port).

    Mirror mode queries the live X display and may raise (Xlib connection/
    auth errors) — the supervisor catches and reports via heartbeat.
    """
    install = Path(cfg["install_dir"])
    s = cfg.get("stream_settings", {})

    env = {
        "HOME": str(HOME),
        "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR",
                                          f"/run/user/{os.getuid()}"),
        "LD_LIBRARY_PATH": str(install / "lib"),   # libva/libwayland shim
        "PYTHONNOUSERSITE": "1",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        # Upload target; must match the gateway's /files dir (downloads).
        "FILE_MANAGER_PATH": os.environ.get("FILE_MANAGER_PATH",
                                            str(HOME / "Downloads")),
    }

    cmd = [
        str(install / "venv/bin/python"),
        str(install / "selkies_launcher.py"),
        f"--port={internal_port}",
        f"--control-port={control_port}",
        "--encoder=x264enc",          # pixelflux switches to VAAPI/NVENC itself
        f"--framerate={s.get('framerate', 60)}",
        "--mode=websockets",
        # Second screen: upstream's Wayland path captures every display at
        # offset 0,0 on a single-output compositor (mirror, broken input);
        # the X11 path would xrandr-resize the REAL display in mirror mode.
        # Server rejects display2 clients with a clear message.
        "--second-screen=false",
    ]
    if cfg.get("mode") == "seat":
        # Steers WAYLAND_DISPLAY for selkies' helper tools (wl-copy/wl-paste
        # clipboard, wlr-randr DPI) — the compositor's own bind is independent,
        # so the supervisor verifies the actual socket and corrects this.
        cmd.append(f"--wayland-socket-index={cfg.get('seat_socket_index', 1)}")

    dri = pick_dri_node()
    if dri:
        cmd.append(f"--dri-node={dri}")

    if cfg.get("mode") == "seat":
        env["PIXELFLUX_WAYLAND"] = "true"
        if dri:
            env["DRINODE"] = dri
        monitor = resolve_monitor_source()
    else:  # mirror
        env["DISPLAY"] = cfg["display"]
        xauth = _find_xauthority(cfg)
        if xauth:
            env["XAUTHORITY"] = xauth
        w, h = query_display_geometry(cfg["display"], xauth)
        cmd += ["--is-manual-resolution-mode=true",
                f"--manual-width={w}", f"--manual-height={h}"]
        monitor = resolve_monitor_source()

    if monitor:
        env["SELKIES_AUDIO_ENABLED"] = "true"
        cmd.append(f"--audio-device-name={monitor}")
    else:
        env["SELKIES_AUDIO_ENABLED"] = "false"

    return cmd, env


def build_waybar_config(launcher: str) -> tuple:
    """(config_json, style_css) for the top panel. `tray` is waybar's built-in
    StatusNotifier host — JetBrains Toolbox and other SNI apps dock there."""
    menu_cmd = launcher or "true"
    # Open windows live on the bottom dock's wlr/taskbar, so the top bar is just
    # launcher + clock + indicators/tray (GNOME-like).
    config = {
        "layer": "top", "position": "top", "height": 32,
        "modules-left": ["custom/menu"],
        "modules-center": ["clock"],
        "modules-right": ["tray", "pulseaudio", "network"],
        "custom/menu": {"format": "  Apps", "on-click": menu_cmd, "tooltip": False},
        "clock": {"format": "{:%a %d %b  %H:%M}"},
        "tray": {"spacing": 8, "icon-size": 18},
        "pulseaudio": {"format": "{icon} {volume}%",
                       "format-muted": "muted",
                       "format-icons": ["", "", ""],
                       "on-click": "pavucontrol"},
        "network": {"format-wifi": "{essid}", "format-ethernet": "wired",
                    "format-disconnected": "offline"},
    }
    style = (
        '* { font-family: "Noto Sans", sans-serif; font-size: 13px; }\n'
        "window#waybar { background: #1d2433; color: #e6e9ef; }\n"
        "#custom-menu { padding: 0 14px; background: #2b3650; color: #ffffff; }\n"
        "#clock, #pulseaudio, #network, #tray { padding: 0 10px; }\n"
    )
    return json.dumps(config, indent=2), style


BROWSERS = ("google-chrome", "chromium", "chromium-browser", "firefox")


def pick_browser() -> str:
    """First GUI browser present on the host. Empty if none."""
    import shutil
    for name in BROWSERS:
        if shutil.which(name):
            return name
    return ""


def browser_launch_cmd(browser: str) -> str:
    """Launch command for the seat browser.

    The seat shares $HOME (and therefore the default browser profile) with any
    other session the user has open — e.g. a VNC desktop on $DISPLAY=:0. Two
    consequences, both of which made the dock's Web button open in the wrong
    session:

    1. Single-instance routing: a browser already running in the :0 session
       owns the profile's singleton lock, so a plain launch here just asks THAT
       instance to open a window — on :0. A dedicated per-seat profile dir
       (--user-data-dir / --profile) gives the seat its own instance.
    2. Display: Chrome defaults to the X11 backend and $DISPLAY is the VNC
       server, so even a fresh instance lands on :0. --ozone-platform=wayland
       binds it to the labwc seat instead. (Firefox follows MOZ_ENABLE_WAYLAND
       from the labwc environment file.)
    """
    if not browser:
        return ""
    if "chrom" in browser:  # google-chrome, chromium, chromium-browser
        prof = HOME / ".config" / "styx-seat-browser"
        return f"{browser} --ozone-platform=wayland --user-data-dir={prof}"
    if "firefox" in browser:
        prof = HOME / ".config" / "styx-seat-firefox"
        return f"firefox --no-remote --profile {prof}"
    return browser


def build_waybar_dock(launcher: str, term: str, file_mgr: str,
                      browser: str) -> tuple:
    """(config_json, style_css) for a second waybar at the BOTTOM, used as a
    dock: pinned launch buttons + wlr/taskbar icons of open windows. Pure
    wlroots (no sway IPC), so — unlike nwg-dock — it runs under labwc."""
    mods: dict = {}
    pins: list = []

    def pin(key: str, label: str, cmd: str) -> None:
        if cmd:
            name = f"custom/{key}"
            pins.append(name)
            mods[name] = {"format": label, "on-click": cmd, "tooltip": False}

    pin("apps", "Apps", launcher)
    pin("files", "Files", f"{file_mgr} {HOME}" if file_mgr else "")
    pin("web", "Web", browser_launch_cmd(browser))
    pin("term", "Term", term)
    config = {
        "layer": "top", "position": "bottom", "height": 48, "margin-bottom": 6,
        "modules-left": [], "modules-center": pins + ["wlr/taskbar"],
        "modules-right": [],
        "wlr/taskbar": {"format": "{icon}", "icon-size": 32,
                        "on-click": "activate", "tooltip-format": "{title}"},
        **mods,
    }
    style = (
        '* { font-family: "Noto Sans", sans-serif; font-size: 13px; }\n'
        "window#waybar { background: transparent; }\n"
        "#taskbar, #custom-apps, #custom-files, #custom-web, #custom-term {\n"
        "  background: #1d2433; color: #e6e9ef; border-radius: 12px;\n"
        "  padding: 2px 12px; margin: 4px 4px; }\n"
        "#taskbar button { padding: 0 6px; }\n"
        "#taskbar button.active { background: #2b3650; border-radius: 8px; }\n"
    )
    return json.dumps(config, indent=2), style


def build_labwc_rc(launcher: str, term: str) -> str:
    """labwc keybinds: Super+D / Super opens the launcher, Super+Enter a
    terminal. `launcher` empty -> bound to `true` (no-op)."""
    launch = launcher or "true"
    term = term or "true"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<labwc_config>
  <theme><cornerRadius>4</cornerRadius></theme>
  <keyboard>
    <keybind key="W-d"><action name="Execute" command="{launch}"/></keybind>
    <keybind key="Super_L"><action name="Execute" command="{launch}"/></keybind>
    <keybind key="W-Return"><action name="Execute" command="{term}"/></keybind>
    <keybind key="A-Tab"><action name="NextWindow"/></keybind>
  </keyboard>
</labwc_config>
"""


def build_labwc_environment() -> str:
    """labwc `environment` file — exported for the whole seat session so GTK/Qt
    apps render dark. Affects theming only, not config paths."""
    return ("GTK_THEME=Adwaita-dark\n"
            "XCURSOR_THEME=Adwaita\n"
            "XCURSOR_SIZE=24\n"
            "QT_QPA_PLATFORM=wayland;xcb\n"
            "QT_STYLE_OVERRIDE=Adwaita-Dark\n"
            "MOZ_ENABLE_WAYLAND=1\n"
            "XDG_CURRENT_DESKTOP=labwc:wlroots\n")


def build_autostart(waybar_config: str, waybar_style: str,
                    dock_config: str, dock_style: str,
                    wallpaper: str = "") -> str:
    """labwc autostart: wallpaper, dark-mode push, portal, top panel, bottom
    dock — each guarded by `command -v` so a missing tool is silently skipped.
    The dock is a second waybar (bottom), not nwg-dock (which is sway-only and
    fatals under labwc). waybar instances get explicit -c/-s paths (NOT
    XDG_CONFIG_HOME) so host apps keep their own ~/.config. `wallpaper` (a PNG
    with the bginfo label) is shown when set; otherwise a flat colour."""
    bg = (f'swaybg -i "{wallpaper}" -m fill &' if wallpaper
          else 'swaybg -c "#1d2433" &')
    return "\n".join([
        "#!/bin/sh",
        "# generated by styx agent — regenerated each seat start; do not edit",
        f"command -v swaybg >/dev/null && {bg}",
        "if command -v gsettings >/dev/null; then",
        "  gsettings set org.gnome.desktop.interface color-scheme 'prefer-dark' 2>/dev/null",
        "  gsettings set org.gnome.desktop.interface gtk-theme 'Adwaita-dark' 2>/dev/null",
        "  gsettings set org.gnome.desktop.interface icon-theme 'Adwaita' 2>/dev/null",
        "  gsettings set org.gnome.desktop.interface cursor-theme 'Adwaita' 2>/dev/null",
        "fi",
        "# xdg portals (frontend + gtk backend) live in libexec, not on PATH;",
        "# they provide org.freedesktop.portal.Settings so GTK4/browsers go dark.",
        "for d in /usr/libexec /usr/lib/x86_64-linux-gnu/xdg-desktop-portal"
        " /usr/lib/xdg-desktop-portal /usr/lib; do",
        '  if [ -x "$d/xdg-desktop-portal" ]; then "$d/xdg-desktop-portal" & break; fi',
        "done",
        "for d in /usr/libexec /usr/lib/x86_64-linux-gnu/xdg-desktop-portal"
        " /usr/lib/xdg-desktop-portal /usr/lib; do",
        '  if [ -x "$d/xdg-desktop-portal-gtk" ]; then "$d/xdg-desktop-portal-gtk" &'
        " break; fi",
        "done",
        f'command -v waybar >/dev/null && waybar -c "{waybar_config}" '
        f'-s "{waybar_style}" &',
        f'command -v waybar >/dev/null && waybar -c "{dock_config}" '
        f'-s "{dock_style}" &',
        "",
    ])
