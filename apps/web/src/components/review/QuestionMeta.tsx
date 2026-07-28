import type { ReviewQuestionDraft } from '../../types';

const TYPE_LABELS: Record<string, string> = {
  single_choice: '单选题',
  multi_choice: '多选题',
  fill: '填空题',
  experiment: '实验题',
  calculation: '计算题',
};

interface QuestionMetaProps {
  draft: ReviewQuestionDraft;
  currentIndex: number;
  totalCount: number;
  onConfirm: () => void;
  onMarkModified: () => void;
  onRestore: () => void;
  onDiscard: () => void;
  onRestoreDiscarded: () => void;
  onPrev: () => void;
  onNext: () => void;
  onJump: (index: number) => void;
  onGenerateAnalysis?: (draft: ReviewQuestionDraft) => void;
  aiProcessing?: boolean;
}

export default function QuestionMeta({
  draft,
  currentIndex,
  totalCount,
  onConfirm,
  onMarkModified,
  onRestore,
  onDiscard,
  onRestoreDiscarded,
  onPrev,
  onNext,
  onJump,
  onGenerateAnalysis,
  aiProcessing,
}: QuestionMetaProps) {
  const isModified = draft.status === 'modified';
  const isDiscarded = draft.status === 'discarded';
  const isConfirmed = draft.status === 'confirmed';

  return (
    <div className="flex h-full flex-col">
      <div
        className="flex-shrink-0 border-b px-3 py-3"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <h2
          className="text-sm font-semibold"
          style={{ color: 'var(--color-text)' }}
        >
          题目信息
        </h2>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-3">
        {/* 题目导航 */}
        <div className="rounded-lg border p-3" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}>
          <div className="mb-2 text-center text-xs" style={{ color: 'var(--color-text-muted)' }}>
            第{' '}
            <strong style={{ color: 'var(--color-text)' }}>{currentIndex + 1}</strong>{' '}
            / {totalCount} 题
          </div>
          <div className="flex gap-1.5">
            <button
              onClick={onPrev}
              disabled={currentIndex <= 0}
              className="flex-1 cursor-pointer rounded border px-2 py-1.5 text-xs transition-colors disabled:opacity-30"
              style={{
                borderColor: 'var(--color-border)',
                background: 'var(--color-bg-hover)',
                color: 'var(--color-text-secondary)',
              }}
            >
              ← 上一题
            </button>
            <button
              onClick={onNext}
              disabled={currentIndex >= totalCount - 1}
              className="flex-1 cursor-pointer rounded border px-2 py-1.5 text-xs transition-colors disabled:opacity-30"
              style={{
                borderColor: 'var(--color-border)',
                background: 'var(--color-bg-hover)',
                color: 'var(--color-text-secondary)',
              }}
            >
              下一题 →
            </button>
          </div>
        </div>

        {/* 题目状态信息 */}
        <div className="rounded-lg border p-3" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}>
          <h3
            className="mb-2 text-xs font-semibold uppercase tracking-wider"
            style={{ color: 'var(--color-text-muted)' }}
          >
            状态信息
          </h3>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span style={{ color: 'var(--color-text-muted)' }}>题号</span>
              <span style={{ color: 'var(--color-text-secondary)' }}>{draft.question_id}</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: 'var(--color-text-muted)' }}>题型</span>
              <span style={{ color: 'var(--color-text-secondary)' }}>
                {TYPE_LABELS[draft.question_type] || draft.question_type}
              </span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: 'var(--color-text-muted)' }}>状态</span>
              <span
                className="rounded-full px-2 py-0.5 text-xs font-medium"
                style={{
                  background: isDiscarded
                    ? 'var(--color-red-light)'
                    : isModified
                      ? 'var(--color-accent-light)'
                      : isConfirmed
                        ? 'var(--color-green-light)'
                        : 'var(--color-orange-light)',
                  color: isDiscarded
                    ? 'var(--color-red)'
                    : isModified
                      ? 'var(--color-accent)'
                      : isConfirmed
                        ? 'var(--color-green)'
                        : 'var(--color-orange)',
                }}
              >
                {isDiscarded ? '已丢弃' : isModified ? '已修改' : isConfirmed ? '已确认' : '待确认'}
              </span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: 'var(--color-text-muted)' }}>难度</span>
              <span style={{ color: 'var(--color-text-secondary)' }}>
                {draft.difficulty !== null ? draft.difficulty : '-'}
              </span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: 'var(--color-text-muted)' }}>选项数</span>
              <span style={{ color: 'var(--color-text-secondary)' }}>
                {draft.options.length || '-'}
              </span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: 'var(--color-text-muted)' }}>子问题数</span>
              <span style={{ color: 'var(--color-text-secondary)' }}>
                {draft.sub_questions.length || '-'}
              </span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: 'var(--color-text-muted)' }}>图片数</span>
              <span style={{ color: 'var(--color-text-secondary)' }}>
                {draft.figures.length || '-'}
              </span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: 'var(--color-text-muted)' }}>标签数</span>
              <span style={{ color: 'var(--color-text-secondary)' }}>
                {draft.tags.length || '-'}
              </span>
            </div>
          </div>
        </div>

        {/* 操作区 */}
        <div className="rounded-lg border p-3" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}>
          <h3
            className="mb-2 text-xs font-semibold uppercase tracking-wider"
            style={{ color: 'var(--color-text-muted)' }}
          >
            操作
          </h3>
          <div className="space-y-1.5">
            {!isDiscarded && (
              <>
                {onGenerateAnalysis && (
                  <button
                    onClick={() => onGenerateAnalysis(draft)}
                    disabled={aiProcessing}
                    className="w-full cursor-pointer rounded border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50"
                    style={{
                      borderColor: '#a78bfa',
                      background: 'rgba(167,139,250,0.08)',
                      color: '#a78bfa',
                    }}
                  >
                    🤖 AI 生成解析
                  </button>
                )}
                <button
                  onClick={onConfirm}
                  disabled={isConfirmed}
                  className="w-full cursor-pointer rounded border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-30"
                  style={{
                    borderColor: 'var(--color-green)',
                    background: isConfirmed ? 'var(--color-green-light)' : 'transparent',
                    color: 'var(--color-green)',
                  }}
                >
                  {isConfirmed ? '✓ 已确认' : '确认本题'}
                </button>
                <button
                  onClick={onMarkModified}
                  disabled={isConfirmed}
                  className="w-full cursor-pointer rounded border px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-30"
                  style={{
                    borderColor: 'var(--color-accent)',
                    background: isModified ? 'var(--color-accent-light)' : 'transparent',
                    color: 'var(--color-accent)',
                  }}
                >
                  {isModified ? '✓ 已标记修改' : '标记已修改'}
                </button>
                <button
                  onClick={onRestore}
                  disabled={!isModified}
                  className="w-full cursor-pointer rounded border px-3 py-1.5 text-xs transition-colors disabled:opacity-30"
                  style={{
                    borderColor: 'var(--color-border)',
                    background: 'var(--color-bg-hover)',
                    color: 'var(--color-text-secondary)',
                  }}
                >
                  恢复原始内容
                </button>
                <button
                  onClick={onDiscard}
                  className="w-full cursor-pointer rounded border px-3 py-1.5 text-xs font-medium transition-colors"
                  style={{
                    borderColor: 'var(--color-red)',
                    background: 'transparent',
                    color: 'var(--color-red)',
                  }}
                >
                  丢弃本题
                </button>
              </>
            )}
            {isDiscarded && (
              <button
                onClick={onRestoreDiscarded}
                className="w-full cursor-pointer rounded border px-3 py-1.5 text-xs font-medium transition-colors"
                style={{
                  borderColor: 'var(--color-green)',
                  background: 'var(--color-green-light)',
                  color: 'var(--color-green)',
                }}
              >
                恢复本题
              </button>
            )}
          </div>
        </div>

        {/* 快速跳转 */}
        <div className="rounded-lg border p-3" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}>
          <h3
            className="mb-1.5 text-xs font-semibold uppercase tracking-wider"
            style={{ color: 'var(--color-text-muted)' }}
          >
            快速跳转
          </h3>
          <input
            type="number"
            min={1}
            max={totalCount}
            placeholder={`1-${totalCount}`}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                const n = Number((e.target as HTMLInputElement).value);
                if (n >= 1 && n <= totalCount) {
                  onJump(n - 1);
                  (e.target as HTMLInputElement).value = '';
                }
              }
            }}
            className="w-full rounded border px-2 py-1.5 text-xs outline-none"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-bg-hover)',
              color: 'var(--color-text)',
            }}
          />
        </div>
      </div>
    </div>
  );
}
