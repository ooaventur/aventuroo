const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const DATE_FIELDS = [
  'date',
  'published',
  'published_at',
  'publishedAt',
  'updated',
  'updated_at',
  'updatedAt',
];

const COLLECTION_KEYS = ['items', 'entries', 'data', 'posts'];
const CANONICAL_FIELDS = ['canonical', 'url', 'link', 'permalink'];

function readJson(filePath) {
  try {
    const text = fs.readFileSync(filePath, 'utf-8');
    return JSON.parse(text);
  } catch (error) {
    return null;
  }
}

function readJsonAllowGzip(filePath) {
  const data = readJson(filePath);
  if (data !== null) {
    return data;
  }
  const gzPath = filePath.endsWith('.gz') ? filePath : `${filePath}.gz`;
  if (!fs.existsSync(gzPath)) {
    return null;
  }
  try {
    const buffer = fs.readFileSync(gzPath);
    const text = zlib.gunzipSync(buffer).toString('utf-8');
    return JSON.parse(text);
  } catch (error) {
    return null;
  }
}

function listIndexJson(rootDir) {
  const results = [];
  if (!rootDir || !fs.existsSync(rootDir)) {
    return results;
  }
  const stack = [rootDir];
  while (stack.length) {
    const current = stack.pop();
    let entries;
    try {
      entries = fs.readdirSync(current, { withFileTypes: true });
    } catch (error) {
      continue;
    }
    for (const entry of entries) {
      if (entry.isDirectory()) {
        stack.push(path.join(current, entry.name));
      } else if (entry.isFile() && entry.name === 'index.json') {
        results.push(path.join(current, entry.name));
      }
    }
  }
  return results;
}

function parseHotParts(parts) {
  if (!Array.isArray(parts) || parts.length <= 1) {
    return { parent: 'index', child: 'index' };
  }
  const parent = parts[0] || 'index';
  if (parts.length === 2) {
    return { parent, child: 'index' };
  }
  const childParts = parts.slice(1, -1).filter(Boolean);
  return { parent, child: childParts.length ? childParts.join('/') : 'index' };
}

function parseArchiveParts(parts) {
  if (!Array.isArray(parts) || parts.length < 4) {
    const parent = parts && parts.length ? parts[0] || 'index' : 'index';
    return { parent, child: 'index' };
  }
  const parent = parts[0] || 'index';
  const childParts = parts.slice(1, -3).filter(Boolean);
  return { parent, child: childParts.length ? childParts.join('/') : 'index' };
}

function extractItems(payload) {
  if (Array.isArray(payload)) {
    return payload.slice();
  }
  if (payload && typeof payload === 'object') {
    for (const key of COLLECTION_KEYS) {
      const candidate = payload[key];
      if (Array.isArray(candidate)) {
        return candidate.slice();
      }
    }
  }
  return [];
}

function parseDateValue(value) {
  if (!value && value !== 0) {
    return null;
  }
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) {
      return null;
    }
    return new Date(Date.UTC(value.getUTCFullYear(), value.getUTCMonth(), value.getUTCDate()));
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      return null;
    }
    const milliseconds = value > 1e12 ? value : value * 1000;
    const date = new Date(milliseconds);
    if (Number.isNaN(date.getTime())) {
      return null;
    }
    return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
  }
  const text = String(value).trim();
  if (!text) {
    return null;
  }
  if (/^\d+$/.test(text)) {
    return parseDateValue(Number(text));
  }
  let parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) {
    const match = text.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
    if (!match) {
      return null;
    }
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
      return null;
    }
    parsed = new Date(Date.UTC(year, month - 1, day));
  }
  return new Date(Date.UTC(parsed.getUTCFullYear(), parsed.getUTCMonth(), parsed.getUTCDate()));
}

function extractDate(item) {
  if (!item || typeof item !== 'object') {
    return null;
  }
  for (const field of DATE_FIELDS) {
    if (field in item) {
      const parsed = parseDateValue(item[field]);
      if (parsed) {
        return parsed;
      }
    }
  }
  return null;
}

function extractCanonical(item) {
  if (!item || typeof item !== 'object') {
    return null;
  }
  for (const field of CANONICAL_FIELDS) {
    const value = item[field];
    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (trimmed) {
        return trimmed;
      }
    }
  }
  return null;
}

