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
  plugins.push(
    ['@semantic-release/changelog', { changelogFile: 'CHANGELOG.md' }],
    ['@semantic-release/exec', { prepareCmd: "printf '%s' \"${nextRelease.version}\" > .release-version" }],
    ['@semantic-release/git', {
      assets: ['CHANGELOG.md'],
      message: 'chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}',
    }],
    '@semantic-release/github',
  );
}

module.exports = {
  branches: ['main', 'master'],
  tagFormat: 'v${version}',
  plugins,
};
