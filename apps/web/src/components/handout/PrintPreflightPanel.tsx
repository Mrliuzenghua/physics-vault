import type { HandoutConfig, PreflightRiskItem } from '../../types';

interface Props {
  config: HandoutConfig;
  pageCount: number;
  questionCount: number;
  risks: PreflightRiskItem[];
  sparsePageCount: number;
  oversizedItemCount: number;
  onPrint: () => void;
  onBack: () => void;
}

const SEVERITY_COLORS: Record<string, string> = {
  warning: 'var(--color-accent, #f08c00)',
  danger: 'var(--color-red, #e03131)',
};

const SEVERITY_BG: Record<string, string> = {
  warning: 'var(--color-accent-light, #fff3bf)',
  danger: 'var(--color-red-light, #ffe3e3)',
};

const SEVERITY_LABELS: Record<string, string> = {
  warning: '提醒',
  danger: '风险',
};

export default function PrintPreflightPanel({
  config,
  pageCount,
  questionCount,
  risks,
  sparsePageCount,
  oversizedItemCount,
  onPrint,
  onBack,
}: Props) {
  const isTeacher = config.showAnswers || config.showAnalysis;

  return (
    <div
      className="handout-screen-only flex h-full flex-col"
      style={{
        width: 320,
        background: 'var(--color-bg-card)',
        borderLeft: '1px solid var(--color-border)',
        boxShadow: 'var(--shadow-lg, 0 4px 16px rgba(20,30,60,.12))',
        zIndex: 20,
      }}
    >
      <div className="flex-shrink-0 border-b px-4 py-3" style={{ borderColor: 'var(--color-border)' }}>
        <h2 className="text-sm font-bold" style={{ color: 'var(--color-text)' }}>
          打印检查
        </h2>
        <p className="mt-0.5 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          正式打印前，先快速核对页数、密度和风险提示。
        </p>
      </div>

      <div className="flex-shrink-0 border-b px-4 py-3" style={{ borderColor: 'var(--color-border)' }}>
        <h3 className="mb-2 text-xs font-semibold" style={{ color: 'var(--color-text-muted)' }}>
          当前配置
        </h3>
        <div className="space-y-1 text-xs">
          <ConfigRow label="版本" value={isTeacher ? '教师版' : '学生版'} />
          <ConfigRow label="答案" value={config.showAnswers ? '显示' : '隐藏'} />
          <ConfigRow label="解析" value={config.showAnalysis ? '显示' : '隐藏'} />
          <ConfigRow label="页眉" value={config.headerFooter.headerEnabled ? '开启' : '关闭'} />
          <ConfigRow label="页脚" value={config.headerFooter.footerEnabled ? '开启' : '关闭'} />
          <ConfigRow label="页码" value={config.headerFooter.showPageNumber ? '显示' : '隐藏'} />
          <ConfigRow label="字号" value={`${config.styleConfig.fontSize}px`} />
          <ConfigRow label="行距" value={String(config.styleConfig.lineHeight)} />
        </div>
        {(sparsePageCount > 0 || oversizedItemCount > 0) && (
          <div className="mt-3 space-y-1 rounded border px-3 py-2 text-xs" style={{ borderColor: 'var(--color-accent)', background: 'var(--color-accent-light)', color: 'var(--color-text)' }}>
            {sparsePageCount > 0 && <div>有 {sparsePageCount} 页内容偏少，可能出现较大空白。</div>}
            {oversizedItemCount > 0 && <div>有 {oversizedItemCount} 个内容块偏长，可能跨页。</div>}
          </div>
        )}
      </div>

      <div className="flex-shrink-0 border-b px-4 py-3" style={{ borderColor: 'var(--color-border)' }}>
        <div className="flex items-center justify-between text-xs">
          <span style={{ color: 'var(--color-text-muted)' }}>总页数</span>
          <span className="font-semibold tabular-nums" style={{ color: 'var(--color-text)' }}>
            {pageCount} 页
          </span>
        </div>
        <div className="mt-1 flex items-center justify-between text-xs">
          <span style={{ color: 'var(--color-text-muted)' }}>总题数</span>
          <span className="font-semibold tabular-nums" style={{ color: 'var(--color-text)' }}>
            {questionCount} 题
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        <h3 className="mb-2 text-xs font-semibold" style={{ color: 'var(--color-text-muted)' }}>
          风险提示
          {risks.length > 0 && (
            <span
              className="ml-1.5 rounded-full px-1.5 py-0.5 text-xs"
              style={{ background: 'var(--color-red-light)', color: 'var(--color-red)' }}
            >
              {risks.length}
            </span>
          )}
        </h3>

        {risks.length === 0 ? (
          <div
            className="rounded border p-3 text-center text-xs"
            style={{
              borderColor: 'var(--color-green)',
              background: 'var(--color-green-light)',
              color: 'var(--color-green)',
            }}
          >
            当前没有发现明显排版风险，可以继续打印。
          </div>
        ) : (
          <div className="space-y-1.5">
            {risks.map((risk, index) => (
              <div
                key={`${risk.pageIndex}-${index}`}
                className="rounded border p-2 text-xs"
                style={{
                  borderColor: SEVERITY_COLORS[risk.severity],
                  background: SEVERITY_BG[risk.severity],
                }}
              >
                <div className="mb-0.5 flex items-center gap-1.5">
                  <span
                    className="rounded px-1 py-0.5 text-xs font-bold"
                    style={{ background: SEVERITY_COLORS[risk.severity], color: '#fff' }}
                  >
                    {SEVERITY_LABELS[risk.severity]}
                  </span>
                  <span style={{ color: 'var(--color-text-secondary)' }}>{risk.pageLabel}</span>
                </div>
                <div style={{ color: 'var(--color-text)' }}>{risk.message}</div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex-shrink-0 border-t px-4 py-3" style={{ borderColor: 'var(--color-border)' }}>
        <div className="space-y-2">
          <button
            type="button"
            onClick={onPrint}
            className="w-full cursor-pointer rounded-lg border-none px-4 py-2.5 text-sm font-semibold text-white transition-colors"
            style={{ background: 'var(--color-accent)' }}
          >
            打印 / 导出 PDF
          </button>
          <button
            type="button"
            onClick={onBack}
            className="w-full cursor-pointer rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors"
            style={{
              borderColor: 'var(--color-border)',
              background: 'var(--color-bg-hover)',
              color: 'var(--color-text-secondary)',
            }}
          >
            返回预览
          </button>
        </div>
      </div>
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span style={{ color: 'var(--color-text-muted)' }}>{label}</span>
      <span style={{ color: 'var(--color-text)' }}>{value}</span>
    </div>
  );
}
