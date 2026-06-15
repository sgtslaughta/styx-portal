// Host-aware semantic-release config (auto-loaded by semantic-release).
//
// GitHub is canonical: it writes/commits CHANGELOG.md and publishes a GitHub
// Release, and writes .release-version for the image-build job to read.
//
// GitLab must NOT commit anything (a CHANGELOG commit would diverge `main` from
// the GitHub mirror). It only creates a tag at the real HEAD — crucially WITHOUT
// a `[skip ci]` commit — plus a GitLab Release. The tag (real commit, not skipped)
// triggers the GitLab tag pipeline that builds the images.
//
// Why a single JS config instead of `--extends ./.releaserc.<host>.json`:
// semantic-release auto-loads `.releaserc.json` as the PRIMARY config, and a
// primary's `plugins` array wins over anything passed via `--extends`. That made
// the host-specific plugin lists silently ineffective. One auto-loaded config
// that branches on the CI host is unambiguous.
const onGitLab = !!process.env.GITLAB_CI;

const plugins = [
  ['@semantic-release/commit-analyzer', { preset: 'conventionalcommits' }],
  ['@semantic-release/release-notes-generator', { preset: 'conventionalcommits' }],
];

if (onGitLab) {
  plugins.push('@semantic-release/gitlab');
} else {
  // GitHub: tag + GitHub Release only — NO commit to main. The MAIN branch
  // ruleset (PR-required) blocks the CI bot from pushing a chore(release)
  // changelog commit, which aborts the release. So we don't use
  // @semantic-release/git/@semantic-release/changelog here; release notes live
  // on the GitHub Releases page. @semantic-release/exec still writes
  // .release-version for the image-build job; core pushes only the tag ref
  // (not refs/heads/main), which the ruleset doesn't gate.
  plugins.push(
    ['@semantic-release/exec', { prepareCmd: "printf '%s' \"${nextRelease.version}\" > .release-version" }],
    '@semantic-release/github',
  );
}

module.exports = {
  branches: ['main', 'master'],
  tagFormat: 'v${version}',
  plugins,
};
