import type { Figure, Option, ReviewQuestionDraft, SubQuestion } from '../../types';

interface QuestionEditorProps {
  draft: ReviewQuestionDraft;
  onChange: (field: string, value: unknown) => void;
}

const TYPE_OPTIONS = [
  { value: 'single_choice', label: '单选题' },
  { value: 'multi_choice', label: '多选题' },
  { value: 'fill', label: '填空题' },
  { value: 'experiment', label: '实验题' },
  { value: 'calculation', label: '计算题' },
];

export default function QuestionEditor({ draft, onChange }: QuestionEditorProps) {
  const handleOptionChange = (index: number, content: string) => {
    const next = [...draft.options];
    next[index] = { ...next[index], content };
    onChange('options', next);
  };

  const handleSubQuestionChange = (index: number, field: string, value: string) => {
    const next = [...draft.sub_questions];
    next[index] = { ...next[index], [field]: value };
    onChange('sub_questions', next);
  };

  const handleTagsChange = (value: string) => {
    const tags = value
      .split(/[,，]/)
      .map((t) => t.trim())
      .filter(Boolean);
    onChange('tags', tags);
  };

  return (
    <div className="flex h-full flex-col">
      <div
        className="flex-shrink-0 border-b px-4 py-3"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <h2
          className="text-sm font-semibold"
          style={{ color: 'var(--color-text)' }}
        >
          题目编辑
        </h2>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {/* 题型 + 难度 */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label
              className="mb-1 block text-xs font-medium"
              style={{ color: 'var(--color-text-muted)' }}
            >
              题型
            </label>
            <select
              value={draft.question_type}
              onChange={(e) => onChange('question_type', e.target.value)}
              className="w-full rounded border px-2 py-1.5 text-sm outline-none"
              style={{
                borderColor: 'var(--color-border)',
                background: 'var(--color-bg-card)',
                color: 'var(--color-text)',
              }}
            >
              {TYPE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label
              className="mb-1 block text-xs font-medium"
              style={{ color: 'var(--color-text-muted)' }}
            >
              难度 (1-5)
            </label>
            <input
              type="number"
              min={1}
              max={5}
              value={draft.difficulty ?? 3}
              onChange={(e) => {
                const v = Number(e.target.value);
                onChange('difficulty', Number.isNaN(v) ? null : Math.max(1, Math.min(5, v)));
              }}
              className="w-full rounded border px-2 py-1.5 text-sm outline-none"
              style={{
                borderColor: 'var(--color-border)',
                background: 'var(--color-bg-card)',
                color: 'var(--color-text)',
              }}
            />
          </div>
        </div>

        {/* 来源 */}
        <div>
          <label
            className="mb-1 block text-xs font-medium"
            style={{ color: 'var(--color-text-muted)' }}
          >
            来源
          </label>
          <input
            value={draft.source}
            onChange={(e) => onChange('source', e.target.value)}
            className="w-full rounded border px-2 py-1.5 text-sm outline-none"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-bg-card)',
              color: 'var(--color-text)',
            }}
          />
        </div>

        {/* 题干 */}
        <div>
          <label
            className="mb-1 block text-xs font-medium"
            style={{ color: 'var(--color-text-muted)' }}
          >
            题干
          </label>
          <textarea
            value={draft.title}
            onChange={(e) => onChange('title', e.target.value)}
            rows={6}
            className="w-full rounded-lg border p-3 text-sm leading-relaxed outline-none"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-bg-card)',
              color: 'var(--color-text)',
              resize: 'vertical',
            }}
          />
        </div>

        {/* 选项 */}
        {draft.options.length > 0 && (
          <div>
            <label
              className="mb-1 block text-xs font-medium"
              style={{ color: 'var(--color-text-muted)' }}
            >
              选项
            </label>
            <div className="space-y-1.5">
              {draft.options.map((opt: Option, index: number) => (
                <div key={`${opt.opt}-${index}`} className="flex items-start gap-2">
                  <span
                    className="mt-1.5 w-6 flex-shrink-0 text-sm font-bold"
                    style={{ color: 'var(--color-accent)' }}
                  >
                    {opt.opt}
                  </span>
                  <input
                    value={opt.content}
                    onChange={(e) => handleOptionChange(index, e.target.value)}
                    className="flex-1 rounded border px-2 py-1.5 text-sm outline-none"
                    style={{
                      borderColor: 'var(--color-border)',
                      background: 'var(--color-bg-card)',
                      color: 'var(--color-text)',
                    }}
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 答案 */}
        <div>
          <label
            className="mb-1 block text-xs font-medium"
            style={{ color: 'var(--color-text-muted)' }}
          >
            答案
          </label>
          <input
            value={draft.answer}
            onChange={(e) => onChange('answer', e.target.value)}
            className="w-full rounded border px-2 py-1.5 text-sm outline-none"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-bg-card)',
              color: 'var(--color-text)',
            }}
          />
        </div>

        {/* 解析 */}
        <div>
          <label
            className="mb-1 block text-xs font-medium"
            style={{ color: 'var(--color-text-muted)' }}
          >
            解析
          </label>
          <textarea
            value={draft.analysis}
            onChange={(e) => onChange('analysis', e.target.value)}
            rows={4}
            className="w-full rounded-lg border p-3 text-sm leading-relaxed outline-none"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-bg-card)',
              color: 'var(--color-text)',
              resize: 'vertical',
            }}
          />
        </div>

        {/* 子问题 */}
        {draft.sub_questions.length > 0 && (
          <div>
            <label
              className="mb-1 block text-xs font-medium"
              style={{ color: 'var(--color-text-muted)' }}
            >
              子问题
            </label>
            <div className="space-y-3">
              {draft.sub_questions.map((sub: SubQuestion, index: number) => (
                <div
                  key={sub.sub_id || index}
                  className="rounded-lg border p-3"
                  style={{
                    borderColor: 'var(--color-border)',
                    background: 'var(--color-bg-card)',
                  }}
                >
                  <div className="mb-1 text-xs font-semibold" style={{ color: 'var(--color-accent)' }}>
                    {sub.sub_id || `子问题 ${index + 1}`}
                  </div>
                  <input
                    value={sub.title}
                    onChange={(e) => handleSubQuestionChange(index, 'title', e.target.value)}
                    placeholder="子问题标题"
                    className="mb-1.5 w-full rounded border px-2 py-1 text-xs outline-none"
                    style={{
                      borderColor: 'var(--color-border)',
                      background: 'var(--color-bg-hover)',
                      color: 'var(--color-text)',
                    }}
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      value={sub.answer}
                      onChange={(e) => handleSubQuestionChange(index, 'answer', e.target.value)}
                      placeholder="答案"
                      className="rounded border px-2 py-1 text-xs outline-none"
                      style={{
                        borderColor: 'var(--color-border)',
                        background: 'var(--color-bg-hover)',
                        color: 'var(--color-text)',
                      }}
                    />
                    <input
                      value={sub.analysis}
                      onChange={(e) => handleSubQuestionChange(index, 'analysis', e.target.value)}
                      placeholder="解析"
                      className="rounded border px-2 py-1 text-xs outline-none"
                      style={{
                        borderColor: 'var(--color-border)',
                        background: 'var(--color-bg-hover)',
                        color: 'var(--color-text)',
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 知识点 + 标签 */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label
              className="mb-1 block text-xs font-medium"
              style={{ color: 'var(--color-text-muted)' }}
            >
              知识点
            </label>
            <input
              value={draft.knowledge_point}
              onChange={(e) => onChange('knowledge_point', e.target.value)}
              className="w-full rounded border px-2 py-1.5 text-sm outline-none"
              style={{
                borderColor: 'var(--color-border)',
                background: 'var(--color-bg-card)',
                color: 'var(--color-text)',
              }}
            />
          </div>
          <div>
            <label
              className="mb-1 block text-xs font-medium"
              style={{ color: 'var(--color-text-muted)' }}
            >
              标签 (逗号分隔)
            </label>
            <input
              value={draft.tags.join(', ')}
              onChange={(e) => handleTagsChange(e.target.value)}
              className="w-full rounded border px-2 py-1.5 text-sm outline-none"
              style={{
                borderColor: 'var(--color-border)',
                background: 'var(--color-bg-card)',
                color: 'var(--color-text)',
              }}
            />
          </div>
        </div>

        {/* 图片与占位符展示 */}
        <div>
          <label
            className="mb-1 block text-xs font-medium"
            style={{ color: 'var(--color-text-muted)' }}
          >
            图片与占位符
          </label>

          {draft.figures.length === 0 && !draft.title.includes('![fig:') ? (
            <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
              本题无关联图片
            </p>
          ) : (
            <div className="space-y-2">
              {draft.figures.length > 0 && (
                <div>
                  <span className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                    关联图片 ({draft.figures.length})：
                  </span>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {draft.figures.map((fig: Figure) => (
                      <span
                        key={fig.fig_uuid}
                        className="rounded px-2 py-0.5 text-xs"
                        style={{
                          background: 'var(--color-bg-hover)',
                          color: 'var(--color-text-secondary)',
                        }}
                      >
                        {fig.fig_uuid}
                        {fig.local_path ? ` (${fig.local_path})` : ''}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 题干中图片占位符检测 */}
              {(() => {
                const refs = draft.title.match(/!\[fig:([^\]]+)\]/g);
                if (refs && refs.length > 0) {
                  return (
                    <div>
                      <span className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                        题干图片占位符 ({refs.length})：
                      </span>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {refs.map((ref, i) => (
                          <code
                            key={i}
                            className="rounded px-1.5 py-0.5 text-xs"
                            style={{
                              background: 'var(--color-bg-code)',
                              color: 'var(--color-text-secondary)',
                            }}
                          >
                            {ref}
                          </code>
                        ))}
                      </div>
                    </div>
                  );
                }
                return null;
              })()}
            </div>
          )}
        </div>

        {/* 图片引用问题 */}
        {draft.figureIssues.length > 0 && (
          <div>
            <label
              className="mb-1 block text-xs font-medium"
              style={{ color: 'var(--color-text-muted)' }}
            >
              图片引用问题
            </label>
            <div className="space-y-1 rounded-lg border p-2.5" style={{ borderColor: 'var(--color-orange)' }}>
              {draft.figureIssues.map((issue, index) => (
                <div
                  key={index}
                  className="flex items-start gap-1.5 text-xs"
                  style={{ color: 'var(--color-orange)' }}
                >
                  <span className="flex-shrink-0">⚠</span>
                  <span>{issue.message}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
