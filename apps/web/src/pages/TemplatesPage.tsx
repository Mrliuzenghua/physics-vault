import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { TemplateList, TemplateSaveForm } from '../components/template/TemplateComponents';
import { deleteMaterialPackage, loadMaterialPackages, loadTemplates, saveTemplate } from '../services/api';
import type { Template, TemplateConfig, TemplateMaterialPackage, TemplateType } from '../types';
import { MATERIAL_PACKAGE_TYPE_LABELS } from '../types';

// ── Constants ────────────────────────────────────────────────────────

const FONT_FAMILIES = [
  { label: '宋体（默认）', value: 'SimSun, 宋体, serif' },
  { label: '黑体', value: 'SimHei, 黑体, sans-serif' },
  { label: '楷体', value: 'KaiTi, 楷体, serif' },
  { label: '微软雅黑', value: '"Microsoft YaHei", "微软雅黑", sans-serif' },
  { label: '思源宋体', value: '"Source Han Serif SC", "Noto Serif CJK SC", serif' },
  { label: '思源黑体', value: '"Source Han Sans SC", "Noto Sans CJK SC", sans-serif' },
  { label: '仿宋', value: 'FangSong, 仿宋, serif' },
];

const FONT_SIZES = ['10px', '11px', '12px', '13px', '14px', '15px', '16px', '18px', '20px'];

const LINE_HEIGHTS = [
  { label: '紧凑（1.3）', value: '1.3' },
  { label: '标准（1.5）', value: '1.5' },
  { label: '舒适（1.6）', value: '1.6' },
  { label: '宽松（1.8）', value: '1.8' },
  { label: '双倍（2.0）', value: '2.0' },
];

const NUMBER_STYLES = [
  { label: '1. 2. 3.', value: 'decimal' },
  { label: '一、二、三', value: 'chinese' },
  { label: '(1) (2) (3)', value: 'paren' },
  { label: '① ② ③', value: 'circled' },
];

const FIGURE_SCALES = [
  { label: '50%', value: '0.5' },
  { label: '60%', value: '0.6' },
  { label: '70%', value: '0.7' },
  { label: '80%', value: '0.8' },
  { label: '90%', value: '0.9' },
  { label: '100%（原大）', value: '1.0' },
];

const KNOWLEDGE_STYLES = [
  { label: '讲义手稿', value: 'teacher_handout' },
  { label: '课堂板书', value: 'classroom_board' },
  { label: '学生笔记', value: 'student_notes' },
  { label: '复习纲要', value: 'review_outline' },
];

const KNOWLEDGE_LENGTHS = [
  { label: '简短', value: 'short' },
  { label: '适中', value: 'medium' },
  { label: '详尽', value: 'long' },
];

const DEFAULT_CONFIG: TemplateConfig = {
  show_answer: true,
  show_analysis: true,
  page_size: 'A4',
  orientation: 'portrait',
  font_family: 'SimSun, 宋体, serif',
  font_size: '13px',
  line_height: '1.6',
  figure_scale: '0.85',
  question_number_style: 'decimal',
  knowledge_mode: 'static',
  knowledge_style: 'teacher_handout',
  knowledge_length: 'medium',
  header: '',
  footer: '',
};

