# Troubleshooting

Symptoms first, fixes after. Admin-side causes link to the [Operate](../operate/index.md) pages.

## Sign-in

| Symptom | Cause and fix |
|---|---|
| "Account locked" | Too many wrong passwords. Wait for the lockout (default 15 minutes) or ask an admin to **Unlock** you. |
| Cannot sign in from this network | Your IP address was temporarily banned after repeated failures (default 1 hour). Wait, or ask an admin to lift the ban. |
| Card prompt but no card | Ask an admin to **Reset sign-in card**, then enroll a new one. |
| Card sign-in returns an error 500 | The server's secret changed. Admin must reset your card. See [Users, groups and SSO](../operate/users-groups-sso.md). |
| Logged out when closing the browser | Card sign-ins are session-only by design. |

## Desktops

| Symptom | Cause and fix |
|---|---|
| 502 Bad Gateway or SSL error in the desktop tab | The image is not Selkies-based, or it is still starting. Wait for the status to leave "starting"; admins check the image ([Templates and instances](../operate/templates-instances.md)). |
| Blank thumbnail | Same cause: the capture probe finds no Selkies canvas. |
| Desktop stopped by itself | Idle timeout. Press **I'm here** next time, or ask for a template that never times out. |
| Launch refused | You may have hit the per-user instance cap or the creation rate limit. Stop a desktop first. |

## Workstations

| Symptom | Cause and fix |
|---|---|
| Card says **Offline** | The agent has not sent a heartbeat for 90 seconds. Ask the admin to run `doctor` on the machine ([Enroll workstations](../operate/workstations-enroll.md#diagnostics)). |
| Black screen or "Waiting for stream" | Refresh the tab. If it persists the engine may be restarting; the admin should check `selkies.log`. |
| Laggy, blocky or stuttering | Lower bitrate and framerate in the panel; shrink the window or turn **HiDPI off**; see [Streaming tuning](../operate/streaming-tuning.md). |
| 401 or 403 on `/w/...` | Not signed in (401) or not assigned to this workstation (403). |
| "Session timed out due to inactivity" | Idle timeout. Press **Reconnect**. |
| Clipboard does not paste | Allow the site's Clipboard permission (Chromium) or use the sidebar clipboard panel (Firefox). |

## Apps

| Symptom | Cause and fix |
|---|---|
| Tile red | The service failed its health check; it still opens. Tell your admin. |
| "&lt;app&gt; can't run inside Styx" | The app forbids framing. Use **Open on its own**. |
| Stuck on the wrong app at `/` | A focus app is active. Visit `/_styx/exit`. |
| 403 on a tile | Your group is not allowed for that service. |