function formatDate(date) {
  return date.toISOString().slice(0, 10);
}

function addItem(groups, parent, child, item) {
  const canonical = extractCanonical(item);
  if (!canonical) {
    return;
  }
  const date = extractDate(item);
  if (!date) {
    return;
  }
  const year = date.getUTCFullYear();
  const month = date.getUTCMonth() + 1;
  const key = `${parent}||${child}||${year}||${month}`;
  let group = groups.get(key);
  if (!group) {
    group = {
      parent,
      child,
      year,
      month,
      items: new Map(),
      latest: null,
    };
    groups.set(key, group);
  }
  const lastmod = formatDate(date);
  const existing = group.items.get(canonical);
  if (!existing || existing.lastmod < lastmod) {
    group.items.set(canonical, { loc: canonical, lastmod });
  }
  if (!group.latest || group.latest < lastmod) {
    group.latest = lastmod;
  }
}

function sanitizeSegment(value) {
  const text = (value == null ? '' : String(value)).trim().toLowerCase();
  const replaced = text.replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  return replaced || 'index';
}

function escapeXml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function buildUrlsetXml(entries) {
  const lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'];
  for (const entry of entries) {
    lines.push('  <url>');
    lines.push(`    <loc>${escapeXml(entry.loc)}</loc>`);
    if (entry.lastmod) {
      lines.push(`    <lastmod>${escapeXml(entry.lastmod)}</lastmod>`);
    }
    lines.push('  </url>');
  }
  lines.push('</urlset>');
  return `${lines.join('\n')}\n`;
}

function buildIndexXml(entries) {
  const lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'];
  for (const entry of entries) {
    lines.push('  <sitemap>');
    lines.push(`    <loc>${escapeXml(entry.loc)}</loc>`);
    if (entry.lastmod) {
      lines.push(`    <lastmod>${escapeXml(entry.lastmod)}</lastmod>`);
    }
    lines.push('  </sitemap>');
  }
  lines.push('</sitemapindex>');
  return `${lines.join('\n')}\n`;
}

