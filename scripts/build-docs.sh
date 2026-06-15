#!/usr/bin/env sh
# Build the Zensical documentation site for publishing to GitHub/GitLab Pages.
#
# Single source of truth for the docs build, called by BOTH .github/workflows/docs.yml
# and the GitLab `pages` job — keeps the two pipelines in parity (no drift).
#
# Two things this script guarantees that a bare `zensical build` does not:
#   1. Pinned Zensical version. The Pages job is privileged (pages:write + OIDC
#      id-token), so an unpinned `pip install zensical` is a supply-chain risk.
#      Bump ZENSICAL_VERSION deliberately (Renovate/Dependabot).
#   2. Internal specs/plans are stripped. Zensical 0.0.45 has no config-level path
#      exclude, and docs/superpowers/** (brainstorm specs + implementation plans)
#      must never be published. We prune it from the built site post-build. This
#      survives future superpowers skill runs that recreate docs/superpowers/.
set -eu

ZENSICAL_VERSION="0.0.45"

pip install "zensical==${ZENSICAL_VERSION}"
zensical build --clean
rm -rf site/superpowers
