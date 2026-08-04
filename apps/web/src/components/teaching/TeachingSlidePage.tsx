import type { SlidePage, SlideSection } from '../../types/slides';
import { imageFileUrl } from '../../utils/imageUrl';
import LatexRenderer from '../render/LatexRenderer';

interface Props {
  data: SlidePage;
  fitToViewport?: boolean;
}

// ── Section type config ──────────────────────────────────────────────

const SECTION_COLORS: Record<string, { border: string; bg: string; accent: string; icon: string }> = {
  summary:   { border: '#3b82f6', bg: '#eff6ff', accent: '#1d4ed8', icon: '📋' },
  method:    { border: '#8b5cf6', bg: '#f5f3ff', accent: '#6d28d9', icon: '🔬' },
  warning:   { border: '#f59e0b', bg: '#fffbeb', accent: '#b45309', icon: '⚠' },
  example:   { border: '#10b981', bg: '#ecfdf5', accent: '#047857', icon: '📝' },
  formula:   { border: '#6366f1', bg: '#eef2ff', accent: '#4338ca', icon: '∑' },
  figure:    { border: '#0ea5e9', bg: '#f0f9ff', accent: '#0369a1', icon: '📐' },
};

const SECTION_LABELS: Record<string, string> = {
  summary: '核心知识',
  method: '解题方法',
  warning: '常见误区',
  example: '典型例题',
  formula: '核心公式',
  figure: '图像分析',
};

// ── Main component ───────────────────────────────────────────────────