function resolveUrl(base, relativePath) {
  if (!relativePath) {
    return base;
  }
  const baseUrl = typeof base === 'string' && base.trim() ? base.trim() : 'https://aventuroo.com';
  try {
    const url = new URL(relativePath, baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`);
    return url.href;
  } catch (error) {
    const normalizedBase = baseUrl.replace(/\/+$/, '');
    return `${normalizedBase}/${relativePath.replace(/^\/+/, '')}`;
  }
}

function ensureDir(filePath) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
}

function addArchiveBucket(groups, archiveDir, bucketPath, parent, child) {
  const payload = readJsonAllowGzip(bucketPath);
  if (!payload) {
    return;
  }
  const items = extractItems(payload);
  if (!items.length) {
    return;
  }
  for (const item of items) {
    addItem(groups, parent, child, item);
  }
}

function buildGroups(hotDir, archiveDir) {
  const groups = new Map();

  for (const shardPath of listIndexJson(hotDir)) {
    const rel = path.relative(hotDir, shardPath);
    const parts = rel.split(path.sep).filter(Boolean);
    const { parent, child } = parseHotParts(parts);
    const payload = readJsonAllowGzip(shardPath);
    if (!payload) {
      continue;
    }
    const items = extractItems(payload);
    for (const item of items) {
      addItem(groups, parent, child, item);
    }
  }

  const visited = new Set();
  const manifestPath = path.join(archiveDir, 'manifest.json');
  const manifest = readJson(manifestPath);
  if (manifest && Array.isArray(manifest.shards)) {
    for (const shard of manifest.shards) {
      if (!shard || typeof shard !== 'object') {
        continue;
      }
      const relPath = typeof shard.path === 'string' ? shard.path : null;
      const pathCandidate = relPath ? path.join(archiveDir, relPath) : null;
      const bucketPath = pathCandidate || null;
      if (!bucketPath) {
        continue;
      }
      visited.add(path.normalize(bucketPath));
      let parent = typeof shard.parent === 'string' && shard.parent ? shard.parent : null;
      let child = typeof shard.child === 'string' && shard.child ? shard.child : null;
      if (!parent || !child) {
        const parts = path.relative(archiveDir, bucketPath).split(path.sep).filter(Boolean);
        const parsed = parseArchiveParts(parts);
        parent = parent || parsed.parent;
        child = child || parsed.child;
      }
      addArchiveBucket(groups, archiveDir, bucketPath, parent || 'index', child || 'index');
    }
  }

  for (const bucketPath of listIndexJson(archiveDir)) {
    const normalized = path.normalize(bucketPath);
    if (visited.has(normalized)) {
      continue;
    }
    const parts = path.relative(archiveDir, bucketPath).split(path.sep).filter(Boolean);
    const { parent, child } = parseArchiveParts(parts);
    addArchiveBucket(groups, archiveDir, bucketPath, parent, child);
  }

  const result = [];
  for (const group of groups.values()) {
    const entries = Array.from(group.items.values()).sort((a, b) => {
      if (a.lastmod !== b.lastmod) {
        return a.lastmod > b.lastmod ? -1 : 1;
      }
      return a.loc.localeCompare(b.loc);
    });
    if (!entries.length) {
      continue;
    }
    result.push({
      parent: group.parent,
      child: group.child,
      year: group.year,
      month: group.month,
      latest: group.latest,
      entries,
    });
  }

  result.sort((a, b) => {
    if (a.parent !== b.parent) {
      return a.parent.localeCompare(b.parent);
    }
    if (a.child !== b.child) {
      return a.child.localeCompare(b.child);
    }
    if (a.year !== b.year) {
      return b.year - a.year;
    }
    return b.month - a.month;
  });

  return result;
}

function cleanupOldSitemaps(outputDir, keep) {
  if (!fs.existsSync(outputDir)) {
    return;
  }
  let entries;
  try {
    entries = fs.readdirSync(outputDir, { withFileTypes: true });
  } catch (error) {
    return;
  }
  for (const entry of entries) {
    if (!entry.isFile()) {
      continue;
    }
    if (!entry.name.startsWith('sitemap-') || !entry.name.endsWith('.xml.gz')) {
      continue;
    }
    if (!keep.has(entry.name)) {
      try {
        fs.unlinkSync(path.join(outputDir, entry.name));
      } catch (error) {
        // ignore
      }
    }
  }
}

module.exports = class SitemapGenerator {
  data() {
    return {
      permalink: 'sitemap.xml',
      eleventyExcludeFromCollections: true,
    };
  }

  render(data) {
    const projectRoot = path.resolve(__dirname, '..', '..');
    const hotDir = path.join(projectRoot, 'data', 'hot');
    const archiveDir = path.join(projectRoot, 'data', 'archive');
    const outputDir = data && data.eleventy && data.eleventy.directories && data.eleventy.directories.output
      ? path.resolve(data.eleventy.directories.output)
      : path.join(projectRoot, '_site');

    const groups = buildGroups(hotDir, archiveDir);
    fs.mkdirSync(outputDir, { recursive: true });

    const baseUrl = data && data.site && typeof data.site.url === 'string' && data.site.url.trim()
      ? data.site.url.trim()
      : 'https://aventuroo.com';

    const generated = new Set();
    const indexEntries = [];

    for (const group of groups) {
      const year = String(group.year).padStart(4, '0');
      const month = String(group.month).padStart(2, '0');
      const parentSegment = sanitizeSegment(group.parent);
      const childSegment = sanitizeSegment(group.child);
      const filename = `sitemap-${parentSegment}-${childSegment}-${year}-${month}.xml.gz`;
      const outputPath = path.join(outputDir, filename);
      ensureDir(outputPath);
      const xml = buildUrlsetXml(group.entries);
      const buffer = zlib.gzipSync(xml, { level: 9, mtime: 0 });
      fs.writeFileSync(outputPath, buffer);
      generated.add(filename);
      if (group.latest) {
        indexEntries.push({
          loc: resolveUrl(baseUrl, filename),
          lastmod: group.latest,
        });
      } else {
        indexEntries.push({
          loc: resolveUrl(baseUrl, filename),
          lastmod: group.entries[0] ? group.entries[0].lastmod : null,
        });
      }
    }

    cleanupOldSitemaps(outputDir, generated);

    indexEntries.sort((a, b) => {
      if (a.lastmod && b.lastmod && a.lastmod !== b.lastmod) {
        return a.lastmod > b.lastmod ? -1 : 1;
      }
      return a.loc.localeCompare(b.loc);
    });

    return buildIndexXml(indexEntries);
  }
};
