import assert from 'node:assert/strict';
import test from 'node:test';

import { assertBundleBudget, formatBundleReport, inspectBundle } from './check-bundle-budget.mjs';

test('bundle budget separates initial and on-demand chunks', () => {
  const manifest = {
    'index.html': { file: 'assets/index.js', isEntry: true, imports: ['_shared.js'] },
    '_shared.js': { file: 'assets/shared.js' },
    'src/lazy.ts': { file: 'assets/lazy.js', isDynamicEntry: true, imports: ['_lazy-dependency.js'] },
    '_lazy-dependency.js': { file: 'assets/lazy-dependency.js' },
  };
  const sizes = {
    'assets/index.js': 10,
    'assets/shared.js': 20,
    'assets/lazy.js': 30,
    'assets/lazy-dependency.js': 40,
  };

  const chunks = inspectBundle(manifest, (file) => sizes[file]);

  assert.deepEqual(
    chunks.map((chunk) => [chunk.source, chunk.loadMode]),
    [
      ['_lazy-dependency.js', 'on-demand'],
      ['src/lazy.ts', 'on-demand'],
      ['_shared.js', 'initial'],
      ['index.html', 'initial'],
    ],
  );
});

test('approved optional engines use their dedicated budget and are reported', () => {
  const manifest = {
    'node_modules/.pnpm/pagedjs@0.4.3/node_modules/pagedjs/src/index.js': {
      file: 'assets/paged.js',
      src: 'node_modules/.pnpm/pagedjs@0.4.3/node_modules/pagedjs/src/index.js',
      isDynamicEntry: true,
    },
  };
  const chunks = inspectBundle(manifest, () => 500 * 1024);

  assert.equal(chunks[0].budget.label, 'Paged.js pagination engine');
  assert.match(formatBundleReport(chunks), /approved: Paged\.js pagination engine/);
  assert.doesNotThrow(() => assertBundleBudget(chunks));
});

test('approved optional engines also match npm manifest source paths', () => {
  const manifest = {
    'node_modules/pagedjs/src/index.js': {
      file: 'assets/paged.js',
      src: 'node_modules/pagedjs/src/index.js',
      isDynamicEntry: true,
    },
    'node_modules/pdfjs-dist/build/pdf.worker.mjs?url': {
      file: 'assets/pdf-worker.js',
      src: 'node_modules/pdfjs-dist/build/pdf.worker.mjs?url',
      isDynamicEntry: true,
    },
  };
  const chunks = inspectBundle(manifest, () => 500 * 1024);

  assert.deepEqual(
    chunks.map((chunk) => chunk.budget.label).sort(),
    ['PDF.js worker', 'Paged.js pagination engine'],
  );
  assert.doesNotThrow(() => assertBundleBudget(chunks));
});

test('unapproved on-demand chunks cannot exceed the default budget', () => {
  const manifest = {
    'src/too-large.ts': { file: 'assets/too-large.js', isDynamicEntry: true },
  };
  const chunks = inspectBundle(manifest, () => 451 * 1024);

  assert.throws(() => assertBundleBudget(chunks), /Bundle budget exceeded/);
});
