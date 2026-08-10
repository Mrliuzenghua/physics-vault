import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

type TimelineModule = {
  getVisibleStageEvents: (events: Array<Record<string, unknown>>, expanded: boolean) => Array<Record<string, unknown>>;
  formatStageDuration: (event: { duration_ms: number | null; started_at: string; finished_at: string | null }) => string;
};

async function loadTimelineModule(): Promise<TimelineModule> {
  const path = fileURLToPath(new URL('./TaskStageTimeline.tsx', import.meta.url));
  const source = readFileSync(path, 'utf8')
    .replace(/^import[\s\S]*?;\s*$/gm, '')
    .replace('export default function TaskStageTimeline', 'function TaskStageTimeline')
    .replace(/export function /g, 'function ');
  const output = ts.transpileModule(`${source}\nexport { getVisibleStageEvents, formatStageDuration };`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.React },
  }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(`const React = { createElement: () => null };\n${output}`).toString('base64')}`) as Promise<TimelineModule>;
}

function event(index: number) {
  return {
    event_id: `event-${index}`,
    started_at: `2026-01-01T00:${String(index).padStart(2, '0')}:00.000Z`,
    finished_at: null,
  };
}

test('keeps large task timelines readable until the user expands them', async () => {
  const { getVisibleStageEvents } = await loadTimelineModule();
  const events = Array.from({ length: 14 }, (_, index) => event(13 - index));

  assert.equal(getVisibleStageEvents(events, false).length, 12);
  assert.equal(getVisibleStageEvents(events, false)[0]?.event_id, 'event-2');
  assert.equal(getVisibleStageEvents(events, true).length, 14);
  assert.equal(getVisibleStageEvents(events, true)[0]?.event_id, 'event-0');
});

test('formats completed and in-progress stage durations', async () => {
  const { formatStageDuration } = await loadTimelineModule();

  assert.equal(formatStageDuration({ duration_ms: 420, started_at: '', finished_at: null }), '420 ms');
  assert.equal(formatStageDuration({ duration_ms: 2_400, started_at: '', finished_at: null }), '2.4 秒');
  assert.equal(formatStageDuration({ duration_ms: null, started_at: '2026-01-01T00:00:00.000Z', finished_at: '2026-01-01T00:00:03.100Z' }), '3 秒');
  assert.equal(formatStageDuration({ duration_ms: null, started_at: '2026-01-01T00:00:00.000Z', finished_at: null }), '进行中');
});

test('keeps the timeline accessible and trace diagnostics actionable', () => {
  const path = fileURLToPath(new URL('./TaskStageTimeline.tsx', import.meta.url));
  const source = readFileSync(path, 'utf8');

  assert.match(source, /aria-label="任务执行阶段时间线"/);
  assert.match(source, /复制 trace_id/);
  assert.match(source, /显示较早的/);
  assert.match(source, /error_code/);
  assert.match(source, /recommended_action/);
});
