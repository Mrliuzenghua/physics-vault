import { Button } from '../ui/Button';
import type { SavedLessonPackageSummary } from '../../types';

interface Props {
  packages: SavedLessonPackageSummary[];
  activeId?: string | null;
  title?: string;
  emptyText?: string;
  onOpen: (id: string) => void;
  onDelete?: (id: string) => void;
  onSaveCurrent?: () => void;
}

export default function LessonPackageTree({
  packages,
  activeId,
  title = '已保存作品',
  emptyText = '还没有保存的讲义作品',
  onOpen,
  onDelete,
  onSaveCurrent,
}: Props) {
  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-sidebar)] p-3">
      <div className="pv-panel p-3">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="text-sm font-semibold text-[var(--color-text-main)]">{title}</div>
          {onSaveCurrent && (
            <Button size="sm" onClick={onSaveCurrent}>
              保存当前
            </Button>
          )}
        </div>

        {packages.length === 0 ? (
          <div className="rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-bg-hover)] px-4 py-6 text-sm text-[var(--color-text-subtle)]">
            {emptyText}
          </div>
        ) : (
          <div className="space-y-1.5">
            {packages.map((pkg) => {
              const active = pkg.id === activeId;
              return (
                <div
                  key={pkg.id}
                  className={`rounded-md border px-3 py-2.5 ${
                    active
                      ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)]'
                      : 'border-[var(--color-border)] bg-[var(--color-bg-card)]'
                  }`}
                >
                  <button type="button" onClick={() => onOpen(pkg.id)} className="w-full text-left">
                    <div className="truncate text-sm font-semibold text-[var(--color-text-main)]">{pkg.title}</div>
                    <div className="mt-1 truncate text-xs text-[var(--color-text-muted)]">{pkg.subtitle}</div>
                    <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-[var(--color-text-subtle)]">
                      <span>{pkg.questionCount} 题</span>
                      <span>{pkg.knowledgeCount} 知识点</span>
                      <span>{pkg.nodeCount} 节点</span>
                    </div>
                  </button>
                  {onDelete && (
                    <div className="mt-2 flex justify-end">
                      <button
                        type="button"
                        onClick={() => onDelete(pkg.id)}
                        className="text-xs text-[var(--color-danger)]"
                      >
                        删除
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </aside>
  );
}
