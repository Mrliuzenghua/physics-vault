import assert from 'node:assert/strict';
import test from 'node:test';

import { decodeMathHtmlEntities, mathFormulaToEditorHtml } from './mathText.ts';

test('decodes single and repeated HTML entities inside formulas', () => {
  assert.equal(decodeMathHtmlEntities('F_{2} &gt; F_{1}'), 'F_{2} > F_{1}');
  assert.equal(decodeMathHtmlEntities('F_{2} &amp;gt; F_{1}'), 'F_{2} > F_{1}');
});

test('editor HTML escapes formula attributes exactly once', () => {
  const html = mathFormulaToEditorHtml('F_{2} > F_{1}');

  assert.match(html, /data-question-formula="F_\{2\} &gt; F_\{1\}"/);
  assert.doesNotMatch(html, /&amp;gt;/);
});