export default function TeachingSlidePage({ data, fitToViewport = false }: Props) {
  const { title, subtitle, badge, sections, footer } = data;

  return (
    <div style={wrapperStyle(fitToViewport)}>
      <div style={slideStyle(fitToViewport)}>
        {/* ── Header ── */}
        <div style={styles.header}>
          <div style={styles.headerTop}>
            <div style={styles.titleRow}>
              {badge && <span style={styles.badge}>{badge}</span>}
              <h1 style={styles.title}>{title}</h1>
            </div>
            {subtitle && <p style={styles.subtitle}>{subtitle}</p>}
          </div>
          <div style={styles.headerBar} />
        </div>

        {/* ── Body: sections grid ── */}
        <div style={styles.body}>
          <div style={gridStyle(sections)}>
            {sections.map((section) => (
              <SectionCard key={section.id} section={section} />
            ))}
          </div>

        </div>

        {/* ── Footer ── */}
        {footer && (
          <div style={styles.footer}>
            <div style={styles.footerBar} />
            <p style={styles.footerText}>{footer}</p>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Section card ──────────────────────────────────────────────────────

function SectionCard({ section }: { section: SlideSection }) {
  const cfg = SECTION_COLORS[section.type] || SECTION_COLORS.summary;
  const label = section.title || SECTION_LABELS[section.type] || '';
  const cols = section.columns || (section.items.length > 4 ? 2 : 1);

  return (
    <div style={cardStyle(cfg)}>
      {/* Header */}
      <div style={cardHeaderStyle(cfg)}>
        <span style={{ fontSize: 16, marginRight: 6 }}>{cfg.icon}</span>
        <span style={{ fontWeight: 700, color: cfg.accent }}>{label}</span>
        {section.note && (
          <span style={{ marginLeft: 8, fontSize: 12, color: '#94a3b8', fontWeight: 400 }}>
            {section.note}
          </span>
        )}
      </div>

      {/* Items */}
      <div style={itemsGridStyle(cols)}>
        {section.items.map((item) => (
          <div key={item.id} style={itemStyle(item.emphasis || false)}>
            <span style={bulletStyle(cfg)}>•</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <span style={itemTextStyle(item.emphasis || false)}>
                <LatexRenderer text={item.text.replace(/!\[fig:[^\]]+\]/g, '').trim()} />
              </span>
              {item.formula && (
                <span style={formulaStyle}><LatexRenderer text={item.formula} /></span>
              )}
              {item.imagePath && <SlideItemImage path={item.imagePath} alt={item.imageAlt} />}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Grid calculation ──────────────────────────────────────────────────
function SlideItemImage({ path, alt }: { path: string; alt?: string }) {
  const src = imageFileUrl(path);
  if (!src) {
    return <div style={imagePlaceholderStyle}><span style={{ fontSize: 11, color: '#94a3b8' }}>{alt || path}</span></div>;
  }
  return (
    <figure style={imagePlaceholderStyle}>
      <img
        src={src}
        alt={alt || '教学插图'}
        style={{ display: 'block', width: 'auto', maxWidth: '100%', maxHeight: 220, objectFit: 'contain', margin: '0 auto' }}
      />
      {alt && <figcaption style={{ marginTop: 5, fontSize: 11, color: '#64748b', textAlign: 'center' }}>{alt}</figcaption>}
    </figure>
  );
}

function gridStyle(sections: SlideSection[]): React.CSSProperties {
  const count = sections.length;
  if (count <= 2) return { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 };
  return { display: 'grid', gridTemplateColumns: count === 3 ? '1fr 1fr 1fr' : '1fr 1fr', gap: 14 };
}

function itemsGridStyle(cols: number): React.CSSProperties {
  return {
    display: 'grid',
    gridTemplateColumns: cols === 2 ? '1fr 1fr' : '1fr',
    gap: '6px 12px',
  };
}

// ── Styles ────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    width: '100%',
    maxWidth: 1280,
    margin: '0 auto',
    padding: '24px 16px',
  },
  slide: {
    aspectRatio: '16 / 9',
    maxHeight: 'calc(100vh - 96px)',
    display: 'flex',
    flexDirection: 'column',
    background: 'linear-gradient(135deg, #f8fafc 0%, #ffffff 50%, #f1f5f9 100%)',
    borderRadius: 16,
    boxShadow: '0 4px 24px rgba(15, 23, 42, 0.10), 0 1px 4px rgba(15, 23, 42, 0.06)',
    border: '1px solid #e2e8f0',
    overflow: 'hidden',
  },
  // Header
  header: {
    flexShrink: 0,
    padding: '28px 40px 0',
  },
  headerTop: {
    marginBottom: 12,
  },
  titleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 14,
    marginBottom: 4,
  },
  badge: {
    display: 'inline-block',
    padding: '4px 14px',
    borderRadius: 20,
    background: 'linear-gradient(135deg, #2563eb, #1d4ed8)',
    color: '#ffffff',
    fontSize: 14,
    fontWeight: 700,
    letterSpacing: 1,
    whiteSpace: 'nowrap',
    lineHeight: '24px',
  },
  title: {
    fontSize: 32,
    fontWeight: 800,
    color: '#0f172a',
    letterSpacing: 1,
    lineHeight: 1.25,
    margin: 0,
  },
  subtitle: {
    fontSize: 15,
    color: '#64748b',
    fontWeight: 400,
    margin: '2px 0 0 0',
  },
  headerBar: {
    height: 3,
    background: 'linear-gradient(90deg, #2563eb, #7c3aed, #06b6d4)',
    borderRadius: 2,
  },
  // Body
  body: {
    flex: 1,
    padding: '18px 40px',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    minHeight: 0,
  },
  aside: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 14px',
    borderRadius: 8,
    background: '#fefce8',
    border: '1px solid #fde68a',
    flexShrink: 0,
  },
  asideIcon: {
    fontSize: 16,
    flexShrink: 0,
  },
  asideText: {
    fontSize: 13,
    color: '#92400e',
    fontWeight: 500,
  },
  // Footer
  footer: {
    flexShrink: 0,
    padding: '0 40px 20px',
  },
  footerBar: {
    height: 1,
    background: '#e2e8f0',
    marginBottom: 8,
  },
  footerText: {
    fontSize: 12,
    color: '#94a3b8',
    textAlign: 'center',
    margin: 0,
  } as React.CSSProperties,
};

function wrapperStyle(fitToViewport: boolean): React.CSSProperties {
  return {
    ...styles.wrapper,
    width: fitToViewport ? '100vw' : styles.wrapper.width,
    height: fitToViewport ? '100vh' : undefined,
    maxWidth: fitToViewport ? 'none' : styles.wrapper.maxWidth,
    padding: fitToViewport ? 0 : styles.wrapper.padding,
    display: fitToViewport ? 'flex' : undefined,
    alignItems: fitToViewport ? 'center' : undefined,
    justifyContent: fitToViewport ? 'center' : undefined,
  };
}

function slideStyle(fitToViewport: boolean): React.CSSProperties {
  return {
    ...styles.slide,
    width: fitToViewport ? 'min(100vw, calc(100vh * 16 / 9))' : undefined,
    height: fitToViewport ? 'min(100vh, calc(100vw * 9 / 16))' : undefined,
    maxHeight: fitToViewport ? 'none' : styles.slide.maxHeight,
    borderRadius: fitToViewport ? 0 : styles.slide.borderRadius,
    boxShadow: fitToViewport ? 'none' : styles.slide.boxShadow,
  };
}

function cardStyle(cfg: { border: string; bg: string; accent: string }): React.CSSProperties {
  return {
    borderRadius: 12,
    border: `1px solid ${cfg.border}30`,
    background: cfg.bg,
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
  };
}

function cardHeaderStyle(cfg: { border: string; bg: string }): React.CSSProperties {
  return {
    display: 'flex',
    alignItems: 'center',
    padding: '10px 16px',
    borderBottom: `1px solid ${cfg.border}30`,
    background: `${cfg.bg}cc`,
    flexShrink: 0,
  };
}

function itemStyle(emphasis: boolean): React.CSSProperties {
  return {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 8,
    padding: emphasis ? '6px 12px' : '4px 12px',
    borderRadius: emphasis ? 6 : undefined,
    background: emphasis ? 'rgba(255,255,255,0.7)' : undefined,
    border: emphasis ? '1px solid rgba(148,163,184,0.2)' : undefined,
  };
}

function bulletStyle(cfg: { accent: string }): React.CSSProperties {
  return {
    color: cfg.accent,
    fontWeight: 700,
    fontSize: 16,
    lineHeight: 1.5,
    flexShrink: 0,
    marginTop: 1,
  };
}

function itemTextStyle(emphasis: boolean): React.CSSProperties {
  return {
    fontSize: 14,
    color: emphasis ? '#0f172a' : '#334155',
    fontWeight: emphasis ? 600 : 400,
    lineHeight: 1.6,
    wordBreak: 'break-word',
  };
}

const formulaStyle: React.CSSProperties = {
  display: 'block',
  marginTop: 4,
  padding: '6px 10px',
  borderRadius: 6,
  background: '#f1f5f9',
  fontFamily: '"KaTeX_Main", "Times New Roman", serif',
  fontSize: 15,
  color: '#1e293b',
  fontWeight: 500,
  letterSpacing: 0.5,
};

const imagePlaceholderStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  marginTop: 6,
  padding: '8px 10px',
  borderRadius: 6,
  background: '#f8fafc',
  border: '1px dashed #cbd5e1',
};
