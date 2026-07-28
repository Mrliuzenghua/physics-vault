import { useCallback, useState } from 'react';

import { batchGenerateAnalysis } from '../services/api';
import type { BatchAnalysisItemResult, BatchAnalysisResponse } from '../types';

const STYLE_OPTIONS = [
  { value: 'classroom_brief' as const, label: '课堂简析' },
  { value: 'self_study_full' as const, label: '自学详解' },
  { value: 'exam_standard' as const, label: '考标解析' },
];

const STATUS_LABELS: Record<string, string> = {
  success: '成功',
  skipped: '已跳过',
  failed: '失败',
};

const STATUS_COLORS: Record<string, { bg: string; fg: string }> = {
  success: { bg: 'var(--color-green-light)', fg: 'var(--color-green)' },
  skipped: { bg: 'var(--color-orange-light)', fg: 'var(--color-orange)' },
  failed: { bg: 'var(--color-red-light)', fg: 'var(--color-red)' },
};

export default function AiBatchPage() {
  const [idsText, setIdsText] = useState('');
  const [style, setStyle] = useState<'classroom_brief' | 'self_study_full' | 'exam_standard'>('classroom_brief');
  const [includeExtension, setIncludeExtension] = useState(true);
  const [forceRegenerate, setForceRegenerate] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BatchAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleStart = useCallback(async () => {
    const ids = parseIds(idsText);
    if (ids.length === 0) {
      setError('请输入至少一个题目 ID');
      return;
    }
    if (ids.length > 50) {
      setError('单次最多处理 50 道题');
      return;
    }

    setRunning(true);
    setError(null);
    setResult(null);

    try {
      const res = await batchGenerateAnalysis({
        question_ids: ids,
        style,
        include_extension: includeExtension,
        force_regenerate: forceRegenerate,
      });
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '请求失败');
    } finally {
      setRunning(false);
    }
  }, [idsText, style, includeExtension, forceRegenerate]);

  const stats = result;
  const failedItems = result?.results.filter((r) => r.status === 'failed') ?? [];

  return (
    <div className="flex h-full flex-col" style={{ background: 'var(--color-bg)' }}>
      {/* Header */}
      <div
        className="flex-shrink-0 border-b px-4 py-3"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
      >
        <h1 className="text-lg font-bold" style={{ color: 'var(--color-text)' }}>
          批量 AI 元数据生成
        </h1>
        <p className="mt-0.5 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          对一批题目统一生成解析。支持课堂简析、自学详解、考标解析三种风格。
        </p>
      </div>

      {/* Config panel */}
      <div
        className="flex-shrink-0 border-b px-4 py-3 space-y-3"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
      >
        {/* Question IDs */}
        <div>
          <label className="mb-1 block text-xs font-semibold" style={{ color: 'var(--color-text-muted)' }}>
            题目 ID 列表（每行一个，或逗号/空格分隔）
          </label>
          <textarea
            value={idsText}
            onChange={(e) => setIdsText(e.target.value)}
            placeholder="Q00000001&#10;Q00000002&#10;Q00000003"
            rows={5}
            className="w-full rounded border p-2.5 text-sm outline-none resize-y"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-bg)',
              color: 'var(--color-text)',
              minHeight: 80,
              fontFamily: 'monospace',
            }}
          />
        </div>

        {/* Options row */}
        <div className="flex items-center gap-4 flex-wrap">
          {/* Style */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold" style={{ color: 'var(--color-text-muted)' }}>
              解析风格
            </span>
            <div className="flex rounded-lg border overflow-hidden" style={{ borderColor: 'var(--color-border)' }}>
              {STYLE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => setStyle(opt.value)}
                  className="cursor-pointer border-none px-3 py-1 text-xs font-medium transition-colors"
                  style={{
                    background: style === opt.value ? 'var(--color-accent)' : 'transparent',
                    color: style === opt.value ? '#fff' : 'var(--color-text-secondary)',
                    borderRight: '1px solid var(--color-border)',
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Include extension */}
          <label className="flex items-center gap-1.5 text-xs cursor-pointer" style={{ color: 'var(--color-text-secondary)' }}>
            <input
              type="checkbox"
              checked={includeExtension}
              onChange={(e) => setIncludeExtension(e.target.checked)}
            />
            包含知识延展
          </label>

          {/* Force regenerate */}
          <label className="flex items-center gap-1.5 text-xs cursor-pointer" style={{ color: 'var(--color-text-secondary)' }}>
            <input
              type="checkbox"
              checked={forceRegenerate}
              onChange={(e) => setForceRegenerate(e.target.checked)}
            />
            强制重生成
          </label>
        </div>

        {/* Start button */}
        <button
          onClick={handleStart}
          disabled={running}
          className="cursor-pointer rounded-lg border-none px-5 py-2 text-sm font-semibold text-white transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: 'var(--color-accent)' }}
        >
          {running ? '生成中...' : '开始批量生成'}
        </button>
      </div>

      {/* Result area */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* Error */}
        {error && (
          <div
            className="mb-3 rounded-lg p-3 text-sm"
            style={{ background: 'var(--color-red-light)', color: 'var(--color-red)' }}
          >
            {error}
          </div>
        )}

        {/* Summary */}
        {stats && (
          <div
            className="mb-4 rounded-lg border p-4"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
          >
            <h2 className="mb-2 text-sm font-bold" style={{ color: 'var(--color-text)' }}>
              生成完成
            </h2>
            <div className="flex gap-6 text-sm">
              <span style={{ color: 'var(--color-text-muted)' }}>
                总计 <strong style={{ color: 'var(--color-text)' }}>{stats.total}</strong> 题
              </span>
              <span style={{ color: 'var(--color-text-muted)' }}>
                成功 <strong style={{ color: 'var(--color-green)' }}>{stats.success_count}</strong>
              </span>
              <span style={{ color: 'var(--color-text-muted)' }}>
                跳过 <strong style={{ color: 'var(--color-orange)' }}>{stats.skipped_count}</strong>
              </span>
              <span style={{ color: 'var(--color-text-muted)' }}>
                失败 <strong style={{ color: 'var(--color-red)' }}>{stats.failed_count}</strong>
              </span>
            </div>
          </div>
        )}

        {/* Per-item results */}
        {stats && stats.results.length > 0 && (
          <div className="space-y-1.5">
            <h3 className="mb-2 text-xs font-semibold" style={{ color: 'var(--color-text-muted)' }}>
              详细结果
            </h3>
            {stats.results.map((item: BatchAnalysisItemResult) => {
              const colors = STATUS_COLORS[item.status] || STATUS_COLORS.failed;
              return (
                <div
                  key={item.question_id}
                  className="flex items-center gap-3 rounded border px-3 py-2 text-xs"
                  style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
                >
                  <span
                    className="rounded-full px-2 py-0.5 font-medium shrink-0"
                    style={{ background: colors.bg, color: colors.fg }}
                  >
                    {STATUS_LABELS[item.status]}
                  </span>
                  <span className="font-mono" style={{ color: 'var(--color-text)' }}>
                    {item.question_id}
                  </span>
                  <span className="flex-1" style={{ color: 'var(--color-text-secondary)' }}>
                    {item.message}
                  </span>
                  {item.saved_to_db && (
                    <span className="text-xs" style={{ color: 'var(--color-green)' }}>
                      已入库
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Failed items highlight */}
        {failedItems.length > 0 && (
          <div
            className="mt-4 rounded-lg border p-3"
            style={{ borderColor: 'var(--color-red)', background: 'var(--color-red-light)' }}
          >
            <h4 className="mb-1 text-xs font-semibold" style={{ color: 'var(--color-red)' }}>
              失败题目（{failedItems.length} 题）
            </h4>
            <div className="text-xs" style={{ color: 'var(--color-red)' }}>
              {failedItems.map((item) => (
                <div key={item.question_id}>
                  {item.question_id}: {item.message}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!running && !error && !stats && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="mb-3 text-4xl">AI</div>
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                在上方输入题目 ID 并选择风格后，点击开始批量生成
              </p>
              <p className="mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                已有解析的题目不会被重复生成（除非勾选强制重生成）
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Parse user input into a clean list of question IDs. */
function parseIds(raw: string): string[] {
  return raw
    .split(/[\n,，\s]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}
