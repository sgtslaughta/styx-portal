# Upgrade

Move to a new Styx release and roll back if needed.

## Compose

Database migrations run automatically on boot.

```bash
# .env
STYX_TAG=2.7.0     # the release you want
docker compose pull && docker compose up -d
```

To roll back, set `STYX_TAG` to the previous version and repeat. Back up `secrets.json` and the data volume first ([Production](production.md#backups)). Without pinning, `latest` tracks the newest release.

After a portal upgrade, rebuild the agent artifacts so workstations get matching wheels:

```bash
scripts/build_agent_artifacts.sh ./data/artifacts
```

## Kubernetes

Bump the `newTag` values in `deploy/k8s/kustomization.yaml`, then:

```bash
kubectl apply -k deploy/k8s
kubectl -n styx rollout status deploy/backend deploy/frontend
```

Roll back by restoring the old tag. Restore the database from `styx-backups` only if a migration went wrong ([Kubernetes](kubernetes.md#backup-restore)).

## Workstation agents

Upgrade in place with no enrollment token and no package installs:

```bash
curl -fsSL https://styx.example.com/api/enroll/script | bash -s -- --upgrade --server https://styx.example.com
```

Roll back with `styx_agent.py rollback` ([details](workstations-enroll.md#upgrade-and-rollback)). Restarting the agent closes apps running in the workstation's seat, so schedule upgrades when nobody is connected.

## Versions

Releases follow semantic versioning and are published by semantic-release; the [changelog](https://github.com/sgtslaughta/styx-portal/blob/main/CHANGELOG.md) lists every change.