export default function TemplatesPage() {
  const navigate = useNavigate();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [materialPackages, setMaterialPackages] = useState<TemplateMaterialPackage[]>([]);
  const [config, setConfig] = useState<TemplateConfig>({ ...DEFAULT_CONFIG });
  const [loadedName, setLoadedName] = useState<string | null>(null);
  const [saveName, _setSaveName] = useState('');
  const [saveType, _setSaveType] = useState<TemplateType>('handout');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setTemplates(loadTemplates());
    setMaterialPackages(loadMaterialPackages());
  }, []);

  const refreshPackages = useCallback(() => {
    setMaterialPackages(loadMaterialPackages());
  }, []);

  // ── Handlers ──

  const handleSaved = useCallback((updated: Template[]) => {
    setTemplates(updated);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }, []);

  const handleDeleted = useCallback((updated: Template[]) => {
    setTemplates(updated);
  }, []);

  const handleLoad = useCallback((tpl: Template) => {
    setConfig({ ...tpl.config });
    setLoadedName(tpl.name);
  }, []);

  const handleReset = useCallback(() => {
    setConfig({ ...DEFAULT_CONFIG });
    setLoadedName(null);
  }, []);

  const toggleBool = useCallback((field: keyof TemplateConfig) => {
    setConfig((prev) => {
      const v = prev[field];
      if (typeof v === 'boolean') return { ...prev, [field]: !v };
      return prev;
    });
  }, []);

  const updateField = useCallback((field: keyof TemplateConfig, value: string) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  }, []);

  // Build a title suggestion for save
  const nameHint = useMemo(() => {
    const parts: string[] = [];
    if (config.page_size) parts.push(config.page_size);
    if (config.orientation === 'landscape') parts.push('横向');
    if (config.show_answer && config.show_analysis) parts.push('教师版');
    else if (!config.show_answer && !config.show_analysis) parts.push('学生版');
    return parts.join(' · ');
  }, [config]);

  return (
    <div className="flex h-full">
      {/* ── Left: saved templates ── */}
      <aside
        className="w-72 flex-shrink-0 overflow-y-auto border-r p-4 space-y-3"
        style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-sidebar)' }}
      >
        <div>
          <h1 className="text-sm font-bold" style={{ color: 'var(--color-text)' }}>
            模板管理
          </h1>
          <p className="mt-0.5 text-xs" style={{ color: 'var(--color-text-muted)' }}>
            保存和复用组卷排版配置
          </p>
        </div>

        <TemplateSaveForm currentConfig={config} onSaved={handleSaved} />

        <div className="border-t pt-3" style={{ borderColor: 'var(--color-border)' }}>
          <div className="mb-2 text-xs font-semibold" style={{ color: 'var(--color-text)' }}>
            已保存模板 ({templates.length})
          </div>
          <TemplateList templates={templates} onLoad={handleLoad} onDeleted={handleDeleted} />
        </div>

        {/* ── Material packages ── */}
        <div className="border-t pt-3" style={{ borderColor: 'var(--color-border)' }}>
          <div className="mb-2 text-xs font-semibold" style={{ color: 'var(--color-text)' }}>
            模板素材包 ({materialPackages.length})
          </div>
          {materialPackages.length === 0 ? (
            <div className="py-3 text-center text-xs" style={{ color: 'var(--color-text-muted)' }}>
              暂无素材包，可在选题篮中导出
            </div>
          ) : (
            <div className="space-y-1">
              {materialPackages.map((pkg) => (
                <div
                  key={pkg.id}
                  className="rounded border p-2 space-y-1"
                  style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
                >
                  <div className="truncate text-xs font-medium" style={{ color: 'var(--color-text)' }}>
                    {pkg.name}
                  </div>
                  <div className="flex items-center gap-1.5 text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                    <span
                      className="rounded px-1 py-0.5"
                      style={{ background: 'var(--color-bg-hover)' }}
                    >
                      {MATERIAL_PACKAGE_TYPE_LABELS[pkg.type] || pkg.type}
                    </span>
                    <span>{pkg.questions.length} 题</span>
                    <span>{pkg.sourceLabel}</span>
                  </div>
                  <div className="flex gap-1">
                    <button
                      onClick={() => {
                        // Load material package into compose page via route state
                        navigate('/compose', {
                          state: { materialPackage: pkg },
                        });
                      }}
                      className="cursor-pointer rounded border-none px-2 py-0.5 text-xs font-medium text-white transition-colors"
                      style={{ background: 'var(--color-accent)' }}
                    >
                      加载到组卷
                    </button>
                    <button
                      onClick={() => {
                        deleteMaterialPackage(pkg.id);
                        refreshPackages();
                      }}
                      className="cursor-pointer rounded border px-2 py-0.5 text-xs transition-colors"
                      style={{
                        borderColor: 'var(--color-red)',
                        background: 'transparent',
                        color: 'var(--color-red)',
                      }}
                    >
                      删除
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>

      {/* ── Right: config editor ── */}
      <main className="flex-1 overflow-y-auto p-6" style={{ background: 'var(--color-bg)' }}>
        <div className="mx-auto max-w-xl space-y-5">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-bold" style={{ color: 'var(--color-text)' }}>
                {loadedName ? `编辑：${loadedName}` : '新建排版配置'}
              </h2>
              <p className="mt-0.5 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                {nameHint}
              </p>
            </div>
            <div className="flex gap-2">
              {loadedName && (
                <button
                  onClick={handleReset}
                  className="cursor-pointer rounded border px-2.5 py-1.5 text-xs transition-colors"
                  style={{
                    borderColor: 'var(--color-border)',
                    background: 'var(--color-bg-hover)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  重置
                </button>
              )}
              {/* Direct save */}
              <button
                onClick={() => {
                  const name = saveName.trim() || nameHint || '未命名模板';
                  const now = new Date().toISOString();
                  const tpl: Template = {
                    id: `tpl-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                    name,
                    type: saveType,
                    config: { ...config },
                    created_at: now,
                    updated_at: now,
                  };
                  const updated = saveTemplate(tpl);
                  handleSaved(updated);
                  setLoadedName(name);
                }}
                className="cursor-pointer rounded-lg border-none px-4 py-1.5 text-xs font-semibold text-white transition-colors"
                style={{ background: saved ? 'var(--color-green)' : 'var(--color-accent)' }}
              >
                {saved ? '已保存' : '保存模板'}
              </button>
            </div>
          </div>

          {/* ── Section: 排版设置 ── */}
          <Section title="排版设置">
            {/* Font family */}
            <Field label="字体">
              <select
                value={config.font_family || DEFAULT_CONFIG.font_family}
                onChange={(e) => updateField('font_family', e.target.value)}
                className="w-full rounded border px-2 py-1.5 text-sm outline-none"
                style={{
                  borderColor: 'var(--color-border)',
                  background: 'var(--color-bg)',
                  color: 'var(--color-text)',
                }}
              >
                {FONT_FAMILIES.map((f) => (
                  <option key={f.value} value={f.value}>{f.label}</option>
                ))}
              </select>
            </Field>

            {/* Font size */}
            <Field label="正文字号">
              <div className="flex flex-wrap gap-1.5">
                {FONT_SIZES.map((size) => (
                  <button
                    key={size}
                    onClick={() => updateField('font_size', size)}
                    className="cursor-pointer rounded border px-2.5 py-1 text-xs font-medium transition-colors"
                    style={{
                      borderColor: config.font_size === size ? 'var(--color-accent)' : 'var(--color-border)',
                      background: config.font_size === size ? 'var(--color-accent-light)' : 'var(--color-bg-card)',
                      color: config.font_size === size ? 'var(--color-accent-dark)' : 'var(--color-text-secondary)',
                    }}
                  >
                    {size}
                  </button>
                ))}
                <input
                  value={config.font_size || ''}
                  onChange={(e) => updateField('font_size', e.target.value)}
                  placeholder="自定义"
                  className="w-20 rounded border px-2 py-1 text-xs outline-none"
                  style={{
                    borderColor: 'var(--color-border)',
                    background: 'var(--color-bg)',
                    color: 'var(--color-text)',
                  }}
                />
              </div>
            </Field>

            {/* Line height */}
            <Field label="行间距">
              <div className="flex flex-wrap gap-1.5">
                {LINE_HEIGHTS.map((lh) => (
                  <button
                    key={lh.value}
                    onClick={() => updateField('line_height', lh.value)}
                    className="cursor-pointer rounded border px-2.5 py-1 text-xs font-medium transition-colors"
                    style={{
                      borderColor: config.line_height === lh.value ? 'var(--color-accent)' : 'var(--color-border)',
                      background: config.line_height === lh.value ? 'var(--color-accent-light)' : 'var(--color-bg-card)',
                      color: config.line_height === lh.value ? 'var(--color-accent-dark)' : 'var(--color-text-secondary)',
                    }}
                  >
                    {lh.label}
                  </button>
                ))}
              </div>
            </Field>

            {/* Figure scale */}
            <Field label="图片缩放">
              <div className="flex flex-wrap gap-1.5">
                {FIGURE_SCALES.map((fs) => (
                  <button
                    key={fs.value}
                    onClick={() => updateField('figure_scale', fs.value)}
                    className="cursor-pointer rounded border px-2.5 py-1 text-xs font-medium transition-colors"
                    style={{
                      borderColor: config.figure_scale === fs.value ? 'var(--color-accent)' : 'var(--color-border)',
                      background: config.figure_scale === fs.value ? 'var(--color-accent-light)' : 'var(--color-bg-card)',
                      color: config.figure_scale === fs.value ? 'var(--color-accent-dark)' : 'var(--color-text-secondary)',
                    }}
                  >
                    {fs.label}
                  </button>
                ))}
              </div>
            </Field>

            {/* Question number style */}
            <Field label="题号样式">
              <div className="flex flex-wrap gap-1.5">
                {NUMBER_STYLES.map((ns) => (
                  <button
                    key={ns.value}
                    onClick={() => updateField('question_number_style', ns.value)}
                    className="cursor-pointer rounded border px-2.5 py-1 text-xs font-medium transition-colors"
                    style={{
                      borderColor: config.question_number_style === ns.value ? 'var(--color-accent)' : 'var(--color-border)',
                      background: config.question_number_style === ns.value ? 'var(--color-accent-light)' : 'var(--color-bg-card)',
                      color: config.question_number_style === ns.value ? 'var(--color-accent-dark)' : 'var(--color-text-secondary)',
                    }}
                  >
                    {ns.label}
                  </button>
                ))}
              </div>
            </Field>
          </Section>

          {/* ── Section: 页面设置 ── */}
          <Section title="页面设置">
            <div className="grid grid-cols-2 gap-3">
              <Field label="纸张大小">
                <select
                  value={config.page_size || 'A4'}
                  onChange={(e) => updateField('page_size', e.target.value)}
                  className="w-full rounded border px-2 py-1.5 text-sm outline-none"
                  style={{
                    borderColor: 'var(--color-border)',
                    background: 'var(--color-bg)',
                    color: 'var(--color-text)',
                  }}
                >
                  <option value="A4">A4</option>
                  <option value="A3">A3</option>
                </select>
              </Field>
              <Field label="页面方向">
                <select
                  value={config.orientation || 'portrait'}
                  onChange={(e) => updateField('orientation', e.target.value)}
                  className="w-full rounded border px-2 py-1.5 text-sm outline-none"
                  style={{
                    borderColor: 'var(--color-border)',
                    background: 'var(--color-bg)',
                    color: 'var(--color-text)',
                  }}
                >
                  <option value="portrait">纵向</option>
                  <option value="landscape">横向</option>
                </select>
              </Field>
            </div>

            <Field label="讲义标题（页眉）">
              <input
                value={config.header || ''}
                onChange={(e) => updateField('header', e.target.value)}
                placeholder="如：高中物理一轮复习讲义"
                className="w-full rounded border px-2 py-1.5 text-sm outline-none"
                style={{
                  borderColor: 'var(--color-border)',
                  background: 'var(--color-bg)',
                  color: 'var(--color-text)',
                }}
              />
            </Field>

            <Field label="页脚文字">
              <input
                value={config.footer || ''}
                onChange={(e) => updateField('footer', e.target.value)}
                placeholder="如：Physics Vault 讲义系统"
                className="w-full rounded border px-2 py-1.5 text-sm outline-none"
                style={{
                  borderColor: 'var(--color-border)',
                  background: 'var(--color-bg)',
                  color: 'var(--color-text)',
                }}
              />
            </Field>
          </Section>

          {/* ── Section: 内容设置 ── */}
          <Section title="内容设置">
            <Field label="答案与解析">
              <div className="flex flex-wrap gap-2">
                <ToggleChip
                  label="显示答案"
                  active={config.show_answer ?? true}
                  onClick={() => toggleBool('show_answer')}
                />
                <ToggleChip
                  label="显示解析"
                  active={config.show_analysis ?? true}
                  onClick={() => toggleBool('show_analysis')}
                />
              </div>
            </Field>

            <Field label="知识点生成">
              <select
                value={config.knowledge_mode || 'static'}
                onChange={(e) => updateField('knowledge_mode', e.target.value)}
                className="w-full rounded border px-2 py-1.5 text-sm outline-none"
                style={{
                  borderColor: 'var(--color-border)',
                  background: 'var(--color-bg)',
                  color: 'var(--color-text)',
                }}
              >
                <option value="static">静态标题（使用原题知识点）</option>
                <option value="ai">AI 动态生成（需启用 AI 服务）</option>
              </select>
            </Field>

            {config.knowledge_mode === 'ai' && (
              <>
                <Field label="知识点风格">
                  <div className="flex flex-wrap gap-1.5">
                    {KNOWLEDGE_STYLES.map((ks) => (
                      <button
                        key={ks.value}
                        onClick={() => updateField('knowledge_style', ks.value)}
                        className="cursor-pointer rounded border px-2.5 py-1 text-xs font-medium transition-colors"
                        style={{
                          borderColor: config.knowledge_style === ks.value ? 'var(--color-accent)' : 'var(--color-border)',
                          background: config.knowledge_style === ks.value ? 'var(--color-accent-light)' : 'var(--color-bg-card)',
                          color: config.knowledge_style === ks.value ? 'var(--color-accent-dark)' : 'var(--color-text-secondary)',
                        }}
                      >
                        {ks.label}
                      </button>
                    ))}
                  </div>
                </Field>

                <Field label="知识点篇幅">
                  <div className="flex flex-wrap gap-1.5">
                    {KNOWLEDGE_LENGTHS.map((kl) => (
                      <button
                        key={kl.value}
                        onClick={() => updateField('knowledge_length', kl.value)}
                        className="cursor-pointer rounded border px-2.5 py-1 text-xs font-medium transition-colors"
                        style={{
                          borderColor: config.knowledge_length === kl.value ? 'var(--color-accent)' : 'var(--color-border)',
                          background: config.knowledge_length === kl.value ? 'var(--color-accent-light)' : 'var(--color-bg-card)',
                          color: config.knowledge_length === kl.value ? 'var(--color-accent-dark)' : 'var(--color-text-secondary)',
                        }}
                      >
                        {kl.label}
                      </button>
                    ))}
                  </div>
                </Field>
              </>
            )}
          </Section>

          {/* ── Section: 当前 JSON 预览 ── */}
          <Section title="配置预览（JSON）">
            <pre
              className="max-h-48 overflow-auto rounded p-3 text-xs leading-relaxed"
              style={{
                background: 'var(--color-bg-code)',
                color: 'var(--color-text-secondary)',
                fontFamily: 'monospace',
                whiteSpace: 'pre-wrap',
              }}
            >
              {JSON.stringify(config, null, 2)}
            </pre>
          </Section>
        </div>
      </main>
    </div>
  );
}

// ── Small helpers ──────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      className="space-y-3 rounded-lg border p-4"
      style={{
        borderColor: 'var(--color-border)',
        background: 'var(--color-bg-card)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      <h3
        className="border-b pb-2 text-xs font-semibold uppercase tracking-wider"
        style={{ borderColor: 'var(--color-border)', color: 'var(--color-text-muted)' }}
      >
        {title}
      </h3>
      {children}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label
        className="mb-1.5 block text-xs font-medium"
        style={{ color: 'var(--color-text-muted)' }}
      >
        {label}
      </label>
      {children}
    </div>
  );
}

function ToggleChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="cursor-pointer rounded-full border-none px-3 py-1.5 text-xs font-medium transition-colors"
      style={{
        background: active ? 'var(--color-green-light)' : 'var(--color-bg-hover)',
        color: active ? 'var(--color-green)' : 'var(--color-text-muted)',
      }}
    >
      {active ? '✓ ' : ''}{label}
    </button>
  );
}
