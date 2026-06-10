# Admin Guide

User management, SSO setup, templates, and operations for Styx Portal administrators.

## User Management

### Inviting Users

1. Navigate to **System → Users**
2. Click **Generate Invite Link**
3. Copy the link — it's single-use and valid for 72 hours
4. Share securely (email, encrypted message, etc.)

When the user clicks the link, they create their account and are automatically added to the portal.

### User Roles

- **User:** Standard access. Can create instances from templates, manage their own instances only.
- **Admin:** Full access. Can manage users, templates, SSO providers, view audit log, manage quotas, and access Health diagnostics.

Admins can promote/demote users in the **Users** panel.

## Physical Workstations

Styx Portal can stream physical Linux machines on the local network alongside container instances.

### Getting Started

1. Navigate to **System → Workstations**
2. Click **Enroll workstation**
3. Copy the one-liner command and run it on a physical Linux machine
4. The machine will appear as **Online** within 60 seconds and users can connect to stream its desktop

### Setup Requirements

- **Network:** Workstations must reach the portal's LAN address (`SERVER_LAN_URL`). Set this to your local IP/hostname before enrolling.
- **Workstation OS:** Linux with X11 or Wayland, Python 3, glibc ≥ 2.17, audio stack (PipeWire/PulseAudio)
- **Optional:** GPU drivers (NVIDIA or VAAPI) for hardware video encoding. Without them, CPU encoding (x264) is used.

### Admin Panel

In **System → Workstations**, you can:
- **Enroll:** Mint single-use tokens (valid 24 hours) with enrollment commands
- **Monitor:** See status (online/offline/pending/revoked), last heartbeat, IP address, GPU info
- **Configure:** Adjust encoder, framerate, bitrate per workstation
- **Access control:** Restrict which users can connect to each workstation
- **Revoke/Purge:** Stop streaming gracefully (Revoke) or remove from portal (Purge)

### Troubleshooting

See **[Physical Workstation Streaming Guide](./WORKSTATIONS.md)** for enrollment error codes (E00–E08), diagnostics, and solutions.

---

## SSO / OAuth Setup

Styx Portal supports federated authentication via OIDC and OAuth2 providers.

### Adding a Provider

1. Navigate to **System → Settings → OAuth Providers** (admin only)
2. Click **Add Provider**
3. Enter:
   - **Name:** display name (e.g., "Google", "GitHub")
   - **Issuer URL:** OIDC discovery endpoint (e.g., `https://accounts.google.com` for Google)
   - **Client ID:** from your OAuth app registration
   - **Client Secret:** from your OAuth app registration
4. Configure options:
   - **Trust Email:** if true, use the email from the IdP without requiring verification (only applies to login/signup; account linking always requires verified email)
   - **Allow Signup:** if true, users with verified email can sign up directly; if false, they must match an existing user or invite
   - **Auto-Promote Admins:** if true, users in the provider's admin group (claims) are automatically promoted to admin; if false, the claim is noted in audit but requires manual promotion

### OAuth Redirect URIs

Register these with your OAuth provider:

- **Login:** `https://<DOMAIN>/api/auth/oauth/<provider_name>/callback`
- **Account Linking:** `https://<DOMAIN>/api/auth/link/<provider_name>/callback`

Replace `<DOMAIN>` with your portal domain and `<provider_name>` with the provider slug (lowercase, URL-safe).

### Account Linking

Logged-in users can link their account to a provider under **System → Connected Accounts**:
- Link: Adds a provider identity to their account
- Unlink: Removes a provider identity (cannot unlink the only login method)

**Security:** Linking always requires a verified email address, regardless of the provider's `trust_email` setting.

## Templates

Templates define the images, resources, and capabilities for launched instances.

### Creating a Template

1. Navigate to **System → Templates**
2. Click **Create Template**
3. Configure:
   - **Name & Image:** template name and Docker image URI
   - **Resources:** memory (MB), CPU (shares), shared memory (MB)
   - **GPU:** enable and set count if GPU acceleration is needed
   - **Timeout:** idle timeout, grace period, action (stop/destroy)
   - **Environment:** template-level environment variables
   - **Capabilities & Overrides:** (admin-only) fine-tune container security

