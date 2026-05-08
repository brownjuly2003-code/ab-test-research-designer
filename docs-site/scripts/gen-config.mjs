import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from 'yaml';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(__dirname, '..', '..');
const CONFIG_FILE = join(PROJECT_ROOT, 'app', 'backend', 'app', 'config.py');
const SLACK_MANIFEST = join(PROJECT_ROOT, 'slack', 'app-manifest.yml');
const OUT_FILE = join(__dirname, '..', 'src', 'content', 'docs', 'architecture', 'config.mdx');

function cleanDefault(raw) {
  if (!raw) return 'None';
  return raw
    .trim()
    .replace(/,$/, '')
    .replace(/^["']|["']$/g, '')
    .replace(/\s+/g, ' ');
}

function parseEnvMatrix(source) {
  const rows = new Map();
  const getenvRe = /os\.getenv\(\s*["'](AB_[A-Z0-9_]+)["']\s*(?:,\s*([^)\n]+))?\)/g;
  const helperRe = /_read_(?:csv|int|bool|float)_env\(\s*["'](AB_[A-Z0-9_]+)["']\s*,\s*([^)]+)\)/g;
  let match;
  while ((match = getenvRe.exec(source))) {
    rows.set(match[1], cleanDefault(match[2] || 'None'));
  }
  while ((match = helperRe.exec(source))) {
    rows.set(match[1], cleanDefault(match[2]));
  }
  return [...rows.entries()]
    .map(([name, defaultValue]) => ({ name, defaultValue }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function groupForEnv(name) {
  if (name.includes('SLACK')) return 'Slack';
  if (name.includes('TOKEN') || name.includes('KEY')) return 'Auth';
  if (name.includes('DB') || name.includes('DATABASE') || name.includes('SQLITE')) return 'Data store';
  if (name.includes('RATE') || name.includes('BODY') || name.includes('FAILURE')) return 'Runtime guard';
  if (name.includes('LLM')) return 'LLM';
  if (name.includes('HF') || name.includes('SNAPSHOT') || name.includes('SEED')) return 'Snapshot and seed';
  if (name.includes('CORS') || name.includes('HOST') || name.includes('PORT')) return 'HTTP';
  return 'Application';
}

async function readSlackManifest() {
  if (!existsSync(SLACK_MANIFEST)) return null;
  const manifest = parse(await readFile(SLACK_MANIFEST, 'utf8')) || {};
  const command = manifest.features?.slash_commands?.[0] || {};
  return {
    name: manifest.display_information?.name || 'Slack app',
    command: command.command || 'none',
    installPath: '/slack/install',
    commandUrl: command.url || 'none',
    interactiveUrl: manifest.settings?.interactivity?.request_url || 'none',
    eventsUrl: manifest.settings?.event_subscriptions?.request_url || 'none',
    scopes: manifest.oauth_config?.scopes?.bot || [],
  };
}

async function main() {
  const source = existsSync(CONFIG_FILE) ? await readFile(CONFIG_FILE, 'utf8') : '';
  const envRows = parseEnvMatrix(source);
  const slack = await readSlackManifest();

  const envTable = envRows
    .map((item) => `| \`${item.name}\` | ${groupForEnv(item.name)} | \`${item.defaultValue}\` |`)
    .join('\n');
  const slackRows = slack
    ? [
        `| App name | \`${slack.name}\` | \`${relative(PROJECT_ROOT, SLACK_MANIFEST).replace(/\\/g, '/')}\` |`,
        `| Slash command | \`${slack.command}\` | \`${slack.commandUrl}\` |`,
        `| Install endpoint | \`${slack.installPath}\` | Backend route |`,
        `| Interactivity | Slack actions | \`${slack.interactiveUrl}\` |`,
        `| Events | Slack Events API | \`${slack.eventsUrl}\` |`,
        `| Bot scopes | ${slack.scopes.map((scope) => `\`${scope}\``).join(', ') || '`none`'} | OAuth manifest |`,
      ].join('\n')
    : '| _Slack manifest not found_ | | |';

  const mdx = `---
title: Configuration Matrix
description: Auto-generated runtime configuration and integration matrix.
---

import { Aside, Card, CardGrid } from '@astrojs/starlight/components';

<CardGrid>
  <Card title="Environment variables" icon="document">
    ${envRows.length}
  </Card>
  <Card title="Slack manifest" icon="puzzle">
    ${slack ? 'present' : 'missing'}
  </Card>
  <Card title="Email manifest" icon="random">
    none detected
  </Card>
</CardGrid>

## Backend Environment

<div class="matrix-table">

| Variable | Group | Default or source |
| --- | --- | --- |
${envTable || '| _none detected_ | | |'}

</div>

## Integrations

<div class="matrix-table">

| Item | Value | Source |
| --- | --- | --- |
${slackRows}
| Outbound webhooks | HTTPS subscriptions | \`app/backend/app/routes/webhooks.py\` |
| Email | Not configured | No email manifest was found in this repository |

</div>

<Aside type="tip" title="Source">
  Generated from <code>app/backend/app/config.py</code> and <code>slack/app-manifest.yml</code>. The build reads text files only and does not import the backend.
</Aside>
`;

  await mkdir(dirname(OUT_FILE), { recursive: true });
  await writeFile(OUT_FILE, mdx, 'utf8');
  console.log(`[gen-config] wrote ${envRows.length} env vars and ${slack ? 1 : 0} Slack manifest`);
}

main().catch((err) => {
  console.error('[gen-config] failed:', err);
  process.exit(1);
});
