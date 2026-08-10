import assert from 'node:assert/strict';
import test from 'node:test';

import { findNextMatchingIndex } from './reviewQueueNavigation.ts';

test('moves from a confirmed pending item to the next pending item', () => {
  const statuses = ['pending', 'confirmed', 'pending', 'pending'];

  assert.equal(
    findNextMatchingIndex(statuses, 0, (status) => status === 'pending'),
    2,
  );
});

test('moves from a confirmed risk item to the next risk item', () => {
  const risks = [true, false, true, true];

  assert.equal(
    findNextMatchingIndex(risks, 0, (isRisk) => isRisk),
    2,
  );
});

test('wraps within the active queue and never reselects the current item', () => {
  const pending = [true, false, true];

  assert.equal(
    findNextMatchingIndex(pending, 2, (isPending) => isPending),
    0,
  );
  assert.equal(
    findNextMatchingIndex([true], 0, (isPending) => isPending),
    null,
  );
});
