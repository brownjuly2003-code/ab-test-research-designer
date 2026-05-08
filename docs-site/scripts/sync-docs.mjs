import { copyFile, readdir, readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { basename, dirname, extname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(__dirname, '..', '..');
const SRC_DOCS = join(PROJECT_ROOT, 'docs');
const OUT_DIR = join(__dirname, '..', 'src', 'content', 'docs', 'guides');

const ROOT_FILES = [
  { src: 'README.md', dest: 'overview.md', title: 'Project overview' },
  { src: 'CHANGELOG.md', dest: 'changelog.md', title: 'Changelog' },
];
const ASSET_DIRS = ['docs/demo'];

async function walkMarkdown(dir, prefix = '') {
  const entries = await readdir(dir, { withFileTypes: true });
  const out = [];
  for (const entry of entries) {
    const full = join(dir, entry.name);
    const rel = prefix ? join(prefix, entry.name) : entry.name;
    if (entry.isDirectory()) {
      out.push(...(await walkMarkdown(full, rel)));
    } else if (entry.isFile() && extname(entry.name).toLowerCase() === '.md') {
      out.push({ full, rel });
    }
  }
  return out;
}

function deriveTitle(content, fallbackName) {
  const h1 = content.match(/^#\s+(.+)$/m);
  if (h1) return h1[1].trim();
  return fallbackName.replace(/[-_]/g, ' ').replace(/\.md$/i, '').trim();
}

function ensureFrontMatter(content, title) {
  const normalized = content.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n');
  if (normalized.startsWith('---')) {
    const fm = normalized.match(/^---\n([\s\S]*?)\n---/);
    if (fm && !/^title:/m.test(fm[1])) {
      return `---\n${fm[1]}\ntitle: ${JSON.stringify(title)}\n---${normalized.slice(fm[0].length)}`;
    }
    return normalized;
  }
  return `---\ntitle: ${JSON.stringify(title)}\n---\n\n${normalized}`;
}

function slugifyPath(rel) {
  return rel
    .split(/[\\/]/)
    .map((part, idx, arr) => {
      const lower = part.toLowerCase().replace(/\s+/g, '-');
      if (idx === arr.length - 1 && lower.endsWith('.md')) {
        return lower.slice(0, -3).replace(/\./g, '-') + '.md';
      }
      return lower.replace(/\./g, '-');
    })
    .join('/');
}

async function copyOne(srcAbs, destAbs, title) {
  const raw = await readFile(srcAbs, 'utf8');
  const patched = ensureFrontMatter(raw, title);
  await mkdir(dirname(destAbs), { recursive: true });
  await writeFile(destAbs, patched, 'utf8');
}

async function copyAssets(srcDir, destDir) {
  if (!existsSync(srcDir)) return 0;
  const entries = await readdir(srcDir, { withFileTypes: true });
  let count = 0;
  for (const entry of entries) {
    const src = join(srcDir, entry.name);
    const dest = join(destDir, entry.name);
    if (entry.isDirectory()) {
      count += await copyAssets(src, dest);
    } else if (entry.isFile()) {
      await mkdir(dirname(dest), { recursive: true });
      await copyFile(src, dest);
      count++;
    }
  }
  return count;
}

async function main() {
  if (existsSync(OUT_DIR)) {
    await rm(OUT_DIR, { recursive: true, force: true });
  }
  await mkdir(OUT_DIR, { recursive: true });

  let count = 0;

  if (existsSync(SRC_DOCS)) {
    const all = await walkMarkdown(SRC_DOCS);
    for (const { full, rel } of all) {
      const raw = await readFile(full, 'utf8');
      const title = deriveTitle(raw.replace(/\r\n/g, '\n'), basename(rel));
      const destAbs = join(OUT_DIR, slugifyPath(rel));
      await copyOne(full, destAbs, title);
      count++;
    }
  }

  for (const file of ROOT_FILES) {
    const srcAbs = join(PROJECT_ROOT, file.src);
    if (!existsSync(srcAbs)) continue;
    await copyOne(srcAbs, join(OUT_DIR, file.dest), file.title);
    count++;
  }

  let assetCount = 0;
  for (const relDir of ASSET_DIRS) {
    assetCount += await copyAssets(join(PROJECT_ROOT, relDir), join(OUT_DIR, relDir));
  }

  console.log(
    `[sync-docs] copied ${count} markdown files and ${assetCount} assets into ${relative(PROJECT_ROOT, OUT_DIR)}`,
  );
}

main().catch((err) => {
  console.error('[sync-docs] failed:', err);
  process.exit(1);
});
