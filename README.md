# Styx Portal
![Styx Portal logo image](./frontend/public/styx_portal_main.jpeg?raw=true "Styx Portal")

> Self-hosted remote-desktop platform — launch containerized desktops and stream
> physical/virtual workstations through the browser.

## Overview

> What is this? Why?

I routinely require access to resources running at home, while not at home, using only a browser.

### Other solutions were lacking:
- Slow or choppy streams
- Undue complexity/overhead
- Paywalls for useful features
- Abandonware
- Freedom to do what I wanted, when I wanted (without reverse engineering)

### My personal requirements:
- Should be easy to use
- Clientless (browser only)
- Fast
- Includes all the nice things (audio, copy/paste, upload/download, SSO, etc)

### What spurred the idea:
Massive shoutout to LinuxServer.io. I discovered their transition away from Kasm Workspaces to a `project selkies`-based image system. Once I saw the performance gain over 'other' options, I knew I had to have it.

### Is it vibe coded?
- Of course it's vibe coded! I don't have months and months to spend grinding! Kidding, not kidding. I have a lot of experience with much of the tech stack involved and needed a solution quickly, so here we are.
- You might disparage anything vibe coded and that is your prerogative, but luckily, you don't have to use it! Fork it and hand jam your own code!

### Is it secure?
- I put a decent amount of thought into making the application as secure as I could. Is it Fort Knox? Not even close. That being said, it should be fine for most people. If you find a security issue, let me know!

> [!CAUTION]
> I highly suggest you do not leave it exposed on the internet — put it behind a CF Application / 2FA! See [Cloudflare Applications](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/).

### Did I run exhaustive tests across every surface?
- No, bugs are likely on the fringes. Make an issue if you hit one.

## Features

- Docker based core
  - Simple `docker compose up -d`
- Linux based workstation agents
  - Connect to physical machines
  - Tested on `Ubuntu 24.04` using `Wayland`
    - Should work on other `Debian` systems
  - No plan for `Windows` or `MacOS` yet, send demand signal if interested
- Basic multi user isolation
- SSO
  - generic OAuth2 (Authentik/Keycloak/Google)
  - GitHub OAuth

## Quickstart

See **[docs/QUICKSTART.md](docs/QUICKSTART.md)**.

## Documentation

Full docs (Zensical site, also published to GitHub/GitLab Pages):

- [Quickstart](docs/QUICKSTART.md)
- [Instances](docs/INSTANCES.md)
- [Workstations](docs/WORKSTATIONS.md)
- [GPU](docs/GPU.md)
- [Admin](docs/ADMIN.md)
- [Production](docs/PRODUCTION.md)
- [Agent Build](docs/AGENT_BUILD.md)
- [CI/CD architecture](docs/CICD.md)

## Development

See **[CLAUDE.md](CLAUDE.md)** for project structure and commands.

## Contributing

This project uses **Conventional Commits** (enforced by commitlint) so releases
and changelogs are automated. Example: `feat(agent): add reconnect backoff`.

## License

<!-- TODO(owner): choose and state a license. -->