### Admin-Only Fields

These require admin privileges to set:

- **cap_add:** Additional Linux capabilities (default `[]`). **Selkies / LinuxServer
  desktop images need a capability set to boot** — their s6 init runs `chown` and
  drops privileges, which `cap_drop: ALL` blocks (symptom: `chown ... Operation not
  permitted`, `s6-applyuidgid: fatal`). Give such templates at least
  `CHOWN, SETUID, SETGID, DAC_OVERRIDE, FOWNER` (the bundled seed templates ship the
  full standard set).
- **security_opt:** Security options (default `[]`). **GPU desktop templates that do
  framebuffer capture (Selkies/pixelflux) need `seccomp=unconfined`** — the default
  seccomp profile blocks syscalls the capture path uses (symptom: a `pixelflux`/Rust
  `PermissionDenied` panic and a black screen with "websocket disconnected"). The seed
  templates ship `["seccomp=unconfined","apparmor=unconfined"]`. The rest of the
  isolation (non-root backend, socket-proxy, per-user networks, audit, quotas) still
  applies; only the desktop container's own seccomp is relaxed.
- **tls_skip_verify:** bool. Set true if the template serves self-signed HTTPS
  internally — **all Selkies desktop images do**, so every `https` template needs this
  (else Traefik fails cert verification and the instance 502s). Seed templates set it.

### DinD (Docker-in-Docker) Templates

Templates that include Docker-in-Docker **must:**
- Be marked DinD-capable (a checkbox in the template editor)
- Have memory and CPU limits (enforced on creation)
- Be admin-only (non-admins cannot launch)
- Are logged in the audit log

## Instance Quotas

### Per-User Limit

Set the max concurrent instances per non-admin user:
```bash
MAX_INSTANCES_PER_USER=3  # in .env
```

- `0` = unlimited
- Admins are always exempt
- Default: `3`

Check the setting in **System → Settings**.

## Audit Log

All security-relevant actions are logged:

- **Auth:** login success/failure, logout, refresh-token reuse
- **Users:** role changes, account linking/unlinking, invites created
- **Providers:** OAuth provider CRUD, configuration changes
- **Instances:** creation, deletion, resource overrides
- **DinD:** privileged template launches

### Viewing the Audit Log

**API:**
```bash
curl -H "Cookie: auth_token=<your-token>" \
  https://your.domain.com/api/audit?page=1&limit=50
```

**UI:**
Admin UI viewer coming in a future release. For now, use the API endpoint or the **System → Health** page for system diagnostics and status.

## Health Monitoring

### Diagnostics Endpoint

Navigate to **System → Settings → Health** to view:
- Docker engine status and version
- Database writability
- Traefik routes volume status
- Disk usage percentage
- GPU availability (if applicable)

Each check displays latency (milliseconds) and remediation hints for failures.

### Health History

The Health page includes a 24-hour status timeline per check, helping identify intermittent issues.

## Instance Management

### User Instance Quotas

Enforce per-user concurrent instance limits:
1. Navigate to **System → Settings**
2. Set **Max Instances Per User** (0 = unlimited; default 3)
3. Admins are exempt

Non-admins who hit the limit see an error message when attempting to launch; they must stop an existing instance first.

### Resource Overrides (Admin)

On instance launch, admins can override template defaults:
- Memory, CPU, shared memory
- Environment variables
- Capabilities (if the template allows overrides)

## Operations Checklist

- [ ] Invited all expected users and confirmed account creation
- [ ] Configured at least one OAuth provider (if using SSO)
- [ ] Set up GPU templates (if GPU hardware is available)
- [ ] Reviewed audit log for any suspicious activity
- [ ] Configured instance quotas per your usage policy
- [ ] Tested Health diagnostics are all green
- [ ] Backed up `secrets.json` from the data volume
- [ ] Verified DinD templates have memory/CPU limits
