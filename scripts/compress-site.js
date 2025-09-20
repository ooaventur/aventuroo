#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const { pipeline } = require('stream/promises');

const extsToCompress = new Set(['.html', '.json']);
const rootDir = path.resolve(__dirname, '..');
const outputDir = path.join(rootDir, '_site');

async function walk(dir) {
  const dirents = await fs.promises.readdir(dir, { withFileTypes: true });
  const files = [];

  for (const entry of dirents) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await walk(fullPath));
    } else if (entry.isFile() && extsToCompress.has(path.extname(entry.name))) {
      files.push(fullPath);
    }
  }

  return files;
}

async function compressFile(sourcePath) {
  const destPath = `${sourcePath}.gz`;
  const [sourceStat, destStat] = await Promise.all([
    fs.promises.stat(sourcePath),
    fs.promises.stat(destPath).catch(() => null)
  ]);

  if (destStat && destStat.mtimeMs >= sourceStat.mtimeMs && destStat.size > 0) {
    return { status: 'skipped', sourcePath };
  }

  const tempPath = `${destPath}.${process.pid}.tmp`;
  await fs.promises.mkdir(path.dirname(destPath), { recursive: true });

  try {
    const readStream = fs.createReadStream(sourcePath);
    const gzipStream = zlib.createGzip({ level: zlib.constants.Z_BEST_COMPRESSION });
    const writeStream = fs.createWriteStream(tempPath);

    await pipeline(readStream, gzipStream, writeStream);
    await fs.promises.rename(tempPath, destPath);
    await fs.promises.utimes(destPath, sourceStat.atime, sourceStat.mtime);
  } catch (error) {
    await fs.promises.rm(tempPath, { force: true }).catch(() => {});
    throw error;
  }

  return { status: 'compressed', sourcePath };
}

async function main() {
  try {
    await fs.promises.access(outputDir, fs.constants.R_OK);
  } catch (error) {
    console.warn(`Nothing to compress – directory not found: ${outputDir}`);
    return;
  }

  const files = await walk(outputDir);

  if (files.length === 0) {
    console.log('No HTML or JSON files found to compress.');
    return;
  }

  let compressed = 0;
  let skipped = 0;

  for (const file of files) {
    try {
      const result = await compressFile(file);
      if (result.status === 'compressed') {
        compressed += 1;
      } else {
        skipped += 1;
      }
    } catch (error) {
      console.error(`Failed to compress ${file}:`, error);
      process.exitCode = 1;
    }
  }

  console.log(`Compression complete: ${compressed} updated, ${skipped} skipped.`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
