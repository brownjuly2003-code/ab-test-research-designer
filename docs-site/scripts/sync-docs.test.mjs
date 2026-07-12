import assert from 'node:assert/strict';
import test from 'node:test';

import { rewriteLinks } from './sync-docs.mjs';

const SITE_BASE = '/ab-test-research-designer';
const REPO_BLOB_BASE = 'https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main';

test('rewrites docs markdown links to generated guide pages', () => {
  const markdown = '[Deploy](docs/DEPLOY.md) and [Release notes](docs/RELEASE_NOTES_v1.1.0.md)';

  assert.equal(
    rewriteLinks(markdown, 'README.md'),
    `[Deploy](${SITE_BASE}/guides/deploy/) and [Release notes](${SITE_BASE}/guides/release_notes_v1-1-0/)`,
  );
});

test('rewrites docs demo asset links to public demo assets', () => {
  assert.equal(
    rewriteLinks('[Sample](docs/demo/sample-project.json)', 'README.md'),
    `[Sample](${SITE_BASE}/demo/sample-project.json)`,
  );
});

test('rewrites docs demo image links to public demo assets', () => {
  assert.equal(
    rewriteLinks('![Wizard overview](docs/demo/wizard-overview.png)', 'README.md'),
    `![Wizard overview](${SITE_BASE}/demo/wizard-overview.png)`,
  );
});

test('rewrites root README and changelog links to guide pages', () => {
  assert.equal(
    rewriteLinks('[Readme](README.md) and [Changes](CHANGELOG.md)', 'docs/DEPLOY.md'),
    `[Readme](${SITE_BASE}/guides/overview/) and [Changes](${SITE_BASE}/guides/changelog/)`,
  );
});

test('rewrites internal plan links to GitHub blob URLs, not guide pages', () => {
  // docs/plans/** is not on the public allowlist (audit F-08): the link must
  // leave the docs site and point at the repository instead.
  assert.equal(
    rewriteLinks('[Plan](docs/plans/2026-04-22-public-api-report.md)', 'README.md'),
    `[Plan](${REPO_BLOB_BASE}/docs/plans/2026-04-22-public-api-report.md)`,
  );
});

test('rewrites relative repo files to GitHub blob URLs', () => {
  assert.equal(
    rewriteLinks('[Fly](fly.toml)', 'README.md'),
    `[Fly](${REPO_BLOB_BASE}/fly.toml)`,
  );
});

test('leaves absolute URLs unchanged', () => {
  const markdown = '[GitHub](https://github.com/brownjuly2003-code/ab-test-research-designer)';

  assert.equal(rewriteLinks(markdown, 'README.md'), markdown);
});

test('rewrites reference-style definitions', () => {
  const markdown = '[Deploy][deploy]\n\n[deploy]: docs/DEPLOY.md';

  assert.equal(rewriteLinks(markdown, 'README.md'), `[Deploy][deploy]\n\n[deploy]: ${SITE_BASE}/guides/deploy/`);
});
