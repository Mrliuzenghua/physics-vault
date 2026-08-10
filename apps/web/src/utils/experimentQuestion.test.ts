import assert from 'node:assert/strict';
import test from 'node:test';

import { mergeExperimentStepsIntoTitle } from './experimentQuestion.ts';

test('moves OCR A/B/C procedures into the experiment stem', () => {
  assert.equal(
    mergeExperimentStepsIntoTitle('实验装置如图所示。', [
      { opt: 'A', content: '调节电场。' },
      { opt: 'B', content: '记录数据。' },
    ]),
    '实验装置如图所示。\n\n实验步骤：\n\n（1）调节电场。\n\n（2）记录数据。',
  );
});
