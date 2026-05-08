import { readdir, readFile, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, extname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(__dirname, '..', '..');
const ROUTES_DIR = join(PROJECT_ROOT, 'app', 'backend', 'app', 'routes');
const MAIN_FILE = join(PROJECT_ROOT, 'app', 'backend', 'app', 'main.py');
const FRONTEND_ROUTES_FILE = join(PROJECT_ROOT, 'app', 'backend', 'app', 'frontend_routes.py');
const OUT_FILE = join(__dirname, '..', 'src', 'content', 'docs', 'architecture', 'routes.mdx');

const METHOD_RE = /@(?:app|router)\.(get|post|put|patch|delete|head|options)\(\s*["']([^"']+)["']/gi;

async function listRoutesInFile(file) {
  const content = await readFile(file, 'utf8');
  const found = [];
  let match;
  while ((match = METHOD_RE.exec(content))) {
    found.push({
      method: match[1].toUpperCase(),
      path: match[2],
      file: relative(PROJECT_ROOT, file).replace(/\\/g, '/'),
    });
  }
  return found;
}

function methodCell(method) {
  return `<span class="route-method route-method-${method.toLowerCase()}">${method}</span>`;
}

async function collectRouteFiles() {
  const files = [];
  for (const file of [MAIN_FILE, FRONTEND_ROUTES_FILE]) {
    if (existsSync(file)) files.push(file);
  }
  if (existsSync(ROUTES_DIR)) {
    const entries = await readdir(ROUTES_DIR, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isFile() && extname(entry.name).toLowerCase() === '.py') {
        files.push(join(ROUTES_DIR, entry.name));
      }
    }
  }
  return files;
}

async function main() {
  const all = [];
  for (const file of await collectRouteFiles()) {
    all.push(...(await listRoutesInFile(file)));
  }
  all.sort((a, b) => a.path.localeCompare(b.path) || a.method.localeCompare(b.method));

  const byFile = new Map();
  for (const route of all) {
    if (!byFile.has(route.file)) byFile.set(route.file, []);
    byFile.get(route.file).push(route);
  }

  const fileRows = [...byFile.entries()]
    .map(([file, items]) => `| \`${file}\` | ${items.length} |`)
    .join('\n');
  const routeRows = all
    .map((route) => `| ${methodCell(route.method)} | \`${route.path}\` | \`${route.file}\` |`)
    .join('\n');

  const mdx = `---
title: API Routes Catalog
description: Auto-generated FastAPI route catalog for AB_TEST.
---

import { Aside, Card, CardGrid } from '@astrojs/starlight/components';

<CardGrid>
  <Card title="Total endpoints" icon="rocket">
    ${all.length}
  </Card>
  <Card title="Source files" icon="document">
    ${byFile.size}
  </Card>
</CardGrid>

## By File

| File | Endpoints |
| --- | ---: |
${fileRows || '| _no routes detected_ | 0 |'}

## All Routes

<div class="route-table">

| Method | Path | Source |
| --- | --- | --- |
${routeRows || '| _no routes detected_ | | |'}

</div>

<Aside type="tip" title="Source">
  Generated from <code>app/backend/app/main.py</code>, <code>app/backend/app/frontend_routes.py</code>, and <code>{"app/backend/app/routes/*.py"}</code> using regex on route decorators. The build does not import the FastAPI app.
</Aside>
`;

  await mkdir(dirname(OUT_FILE), { recursive: true });
  await writeFile(OUT_FILE, mdx, 'utf8');
  console.log(`[gen-routes] wrote ${all.length} routes from ${byFile.size} files`);
}

main().catch((err) => {
  console.error('[gen-routes] failed:', err);
  process.exit(1);
});
