import assert from 'node:assert/strict';
import test from 'node:test';

import { responseFileName } from './fileDownload.ts';

test('responseFileName decodes RFC 5987 filenames', () => {
  const response = new Response(null, {
    headers: { 'Content-Disposition': "attachment; filename*=UTF-8''%E7%89%A9%E7%90%86%E8%AF%95%E5%8D%B7.docx" },
  });

  assert.equal(responseFileName(response, 'fallback.docx'), '物理试卷.docx');
});

test('responseFileName supports quoted names and fallback', () => {
  const quoted = new Response(null, {
    headers: { 'Content-Disposition': 'attachment; filename="paper.pptx"' },
  });
  assert.equal(responseFileName(quoted, 'fallback.pptx'), 'paper.pptx');
  assert.equal(responseFileName(new Response(), 'fallback.zip'), 'fallback.zip');
});
