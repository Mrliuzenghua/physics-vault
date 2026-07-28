import { type ReactNode, useMemo, useRef, useState } from 'react';

import type { Figure, ImportMediaAsset, Option, QuestionType } from '../../types';
import FigurePickerModal from './FigurePickerModal';
import ImportStemRenderer from './ImportStemRenderer';

export interface EditableQuestion {
  question_id: string;
  question_no?: number;
  question_type: QuestionType;
  title: string;
  options: Option[];
  answer: string;
  analysis: string;
  figures: Figure[];
  _key: string;
  _aiRefined?: boolean;
}

const TYPE_OPTIONS: { value: QuestionType; label: string }[] = [
  { value: 'single_choice', label: '单选题' },
  { value: 'multi_choice', label: '多选题' },
  { value: 'fill', label: '填空题' },
  { value: 'experiment', label: '实验题' },
  { value: 'calculation', label: '计算题' },
];

const TYPE_LABELS: Record<string, string> = Object.fromEntries(TYPE_OPTIONS.map((t) => [t.value, t.label]));
const FIG_PLACEHOLDER_RE = /!\[fig:[^\]]+\]/g;

function makeFigUuid(): string {
  return `fig_${Math.random().toString(16).slice(2, 14)}`;
}

interface Props {
  questions: EditableQuestion[];
  selectedKey: string | null;
  onSelect: (key: string) => void;
  onChange: (key: string, patch: Partial<EditableQuestion>) => void;
  onDelete: (key: string) => void;
  onMergeWithNext: (key: string) => void;
  mediaAssets: ImportMediaAsset[];
  onUploadImage: (file: File) => Promise<ImportMediaAsset>;
}

