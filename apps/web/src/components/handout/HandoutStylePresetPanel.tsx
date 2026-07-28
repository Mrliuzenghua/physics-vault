import { useCallback, useState } from 'react';
import type { HandoutStyleConfig, HandoutStylePreset } from '../../types';
import {
  DEFAULT_STYLE_CONFIG,
  deletePreset,
  loadPresets,
  makePresetId,
  savePreset,
} from './handoutStylePresets';

const NUMBER_STYLE_OPTIONS: { value: HandoutStyleConfig['questionNumberStyle']; label: string }[] = [
  { value: 'decimal', label: '1. 2. 3.' },
  { value: 'circled', label: '①②③' },
  { value: 'bracket', label: '(1)(2)(3)' },
];

interface Props {
  currentConfig: HandoutStyleConfig;
  onApplyConfig: (config: HandoutStyleConfig) => void;
}

export default function HandoutStylePresetPanel({ currentConfig, onApplyConfig }: Props) {
  const [presets, setPresets] = useState<HandoutStylePreset[]>(() => loadPresets());
  const [newName, setNewName] = useState('');
  const [msg, setMsg] = useState<string | null>(null);

  const flash = (text: string) => {
    setMsg(text);
    setTimeout(() => setMsg(null), 2000);
  };

  const handleSave = useCallback(() => {
    const name = newName.trim();
    if (!name) return;
    const preset: HandoutStylePreset = {
      id: makePresetId(),
      name,
      config: { ...currentConfig },
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    const updated = savePreset(preset);
    setPresets(updated);
    setNewName('');
    flash(`已保存预设"${name}"`);
  }, [currentConfig, newName]);

  const handleLoad = useCallback(
    (preset: HandoutStylePreset) => {
      onApplyConfig({ ...preset.config });
      flash(`已加载预设"${preset.name}"`);
    },
    [onApplyConfig],
  );

  const handleDelete = useCallback((preset: HandoutStylePreset) => {
    const updated = deletePreset(preset.id);
    setPresets(updated);
    flash(`已删除预设"${preset.name}"`);
  }, []);

  const handleReset = useCallback(() => {
    onApplyConfig({ ...DEFAULT_STYLE_CONFIG });
    flash('已重置为标准样式');
  }, [onApplyConfig]);

  const updateField = <K extends keyof HandoutStyleConfig>(key: K, value: HandoutStyleConfig[K]) => {
    onApplyConfig({ ...currentConfig, [key]: value });
  };

  return (
    <div
      className="rounded-lg border p-4 space-y-4"
      style={{
        background: 'var(--color-bg-card)',
        borderColor: 'var(--color-border)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      <h3
        className="text-xs font-semibold uppercase tracking-wider"
        style={{ color: 'var(--color-text-muted)' }}
      >
        样式预设与编辑
      </h3>

      {/* Flash message */}
      {msg && (
        <div
          className="rounded px-2 py-1 text-xs text-center"
          style={{ background: 'var(--color-green-light)', color: 'var(--color-green)' }}
        >
          {msg}
        </div>
      )}

      {/* ── Quick style editor ── */}
      <div className="space-y-2 border-b pb-3" style={{ borderColor: 'var(--color-border)' }}>
        <div className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          当前样式
        </div>

        <StyleRow label="字号" unit="px">
          <input
            type="range"
            min={10}
            max={24}
            value={currentConfig.fontSize}
            onChange={(e) => updateField('fontSize', Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span className="text-xs tabular-nums" style={{ color: 'var(--color-text)', minWidth: 28, textAlign: 'right' }}>
            {currentConfig.fontSize}
          </span>
        </StyleRow>

        <StyleRow label="行距">
          <input
            type="range"
            min={1.2}
            max={3}
            step={0.1}
            value={currentConfig.lineHeight}
            onChange={(e) => updateField('lineHeight', Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span className="text-xs tabular-nums" style={{ color: 'var(--color-text)', minWidth: 28, textAlign: 'right' }}>
            {currentConfig.lineHeight}
          </span>
        </StyleRow>

        <StyleRow label="题间距" unit="px">
          <input
            type="range"
            min={6}
            max={40}
            step={2}
            value={currentConfig.questionSpacing}
            onChange={(e) => updateField('questionSpacing', Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span className="text-xs tabular-nums" style={{ color: 'var(--color-text)', minWidth: 28, textAlign: 'right' }}>
            {currentConfig.questionSpacing}
          </span>
        </StyleRow>

        <StyleRow label="图片比例">
          <input
            type="range"
            min={0.3}
            max={1.5}
            step={0.1}
            value={currentConfig.figureScale}
            onChange={(e) => updateField('figureScale', Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span className="text-xs tabular-nums" style={{ color: 'var(--color-text)', minWidth: 28, textAlign: 'right' }}>
            {Math.round(currentConfig.figureScale * 100)}%
          </span>
        </StyleRow>

        <StyleRow label="上边距" unit="mm">
          <input
            type="range"
            min={5}
            max={30}
            value={currentConfig.pageMarginTop}
            onChange={(e) => updateField('pageMarginTop', Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span className="text-xs tabular-nums" style={{ color: 'var(--color-text)', minWidth: 28, textAlign: 'right' }}>
            {currentConfig.pageMarginTop}
          </span>
        </StyleRow>

        <StyleRow label="下边距" unit="mm">
          <input
            type="range"
            min={5}
            max={30}
            value={currentConfig.pageMarginBottom}
            onChange={(e) => updateField('pageMarginBottom', Number(e.target.value))}
            style={{ flex: 1 }}
          />
          <span className="text-xs tabular-nums" style={{ color: 'var(--color-text)', minWidth: 28, textAlign: 'right' }}>
            {currentConfig.pageMarginBottom}
          </span>
        </StyleRow>

        <StyleRow label="左/右边距" unit="mm">
          <input
            type="range"
            min={8}
            max={30}
            value={currentConfig.pageMarginLeft}
            onChange={(e) => {
              updateField('pageMarginLeft', Number(e.target.value));
              updateField('pageMarginRight', Number(e.target.value));
            }}
            style={{ flex: 1 }}
          />
          <span className="text-xs tabular-nums" style={{ color: 'var(--color-text)', minWidth: 28, textAlign: 'right' }}>
            {currentConfig.pageMarginLeft}
          </span>
        </StyleRow>

        <StyleRow label="题号样式">
          <select
            value={currentConfig.questionNumberStyle}
            onChange={(e) => updateField('questionNumberStyle', e.target.value as HandoutStyleConfig['questionNumberStyle'])}
            className="rounded border px-2 py-0.5 text-xs outline-none"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-bg)',
              color: 'var(--color-text)',
              flex: 1,
            }}
          >
            {NUMBER_STYLE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </StyleRow>

        <button
          onClick={handleReset}
          className="cursor-pointer rounded border px-2 py-0.5 text-xs transition-colors"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg-hover)',
            color: 'var(--color-text-muted)',
          }}
        >
          重置为标准
        </button>
      </div>

      {/* ── Save current as preset ── */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleSave(); }}
          placeholder="预设名称，如：周练用"
          className="flex-1 rounded border px-2 py-1.5 text-xs outline-none"
          style={{
            borderColor: 'var(--color-border)',
            background: 'var(--color-bg)',
            color: 'var(--color-text)',
          }}
        />
        <button
          onClick={handleSave}
          disabled={!newName.trim()}
          className="cursor-pointer rounded border-none px-3 py-1.5 text-xs font-semibold text-white transition-colors disabled:opacity-40"
          style={{ background: 'var(--color-accent)' }}
        >
          保存预设
        </button>
      </div>

      {/* ── Preset list ── */}
      <div className="space-y-1.5 border-t pt-3" style={{ borderColor: 'var(--color-border)' }}>
        <div className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          已有预设 ({presets.length})
        </div>
        {presets.length === 0 ? (
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            暂无预设，调整样式后可保存
          </p>
        ) : (
          presets.map((preset) => {
            const isBuiltin = preset.id.startsWith('__');
            const isActive =
              JSON.stringify(preset.config) === JSON.stringify(currentConfig);
            return (
              <div
                key={preset.id}
                className="flex items-center gap-2 rounded border px-2 py-1.5"
                style={{
                  borderColor: isActive ? 'var(--color-accent)' : 'var(--color-border)',
                  background: isActive ? 'var(--color-accent-light)' : 'var(--color-bg)',
                }}
              >
                <span
                  className="flex-1 truncate text-xs font-medium"
                  style={{ color: isActive ? 'var(--color-accent-dark)' : 'var(--color-text)' }}
                >
                  {preset.name}
                  {isActive ? ' ✓' : ''}
                  {isBuiltin ? (
                    <span className="ml-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                      (内置)
                    </span>
                  ) : null}
                </span>
                <button
                  onClick={() => handleLoad(preset)}
                  className="cursor-pointer rounded border-none px-2 py-0.5 text-xs font-medium transition-colors"
                  style={{
                    background: 'var(--color-accent-light)',
                    color: 'var(--color-accent-dark)',
                  }}
                >
                  加载
                </button>
                {!isBuiltin && (
                  <button
                    onClick={() => handleDelete(preset)}
                    className="cursor-pointer rounded border-none px-2 py-0.5 text-xs transition-colors"
                    style={{
                      background: 'var(--color-red-light)',
                      color: 'var(--color-red)',
                    }}
                  >
                    删除
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function StyleRow({
  label,
  unit,
  children,
}: {
  label: string;
  unit?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs shrink-0" style={{ color: 'var(--color-text-muted)', width: 56 }}>
        {label}{unit ? ` (${unit})` : ''}
      </span>
      {children}
    </div>
  );
}
