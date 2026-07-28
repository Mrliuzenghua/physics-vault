import type { ComposeItem } from '../../types';

interface Props {
  items: ComposeItem[];
  selectedIndex: number;
  onSelect: (index: number) => void;
  onMoveUp: (index: number) => void;
  onMoveDown: (index: number) => void;
  onRemove: (index: number) => void;
}

const ITEM_META: Record<string, { label: string; badge: string }> = {
  question: { label: '题目', badge: 'Q' },
  knowledge: { label: '知识点', badge: 'K' },
  text: { label: '文本', badge: 'T' },
  separator: { label: '分页', badge: 'P' },
};

export default function ComposeItemRow({
  items,
  selectedIndex,
  onSelect,
  onMoveUp,
  onMoveDown,
  onRemove,
}: Props) {
  return (
    <div className="space-y-1.5">
      {items.map((item, index) => {
        const isSelected = index === selectedIndex;
        const isFirst = index === 0;
        const isLast = index === items.length - 1;
        const meta = ITEM_META[item.type];

        const title =
          item.type === 'question'
            ? item.question?.title || item.questionId
            : item.type === 'knowledge'
              ? item.title
              : item.title;

        const subline =
          item.type === 'question'
            ? item.question?.question_id || item.questionId
            : item.type === 'knowledge'
              ? `${item.points.length} 个要点`
              : item.type === 'text'
                ? `${item.content.length} 字`
                : '手动分页';

        return (
          <div
            key={item.id}
            role="button"
            tabIndex={0}
            onClick={() => onSelect(index)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onSelect(index);
              }
            }}
            className={`flex w-full items-start gap-3 rounded-xl border px-3 py-3 text-left transition-colors ${
              isSelected
                ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)] shadow-sm'
                : 'border-[var(--color-border)] bg-[var(--color-bg-card)] hover:border-[var(--color-accent)]/40 hover:bg-[var(--color-bg-hover)]'
            }`}
          >
            <div className="flex flex-col items-center gap-1">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--color-bg-hover)] text-[11px] font-bold text-[var(--color-text-muted)]">
                {meta.badge}
              </span>
              <span className="text-[10px] font-semibold text-[var(--color-text-subtle)]">
                {index + 1}
              </span>
            </div>
            <div className="min-w-0 flex-1">
              <div className="mb-1 flex items-center gap-2">
                <span className="rounded-full bg-[var(--color-bg-hover)] px-2 py-0.5 text-[10px] font-semibold text-[var(--color-text-muted)]">
                  {meta.label}
                </span>
                <span className="truncate text-[11px] text-[var(--color-text-subtle)]">
                  {subline}
                </span>
              </div>
              <div className="line-clamp-2 text-sm font-semibold leading-5 text-[var(--color-text-main)]">
                {title}
              </div>
            </div>
            <div className="flex items-center gap-1 pt-0.5 text-[var(--color-text-subtle)]">
              <button
                type="button"
                disabled={isFirst}
                onClick={(event) => {
                  event.stopPropagation();
                  onMoveUp(index);
                }}
                className="rounded-md px-1.5 py-1 text-xs hover:bg-[var(--color-bg-hover)] disabled:opacity-30"
              >
                ↑
              </button>
              <button
                type="button"
                disabled={isLast}
                onClick={(event) => {
                  event.stopPropagation();
                  onMoveDown(index);
                }}
                className="rounded-md px-1.5 py-1 text-xs hover:bg-[var(--color-bg-hover)] disabled:opacity-30"
              >
                ↓
              </button>
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onRemove(index);
                }}
                className="rounded-md px-1.5 py-1 text-xs hover:bg-[var(--color-danger-soft)] hover:text-[var(--color-danger)]"
              >
                ×
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
