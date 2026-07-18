import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { basename, dirname, extname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from 'yaml';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(__dirname, '..', '..');
const TEMPLATES_DIR = join(PROJECT_ROOT, 'app', 'backend', 'templates');
const STATS_DIR = join(PROJECT_ROOT, 'app', 'backend', 'app', 'stats');
const OUT_FILE = join(__dirname, '..', 'src', 'content', 'docs', 'architecture', 'experiments.mdx');

async function readTemplates() {
  if (!existsSync(TEMPLATES_DIR)) return [];
  const entries = await readdir(TEMPLATES_DIR, { withFileTypes: true });
  const templates = [];
  for (const entry of entries) {
    if (!entry.isFile() || extname(entry.name).toLowerCase() !== '.yaml') continue;
    const file = join(TEMPLATES_DIR, entry.name);
    const doc = parse(await readFile(file, 'utf8')) || {};
    const payload = doc.payload || {};
    const metrics = payload.metrics || {};
    const setup = payload.setup || {};
    templates.push({
      id: basename(entry.name, '.yaml'),
      name: doc.name || basename(entry.name, '.yaml'),
      category: doc.category || 'uncategorized',
      metricType: metrics.metric_type || 'unknown',
      primaryMetric: metrics.primary_metric_name || 'unknown',
      variants: setup.variants_count || 'unknown',
      file: relative(PROJECT_ROOT, file).replace(/\\/g, '/'),
    });
  }
  return templates.sort((a, b) => a.id.localeCompare(b.id));
}

async function readStats() {
  if (!existsSync(STATS_DIR)) return [];
  const entries = await readdir(STATS_DIR, { withFileTypes: true });
  const tests = [];
  for (const entry of entries) {
    if (!entry.isFile() || extname(entry.name).toLowerCase() !== '.py' || entry.name === '__init__.py') continue;
    const file = join(STATS_DIR, entry.name);
    const source = await readFile(file, 'utf8');
    const functions = [...source.matchAll(/^def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/gm)].map((m) => m[1]);
    tests.push({
      module: basename(entry.name, '.py'),
      functions,
      file: relative(PROJECT_ROOT, file).replace(/\\/g, '/'),
    });
  }
  return tests.sort((a, b) => a.module.localeCompare(b.module));
}

function tableEscape(value) {
  return String(value).replace(/\\/g, '\\\\').replace(/\|/g, '\\|');
}

async function main() {
  const templates = await readTemplates();
  const stats = await readStats();

  const metricTypes = [...new Set(templates.map((item) => item.metricType))].sort();
  const categories = [...new Set(templates.map((item) => item.category))].sort();

  const templateRows = templates
    .map(
      (item) =>
        `| \`${item.id}\` | ${tableEscape(item.name)} | ${tableEscape(item.category)} | \`${item.metricType}\` | \`${item.primaryMetric}\` | ${item.variants} | \`${item.file}\` |`,
    )
    .join('\n');
  const statRows = stats
    .map(
      (item) =>
        `| \`${item.module}\` | ${item.functions.map((fn) => `\`${fn}\``).join(', ') || '_none_'} | \`${item.file}\` |`,
    )
    .join('\n');

  const mdx = `---
title: Experiment Catalog
description: Auto-generated catalog of built-in experiment templates and statistical routines.
---

import { Aside, Card, CardGrid } from '@astrojs/starlight/components';

<CardGrid>
  <Card title="Built-in templates" icon="document">
    ${templates.length}
  </Card>
  <Card title="Metric types" icon="puzzle">
    ${metricTypes.join(', ') || 'none'}
  </Card>
  <Card title="Template categories" icon="random">
    ${categories.length}
  </Card>
</CardGrid>

## One Experiment Run

\`\`\`mermaid
flowchart TD
  A[Select built-in template] --> B[Fill project, hypothesis, setup, metrics, constraints]
  B --> C[POST /api/v1/calculate]
  C --> D[Sample size and duration]
  D --> E[POST /api/v1/design]
  E --> F[Structured experiment report]
  F --> G[Save project and analysis history]
  G --> H[Compare, export, notify, or rerun]
\`\`\`

## Built-in Templates

<div class="matrix-table">

| ID | Name | Category | Metric type | Primary metric | Variants | Source |
| --- | --- | --- | --- | --- | ---: | --- |
${templateRows || '| _none_ | | | | | | |'}

</div>

## Registered Statistical Routines

<div class="matrix-table">

| Module | Public functions | Source |
| --- | --- | --- |
${statRows || '| _none_ | | |'}

</div>

<Aside type="tip" title="Source">
  Generated from <code>{"app/backend/templates/*.yaml"}</code> and <code>{"app/backend/app/stats/*.py"}</code>. The build reads text files only and does not execute Python.
</Aside>
`;

  await mkdir(dirname(OUT_FILE), { recursive: true });
  await writeFile(OUT_FILE, mdx, 'utf8');
  console.log(`[gen-experiments] wrote ${templates.length} templates and ${stats.length} stats modules`);
}

main().catch((err) => {
  console.error('[gen-experiments] failed:', err);
  process.exit(1);
});
