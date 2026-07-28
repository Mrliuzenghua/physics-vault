import { useCallback, useEffect, useRef, useState } from 'react';
import { createAnnotation, deleteAnnotation, fetchAnnotations, updateAnnotation } from '../../services/api';
import type { AnnotationType, QuestionAnnotation } from '../../types';
import { ANNOTATION_COLORS, ANNOTATION_TYPE_LABELS } from '../../types';

const TYPE_OPTIONS = Object.entries(ANNOTATION_TYPE_LABELS) as [AnnotationType, string][];

interface Props {
  questionId: string;
}

export default function AnnotationPanel({ questionId }: Props) {
  const [annotations, setAnnotations] = useState<QuestionAnnotation[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState({ content: '', annotation_type: 'text' as AnnotationType, color: '#fbbf24' });
  const [showNew, setShowNew] = useState(false);
  const [filterType, setFilterType] = useState<AnnotationType | ''>('');
  const panelRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const data = await fetchAnnotations(questionId);
      setAnnotations(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [questionId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async () => {
    if (!form.content.trim()) return;
    const sel = window.getSelection();
    const anchorText = sel?.toString().slice(0, 200) || null;
    await createAnnotation(questionId, {
      content: form.content.trim(),
      annotation_type: form.annotation_type,
      color: form.color,
      anchor_text: anchorText,
    });
    setForm({ content: '', annotation_type: 'text', color: '#fbbf24' });
    setShowNew(false);
    load();
  };

  const handleUpdate = async (id: string, content: string) => {
    await updateAnnotation(id, { content });
    setEditingId(null);
    load();
  };

  const handleDelete = async (id: string) => {
    await deleteAnnotation(id);
    load();
  };

  const handleJumpToAnchor = (ann: QuestionAnnotation) => {
    if (ann.anchor_text && panelRef.current) {
      const main = panelRef.current.closest('.flex-1')?.querySelector('[class*="whitespace-pre-wrap"]');
      if (main && main.textContent && ann.anchor_text) {
        const idx = main.textContent.indexOf(ann.anchor_text);
        if (idx >= 0 && main instanceof HTMLElement) {
          main.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }
    }
  };

  const filtered = filterType ? annotations.filter((item) => item.annotation_type === filterType) : annotations;

  if (loading) {
    return (
      <div className="p-4 text-sm" style={{ color: '#94a3b8' }}>
        批注加载中…
      </div>
    );
  }

  return (
    <div ref={panelRef} className="flex h-full flex-col bg-white">
      <div
        className="flex items-center justify-between border-b px-4 py-4"
        style={{ borderColor: '#e2e8f0', background: 'linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)' }}
      >
        <div>
          <div className="text-sm font-semibold" style={{ color: '#0f172a' }}>
            批注区
          </div>
          <div className="mt-1 text-xs" style={{ color: '#94a3b8' }}>
            共 {annotations.length} 条备注
          </div>
        </div>
        <button
          onClick={() => setShowNew(!showNew)}
          className="cursor-pointer rounded-full border-none px-3 py-1.5 text-xs font-medium text-white"
          style={{ background: '#2f76dd' }}
        >
          {showNew ? '收起' : '新增批注'}
        </button>
      </div>

      {showNew && (
        <div className="border-b px-4 py-4" style={{ borderColor: '#e2e8f0', background: '#fbfdff' }}>
          <textarea
            value={form.content}
            onChange={(e) => setForm((prev) => ({ ...prev, content: e.target.value }))}
            placeholder="输入批注内容"
            rows={4}
            className="w-full rounded-[16px] border px-3 py-3 text-sm outline-none resize-y"
            style={{ borderColor: '#dbe5f0', background: '#ffffff', color: '#0f172a' }}
          />
          <div className="mt-3 flex flex-wrap gap-2">
            {TYPE_OPTIONS.map(([key, label]) => (
              <button
                key={key}
                onClick={() => setForm((prev) => ({ ...prev, annotation_type: key }))}
                className="cursor-pointer rounded-full border-none px-3 py-1 text-xs transition-colors"
                style={{
                  background: form.annotation_type === key ? '#2f76dd' : '#eef4ff',
                  color: form.annotation_type === key ? '#ffffff' : '#2f76dd',
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-2">
            {ANNOTATION_COLORS.map((color) => (
              <button
                key={color.value}
                onClick={() => setForm((prev) => ({ ...prev, color: color.value }))}
                className="h-6 w-6 cursor-pointer rounded-full border-2 transition-colors"
                style={{
                  background: color.value,
                  borderColor: form.color === color.value ? '#0f172a' : 'transparent',
                }}
                title={color.label}
              />
            ))}
          </div>
          <button
            onClick={handleCreate}
            disabled={!form.content.trim()}
            className="mt-4 w-full cursor-pointer rounded-full border-none px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            style={{ background: '#2f76dd' }}
          >
            保存批注
          </button>
        </div>
      )}

      <div className="border-b px-4 py-3" style={{ borderColor: '#e2e8f0', background: '#ffffff' }}>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setFilterType('')}
            className="cursor-pointer rounded-full border-none px-3 py-1 text-xs"
            style={{
              background: !filterType ? '#2f76dd' : '#f1f5f9',
              color: !filterType ? '#ffffff' : '#64748b',
            }}
          >
            全部
          </button>
          {TYPE_OPTIONS.map(([key, label]) => (
            <button
              key={key}
              onClick={() => setFilterType(filterType === key ? '' : key)}
              className="cursor-pointer rounded-full border-none px-3 py-1 text-xs"
              style={{
                background: filterType === key ? '#2f76dd' : '#f1f5f9',
                color: filterType === key ? '#ffffff' : '#64748b',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto bg-[#fbfdff]">
        {filtered.length === 0 ? (
          <div className="px-6 py-12 text-center">
            <div className="text-sm font-medium" style={{ color: '#64748b' }}>
              暂无批注
            </div>
            <div className="mt-2 text-xs" style={{ color: '#94a3b8' }}>
              可以在这里记录讲课提醒、易错点或课堂备注
            </div>
          </div>
        ) : (
          filtered.map((ann) => (
            <div
              key={ann.annotation_id}
              className="border-b px-4 py-4"
              style={{ borderColor: '#eef2f7' }}
            >
              <div className="mb-2 flex items-center gap-2">
                <span
                  className="rounded-full px-2 py-0.5 text-xs font-medium"
                  style={{ background: `${ann.color}22`, color: ann.color, border: `1px solid ${ann.color}55` }}
                >
                  {ANNOTATION_TYPE_LABELS[ann.annotation_type] || ann.annotation_type}
                </span>
                <span className="flex-1 text-xs" style={{ color: '#94a3b8' }}>
                  {ann.author || '教师'} · {ann.created_at?.slice(0, 10)}
                </span>
                <button
                  onClick={() => setEditingId(editingId === ann.annotation_id ? null : ann.annotation_id)}
                  className="cursor-pointer border-none bg-transparent text-xs"
                  style={{ color: '#2f76dd' }}
                >
                  编辑
                </button>
                <button
                  onClick={() => handleDelete(ann.annotation_id)}
                  className="cursor-pointer border-none bg-transparent text-xs"
                  style={{ color: '#ef4444' }}
                >
                  删除
                </button>
              </div>

              {ann.anchor_text && (
                <div
                  className="mb-2 cursor-pointer rounded-[14px] px-3 py-2 text-xs italic"
                  style={{ background: '#f8fafc', color: '#64748b' }}
                  onClick={() => handleJumpToAnchor(ann)}
                >
                  “{ann.anchor_text.slice(0, 100)}{ann.anchor_text.length > 100 ? '…' : ''}”
                </div>
              )}

              {editingId === ann.annotation_id ? (
                <div className="space-y-2">
                  <textarea
                    defaultValue={ann.content}
                    rows={3}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleUpdate(ann.annotation_id, (e.target as HTMLTextAreaElement).value);
                      }
                    }}
                    className="w-full rounded-[16px] border px-3 py-3 text-sm outline-none"
                    style={{ borderColor: '#dbe5f0', background: '#ffffff', color: '#0f172a', resize: 'vertical' }}
                  />
                  <button
                    onClick={(e) => {
                      const ta = (e.target as HTMLElement).previousElementSibling as HTMLTextAreaElement;
                      handleUpdate(ann.annotation_id, ta.value);
                    }}
                    className="cursor-pointer rounded-full border-none px-4 py-1.5 text-xs font-medium text-white"
                    style={{ background: '#2f76dd' }}
                  >
                    保存
                  </button>
                </div>
              ) : (
                <div className="whitespace-pre-wrap text-sm leading-7" style={{ color: '#334155' }}>
                  {ann.content}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
