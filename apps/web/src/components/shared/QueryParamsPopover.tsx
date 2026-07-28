import { useEffect, useRef } from 'react';
import type { SearchFilters } from '../../types';

interface Props {
  open: boolean;
  onClose: () => void;
  filters: SearchFilters;
  total: number;
}

const FIELD_LABELS: Array<{ key: keyof SearchFilters; label: string }> = [
  { key: 'query', label: '关键词' },
  { key: 'year', label: '年份' },
  { key: 'module', label: '模块' },
  { key: 'question_type', label: '题型' },
  { key: 'difficulty', label: '难度' },
  { key: 'topic1_id', label: '一级考点' },
  { key: 'topic2_id', label: '二级考点' },
  { key: 'topic3_id', label: '三级考点' },
  { key: 'status', label: '状态' },
];

export default function QueryParamsPopover({ open, onClose, filters, total }: Props) {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;

    function handlePointerDown(event: MouseEvent) {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(event.target as Node)) {
        onClose();
      }
    }

    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [open, onClose]);

  if (!open) return null;

  const conditionItems = FIELD_LABELS
    .map(({ key, label }) => {
      const value = filters[key];
      if (value === undefined || value === null || value === '') return null;
      return { label, value: String(value) };
    })
    .filter(Boolean) as Array<{ label: string; value: string }>;

  return (
    <div
      ref={rootRef}
      className="absolute right-[calc(100%+12px)] top-0 z-40 w-[360px] overflow-hidden rounded-2xl border border-[#d5dfef] bg-white shadow-[0_18px_40px_rgba(22,40,79,0.16)]"
    >
      <div className="flex items-center justify-between bg-[#3f536f] px-4 py-3 text-white">
        <div>
          <div className="text-base font-semibold">查询参数报告</div>
          <div className="mt-1 text-xs text-white/70">{conditionItems.length} 项</div>
        </div>
        <button
          onClick={onClose}
          className="rounded-md px-2 py-1 text-sm text-white/80 transition-colors hover:bg-white/10 hover:text-white"
        >
          ×
        </button>
      </div>

      <div className="space-y-4 px-4 py-4 text-sm text-[#4d5e77]">
        <div>
          <div className="mb-2 text-xs font-semibold tracking-wide text-[#6f809b]">排序逻辑</div>
          <div className="rounded-xl bg-[#f5f8fc] px-3 py-3 text-sm text-[#40536f]">
            年份 &gt; 标题 &gt; 题号 &gt; 时间
          </div>
        </div>

        <div>
          <div className="mb-2 text-xs font-semibold tracking-wide text-[#6f809b]">当前筛选条件</div>
          {conditionItems.length > 0 ? (
            <div className="space-y-2">
              {conditionItems.map((item) => (
                <div key={`${item.label}-${item.value}`} className="flex items-center justify-between rounded-xl bg-[#f8fbff] px-3 py-2">
                  <span className="text-[#71839c]">{item.label}</span>
                  <span className="font-medium text-[#334863]">{item.value}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl bg-[#f8fbff] px-3 py-3 text-[#8a97aa]">
              当前没有额外筛选条件，默认按当前知识点范围查询。
            </div>
          )}
        </div>

        <div>
          <div className="mb-2 text-xs font-semibold tracking-wide text-[#6f809b]">结果规模</div>
          <div className="rounded-xl border border-[#e4ebf5] bg-white px-3 py-3">
            符合条件的题目共 <span className="font-semibold text-[#f08a38]">{total}</span> 道
          </div>
        </div>
      </div>
    </div>
  );
}
