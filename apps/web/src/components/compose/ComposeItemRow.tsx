import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DraggableAttributes,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useVirtualizer } from '@tanstack/react-virtual';
import { useRef, type CSSProperties, type ReactNode } from 'react';
import type { ComposeItem, Question } from '../../types';

interface Props {
  items: ComposeItem[];
  selectedIndex: number;
  selectedIds: Set<string>;
  onSelect: (index: number) => void;
  onToggleSelected: (id: string) => void;
  onMoveUp: (index: number) => void;
  onMoveDown: (index: number) => void;
  onRemove: (index: number) => void;
  onReorder: (from: number, to: number) => void;
}

const ITEM_META: Record<string, { label: string; badge: string; tone: string }> = {
  question: { label: '题目', badge: 'Q', tone: 'var(--color-accent)' },
  knowledge: { label: '知识目录', badge: 'K', tone: 'var(--color-purple)' },
  text: { label: '文本', badge: 'T', tone: 'var(--color-teal)' },
  separator: { label: '分页', badge: 'P', tone: 'var(--color-orange)' },
};

const QUESTION_TYPE_LABELS: Record<string, string> = {
  single_choice: '单选',
  multi_choice: '多选',
  fill: '填空',
  experiment: '实验',
  calculation: '计算',
};

function normalizeSnippet(value?: string | null, fallback = '-'): string {
  const text = String(value || '')
    .replace(/!\[fig:[^\]]+\]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  return text || fallback;
}

function buildQuestionChips(question?: Question): string[] {
  if (!question) return ['未加载'];
  const chips = [
    QUESTION_TYPE_LABELS[question.question_type] || question.question_type,
    question.answer ? `答案 ${normalizeSnippet(question.answer)}` : '缺答案',
    question.difficulty ? `难度 ${question.difficulty}` : '难度 -',
  ];
  const source = normalizeSnippet(question.source || question.primary_paper_id, '');
  if (source) chips.push(source);
  const topic = normalizeSnippet(
    question.topic3 || question.topic2 || question.knowledge_point || question.knowledge_points?.[0]?.topic3_name,
    '',
  );
  if (topic) chips.push(topic);
  if (question.review_status) chips.push(question.review_status === 'approved' ? '已审核' : question.review_status);
  return chips.slice(0, 2);
}

type SortableState = ReturnType<typeof useSortable>;

interface SortableRowProps {
  id: string;
  layoutStyle?: CSSProperties;
  measureElement?: (node: Element | null) => void;
  children: (props: {
    setActivatorNodeRef: SortableState['setActivatorNodeRef'];
    listeners: SortableState['listeners'];
    attributes: DraggableAttributes;
  }) => ReactNode;
}

function SortableRow({ id, layoutStyle, measureElement, children }: SortableRowProps) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <div
      ref={(node) => { setNodeRef(node); measureElement?.(node); }}
      style={{ ...layoutStyle, transform: `${layoutStyle?.transform || ''} ${CSS.Transform.toString(transform) || ''}`.trim() || undefined, transition, opacity: isDragging ? 0.55 : undefined, zIndex: isDragging ? 1 : undefined }}
      className="relative"
    >
      {children({ setActivatorNodeRef, listeners, attributes })}
    </div>
  );
}

