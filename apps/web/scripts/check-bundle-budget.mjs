import { readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const KIB = 1024;
const INITIAL_CHUNK_BUDGET = 275 * KIB;
const ON_DEMAND_CHUNK_BUDGET = 450 * KIB;
const REPORT_THRESHOLD = 200 * KIB;

const approvedOnDemandBudgets = [
  {
    label: 'Paged.js pagination engine',
    maximumBytes: 600 * KIB,
    // Vite's manifest preserves the package's source path. npm installs use
    // `node_modules/pagedjs/...`, while pnpm adds a versioned `.pnpm` segment.
    matches: (source) => /(?:^|\/)pagedjs(?:@[^/]+)?\//.test(source),
  },
  {
    label: 'PDF.js worker',
    maximumBytes: 2500 * KIB,
    matches: (source) => /(?:^|\/)pdfjs-dist(?:@[^/]+)?\//.test(source) && source.includes('/pdf.worker.mjs'),
  },
];

const javascriptFilePattern = /\.(?:js|mjs)$/;

function displaySource(key, item) {
  return item.src ?? item.name ?? key;
}

function selectBudget(loadMode, source) {
  if (loadMode === 'initial') {
    return { label: 'initial application', maximumBytes: INITIAL_CHUNK_BUDGET };
  }

  return approvedOnDemandBudgets.find((budget) => budget.matches(source))
    ?? { label: 'on-demand chunk', maximumBytes: ON_DEMAND_CHUNK_BUDGET };
}

function walkManifest(manifest, rootKey, loadMode, seen, files, owner) {
  if (seen.has(rootKey)) return;
  seen.add(rootKey);

  const item = manifest[rootKey];
  if (!item) return;
  const source = displaySource(rootKey, item);
  for (const file of [item.file, ...(item.assets ?? [])]) {
    if (!file || !javascriptFilePattern.test(file)) continue;
    const existing = files.get(file);
    if (existing) {
      if (loadMode === 'initial') existing.loadMode = 'initial';
      existing.sources.add(source);
      existing.owners.add(owner);
      continue;
    }
    files.set(file, {
      file,
      loadMode,
      sources: new Set([source]),
      owners: new Set([owner]),
    });
  }

  for (const importedKey of item.imports ?? []) {
    walkManifest(manifest, importedKey, loadMode, seen, files, owner);
  }
}

export function inspectBundle(manifest, fileSize) {
  const files = new Map();
  const initialRoots = Object.entries(manifest)
    .filter(([, item]) => item.isEntry)
    .map(([key]) => key);
  const dynamicRoots = Object.entries(manifest)
    .filter(([, item]) => item.isDynamicEntry)
    .map(([key]) => key);

  for (const root of initialRoots) {
    walkManifest(manifest, root, 'initial', new Set(), files, displaySource(root, manifest[root]));
  }
  for (const root of dynamicRoots) {
    walkManifest(manifest, root, 'on-demand', new Set(), files, displaySource(root, manifest[root]));
  }

  return [...files.values()]
    .map((item) => {
      const sources = [...item.sources].sort();
      const source = sources.find((candidate) => candidate.includes('/node_modules/')) ?? sources[0];
      const budget = selectBudget(item.loadMode, source);
      return {
        ...item,
        sources,
        owners: [...item.owners].sort(),
        source,
        bytes: fileSize(item.file),
        budget,
      };
    })
    .sort((left, right) => right.bytes - left.bytes || left.source.localeCompare(right.source));
}

export function formatBundleReport(chunks) {
  const largeChunks = chunks.filter((chunk) => chunk.bytes > REPORT_THRESHOLD);
  const lines = ['Bundle budget report (minified JavaScript, KiB):'];

  if (largeChunks.length === 0) {
    lines.push(`  No chunk exceeds ${REPORT_THRESHOLD / KIB} KiB.`);
  } else {
    for (const chunk of largeChunks) {
      const status = chunk.bytes <= chunk.budget.maximumBytes ? 'PASS' : 'FAIL';
      const allowance = chunk.budget.label === 'on-demand chunk' || chunk.budget.label === 'initial application'
        ? ''
        : `; approved: ${chunk.budget.label}`;
      lines.push(
        `  ${status} ${chunk.loadMode} ${Math.ceil(chunk.bytes / KIB)} KiB / ${chunk.budget.maximumBytes / KIB} KiB — ${chunk.source}${allowance}`,
      );
    }
  }

  return lines.join('\n');
}

export function assertBundleBudget(chunks) {
  const failures = chunks.filter((chunk) => chunk.bytes > chunk.budget.maximumBytes);
  if (failures.length > 0) {
    const details = failures
      .map((chunk) => `${chunk.source} is ${Math.ceil(chunk.bytes / KIB)} KiB (limit ${chunk.budget.maximumBytes / KIB} KiB)`)
      .join('; ');
    throw new Error(`Bundle budget exceeded: ${details}`);
  }
}

function main() {
  const distDirectory = resolve('dist');
  const manifestPath = resolve(distDirectory, '.vite', 'manifest.json');
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  const chunks = inspectBundle(manifest, (file) => statSync(resolve(distDirectory, file)).size);
  console.log(formatBundleReport(chunks));
  assertBundleBudget(chunks);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main();
}
