const fs = require('fs');
const path = require('path');

function readJson(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf8');
    if (!content) return null;
    return JSON.parse(content);
  } catch (error) {
    return null;
  }
}

function padNumber(value, length) {
  const number = Number.parseInt(value, 10);
  if (Number.isFinite(number)) {
    return String(Math.abs(number)).padStart(length, '0');
  }
  return String(value == null ? '' : value).padStart(length, '0');
}

module.exports = function archiveManifestData() {
  const rootDir = path.resolve(__dirname, '..', '..', '..');
  const archiveDir = path.join(rootDir, 'data', 'archive');
  const manifestPath = path.join(archiveDir, 'manifest.json');

  const manifest = readJson(manifestPath) || {};
  const shards = Array.isArray(manifest.shards) ? manifest.shards : [];

  const processed = shards.map((shard) => {
    const parent = shard && typeof shard.parent === 'string' ? shard.parent : '';
    const child = shard && typeof shard.child === 'string' ? shard.child : '';
    const year = shard && shard.year != null ? shard.year : '';
    const month = shard && shard.month != null ? shard.month : '';

    const yearString = padNumber(year, 4);
    const monthString = padNumber(month, 2);

    const shardPath = path.join(archiveDir, parent, child, yearString, monthString, 'index.json');
    const shardData = readJson(shardPath);
    const items = Array.isArray(shardData && shardData.items) ? shardData.items : [];
    const pagination = shardData && typeof shardData.pagination === 'object' ? shardData.pagination : null;
    const updatedAt = shardData && (shardData.updated_at || shardData.updatedAt || null);

    let count = items.length;
    if (shardData && typeof shardData.count === 'number') {
      count = shardData.count;
    } else if (typeof shard.items === 'number') {
      count = shard.items;
    }

    const dataHref = '/' + path.posix.join('data', 'archive', parent, child, yearString, monthString, 'index.json');
    let gzipHref = null;
    if (shard && typeof shard.path_gz === 'string' && shard.path_gz.trim()) {
      const gzipRelative = shard.path_gz.replace(/\\/g, '/').replace(/^\/+/, '');
      gzipHref = '/' + path.posix.join('data', 'archive', gzipRelative);
    }

    return {
      ...shard,
      parent,
      child,
      year,
      month,
      yearString,
      monthString,
      stories: items,
      pagination,
      updatedAt,
      count,
      dataHref,
      gzipHref,
      dataMissing: !shardData
    };
  });

  return {
    generated_at: manifest.generated_at || null,
    per_page: manifest.per_page || null,
    total_items: manifest.total_items || 0,
    shards: processed
  };
};
