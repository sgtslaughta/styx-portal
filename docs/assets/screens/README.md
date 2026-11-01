# Screenshots

Generated, demo data only (users `admin`/`alice`/`bob`, workstations `studio-pc`, `render-box`, `gpu-lab`, `laptop-dev`, domain `styx.example.com`).

Regenerate everything: `e2e/docs-shots/run.sh` (builds the isolated `styx-e2e` compose stack, seeds it through the real API, captures with Playwright, tears down; `KEEP=1` keeps the stack). Pillow is used to shrink PNGs over 1.2 MB.
Code: `e2e/tests/docs-shots.spec.ts` (captures), `e2e/docs-shots/seed.ts` (demo data), `scenes.ts` (rendered desktops), `hero.ts` (hero composite).

`ui-*.png` are 1440x900 @2x dark UI captures; `hero-*.png` are 2400x1400 composites (the same capture in a browser frame over the brand backdrop).

| File | Kind |
| --- | --- |
| `ui-login`, `ui-login-2fa` | real page; 2FA challenge answered by a mocked login response |
| `ui-desktops`, `ui-workstations`, `ui-dashboard-light`, `hero-dashboard` | real UI; instances are mocked (no container runtime images offline); workstations are real rows (enroll, heartbeat, thumbnail via the API) with self-rendered desktop thumbnails |
| `ui-desktop-launch`, `ui-templates` | real |
| `ui-services`, `ui-service-form`, `ui-shell-dock`, `hero-services` | real UI; dock icons and the framed app content are stand-ins |
| `ui-admin-users`, `-groups`, `-settings`, `-sso`, `ui-health`, `ui-workstation-settings`, `ui-enroll`, `hero-admin` | real (enroll token, pin and address are replaced by placeholders before capture) |
