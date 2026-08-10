import { useState } from 'react';
import type { Template, TemplateConfig, TemplateScope, TemplateType } from '../../types';
import { deleteTemplate, saveTemplate } from '../../services/api';

const TYPE_LABELS: Record<TemplateType, string> = {
  handout: '讲义',
  teaching: '教案',
  layout: '排版',
  style: '样式',
};

const SCOPE_LABELS: Record<TemplateScope, string> = {
  all: '通用',
  compose: '组卷',
  handout: '讲义',
  slides: '课件',
  classroom: '课堂',
};

function makeTemplateId(): string {
  return `tpl-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

interface TemplateSaveFormProps {
  currentConfig: TemplateConfig;
  onSaved: (templates: Template[]) => void;
  defaultScope?: TemplateScope;
}

export function TemplateSaveForm({ currentConfig, onSaved, defaultScope = 'handout' }: TemplateSaveFormProps) {
  const [name, setName] = useState('');
  const [type, setType] = useState<TemplateType>('handout');
  const [scope, setScope] = useState<TemplateScope>(defaultScope);
  const [showForm, setShowForm] = useState(false);

  if (!showForm) {
    return (
      <button
        onClick={() => setShowForm(true)}
        className="w-full cursor-pointer rounded-lg border px-3 py-2 text-xs font-medium transition-colors"
        style={{
          borderColor: 'var(--color-accent)',
          background: 'var(--color-accent-light)',
          color: 'var(--color-accent)',
        }}
      >
        + 保存为模板
      </button>
    );
  }

  const handleSave = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const template: Template = {
      id: makeTemplateId(),
      name: trimmed,
      type,
      scope,
      config: { ...currentConfig },
    };
    const updated = saveTemplate(template);
    onSaved(updated);
    setName('');
    setShowForm(false);
  };

  return (
    <div
      className="space-y-2 rounded-lg border p-3"
      style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
    >
      <div className="text-xs font-semibold" style={{ color: 'var(--color-text)' }}>
        保存为模板
      </div>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleSave()}
        placeholder="模板名称，如：一轮复习讲义"
        className="w-full rounded border px-2 py-1.5 text-xs outline-none"
        style={{
          borderColor: 'var(--color-border)',
          background: 'var(--color-bg)',
          color: 'var(--color-text)',
        }}
      />
      <div className="flex gap-1">
        {(Object.keys(TYPE_LABELS) as TemplateType[]).map((t) => (
          <button
            key={t}
            onClick={() => setType(t)}
            className="cursor-pointer rounded border-none px-2 py-1 text-xs font-medium transition-colors"
            style={{
              background: type === t ? 'var(--color-accent)' : 'var(--color-bg-hover)',
              color: type === t ? '#fff' : 'var(--color-text-muted)',
            }}
          >
            {TYPE_LABELS[t]}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-1">
        {(Object.keys(SCOPE_LABELS) as TemplateScope[]).map((value) => (
          <button
            key={value}
            onClick={() => setScope(value)}
            className="cursor-pointer rounded border-none px-2 py-1 text-xs font-medium transition-colors"
            style={{
              background: scope === value ? 'var(--color-accent)' : 'var(--color-bg-hover)',
              color: scope === value ? '#fff' : 'var(--color-text-muted)',
            }}
          >
            {SCOPE_LABELS[value]}
          </button>
        ))}
      </div>
      <div className="flex gap-2">
        <button
          onClick={handleSave}
          disabled={!name.trim()}
          className="cursor-pointer rounded border-none px-3 py-1 text-xs font-medium text-white transition-colors disabled:opacity-40"
          style={{ background: 'var(--color-accent)' }}
        >
          保存
        </button>
        <button
          onClick={() => setShowForm(false)}
          className="cursor-pointer rounded border px-3 py-1 text-xs transition-colors"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg-hover)',
            color: 'var(--color-text-muted)',
          }}
        >
          取消
        </button>
      </div>
    </div>
  );
}

// ── Template List ──────────────────────────────────────────────────

interface TemplateListProps {
  templates: Template[];
  onLoad: (template: Template) => void;
  onDeleted: (templates: Template[]) => void;
}

export function TemplateList({ templates, onLoad, onDeleted }: TemplateListProps) {
  const handleDelete = (id: string) => {
    const updated = deleteTemplate(id);
    onDeleted(updated);
  };

  if (templates.length === 0) {
    return (
      <div className="py-6 text-center text-xs" style={{ color: 'var(--color-text-muted)' }}>
        暂无模板
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {templates.map((tpl) => (
        <div
          key={tpl.id}
          className="flex items-center gap-2 rounded border p-2"
          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
        >
          <div className="min-w-0 flex-1">
            <div className="truncate text-xs font-medium" style={{ color: 'var(--color-text)' }}>
              {tpl.name}
            </div>
            <div className="flex items-center gap-2 text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
              <span
                className="rounded px-1 py-0.5"
                style={{ background: 'var(--color-bg-hover)' }}
              >
                {TYPE_LABELS[tpl.type] || tpl.type}
              </span>
              <span
                className="rounded px-1 py-0.5"
                style={{ background: 'var(--color-accent-light)', color: 'var(--color-accent)' }}
              >
                {SCOPE_LABELS[tpl.scope || 'all'] || '通用'}
              </span>
              {tpl.config.show_answer !== undefined && (
                <span>{tpl.config.show_answer ? '含答案' : '无答案'}</span>
              )}
              {tpl.config.show_analysis !== undefined && (
                <span>{tpl.config.show_analysis ? '含解析' : '无解析'}</span>
              )}
              {tpl.updated_at && (
                <span>{new Date(tpl.updated_at).toLocaleDateString('zh-CN')}</span>
              )}
            </div>
          </div>
          <button
            onClick={() => onLoad(tpl)}
            className="cursor-pointer rounded border-none px-2 py-1 text-xs font-medium text-white transition-colors"
            style={{ background: 'var(--color-accent)' }}
          >
            加载
          </button>
          <button
            onClick={() => handleDelete(tpl.id)}
            className="cursor-pointer rounded border px-2 py-1 text-xs transition-colors"
            style={{
              borderColor: 'var(--color-red)',
              background: 'transparent',
              color: 'var(--color-red)',
            }}
          >
            删除
          </button>
        </div>
      ))}
    </div>
  );
}
