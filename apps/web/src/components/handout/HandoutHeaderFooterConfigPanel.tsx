import type { JSX } from 'react';
import type { HandoutHeaderFooterConfig, HeaderFooterAlignment } from '../../types';

const DEFAULT_CONFIG: HandoutHeaderFooterConfig = {
  headerEnabled: true,
  headerText: '',
  headerAlign: 'center',
  footerEnabled: true,
  footerText: '',
  footerAlign: 'center',
  showPageNumber: true,
};

const ALIGN_OPTIONS: { value: HeaderFooterAlignment; label: string; icon: JSX.Element }[] = [
  {
    value: 'left',
    label: '居左',
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="13" y2="12" /><line x1="3" y1="18" x2="17" y2="18" />
      </svg>
    ),
  },
  {
    value: 'center',
    label: '居中',
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <line x1="3" y1="6" x2="21" y2="6" /><line x1="7" y1="12" x2="17" y2="12" /><line x1="5" y1="18" x2="19" y2="18" />
      </svg>
    ),
  },
  {
    value: 'right',
    label: '居右',
    icon: (
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <line x1="3" y1="6" x2="21" y2="6" /><line x1="11" y1="12" x2="21" y2="12" /><line x1="7" y1="18" x2="21" y2="18" />
      </svg>
    ),
  },
];

interface Props {
  config: HandoutHeaderFooterConfig;
  onChange: (config: HandoutHeaderFooterConfig) => void;
}

export { DEFAULT_CONFIG };

/* ── Toggle switch ── */
function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className="cursor-pointer border-none"
      style={{
        width: 34,
        height: 20,
        borderRadius: 999,
        background: checked ? 'var(--color-accent)' : 'var(--color-border-strong)',
        position: 'relative',
        transition: 'background 0.2s ease',
        flexShrink: 0,
        padding: 0,
        boxShadow: checked ? '0 1px 3px rgba(47,111,221,0.35)' : 'inset 0 1px 2px rgba(16,24,40,0.08)',
      }}
    >
      <span
        style={{
          position: 'absolute',
          top: 2,
          left: checked ? 16 : 2,
          width: 16,
          height: 16,
          borderRadius: '50%',
          background: '#fff',
          transition: 'left 0.2s ease',
          boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
        }}
      />
    </button>
  );
}

