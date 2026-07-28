import type { HandoutStyleConfig } from '../../types';

interface Props {
  styleConfig: HandoutStyleConfig;
  children: React.ReactNode;
}

interface PageSizeMm {
  width: number;
  height: number;
}

const RULER_HEIGHT = 28;
const RULER_WIDTH = 34;

export default function PageRuler({ styleConfig, children }: Props) {
  const page = getPageSizeMm(styleConfig);
  const horizontalTicks = buildTicks(page.width);
  const verticalTicks = buildTicks(page.height);

  return (
    <div className="handout-screen-only mx-auto inline-grid max-w-full grid-cols-[34px_minmax(0,auto)] grid-rows-[28px_auto]">
      <div className="sticky left-0 top-0 z-20 border-b border-r border-[#b8c2d1] bg-[#f4f7fb]" />

      <div
        className="sticky top-0 z-20 overflow-hidden border-b border-[#b8c2d1] bg-[#f4f7fb] text-[10px] text-slate-500"
        style={{ height: RULER_HEIGHT, width: `${page.width}mm` }}
      >
        {horizontalTicks.map((tick) => (
          <span
            key={`h-${tick.mm}`}
            className="absolute bottom-0 border-l border-slate-400"
            style={{
              left: `${tick.mm}mm`,
              height: tick.major ? 14 : tick.medium ? 9 : 5,
            }}
          >
            {tick.major && tick.mm > 0 && (
              <span className="absolute -left-2 bottom-3 tabular-nums">{tick.mm / 10}</span>
            )}
          </span>
        ))}
      </div>

      <div
        className="sticky left-0 z-10 overflow-hidden border-r border-[#b8c2d1] bg-[#f4f7fb] pt-6 text-[10px] text-slate-500"
        style={{ width: RULER_WIDTH, minHeight: `calc(${page.height}mm + 48px)` }}
      >
        <div className="relative" style={{ height: `${page.height}mm` }}>
          {verticalTicks.map((tick) => (
            <span
              key={`v-${tick.mm}`}
              className="absolute right-0 border-t border-slate-400"
              style={{
                top: `${tick.mm}mm`,
                width: tick.major ? 16 : tick.medium ? 10 : 5,
              }}
            >
              {tick.major && tick.mm > 0 && (
                <span className="absolute right-4 -top-2 tabular-nums">{tick.mm / 10}</span>
              )}
            </span>
          ))}
        </div>
      </div>

      <div className="min-w-0 overflow-visible">{children}</div>
    </div>
  );
}

function getPageSizeMm(styleConfig: HandoutStyleConfig): PageSizeMm {
  const base = styleConfig.pageSize === 'A3'
    ? { width: 297, height: 420 }
    : { width: 210, height: 297 };

  return styleConfig.pageOrientation === 'landscape'
    ? { width: base.height, height: base.width }
    : base;
}

function buildTicks(maxMm: number): Array<{ mm: number; major: boolean; medium: boolean }> {
  const ticks: Array<{ mm: number; major: boolean; medium: boolean }> = [];
  for (let mm = 0; mm <= maxMm; mm += 5) {
    ticks.push({
      mm,
      major: mm % 10 === 0,
      medium: mm % 10 !== 0,
    });
  }
  return ticks;
}

