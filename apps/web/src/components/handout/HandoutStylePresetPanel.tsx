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
  { value: 'circled', label: '① ② ③' },
  { value: 'bracket', label: '(1) (2) (3)' },
];

const ORIENTATION_OPTIONS: { value: HandoutStyleConfig['pageOrientation']; label: string }[] = [
  { value: 'portrait', label: '竖排' },
  { value: 'landscape', label: '横排' },
];

export type HandoutStyleTab = 'page' | 'text' | 'question' | 'image' | 'template';

export const HANDOUT_STYLE_TABS: Array<{ value: HandoutStyleTab; label: string; icon: string }> = [
  { value: 'page', label: '页面', icon: '▣' },
  { value: 'text', label: '文字', icon: 'A' },
  { value: 'question', label: '题目', icon: '№' },
  { value: 'image', label: '图片', icon: '▧' },
  { value: 'template', label: '模板', icon: '▤' },
];

interface Props {
  currentConfig: HandoutStyleConfig;
  onApplyConfig: (config: HandoutStyleConfig) => void;
  activeTab?: HandoutStyleTab;
}

export default function HandoutStylePresetPanel({ currentConfig, onApplyConfig, activeTab = 'page' }: Props) {
  const [presets, setPresets] = useState<HandoutStylePreset[]>(() => loadPresets());
  const [newName, setNewName] = useState('');
  const [msg, setMsg] = useState<string | null>(null);

  const flash = (text: string) => {
    setMsg(text);
    window.setTimeout(() => setMsg(null), 2000);
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
    setPresets(savePreset(preset));
    setNewName('');
    flash(`已保存“${name}”`);
  }, [currentConfig, newName]);

  const handleLoad = useCallback((preset: HandoutStylePreset) => {
    onApplyConfig({ ...preset.config });
    flash(`已应用“${preset.name}”`);
  }, [onApplyConfig]);

  const handleDelete = useCallback((preset: HandoutStylePreset) => {
    setPresets(deletePreset(preset.id));
    flash(`已删除“${preset.name}”`);
  }, []);

  const updateField = <K extends keyof HandoutStyleConfig>(key: K, value: HandoutStyleConfig[K]) => {
    onApplyConfig({ ...currentConfig, [key]: value });
  };

  return (
    <aside className="pv-style-inspector">
      <header className="pv-style-inspector__header">
        <div className="pv-style-inspector__eyebrow">页面</div>
        <div className="pv-style-inspector__title-row">
          <div>
            <h3>样式预设与编辑</h3>
            <p>设置纸张、文字、题目与图片的版式</p>
          </div>
          <button type="button" className="pv-style-inspector__reset" onClick={() => {
            onApplyConfig({ ...DEFAULT_STYLE_CONFIG });
            flash('已恢复标准样式');
          }}>
            恢复默认
          </button>
        </div>
      </header>

      {msg && <div className="pv-style-inspector__notice">{msg}</div>}

      {activeTab === 'page' && <section className="pv-style-card">
        <SectionHeading icon="▣" title="页面设置" description="纸张方向与页面留白" />
        <div className="pv-word-option-grid">
          <OptionButton active={currentConfig.pageSize === 'A4'} onClick={() => updateField('pageSize', 'A4')}>
            <span className="pv-page-icon pv-page-icon--a4" /><span><strong>A4</strong><small>常用讲义</small></span>
          </OptionButton>
          <OptionButton active={currentConfig.pageSize === 'A3'} onClick={() => updateField('pageSize', 'A3')}>
            <span className="pv-page-icon pv-page-icon--a3" /><span><strong>A3</strong><small>大幅讲义</small></span>
          </OptionButton>
        </div>
        <div className="pv-segmented-control">
          {ORIENTATION_OPTIONS.map((option) => (
            <button
              type="button"
              key={option.value}
              className={currentConfig.pageOrientation === option.value ? 'is-active' : ''}
              onClick={() => onApplyConfig({ ...currentConfig, pageOrientation: option.value, layoutMode: 'flow' })}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="pv-style-card__rows">
          <ControlRow label="上边距" value={`${currentConfig.pageMarginTop} mm`}>
            <RangeInput min={5} max={30} value={currentConfig.pageMarginTop} onChange={(value) => updateField('pageMarginTop', value)} />
          </ControlRow>
          <ControlRow label="下边距" value={`${currentConfig.pageMarginBottom} mm`}>
            <RangeInput min={5} max={30} value={currentConfig.pageMarginBottom} onChange={(value) => updateField('pageMarginBottom', value)} />
          </ControlRow>
          <ControlRow label="左右边距" value={`${currentConfig.pageMarginLeft} mm`}>
            <RangeInput min={8} max={30} value={currentConfig.pageMarginLeft} onChange={(value) => onApplyConfig({ ...currentConfig, pageMarginLeft: value, pageMarginRight: value })} />
          </ControlRow>
        </div>
        <div className="pv-word-layout-row">
          <span>版式</span>
          <div className="pv-segmented-control">
            <button type="button" className="is-active" onClick={() => updateField('layoutMode', 'flow')}>流式布局</button>
          </div>
        </div>
      </section>}

      {activeTab === 'text' && <section className="pv-style-card">
        <SectionHeading icon="Aa" title="文字排版" description="正文的阅读节奏" />
        <div className="pv-style-card__rows">
          <ControlRow label="字号" value={`${currentConfig.fontSize} px`}>
            <RangeInput min={10} max={24} value={currentConfig.fontSize} onChange={(value) => updateField('fontSize', value)} />
          </ControlRow>
          <ControlRow label="行距" value={currentConfig.lineHeight.toFixed(2)}>
            <RangeInput min={1.2} max={3} step={0.1} value={currentConfig.lineHeight} onChange={(value) => updateField('lineHeight', value)} />
          </ControlRow>
        </div>
        <label className="pv-style-select">
          <span>字体</span>
          <select value={currentConfig.fontFamily} onChange={(event) => updateField('fontFamily', event.target.value as HandoutStyleConfig['fontFamily'])}>
            <option value="songti">宋体</option><option value="heiti">黑体</option><option value="kaiti">楷体</option><option value="fangsong">仿宋</option><option value="system">系统默认</option>
          </select>
        </label>
      </section>}

      {activeTab === 'question' && <section className="pv-style-card">
        <SectionHeading icon="#" title="题目样式" description="题号、选项与分页规则" />
        <label className="pv-style-select">
          <span>题号样式</span>
          <select value={currentConfig.questionNumberStyle} onChange={(event) => updateField('questionNumberStyle', event.target.value as HandoutStyleConfig['questionNumberStyle'])}>
            {NUMBER_STYLE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <div className="pv-style-card__rows">
          <ControlRow label="题间距" value={`${currentConfig.questionSpacing} px`}>
            <RangeInput min={6} max={40} step={2} value={currentConfig.questionSpacing} onChange={(value) => updateField('questionSpacing', value)} />
          </ControlRow>
        </div>
        <label className="pv-style-select">
          <span>选项布局</span>
          <select value={currentConfig.optionLayout} onChange={(event) => updateField('optionLayout', event.target.value as HandoutStyleConfig['optionLayout'])}>
            <option value="auto">智能判断</option><option value="single">单列</option><option value="double">双列</option>
          </select>
        </label>
        <div className="pv-style-card__rows">
          <ControlRow label="页面填充" value={`${currentConfig.pageFillPercent}%`}>
            <RangeInput min={78} max={98} step={1} value={currentConfig.pageFillPercent} onChange={(value) => updateField('pageFillPercent', value)} />
          </ControlRow>
        </div>
        <div className="pv-rule-list">
          <RuleToggle label="题目尽量保持同页" checked={currentConfig.keepQuestionTogether} onChange={(checked) => updateField('keepQuestionTogether', checked)} />
          <RuleToggle label="题图跟随题干" checked={currentConfig.keepFigureWithStem} onChange={(checked) => updateField('keepFigureWithStem', checked)} />
          <RuleToggle label="长题优先从新页开始" checked={currentConfig.startLongQuestionOnNewPage} onChange={(checked) => updateField('startLongQuestionOnNewPage', checked)} />
        </div>
      </section>}

      {activeTab === 'image' && <section className="pv-style-card">
        <SectionHeading icon="▧" title="图片" description="统一图片在页面中的显示比例" />
        <ControlRow label="图片比例" value={`${Math.round(currentConfig.figureScale * 100)}%`}>
          <RangeInput min={0.3} max={1.5} step={0.1} value={currentConfig.figureScale} onChange={(value) => updateField('figureScale', value)} />
        </ControlRow>
      </section>}

      {activeTab === 'template' && <section className="pv-style-presets">
        <div className="pv-style-presets__heading">
          <div>
            <span>样式预设</span>
            <small>保存并复用当前设置</small>
          </div>
          <span className="pv-style-presets__count">{presets.length}</span>
        </div>
        <div className="pv-style-presets__save">
          <input value={newName} onChange={(event) => setNewName(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') handleSave(); }} placeholder="例如：周练双栏" />
          <button type="button" disabled={!newName.trim()} onClick={handleSave}>保存</button>
        </div>
        <div className="pv-style-presets__list">
          {presets.length === 0 ? <p>暂无预设，调整后可保存为常用版式。</p> : presets.map((preset) => {
            const isBuiltin = preset.id.startsWith('__');
            const isActive = JSON.stringify(preset.config) === JSON.stringify(currentConfig);
            return (
              <div key={preset.id} className={`pv-style-preset ${isActive ? 'is-active' : ''}`}>
                <div className="pv-style-preset__name">
                  <span>{preset.name}</span>
                  {isBuiltin && <small>内置</small>}
                  {preset.description && <p>{preset.description}</p>}
                </div>
                <div className="pv-style-preset__actions">
                  <button type="button" onClick={() => handleLoad(preset)}>{isActive ? '已使用' : '应用'}</button>
                  {!isBuiltin && <button type="button" className="is-danger" onClick={() => handleDelete(preset)}>删除</button>}
                </div>
              </div>
            );
          })}
        </div>
      </section>}
    </aside>
  );
}

function OptionButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" className={`pv-word-option ${active ? 'is-active' : ''}`} onClick={onClick}>{children}</button>;
}

function SectionHeading({ icon, title, description }: { icon: string; title: string; description: string }) {
  return <div className="pv-style-card__heading"><span>{icon}</span><div><h4>{title}</h4><p>{description}</p></div></div>;
}

function ControlRow({ label, value, children }: { label: string; value: string; children: React.ReactNode }) {
  return <div className="pv-style-control-row"><div><span>{label}</span><strong>{value}</strong></div>{children}</div>;
}

function RangeInput({ min, max, step = 1, value, onChange }: { min: number; max: number; step?: number; value: number; onChange: (value: number) => void }) {
  return <input className="pv-style-range" type="range" min={min} max={max} step={step} value={value} onChange={(event) => onChange(Number(event.target.value))} />;
}

function RuleToggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="pv-rule-toggle">
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}