/* ── Segmented alignment control ── */
function AlignSegment({
  value,
  onChange,
}: {
  value: HeaderFooterAlignment;
  onChange: (v: HeaderFooterAlignment) => void;
}) {
  return (
    <div
      className="inline-flex rounded-lg p-0.5"
      style={{
        border: '1px solid var(--color-border)',
        background: 'var(--color-bg)',
        gap: 2,
      }}
    >
      {ALIGN_OPTIONS.map((opt) => {
        const active = value === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className="cursor-pointer border-none flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-medium transition-all duration-150"
            style={{
              background: active ? 'var(--color-bg-card)' : 'transparent',
              color: active ? 'var(--color-accent)' : 'var(--color-text-muted)',
              boxShadow: active ? 'var(--shadow-sm)' : 'none',
            }}
          >
            {opt.icon}
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}

/* ── Section row ── */
function Section({
  icon,
  title,
  hint,
  checked,
  onToggle,
  children,
}: {
  icon: JSX.Element;
  title: string;
  hint?: string;
  checked: boolean;
  onToggle: (v: boolean) => void;
  children?: React.ReactNode;
}) {
  return (
    <div
      className="rounded-lg transition-colors"
      style={{
        border: '1px solid var(--color-border)',
        background: checked ? 'var(--color-bg-card)' : 'var(--color-bg)',
      }}
    >
      <div className="flex items-center gap-2.5 px-3 py-2.5">
        <span
          className="flex h-6 w-6 items-center justify-center rounded-md"
          style={{
            background: checked ? 'var(--color-accent-light)' : 'var(--color-bg-hover)',
            color: checked ? 'var(--color-accent)' : 'var(--color-text-muted)',
            transition: 'all 0.2s ease',
          }}
        >
          {icon}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-medium leading-tight" style={{ color: 'var(--color-text)' }}>
            {title}
          </div>
          {hint && (
            <div className="text-[11px] leading-tight mt-0.5" style={{ color: 'var(--color-text-muted)' }}>
              {hint}
            </div>
          )}
        </div>
        <Toggle checked={checked} onChange={onToggle} label={title} />
      </div>
      {checked && children && (
        <div
          className="px-3 pb-3 pt-2.5 space-y-2.5"
          style={{ borderTop: '1px dashed var(--color-border)' }}
        >
          {children}
        </div>
      )}
    </div>
  );
}

/* ── Text input ── */
function PanelInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full rounded-md px-2.5 py-1.5 text-[13px] outline-none transition-all duration-150"
      style={{
        border: '1px solid var(--color-border)',
        background: 'var(--color-bg)',
        color: 'var(--color-text)',
      }}
      onFocus={(e) => {
        e.currentTarget.style.borderColor = 'var(--color-accent)';
        e.currentTarget.style.boxShadow = '0 0 0 3px rgba(47,111,221,0.12)';
      }}
      onBlur={(e) => {
        e.currentTarget.style.borderColor = 'var(--color-border)';
        e.currentTarget.style.boxShadow = 'none';
      }}
    />
  );
}

export default function HandoutHeaderFooterConfigPanel({ config, onChange }: Props) {
  const update = (patch: Partial<HandoutHeaderFooterConfig>) => {
    onChange({ ...config, ...patch });
  };

  return (
    <div
      className="rounded-xl border p-3.5 space-y-2.5"
      style={{
        background: 'var(--color-bg-card)',
        borderColor: 'var(--color-border)',
        boxShadow: 'var(--shadow-card)',
      }}
    >
      {/* Panel title */}
      <div className="flex items-center gap-2 px-0.5 pb-1">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-muted)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <line x1="3" y1="9" x2="21" y2="9" />
          <line x1="3" y1="15" x2="21" y2="15" />
        </svg>
        <h3 className="text-xs font-semibold uppercase" style={{ color: 'var(--color-text-muted)', letterSpacing: '0.08em' }}>
          页眉页脚
        </h3>
      </div>

      {/* Header section */}
      <Section
        title="页眉"
        hint="每页顶部显示的标题文字"
        checked={config.headerEnabled}
        onToggle={(v) => update({ headerEnabled: v })}
        icon={
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="4" y1="5" x2="20" y2="5" /><line x1="4" y1="9" x2="16" y2="9" />
            <line x1="4" y1="15" x2="20" y2="15" strokeOpacity="0.35" /><line x1="4" y1="19" x2="14" y2="19" strokeOpacity="0.35" />
          </svg>
        }
      >
        <PanelInput
          value={config.headerText}
          onChange={(v) => update({ headerText: v })}
          placeholder="如：XX中学高三物理周练"
        />
        <div className="flex items-center justify-between">
          <span className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>对齐方式</span>
          <AlignSegment value={config.headerAlign} onChange={(v) => update({ headerAlign: v })} />
        </div>
      </Section>

      {/* Footer section */}
      <Section
        title="页脚"
        hint="每页底部显示的备注文字"
        checked={config.footerEnabled}
        onToggle={(v) => update({ footerEnabled: v })}
        icon={
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <line x1="4" y1="5" x2="20" y2="5" strokeOpacity="0.35" /><line x1="4" y1="9" x2="16" y2="9" strokeOpacity="0.35" />
            <line x1="4" y1="15" x2="20" y2="15" /><line x1="4" y1="19" x2="14" y2="19" />
          </svg>
        }
      >
        <PanelInput
          value={config.footerText}
          onChange={(v) => update({ footerText: v })}
          placeholder="如：认真审题，规范作答"
        />
        <div className="flex items-center justify-between">
          <span className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>对齐方式</span>
          <AlignSegment value={config.footerAlign} onChange={(v) => update({ footerAlign: v })} />
        </div>
      </Section>

      {/* Page number section */}
      <Section
        title="页码"
        hint="在页脚处显示「第 X 页」"
        checked={config.showPageNumber}
        onToggle={(v) => update({ showPageNumber: v })}
        icon={
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 19h16" /><path d="M7 15l3-9 2 6 2-4 3 7" />
          </svg>
        }
      />
    </div>
  );
}
