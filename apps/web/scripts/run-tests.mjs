import { readdirSync } from 'node:fs';
import { join, relative } from 'node:path';
import { spawnSync } from 'node:child_process';

const sourceRoot = 'src';
const testFilePattern = /\.test\.(?:ts|tsx)$/;

function collectTestFiles(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) => {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) return collectTestFiles(path);
      return testFilePattern.test(entry.name) ? [relative('.', path)] : [];
    })
    .sort();
}

const testFiles = collectTestFiles(sourceRoot);
if (testFiles.length === 0) {
  throw new Error('No frontend test files were found.');
}

const result = spawnSync(
  process.execPath,
  ['--experimental-strip-types', '--test', ...testFiles],
  { stdio: 'inherit' },
);

process.exit(result.status ?? 1);
