#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

function readJson(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    if (!content) {
      return null;
    }
    return JSON.parse(content);
  } catch (error) {
    return null;
  }
}

function normalizeRelative(relativePath) {
  return String(relativePath || '')
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
    .trim();
}

function collectHotCriticalIndexes(rootDir) {
  const hotManifestPath = path.join(rootDir, 'data', 'hot', 'manifest.json');
  const manifest = readJson(hotManifestPath);
  if (!manifest || !Array.isArray(manifest.shards)) {
    return [];
  }

  const critical = new Set();
  for (const shard of manifest.shards) {
    if (!shard || typeof shard !== 'object') {
      continue;
    }
    if (!shard.is_global && !shard.critical) {
      continue;
    }
    const normalized = normalizeRelative(shard.path);
    if (!normalized || !normalized.endsWith('index.json')) {
      continue;
    }
    critical.add(path.join(rootDir, 'data', 'hot', normalized));
  }

  return Array.from(critical);
}

function verifyIndexes(indexPaths, rootDir) {
  const missing = [];
  const empty = [];

  for (const absolute of indexPaths) {
    try {
      const stat = fs.statSync(absolute);
      if (!stat.isFile()) {
        missing.push(absolute);
      } else if (stat.size === 0) {
        empty.push(absolute);
      }
    } catch (error) {
      missing.push(absolute);
    }
  }

  if (missing.length || empty.length) {
    if (missing.length) {
      console.error('Missing critical index.json files:');
      for (const filePath of missing) {
        console.error('  - ' + path.relative(rootDir, filePath));
      }
    }
    if (empty.length) {
      console.error('Empty critical index.json files:');
      for (const filePath of empty) {
        console.error('  - ' + path.relative(rootDir, filePath));
      }
    }
    process.exit(1);
  }
}

function main() {
  const projectRoot = path.resolve(__dirname, '..');
  const dataRoot = path.join(projectRoot, 'data');
  const manualCritical = [path.join(dataRoot, 'index.json')];
  const hotCritical = collectHotCriticalIndexes(projectRoot);

  const uniquePaths = new Set([...manualCritical, ...hotCritical]);
  if (!uniquePaths.size) {
    console.warn('No critical index.json paths were detected.');
    return;
  }

  verifyIndexes(Array.from(uniquePaths), projectRoot);
  console.log(`Verified ${uniquePaths.size} critical index.json file(s).`);
}

main();
