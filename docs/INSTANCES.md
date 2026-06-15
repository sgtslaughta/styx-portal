# Instances

An **instance** is a containerized desktop (or app) you launch from a **template**
and use in your browser. It's the core unit of Styx Portal: each instance is a
Docker container running a streaming desktop, reachable at its own subdomain, with
its data persisted in a Docker volume.

## What an instance is

- **A Docker container** created from a template's image, started on the host the
  portal runs on.
- **Streamed to your browser** — the container runs a full Linux desktop and serves
  a [Selkies](https://github.com/selkies-project) WebRTC stream that renders in a
  browser tab. No VNC client, no extra software.
- **Persistent** — a named Docker volume (mounted at `/config`) survives stop,
  restart, and rebuild, so your home directory and installed apps stick around.
- **Isolated** — each user's instances run on their own private Docker network.

## How it works

When you launch an instance, the backend:

1. **Pulls the image** (if not already cached), streaming progress to the UI.
2. **Creates the volumes** named for this instance (e.g. `<id>-home` → `/config`).
3. **Creates the container** named `selkies-<subdomain>` with the template's image,
   environment, resource limits, and security settings. It injects
   `PIXELFLUX_WAYLAND=true` (and `AUTO_GPU=true` when GPU is enabled).
4. **Starts it** and writes a **Traefik** route: `https://<subdomain>.<domain>` →
   `<protocol>://selkies-<subdomain>:<internal_port>` (default `https` / `3001`).
5. Your browser opens that subdomain and **Selkies streams the desktop** over WebRTC.

```
browser ──https──▶ Traefik (TLS edge) ──▶ selkies-<subdomain>:3001 (Selkies WebRTC)
                                                  │
                                          /config  (persistent volume)
```

Idle instances are managed by `session_config`: after `idle_timeout` of no activity
plus a `grace_period`, the instance is auto-stopped (configurable per template).

## linuxserver.io integration

Styx Portal is built around **[linuxserver.io](https://www.linuxserver.io/)'s
`baseimage-selkies`** images. Every bundled template uses
`ghcr.io/linuxserver/baseimage-selkies` (or an image derived from it), and the
portal assumes that image family's conventions throughout:

| Convention | Where it comes from | Used for |
|------------|---------------------|----------|
| **`PUID` / `PGID`** (default `1000`) | linuxserver.io base images | Run the desktop as your uid/gid; correct file ownership in `/config` |
| **`/config` volume** | linuxserver.io persistence convention | Home directory + app data that survives rebuilds |
| **Port `3001`, HTTPS** | `baseimage-selkies` serves Selkies here | Traefik routes the browser stream to it |
| **`AUTO_GPU=true`** | linuxserver.io GPU auto-detect | Picks up host NVIDIA/Intel/AMD GPUs |

Because of this, **linuxserver.io selkies images (and images built on top of them)
are the supported, batteries-included way to run instances.** The bundled
templates — Blank, XFCE Desktop, Developer Workstation, Gaming — are all of this
family. You can extend them or add your own that derive from `baseimage-selkies`
and everything (streaming, screenshots, GPU, persistence) just works.

## Using images from a registry — important caveat

A template's `image` can point at **any** container image from any registry
(GHCR, Docker Hub, `lscr.io`, a private registry). **But the portal does not
validate that the image is Selkies-based, and only Selkies-based images can be
streamed.**

!!! warning "Not every registry container will work as an instance"
    The portal expects the container to serve a **Selkies web UI** on its
    `internal_port` (default `3001`, HTTPS). If you point a template at an image
    that is **not** Selkies-based — a plain `nginx`, a bare Ubuntu, a generic app
    container, or another remote-desktop stack that isn't Selkies — the instance
    will **start** (Docker shows it "running") but:

    - the browser tab shows **502 Bad Gateway / SSL error** instead of a desktop
      (Traefik is routing to a Selkies stream that isn't there),
    - the **thumbnail/screenshot stays blank** (the capture probe looks for the
      Selkies canvas and times out),
    - **idle detection is unreliable** (it relies on the browser's keepalive,
      which never connects).

    There is no health check that catches this — the failure is silent. **If you
    want a desktop you can stream, use a `linuxserver.io baseimage-selkies` image
    or one derived from it.** Non-Selkies images are only suitable if you've added
    your own Selkies layer that serves the expected web UI on the configured port.

If you must use a non-default image, set `internal_port` / `internal_protocol` to
whatever Selkies-compatible endpoint it actually serves — but the image still has
to speak the Selkies streaming protocol for the browser view to work.

## Template fields

Templates are JSON (seeded from `templates/*.json`, editable in the admin UI). The
fields that shape an instance:

| Field | Default | What it controls |
|-------|---------|------------------|
| `image` | — | Container image (registry path). **Must be Selkies-based to stream.** |
| `internal_port` | `3001` | Port the container serves the Selkies UI on; Traefik routes here |
| `internal_protocol` | `https` | `https` for Selkies (`http` only if your image serves plain HTTP) |
| `env_vars` | `{}` | Environment injected into the container (`PUID`, `PGID`, encoder opts, …) |
| `volumes` | `[]` | Persistent named volumes, e.g. `{"name": "{instance_id}-home", "mount": "/config"}` |
| `memory_limit` / `cpu_limit` | none | Docker resource caps (`2g`, `8.0` …) |
| `shm_size` | none | Shared memory (GUI apps need this, e.g. `512m`) |
| `gpu_enabled` / `gpu_count` | `false` / `1` | GPU passthrough (auto-detects NVIDIA/Intel/AMD) |
| `cap_add` / `security_opt` | `[]` | Linux capabilities / security options (defaults run unprivileged) |
| `session_config` | 30m idle / 5m grace / stop | Idle timeout, grace period, max session, never-timeout |
| `tls_skip_verify` | `false` | Skip cert check when routing to the container's HTTPS port |
| `dind`, `privileged`, `devices`, `tmpfs`, `entrypoint`, `command` | off / none | Advanced container options |

`session_config` example:

```json
{
  "idle_timeout": "30m",
  "grace_period": "5m",
  "timeout_action": "stop",
  "never_timeout": false,
  "max_session_duration": null
}
```

## Related

- **[GPU](GPU.md)** — enabling GPU acceleration for instances.
- **[Workstations](WORKSTATIONS.md)** — streaming a *physical* machine (also Selkies-based) rather than a container.
- **[Admin](ADMIN.md)** — managing templates, users, and quotas.