export default function ComposeItemRow({
  items,
  selectedIndex,
  selectedIds,
  onSelect,
  onToggleSelected,
  onMoveUp,
  onMoveDown,
  onRemove,
  onReorder,
}: Props) {
  const listScrollRef = useRef<HTMLDivElement | null>(null);
  const virtualMode = items.length >= 24;
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => listScrollRef.current,
    estimateSize: () => 76,
    overscan: 8,
  });
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = items.findIndex((item) => item.id === active.id);
    const to = items.findIndex((item) => item.id === over.id);
    if (from >= 0 && to >= 0 && from !== to) onReorder(from, to);
  };
  const visibleItems = virtualMode
    ? virtualizer.getVirtualItems().map((virtualItem) => ({
      item: items[virtualItem.index],
      index: virtualItem.index,
      key: virtualItem.key,
      start: virtualItem.start,
    }))
    : items.map((item, index) => ({ item, index, key: item.id, start: 0 }));

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={items.map((item) => item.id)} strategy={verticalListSortingStrategy}>
        <div ref={listScrollRef} className={virtualMode ? 'max-h-[calc(100vh-270px)] overflow-y-auto pr-1' : undefined}>
          <div className="space-y-1.5" style={virtualMode ? { height: `${virtualizer.getTotalSize()}px`, position: 'relative' } : undefined}>
          {visibleItems.map(({ item, index, key, start }) => {
            const isSelected = index === selectedIndex;
            const isBatchSelected = selectedIds.has(item.id);
            const meta = ITEM_META[item.type];
            const title = item.type === 'question' ? item.question?.title || item.questionId : item.title;
            const subline = item.type === 'question'
              ? item.question?.question_id || item.questionId
              : item.type === 'knowledge'
                ? `${item.points.length} 个要点`
                : item.type === 'text'
                  ? `${item.content.length} 字`
                  : '手动分页';
            const questionChips = item.type === 'question' ? buildQuestionChips(item.question) : [];

            return (
              <SortableRow
                key={key}
                id={item.id}
                measureElement={virtualMode ? virtualizer.measureElement : undefined}
                layoutStyle={virtualMode ? { position: 'absolute', top: 0, left: 0, width: '100%', paddingBottom: '5px', transform: `translateY(${start}px)` } : undefined}
              >
                {({ setActivatorNodeRef, listeners, attributes }) => (
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() => onSelect(index)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        onSelect(index);
                      }
                    }}
                    className={`group flex w-full items-start gap-1.5 rounded-md border px-1.5 py-1.5 text-left transition-colors duration-150 ${
                      isSelected
                        ? 'border-[var(--color-accent)]/45 bg-[var(--color-accent-light)] shadow-[inset_2px_0_0_var(--color-accent)]'
                        : isBatchSelected
                          ? 'border-[#9fc4ee] bg-[#f0f7ff] shadow-[var(--shadow-sm)]'
                          : 'border-transparent bg-[var(--color-bg-card)] shadow-[var(--shadow-sm)] hover:border-[var(--color-border-strong)]'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={isBatchSelected}
                      onChange={() => onToggleSelected(item.id)}
                      onClick={(event) => event.stopPropagation()}
                      aria-label={`选择第 ${index + 1} 个对象`}
                      className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[#2567b8]"
                    />
                    <span
                      ref={setActivatorNodeRef}
                      {...listeners}
                      {...attributes}
                      className="mt-0.5 w-2 cursor-grab select-none text-center text-[10px] leading-none text-[var(--color-text-subtle)] opacity-0 transition-opacity group-hover:opacity-100 active:cursor-grabbing"
                      title="拖拽调整顺序"
                    >
                      ⠿
                    </span>
                    <div className="flex w-5 shrink-0 flex-col items-center gap-0.5">
                      <span className="flex h-5 w-5 items-center justify-center rounded text-[8px] font-bold text-white" style={{ background: meta.tone }}>
                        {meta.badge}
                      </span>
                      <span className="text-[7px] font-semibold tabular-nums leading-none text-[var(--color-text-subtle)]">{index + 1}</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1">
                        <span className="rounded px-0.5 py-px text-[7px] font-semibold leading-3" style={{ background: 'var(--color-bg-hover)', color: meta.tone }}>{meta.label}</span>
                        <span className="truncate text-[8px] leading-3 text-[var(--color-text-subtle)]">{subline}</span>
                      </div>
                      <div className="truncate text-[10px] font-semibold leading-4 text-[var(--color-text-main)]">{title}</div>
                      {questionChips.length > 0 && (
                        <div className="mt-0.5 flex flex-wrap gap-0.5">
                          {questionChips.map((chip) => <span key={chip} className="max-w-[112px] truncate rounded border border-[var(--color-border)] bg-[var(--color-bg-code)] px-1 py-px text-[8px] font-medium leading-3 text-[var(--color-text-muted)]" title={chip}>{chip}</span>)}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-0.5 pt-0.5 text-[var(--color-text-subtle)] opacity-0 transition-opacity group-hover:opacity-100">
                      <button type="button" disabled={index === 0} onClick={(event) => { event.stopPropagation(); onMoveUp(index); }} className="rounded px-0.5 py-0 text-[10px] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text)] disabled:opacity-30" title="上移">↑</button>
                      <button type="button" disabled={index === items.length - 1} onClick={(event) => { event.stopPropagation(); onMoveDown(index); }} className="rounded px-0.5 py-0 text-[10px] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text)] disabled:opacity-30" title="下移">↓</button>
                      <button type="button" onClick={(event) => { event.stopPropagation(); onRemove(index); }} className="rounded px-0.5 py-0 text-[10px] hover:bg-[var(--color-danger-soft)] hover:text-[var(--color-danger)]" title="删除">×</button>
                    </div>
                  </div>
                )}
              </SortableRow>
            );
          })}
          </div>
        </div>
      </SortableContext>
    </DndContext>
  );
}
