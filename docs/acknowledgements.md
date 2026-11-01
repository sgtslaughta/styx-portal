# Acknowledgements

Styx Portal is a thin layer of glue on top of a great deal of other people's work.
The parts that make it feel fast — capture, encoding, the streaming protocol, the
browser client — are not ours. We could not have built this without them.

## The Selkies Project

The streaming heart of Styx is [**Selkies**](https://github.com/selkies-project/selkies)
and its sister libraries from the [Selkies Project](https://github.com/selkies-project):

| Project | What it gives Styx |
|---|---|
| [selkies](https://github.com/selkies-project/selkies) | The stream server and browser client: WebSockets and WebRTC transports, input, clipboard, audio, the side panel, congestion control. Every workstation and desktop stream runs on it. |
| [pixelflux](https://github.com/selkies-project/pixelflux) | Screen capture and hardware encoding — VA-API and NVENC, AV1/HEVC/H.264, zero-copy Wayland capture, the portal capture path our GNOME seat uses. |
| [pcmflux](https://github.com/selkies-project/pcmflux) | Low-latency Opus audio capture and encoding. |

The maintainers have been remarkably generous: issues we filed were answered with
root-cause analysis, measurements and fixes, often within hours, and our patches were
reviewed and merged with care. Some of that shared work:

- **selkies#489** — the still-screen bitrate sawtooth in `CongestionSteer`, fixed upstream
  (`f22ce7562`, `17b2884f6`) with measurements that went well beyond our report.
- **pixelflux#55** — pointer mapping and the missing cursor sprite on scaled GNOME
  outputs, fixed upstream along with a GNOME test rig for Selkies' own suite.
- **pixelflux#58** and **selkies#496** — signalling and cropping AV1 frames that a hardware
  encoder pads (merged), extended upstream to WebKit.

See [Upstream contributions](build/upstream.md) for the patches and their evidence.
If Styx is useful to you, please consider
[starring](https://github.com/selkies-project/selkies) and supporting Selkies.

## LinuxServer.io

Container desktops build on [LinuxServer.io](https://www.linuxserver.io/)'s
[`baseimage-selkies`](https://github.com/linuxserver/docker-baseimage-selkies) and their
long-maintained family of images. Their work made "a desktop in a container" a solved problem.

## Desktop and media stack

- [GNOME](https://www.gnome.org/) / **Mutter** — the headless GNOME seat, its
  ScreenCast and RemoteDesktop APIs, and on-demand Xwayland.
- [PipeWire](https://pipewire.org/) and [xdg-desktop-portal](https://github.com/flatpak/xdg-desktop-portal) — the capture path between the compositor and pixelflux.
- [labwc](https://labwc.github.io/), [nwg-shell](https://nwg-piotr.github.io/nwg-shell/) tools and [Waybar](https://github.com/Alexays/Waybar) — the lightweight seat shell.
- Mesa (VA-API), NVIDIA NVENC and Opus.

## Platform

- [Traefik](https://traefik.io/) — routing, TLS, forward-auth and rate limiting.
- [FastAPI](https://fastapi.tiangolo.com/), [SQLModel](https://sqlmodel.tiangolo.com/), [Pydantic](https://docs.pydantic.dev/), [SQLAlchemy](https://www.sqlalchemy.org/), [Uvicorn](https://www.uvicorn.org/), [Authlib](https://authlib.org/), [PyJWT](https://pyjwt.readthedocs.io/), [argon2-cffi](https://argon2-cffi.readthedocs.io/), [cryptography](https://cryptography.io/), [docker-py](https://docker-py.readthedocs.io/), [HTTPX](https://www.python-httpx.org/).
- [React](https://react.dev/), [Radix UI](https://www.radix-ui.com/) and the [shadcn/ui](https://ui.shadcn.com/) patterns, [Tailwind CSS](https://tailwindcss.com/), [TanStack Query](https://tanstack.com/query), [React Router](https://reactrouter.com/), [Framer Motion](https://motion.dev/), [Lucide](https://lucide.dev/), [Sonner](https://sonner.emilkowal.ski/), [zxcvbn](https://github.com/dropbox/zxcvbn), [Vite](https://vite.dev/).
- [Docker](https://www.docker.com/), [Kubernetes](https://kubernetes.io/) / [k3s](https://k3s.io/), [Cloudflare Tunnel and Realtime TURN](https://developers.cloudflare.com/).
- [Playwright](https://playwright.dev/), [pytest](https://pytest.org/), [Vitest](https://vitest.dev/), [Ruff](https://docs.astral.sh/ruff/), [semantic-release](https://semantic-release.gitbook.io/), and [Zensical](https://zensical.org/) for this site.

Thank you all. Every one of these projects is maintained by people who chose to share
their work — please support them.
