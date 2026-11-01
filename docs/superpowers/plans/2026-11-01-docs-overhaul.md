# Docs overhaul — shared brief (README + Zensical site)

Worktree: /home/user/code/remote-access-docs, branch docs/overhaul (from origin/main).
Three parallel agents: SHOTS (screenshots), GUIDES (README + user + admin), ENG (engineering).
Do not commit/push; the lead reviews and commits. Never touch production
(g.jmolabs.dev, k8s, 192.168.1.x hosts). Never print or embed secrets, real IPs,
real hostnames, real usernames/emails: use demo values (styx.example.com,
alice/bob/admin, 10.0.0.x, "studio-pc", "render-box").

## Audience + voice
- README: product landing page. Hero image, one-line pitch, 4–6 feature highlights with
  screenshots, 60-second quickstart, links into the site. Confident, concrete, no hype words.
- Site: three sections — **Use** (end users), **Operate** (admins/self-hosters),
  **Build** (engineers/contributors). Task-oriented pages; each starts with what you'll
  achieve, prerequisites, then steps; admonitions for gotchas.
- Facts come from the code on origin/main (and CHANGELOG.md, existing docs/*.md). Don't
  invent features. If unsure, read the code; if still unsure, leave `<!-- TODO(verify): … -->`
  and list it in your report.

## Information architecture (zensical.toml nav — GUIDES owns nav edits, ENG sends its list)
- Home (index.md): hero + feature grid (cards) + "choose your path" (Use / Operate / Build)
- Use/: getting-started (sign-in, 2FA matrix card, SSO), desktops (launch/stop instances,
  idle + "I'm here"), workstations (connect, stream panel, clipboard/files/audio, scaling,
  keyboard shortcuts, codecs/HEVC tip), services (proxied apps, shell/dock), troubleshooting
- Operate/: install (compose quickstart), production (TLS, Traefik, backups), kubernetes,
  workstations-enroll (enroll.sh, preflight E01–E08, agent updates), templates & instances,
  services (presets, auth modes, mounts), users-groups-sso, security (brute force, 2FA,
  CSP, CSRF), settings reference (every admin setting), gpu, performance & streaming tuning
  (encoders AV1/HEVC/H.264, bitrate, framerate), monitoring/health, upgrade
- Build/: architecture (diagram: browser → Traefik → backend/frontend → Docker|k8s →
  instances; agent + gateway + selkies + GNOME seat), backend, frontend, agent internals
  (engine, gateway, seat_gnome/labwc, portal, refit/scale, thumbnails), streaming pipeline
  (pixelflux, selkies 2.1, websockets vs webrtc), security model, testing (pytest, vitest,
  e2e, stream A/B harness), CI/CD + releases (semantic-release), contributing, ADRs (existing
  decisions/), upstream contributions (docs/upstream)
- Keep existing pages' content: migrate/merge into the new structure, don't lose facts.
  Old top-level page URLs (QUICKSTART.md etc.) → keep as short redirect stubs linking to the
  new page (no redirect plugin assumed).

## Screenshot spec (SHOTS produces; GUIDES/ENG reference these exact paths)
Output dir: docs/assets/screens/. Two kinds:
- `hero-*.png`: marketing composites, 2400×1400, app captured at 1440×900 @2x inside a
  minimal browser frame (rounded corners, subtle shadow) over the brand backdrop
  (derive colours from frontend theme / frontend/public/styx_portal_main.jpeg).
- `ui-*.png`: plain UI captures 1440×900 @2x, dark theme, for docs pages. Light variants
  only where noted (`-light`).
Shot list (filenames are the contract):
- hero-dashboard.png — home/dashboard with several running desktops + workstations, live thumbnails
- hero-workstation-stream.png — a streamed desktop in the viewer with the side panel open
- hero-services.png — services grid / shell dock
- hero-admin.png — admin settings / health overview
- ui-login.png, ui-login-2fa.png (matrix card prompt)
- ui-desktops.png (instances list), ui-desktop-launch.png (template picker)
- ui-workstations.png (cards with previews), ui-workstation-settings.png (stream settings panel)
- ui-viewer.png (stream + panel), ui-idle-banner.png ("Pausing soon" + I'm here)
- ui-services.png, ui-service-form.png, ui-shell-dock.png
- ui-admin-users.png, ui-admin-groups.png, ui-admin-settings.png, ui-admin-sso.png,
  ui-health.png, ui-templates.png, ui-enroll.png (workstation enrollment / token dialog)
- ui-dashboard-light.png (one light-mode example)
If a shot is impossible (e.g. no streaming source), produce the closest honest substitute,
name it as specified, and say so in the report. Also write docs/assets/screens/README.md
listing each file + how to regenerate (script path).
