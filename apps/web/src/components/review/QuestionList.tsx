import type { ReviewQuestionDraft } from '../../types';

const STATUS_LABELS: Record<string, string> = {
  pending: '待确认',
  modified: '已修改',
  discarded: '已丢弃',
  confirmed: '已确认',
};

const STATUS_COLORS: Record<string, { bg: string; fg: string }> = {
  pending: { bg: 'var(--color-orange-light)', fg: 'var(--color-orange)' },
  modified: { bg: 'var(--color-accent-light)', fg: 'var(--color-accent)' },
  discarded: { bg: 'var(--color-red-light)', fg: 'var(--color-red)' },
  confirmed: { bg: 'var(--color-green-light)', fg: 'var(--color-green)' },
};

const TYPE_LABELS: Record<string, string> = {
  single_choice: '单选',
  multi_choice: '多选',
  fill: '填空',
  experiment: '实验',
  calculation: '计算',
};

interface QuestionListProps {
  drafts: ReviewQuestionDraft[];
  currentIndex: number;
  onSelect: (index: number) => void;
}

export default function QuestionList({ drafts, currentIndex, onSelect }: QuestionListProps) {
  const totalCount = drafts.length;
  const keptCount = drafts.filter((d) => d.status !== 'discarded').length;
  const discardedCount = drafts.filter((d) => d.status === 'discarded').length;

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
          题目列表
        </h2>
        <div
          className="mt-1.5 flex gap-3 text-xs"
          style={{ color: 'var(--color-text-muted)' }}
        >
          <span>
            共 <strong style={{ color: 'var(--color-text)' }}>{totalCount}</strong> 题
          </span>
          <span>
            保留{' '}
            <strong style={{ color: 'var(--color-green)' }}>
              {keptCount}
            </strong>
          </span>
          <span>
            丢弃{' '}
            <strong style={{ color: 'var(--color-red)' }}>
              {discardedCount}
            </strong>
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {drafts.length === 0 ? (
          <div className="px-3 py-8 text-center text-xs" style={{ color: 'var(--color-text-muted)' }}>
            暂无题目
          </div>
        ) : (
          <div className="py-1">
            {drafts.map((draft, index) => {
              const isCurrent = index === currentIndex;
              const status = draft.status;
              const colors = STATUS_COLORS[status] || STATUS_COLORS.pending;
              const typeLabel = TYPE_LABELS[draft.question_type] || draft.question_type;
              const titlePreview =
                draft.title.length > 40 ? `${draft.title.slice(0, 40)}…` : draft.title;

              return (
                <button
                  key={draft.question_id}
                  onClick={() => onSelect(index)}
                  className="w-full cursor-pointer border-b px-3 py-2.5 text-left transition-colors last:border-b-0"
                  style={{
                    borderColor: 'var(--color-border)',
                    background: isCurrent ? 'var(--color-bg-hover)' : 'transparent',
                    borderLeft: isCurrent
                      ? '3px solid var(--color-accent)'
                      : '3px solid transparent',
                    opacity: status === 'discarded' ? 0.5 : 1,
                  }}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="flex-shrink-0 text-xs font-bold"
                      style={{
                        color: isCurrent ? 'var(--color-accent)' : 'var(--color-text-muted)',
                        minWidth: '1.5rem',
                      }}
                    >
                      {index + 1}
                    </span>
                    <span
                      className="flex-shrink-0 rounded px-1 py-0.5 text-[10px] font-medium"
                      style={{ background: colors.bg, color: colors.fg }}
                    >
                      {STATUS_LABELS[status]}
                    </span>
                    <span
                      className="flex-shrink-0 text-[10px]"
                      style={{ color: 'var(--color-text-muted)' }}
                    >
                      {typeLabel}
                    </span>
                  </div>
                  <div
                    className="mt-1 text-xs leading-snug"
                    style={{
                      color: isCurrent ? 'var(--color-text)' : 'var(--color-text-secondary)',
                      textDecoration: status === 'discarded' ? 'line-through' : 'none',
                    }}
                  >
                    {titlePreview || '(无题干)'}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
