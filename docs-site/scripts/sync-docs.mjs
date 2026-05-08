import { copyFile, readdir, readFile, writeFile, mkdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { basename, dirname, extname, join, posix, relative } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = join(__dirname, '..', '..');
const SRC_DOCS = join(PROJECT_ROOT, 'docs');
const OUT_DIR = join(__dirname, '..', 'src', 'content', 'docs', 'guides');
const PUBLIC_DEMO_DIR = join(__dirname, '..', 'public', 'demo');
const SITE_BASE = '/ab-test-research-designer';
const REPO_BLOB_BASE = 'https://github.com/brownjuly2003-code/ab-test-research-designer/blob/main';
const MARKDOWN_EXTENSIONS = new Set(['.md', '.mdx']);

const ROOT_FILES = [
  { src: 'README.md', dest: 'overview.md', title: 'Project overview' },
  { src: 'CHANGELOG.md', dest: 'changelog.md', title: 'Changelog' },
];

async function walkMarkdown(dir, prefix = '') {
  const entries = await readdir(dir, { withFileTypes: true });
  const out = [];
  for (const entry of entries) {
    const full = join(dir, entry.name);
    const rel = prefix ? join(prefix, entry.name) : entry.name;
    if (entry.isDirectory()) {
      out.push(...(await walkMarkdown(full, rel)));
    } else if (entry.isFile() && MARKDOWN_EXTENSIONS.has(extname(entry.name).toLowerCase())) {
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
  return toPosixPath(rel)
    .split(/[\\/]/)
    .map((part, idx, arr) => {
      const lower = part.toLowerCase().replace(/\s+/g, '-');
      if (idx === arr.length - 1) {
        const ext = extname(lower);
        if (MARKDOWN_EXTENSIONS.has(ext)) {
          return lower.slice(0, -ext.length).replace(/\./g, '-') + ext;
        }
      }
      return lower.replace(/\./g, '-');
    })
    .join('/');
}

function toPosixPath(value) {
  return value.replace(/\\/g, '/');
}

function guideUrlForDocsRel(docsRel, suffix = '') {
  const slug = slugifyPath(docsRel).replace(/\.(md|mdx)$/i, '');
  return `${SITE_BASE}/guides/${slug}/${suffix}`;
}

function isSkippableTarget(target) {
  const lower = target.toLowerCase();
  return (
    target.startsWith('#') ||
    lower.startsWith('http://') ||
    lower.startsWith('https://') ||
    lower.startsWith('mailto:') ||
    target.startsWith('//') ||
    target === SITE_BASE ||
    target.startsWith(`${SITE_BASE}/`)
  );
}

function splitTarget(target) {
  const suffixStart = target.search(/[?#]/);
  if (suffixStart === -1) return { path: target, suffix: '' };
  return {
    path: target.slice(0, suffixStart),
    suffix: target.slice(suffixStart),
  };
}

function cleanRelativePath(targetPath) {
  return posix.normalize(toPosixPath(targetPath).replace(/^\.\//, ''));
}

function isDocsCandidate(candidate) {
  return candidate && candidate !== '.' && !candidate.startsWith('../') && !candidate.includes('/../');
}

function resolveRepoRel(targetPath, sourceRelPath) {
  const cleanTarget = cleanRelativePath(targetPath);
  if (cleanTarget.startsWith('docs/')) return cleanTarget;

  const sourceRel = cleanRelativePath(sourceRelPath);
  if (sourceRel.startsWith('docs/')) {
    return cleanRelativePath(posix.join(posix.dirname(sourceRel), cleanTarget));
  }

  return cleanTarget;
}

function findDocsMarkdownRel(targetPath, sourceRelPath) {
  const cleanTarget = cleanRelativePath(targetPath);
  const repoRel = resolveRepoRel(cleanTarget, sourceRelPath);
  const candidates = [];

  if (repoRel.startsWith('docs/')) candidates.push(repoRel.slice('docs/'.length));
  if (!cleanTarget.startsWith('docs/')) candidates.push(cleanTarget);
  if (cleanTarget.startsWith('docs/')) candidates.push(cleanTarget.slice('docs/'.length));

  for (const candidate of [...new Set(candidates)]) {
    if (!isDocsCandidate(candidate)) continue;
    if (!MARKDOWN_EXTENSIONS.has(extname(candidate).toLowerCase())) continue;
    if (existsSync(join(SRC_DOCS, ...candidate.split('/')))) return candidate;
  }

  return null;
}

function findDemoAssetRel(targetPath, sourceRelPath) {
  const cleanTarget = cleanRelativePath(targetPath);
  const repoRel = resolveRepoRel(cleanTarget, sourceRelPath);
  const candidates = [repoRel, cleanTarget];

  for (const candidate of candidates) {
    if (candidate.startsWith('docs/demo/')) return candidate.slice('docs/demo/'.length);
  }

  return null;
}

function rootGuideUrl(targetPath, sourceRelPath, suffix = '') {
  const cleanTarget = cleanRelativePath(targetPath);
  const repoRel = resolveRepoRel(cleanTarget, sourceRelPath);
  const rootRel = cleanTarget === 'README.md' || cleanTarget === 'CHANGELOG.md' ? cleanTarget : repoRel;

  if (rootRel === 'README.md') return `${SITE_BASE}/guides/overview/${suffix}`;
  if (rootRel === 'CHANGELOG.md') return `${SITE_BASE}/guides/changelog/${suffix}`;
  return null;
}

function rewriteTarget(rawTarget, sourceRelPath) {
  const wrappedInAngles = rawTarget.startsWith('<') && rawTarget.endsWith('>');
  const target = wrappedInAngles ? rawTarget.slice(1, -1) : rawTarget;

  if (isSkippableTarget(target)) return rawTarget;

  const { path, suffix } = splitTarget(target);
  if (!path || path.startsWith('/')) return rawTarget;

  const docsRel = findDocsMarkdownRel(path, sourceRelPath);
  const demoRel = findDemoAssetRel(path, sourceRelPath);
  const rootUrl = rootGuideUrl(path, sourceRelPath, suffix);
  let rewritten = null;

  if (docsRel) {
    rewritten = guideUrlForDocsRel(docsRel, suffix);
  } else if (demoRel) {
    rewritten = `${SITE_BASE}/demo/${demoRel}${suffix}`;
  } else if (rootUrl) {
    rewritten = rootUrl;
  } else {
    rewritten = `${REPO_BLOB_BASE}/${resolveRepoRel(path, sourceRelPath)}${suffix}`;
  }

  return wrappedInAngles ? `<${rewritten}>` : rewritten;
}

export function rewriteLinks(markdown, sourceRelPath) {
  return markdown
    .replace(/(!?\[[^\]\n]*\]\()([^\s)]+)([^)]*\))/g, (_match, prefix, target, suffix) => {
      return `${prefix}${rewriteTarget(target, sourceRelPath)}${suffix}`;
    })
    .replace(/^(\s*\[[^\]\n]+\]:\s*)(<[^>\s]+>|[^\s]+)(.*)$/gm, (_match, prefix, target, suffix) => {
      return `${prefix}${rewriteTarget(target, sourceRelPath)}${suffix}`;
    });
}

async function copyOne(srcAbs, destAbs, title, sourceRelPath) {
  const raw = await readFile(srcAbs, 'utf8');
  const patched = ensureFrontMatter(rewriteLinks(raw, sourceRelPath), title);
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
  await rm(PUBLIC_DEMO_DIR, { recursive: true, force: true });
  await mkdir(PUBLIC_DEMO_DIR, { recursive: true });

  let count = 0;

  if (existsSync(SRC_DOCS)) {
    const all = await walkMarkdown(SRC_DOCS);
    for (const { full, rel } of all) {
      const raw = await readFile(full, 'utf8');
      const title = deriveTitle(raw.replace(/\r\n/g, '\n'), basename(rel));
      const destAbs = join(OUT_DIR, slugifyPath(rel));
      await copyOne(full, destAbs, title, `docs/${toPosixPath(rel)}`);
      count++;
    }
  }

  for (const file of ROOT_FILES) {
    const srcAbs = join(PROJECT_ROOT, file.src);
    if (!existsSync(srcAbs)) continue;
    await copyOne(srcAbs, join(OUT_DIR, file.dest), file.title, file.src);
    count++;
  }

  const assetCount = await copyAssets(join(PROJECT_ROOT, 'docs', 'demo'), PUBLIC_DEMO_DIR);

  console.log(
    `[sync-docs] copied ${count} markdown files into ${relative(PROJECT_ROOT, OUT_DIR)} and ${assetCount} demo assets into ${relative(PROJECT_ROOT, PUBLIC_DEMO_DIR)}`,
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((err) => {
    console.error('[sync-docs] failed:', err);
    process.exit(1);
  });
}