export default function ImportQuestionEditor({
  questions,
  selectedKey,
  onSelect,
  onChange,
  onDelete,
  onMergeWithNext,
  mediaAssets,
  onUploadImage,
}: Props) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [editingStem, setEditingStem] = useState(false);
  const [uploading, setUploading] = useState(false);
  const stemTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  const selected = questions.find((q) => q._key === selectedKey) ?? null;
  const selectedIndex = selected ? questions.indexOf(selected) : -1;

  const usageMap = useMemo(() => {
    const map = new Map<string, number[]>();
    questions.forEach((q, i) => {
      for (const fig of q.figures) {
        const list = map.get(fig.local_path) ?? [];
        list.push(i + 1);
        map.set(fig.local_path, list);
      }
    });
    return map;
  }, [questions]);

  const handleRemoveFigure = (fig: Figure) => {
    if (!selected) return;
    const newTitle = selected.title
      .replace(new RegExp(`!\\[fig:${fig.fig_uuid}\\]`, 'g'), '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    onChange(selected._key, {
      figures: selected.figures.filter((f) => f.fig_uuid !== fig.fig_uuid),
      title: newTitle,
    });
  };

  const attachAsset = (asset: ImportMediaAsset) => {
    if (!selected) return;
    const uuid = makeFigUuid();
    const placeholder = `![fig:${uuid}]`;
    const ta = stemTextareaRef.current;

    let newTitle: string;
    if (editingStem && ta && ta.selectionStart != null) {
      const pos = ta.selectionStart;
      newTitle = selected.title.slice(0, pos) + placeholder + selected.title.slice(pos);
    } else {
      newTitle = `${selected.title.trimEnd()}\n${placeholder}`;
    }

    onChange(selected._key, {
      figures: [...selected.figures, { fig_uuid: uuid, local_path: asset.relative_path }],
      title: newTitle,
    });
  };

  const handlePickFigure = (asset: ImportMediaAsset) => {
    attachAsset(asset);
    setPickerOpen(false);
  };

  const handleUploadFigure = async (file: File) => {
    if (!selected) return;
    setUploading(true);
    try {
      const asset = await onUploadImage(file);
      attachAsset(asset);
      setPickerOpen(false);
    } catch (err) {
      alert(`图片上传失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setUploading(false);
    }
  };

  const handleOptionChange = (idx: number, content: string) => {
    if (!selected) return;
    const next = selected.options.map((o, i) => (i === idx ? { ...o, content } : o));
    onChange(selected._key, { options: next });
  };

  const handleOptionRemove = (idx: number) => {
    if (!selected) return;
    const next = selected.options
      .filter((_, i) => i !== idx)
      .map((o, i) => ({ ...o, opt: String.fromCharCode(65 + i) }));
    onChange(selected._key, { options: next });
  };

  const handleOptionAdd = () => {
    if (!selected) return;
    const letter = String.fromCharCode(65 + selected.options.length);
    onChange(selected._key, { options: [...selected.options, { opt: letter, content: '' }] });
  };

  return (
    <div className="flex h-full min-h-0">
      <aside
        className="w-72 flex-shrink-0 overflow-y-auto border-r p-3"
        style={{
          borderColor: 'var(--color-border)',
          background:
            'linear-gradient(180deg, color-mix(in srgb, var(--color-bg-sidebar) 85%, white) 0%, var(--color-bg-sidebar) 100%)',
        }}
      >
        <div className="mb-3 rounded-2xl border px-3 py-3" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}>
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em]" style={{ color: 'var(--color-text-muted)' }}>
            Question Queue
          </div>
          <div className="mt-1 text-sm font-bold" style={{ color: 'var(--color-text)' }}>
            共 {questions.length} 道待确认题目
          </div>
        </div>

        <div className="space-y-2">
          {questions.map((q, i) => {
            const active = q._key === selectedKey;
            const plain = q.title.replace(FIG_PLACEHOLDER_RE, '[图片]').replace(/\$[^$]*\$/g, '·');
            return (
              <button
                key={q._key}
                onClick={() => onSelect(q._key)}
                className="group w-full cursor-pointer rounded-2xl border px-3 py-3 text-left transition-all"
                style={{
                  borderColor: active ? 'var(--color-accent)' : 'var(--color-border)',
                  background: active ? 'var(--color-accent-light)' : 'var(--color-bg-card)',
                  boxShadow: active ? '0 10px 24px rgba(37,111,202,0.12)' : 'var(--shadow-sm)',
                }}
              >
                <div className="flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-bold" style={{ background: active ? 'var(--color-accent)' : 'var(--color-bg-code)', color: active ? '#fff' : 'var(--color-text-secondary)' }}>
                    {i + 1}
                  </span>
                  <span className="rounded-full px-2 py-0.5 text-[10px]" style={{ background: 'var(--color-bg-code)', color: 'var(--color-text-secondary)' }}>
                    {TYPE_LABELS[q.question_type] ?? q.question_type}
                  </span>
                  {q.figures.length > 0 && (
                    <span className="text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                      图 {q.figures.length}
                    </span>
                  )}
                  {q._aiRefined && (
                    <span className="text-[10px] font-semibold" style={{ color: 'var(--color-purple)' }} title="已完成 AI 整理">
                      AI
                    </span>
                  )}
                  <span
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(q._key);
                    }}
                    className="ml-auto hidden rounded-md px-1.5 py-0.5 text-xs group-hover:inline"
                    style={{ color: 'var(--color-red)' }}
                    title="删除此题"
                  >
                    ×
                  </span>
                </div>

                <div className="mt-2 line-clamp-2 text-xs leading-6" style={{ color: 'var(--color-text-secondary)' }}>
                  {plain.slice(0, 96) || '(空题干)'}
                </div>
              </button>
            );
          })}
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto px-5 py-5" style={{ background: 'var(--color-bg)' }}>
        {!selected ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
              从左侧选择一道题开始编辑
            </p>
          </div>
        ) : (
          <div className="mx-auto max-w-4xl space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-bold" style={{ color: 'var(--color-text)' }}>
                第 {selectedIndex + 1} 题
              </h2>
              <select
                value={selected.question_type}
                onChange={(e) => onChange(selected._key, { question_type: e.target.value as QuestionType })}
                className="cursor-pointer rounded-xl border px-3 py-2 text-xs outline-none"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)', color: 'var(--color-text)' }}
              >
                {TYPE_OPTIONS.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              <div className="flex-1" />
              <button
                onClick={() => onMergeWithNext(selected._key)}
                disabled={selectedIndex >= questions.length - 1}
                className="cursor-pointer rounded-xl border px-3 py-2 text-xs transition-colors disabled:opacity-40"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)', color: 'var(--color-text-secondary)' }}
                title="把下一题合并到本题，用于修复错误切题"
              >
                与下一题合并
              </button>
              <button
                onClick={() => onDelete(selected._key)}
                className="cursor-pointer rounded-xl border-none px-3 py-2 text-xs"
                style={{ background: 'var(--color-red-light)', color: 'var(--color-red)' }}
              >
                删除此题
              </button>
            </div>

            <EditorCard
              title="题干"
              extra={
                <button
                  onClick={() => setEditingStem((v) => !v)}
                  className="cursor-pointer rounded-full border-none px-2.5 py-1 text-xs"
                  style={{
                    background: editingStem ? 'var(--color-accent-light)' : 'var(--color-bg-hover)',
                    color: editingStem ? 'var(--color-accent)' : 'var(--color-text-secondary)',
                  }}
                >
                  {editingStem ? '预览模式' : '编辑文本'}
                </button>
              }
            >
              {editingStem ? (
                <>
                  <textarea
                    ref={stemTextareaRef}
                    value={selected.title}
                    onChange={(e) => onChange(selected._key, { title: e.target.value })}
                    rows={Math.min(12, Math.max(4, selected.title.split('\n').length + 1))}
                    className="w-full resize-y rounded-2xl border p-3 text-sm outline-none"
                    style={{
                      borderColor: 'var(--color-border)',
                      background: 'var(--color-bg)',
                      color: 'var(--color-text)',
                      lineHeight: 1.8,
                    }}
                  />
                  <p className="mt-2 text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
                    图片使用 `![fig:xxx]` 占位标记；公式使用 `$...$`；如果图片位置错了，直接剪切占位符即可。
                  </p>
                </>
              ) : (
                <div className="text-sm leading-8" style={{ color: 'var(--color-text)' }}>
                  {selected.title.trim() ? (
                    <ImportStemRenderer title={selected.title} figures={selected.figures} />
                  ) : (
                    <span style={{ color: 'var(--color-text-muted)' }}>(空题干，点击“编辑文本”填写)</span>
                  )}
                </div>
              )}
            </EditorCard>

            <EditorCard
              title={`配图 (${selected.figures.length})`}
              extra={
                <button
                  onClick={() => setPickerOpen(true)}
                  className="cursor-pointer rounded-full border-none px-2.5 py-1 text-xs"
                  style={{ background: 'var(--color-accent-light)', color: 'var(--color-accent)' }}
                >
                  + 添加图片
                </button>
              }
            >
              {selected.figures.length === 0 ? (
                <p className="text-xs leading-6" style={{ color: 'var(--color-text-muted)' }}>
                  本题暂无配图。点击“添加图片”可从当前批次素材库选择，或直接上传新图。
                </p>
              ) : (
                <div className="flex flex-wrap gap-3">
                  {selected.figures.map((fig) => (
                    <div
                      key={fig.fig_uuid}
                      className="relative overflow-hidden rounded-2xl border"
                      style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-code)' }}
                    >
                      <img
                        src={`/files/${fig.local_path}`}
                        alt=""
                        style={{ height: 112, maxWidth: 220, objectFit: 'contain', display: 'block' }}
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = 'none';
                        }}
                      />
                      <button
                        onClick={() => handleRemoveFigure(fig)}
                        className="absolute right-2 top-2 flex h-6 w-6 cursor-pointer items-center justify-center rounded-full border-none text-xs text-white"
                        style={{ background: 'rgba(220,38,38,0.92)' }}
                        title="删除此图，并同步移除题干中的图片占位符"
                      >
                        ×
                      </button>
                      <div className="truncate px-2 py-1 text-[10px]" style={{ color: 'var(--color-text-muted)', maxWidth: 220 }}>
                        {fig.local_path.split('/').pop()}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </EditorCard>

            {(selected.question_type === 'single_choice' ||
              selected.question_type === 'multi_choice' ||
              selected.options.length > 0) && (
              <EditorCard
                title={`选项 (${selected.options.length})`}
                extra={
                  <button
                    onClick={handleOptionAdd}
                    className="cursor-pointer rounded-full border-none px-2.5 py-1 text-xs"
                    style={{ background: 'var(--color-bg-hover)', color: 'var(--color-text-secondary)' }}
                  >
                    + 添加选项
                  </button>
                }
              >
                {selected.options.length === 0 ? (
                  <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    当前没有选项，点击“添加选项”创建。
                  </p>
                ) : (
                  <div className="space-y-2">
                    {selected.options.map((opt, idx) => (
                      <div key={idx} className="flex items-start gap-2">
                        <span
                          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl text-xs font-bold"
                          style={{ background: 'var(--color-accent-light)', color: 'var(--color-accent)' }}
                        >
                          {opt.opt}
                        </span>
                        <div className="min-w-0 flex-1">
                          <input
                            value={opt.content}
                            onChange={(e) => handleOptionChange(idx, e.target.value)}
                            className="w-full rounded-xl border px-3 py-2 text-sm outline-none"
                            style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)', color: 'var(--color-text)' }}
                          />
                          {opt.content.trim() && (
                            <div className="mt-2 rounded-xl px-3 py-2 text-sm" style={{ background: 'var(--color-bg-code)', color: 'var(--color-text-secondary)' }}>
                              <ImportStemRenderer title={opt.content} figures={selected.figures} maxImageHeight={80} />
                            </div>
                          )}
                        </div>
                        <button
                          onClick={() => handleOptionRemove(idx)}
                          className="cursor-pointer rounded-xl border-none px-2 py-2 text-xs"
                          style={{ color: 'var(--color-text-muted)' }}
                          title="删除选项"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </EditorCard>
            )}

            <EditorCard title="答案">
              <textarea
                value={selected.answer}
                onChange={(e) => onChange(selected._key, { answer: e.target.value })}
                rows={Math.min(6, Math.max(2, selected.answer.split('\n').length + 1))}
                placeholder="例如：A，或（1）……（2）……"
                className="w-full resize-y rounded-2xl border p-3 text-sm outline-none"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)', color: 'var(--color-text)', lineHeight: 1.8 }}
              />
              {selected.answer.trim() && (
                <div className="mt-2 rounded-xl px-3 py-2 text-sm" style={{ background: 'var(--color-green-light)', color: 'var(--color-green)' }}>
                  <ImportStemRenderer title={selected.answer} figures={selected.figures} maxImageHeight={80} />
                </div>
              )}
            </EditorCard>

            <EditorCard title="解析">
              <textarea
                value={selected.analysis}
                onChange={(e) => onChange(selected._key, { analysis: e.target.value })}
                rows={Math.min(8, Math.max(2, selected.analysis.split('\n').length + 1))}
                placeholder="题目解析（可选）"
                className="w-full resize-y rounded-2xl border p-3 text-sm outline-none"
                style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)', color: 'var(--color-text)', lineHeight: 1.8 }}
              />
              {selected.analysis.trim() && (
                <div className="mt-2 rounded-xl px-3 py-2 text-sm" style={{ background: 'var(--color-bg-code)', color: 'var(--color-text-secondary)' }}>
                  <ImportStemRenderer title={selected.analysis} figures={selected.figures} maxImageHeight={80} />
                </div>
              )}
            </EditorCard>
          </div>
        )}
      </main>

      {pickerOpen && (
        <FigurePickerModal
          assets={mediaAssets}
          usageMap={usageMap}
          onPick={handlePickFigure}
          onUpload={handleUploadFigure}
          onClose={() => setPickerOpen(false)}
          uploading={uploading}
        />
      )}
    </div>
  );
}

function EditorCard({
  title,
  extra,
  children,
}: {
  title: string;
  extra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div
      className="rounded-[20px] border p-4"
      style={{
        borderColor: 'var(--color-border)',
        background: 'var(--color-bg-card)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em]" style={{ color: 'var(--color-text-muted)' }}>
          {title}
        </span>
        {extra}
      </div>
      {children}
    </div>
  );
}
