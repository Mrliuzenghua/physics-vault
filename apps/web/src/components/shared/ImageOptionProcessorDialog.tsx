import { useEffect, useMemo, useRef, useState } from 'react';

export type ImageProcessMode = 'split' | 'enhance';
type SplitLayout = 'horizontal' | 'grid' | 'vertical';

export interface ImageProcessResult {
  mode: ImageProcessMode;
  files: File[];
}

interface Props {
  open: boolean;
  sourceUrl: string;
  sourceName: string;
  onClose: () => void;
  onApply: (result: ImageProcessResult) => void | Promise<void>;
}

interface Region {
  x: number;
  y: number;
  width: number;
  height: number;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function buildImageRegions(
  width: number,
  height: number,
  layout: SplitLayout,
  horizontalCuts: number[],
  verticalCuts: number[],
  gridCut: [number, number],
): Region[] {
  if (layout === 'horizontal') {
    const cuts = [0, ...horizontalCuts, 100];
    return cuts.slice(0, -1).map((cut, index) => ({
      x: Math.round(width * cut / 100),
      y: 0,
      width: Math.max(1, Math.round(width * (cuts[index + 1] - cut) / 100)),
      height,
    }));
  }
  if (layout === 'vertical') {
    const cuts = [0, ...verticalCuts, 100];
    return cuts.slice(0, -1).map((cut, index) => ({
      x: 0,
      y: Math.round(height * cut / 100),
      width,
      height: Math.max(1, Math.round(height * (cuts[index + 1] - cut) / 100)),
    }));
  }
  const splitX = Math.round(width * gridCut[0] / 100);
  const splitY = Math.round(height * gridCut[1] / 100);
  return [
    { x: 0, y: 0, width: splitX, height: splitY },
    { x: splitX, y: 0, width: width - splitX, height: splitY },
    { x: 0, y: splitY, width: splitX, height: height - splitY },
    { x: splitX, y: splitY, width: width - splitX, height: height - splitY },
  ];
}

function sharpenImage(data: ImageData, amount: number): void {
  if (amount <= 0) return;
  const { width, height } = data;
  const source = new Uint8ClampedArray(data.data);
  const center = 1 + amount * 4;
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const offset = (y * width + x) * 4;
      for (let channel = 0; channel < 3; channel += 1) {
        const value = source[offset + channel] * center
          - amount * source[offset - 4 + channel]
          - amount * source[offset + 4 + channel]
          - amount * source[offset - width * 4 + channel]
          - amount * source[offset + width * 4 + channel];
        data.data[offset + channel] = clamp(Math.round(value), 0, 255);
      }
    }
  }
}

function cleanBackground(data: ImageData, threshold: number): void {
  for (let index = 0; index < data.data.length; index += 4) {
    const gray = Math.round(data.data[index] * 0.299 + data.data[index + 1] * 0.587 + data.data[index + 2] * 0.114);
    const value = gray >= threshold ? 255 : gray;
    data.data[index] = value;
    data.data[index + 1] = value;
    data.data[index + 2] = value;
  }
}

function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('PNG 生成失败')), 'image/png');
  });
}

function safeStem(filename: string): string {
  return (filename.replace(/\.[^.]+$/, '').replace(/[\\/:*?"<>|]+/g, '-').trim() || 'option-image').slice(0, 80);
}

export default function ImageOptionProcessorDialog({ open, sourceUrl, sourceName, onClose, onApply }: Props) {
  const previewRef = useRef<HTMLCanvasElement>(null);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [mode, setMode] = useState<ImageProcessMode>('split');
  const [layout, setLayout] = useState<SplitLayout>('horizontal');
  const [horizontalCuts, setHorizontalCuts] = useState([25, 50, 75]);
  const [verticalCuts, setVerticalCuts] = useState([25, 50, 75]);
  const [gridCut, setGridCut] = useState<[number, number]>([50, 50]);
  const [scale, setScale] = useState(2);
  const [brightness, setBrightness] = useState(100);
  const [contrast, setContrast] = useState(120);
  const [sharpen, setSharpen] = useState(0.35);
  const [grayscale, setGrayscale] = useState(false);
  const [backgroundClean, setBackgroundClean] = useState(false);
  const [threshold, setThreshold] = useState(235);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const regions = useMemo(() => image
    ? buildImageRegions(image.naturalWidth, image.naturalHeight, layout, horizontalCuts, verticalCuts, gridCut)
    : [], [gridCut, horizontalCuts, image, layout, verticalCuts]);

  useEffect(() => {
    if (!open || !sourceUrl) return;
    let disposed = false;
    setError(null);
    const next = new Image();
    next.crossOrigin = 'anonymous';
    next.onload = () => { if (!disposed) setImage(next); };
    next.onerror = () => { if (!disposed) setError('图片加载失败，请确认文件仍然存在'); };
    next.src = sourceUrl;
    return () => { disposed = true; };
  }, [open, sourceUrl]);

  useEffect(() => {
    const canvas = previewRef.current;
    if (!canvas || !image) return;
    const context = canvas.getContext('2d');
    if (!context) return;
    const maxWidth = 900;
    const maxHeight = 420;
    const ratio = Math.min(maxWidth / image.naturalWidth, maxHeight / image.naturalHeight, 1);
    canvas.width = Math.max(1, Math.round(image.naturalWidth * ratio));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * ratio));
    context.fillStyle = '#f8fafc';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.filter = `brightness(${brightness}%) contrast(${contrast}%) grayscale(${grayscale || backgroundClean ? 100 : 0}%)`;
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    context.filter = 'none';
    if (sharpen > 0 || backgroundClean) {
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
      if (backgroundClean) cleanBackground(pixels, threshold);
      sharpenImage(pixels, sharpen);
      context.putImageData(pixels, 0, 0);
    }
    if (mode === 'split') {
      context.strokeStyle = '#ef4444';
      context.lineWidth = 2;
      context.setLineDash([8, 5]);
      for (const region of regions.slice(0, -1)) {
        const right = (region.x + region.width) * ratio;
        const bottom = (region.y + region.height) * ratio;
        if (layout === 'horizontal') {
          context.beginPath(); context.moveTo(right, 0); context.lineTo(right, canvas.height); context.stroke();
        } else if (layout === 'vertical') {
          context.beginPath(); context.moveTo(0, bottom); context.lineTo(canvas.width, bottom); context.stroke();
        }
      }
      if (layout === 'grid') {
        context.beginPath(); context.moveTo(gridCut[0] * canvas.width / 100, 0); context.lineTo(gridCut[0] * canvas.width / 100, canvas.height); context.stroke();
        context.beginPath(); context.moveTo(0, gridCut[1] * canvas.height / 100); context.lineTo(canvas.width, gridCut[1] * canvas.height / 100); context.stroke();
      }
    }
  }, [backgroundClean, brightness, contrast, grayscale, gridCut, image, layout, mode, regions, sharpen, threshold]);

  function updateThreeCuts(current: number[], index: number, value: number): number[] {
    const next = [...current];
    const min = index === 0 ? 5 : next[index - 1] + 5;
    const max = index === 2 ? 95 : next[index + 1] - 5;
    next[index] = clamp(value, min, max);
    return next;
  }

  async function renderRegion(region: Region): Promise<HTMLCanvasElement> {
    if (!image) throw new Error('图片尚未加载');
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(region.width * scale));
    canvas.height = Math.max(1, Math.round(region.height * scale));
    const context = canvas.getContext('2d', { willReadFrequently: sharpen > 0 || backgroundClean });
    if (!context) throw new Error('浏览器无法处理图片');
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = 'high';
    context.fillStyle = '#fff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.filter = `brightness(${brightness}%) contrast(${contrast}%) grayscale(${grayscale || backgroundClean ? 100 : 0}%)`;
    context.drawImage(image, region.x, region.y, region.width, region.height, 0, 0, canvas.width, canvas.height);
    context.filter = 'none';
    if (sharpen > 0 || backgroundClean) {
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
      if (backgroundClean) cleanBackground(pixels, threshold);
      sharpenImage(pixels, sharpen);
      context.putImageData(pixels, 0, 0);
    }
    return canvas;
  }

  async function apply() {
    if (!image) return;
    setBusy(true);
    setError(null);
    try {
      const selectedRegions = mode === 'split'
        ? regions
        : [{ x: 0, y: 0, width: image.naturalWidth, height: image.naturalHeight }];
      const labels = mode === 'split' ? ['A', 'B', 'C', 'D'] : ['enhanced'];
      const files: File[] = [];
      for (let index = 0; index < selectedRegions.length; index += 1) {
        const canvas = await renderRegion(selectedRegions[index]);
        const blob = await canvasToBlob(canvas);
        files.push(new File([blob], `${safeStem(sourceName)}-${labels[index]}.png`, { type: 'image/png' }));
      }
      await onApply({ mode, files });
      onClose();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : '图片处理失败');
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  const cutControls = layout === 'horizontal' ? horizontalCuts : verticalCuts;
  const setCuts = layout === 'horizontal' ? setHorizontalCuts : setVerticalCuts;

  return (
    <div className="fixed inset-0 z-[130] grid place-items-center bg-slate-950/45 p-4" role="dialog" aria-modal="true" aria-label="图片切分与清晰化">
      <section className="flex max-h-[94vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl">
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <div><h2 className="text-base font-bold text-slate-800">图片切分与清晰化</h2><p className="mt-0.5 text-xs text-slate-500">{sourceName} · 结果另存为 PNG，不覆盖原图</p></div>
          <button type="button" onClick={onClose} className="rounded px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100">关闭</button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-5">
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
            <div className="min-w-0">
              <div className="flex min-h-[280px] items-center justify-center overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-3">
                {error && !image ? <p className="text-sm text-red-600">{error}</p> : <canvas ref={previewRef} className="max-h-[56vh] max-w-full" />}
              </div>
              <p className="mt-2 text-xs text-slate-500">红色虚线是切分位置；可在右侧微调。切分顺序按从左到右、从上到下对应 A/B/C/D。</p>
            </div>
            <div className="space-y-4 text-sm text-slate-700">
              <fieldset><legend className="mb-2 text-xs font-bold text-slate-500">处理方式</legend><div className="grid grid-cols-2 gap-2">
                <button type="button" onClick={() => setMode('split')} className={`rounded-md border px-3 py-2 font-semibold ${mode === 'split' ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-slate-200'}`}>切成 A-D</button>
                <button type="button" onClick={() => setMode('enhance')} className={`rounded-md border px-3 py-2 font-semibold ${mode === 'enhance' ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-slate-200'}`}>仅清晰化</button>
              </div></fieldset>
              {mode === 'split' && <fieldset><legend className="mb-2 text-xs font-bold text-slate-500">选项排列</legend><div className="grid grid-cols-3 gap-2">
                {([['horizontal', '横向 1×4'], ['grid', '网格 2×2'], ['vertical', '纵向 4×1']] as const).map(([value, label]) => <button key={value} type="button" onClick={() => setLayout(value)} className={`rounded-md border px-2 py-2 text-xs font-semibold ${layout === value ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-slate-200'}`}>{label}</button>)}
              </div></fieldset>}
              {mode === 'split' && layout !== 'grid' && <fieldset><legend className="mb-2 text-xs font-bold text-slate-500">三条分割线</legend><div className="space-y-2">{cutControls.map((cut, index) => <label key={index} className="grid grid-cols-[44px_1fr_38px] items-center gap-2 text-xs"><span>线 {index + 1}</span><input type="range" min="5" max="95" value={cut} onChange={(event) => setCuts((current) => updateThreeCuts(current, index, Number(event.target.value)))} /><span>{cut}%</span></label>)}</div></fieldset>}
              {mode === 'split' && layout === 'grid' && <fieldset><legend className="mb-2 text-xs font-bold text-slate-500">网格分割线</legend><div className="space-y-2"><label className="grid grid-cols-[44px_1fr_38px] items-center gap-2 text-xs"><span>左右</span><input type="range" min="20" max="80" value={gridCut[0]} onChange={(event) => setGridCut([Number(event.target.value), gridCut[1]])} /><span>{gridCut[0]}%</span></label><label className="grid grid-cols-[44px_1fr_38px] items-center gap-2 text-xs"><span>上下</span><input type="range" min="20" max="80" value={gridCut[1]} onChange={(event) => setGridCut([gridCut[0], Number(event.target.value)])} /><span>{gridCut[1]}%</span></label></div></fieldset>}
              <fieldset><legend className="mb-2 text-xs font-bold text-slate-500">清晰化</legend><div className="space-y-2">
                <label className="grid grid-cols-[64px_1fr_42px] items-center gap-2 text-xs"><span>放大</span><input type="range" min="1" max="3" step="1" value={scale} onChange={(event) => setScale(Number(event.target.value))} /><span>{scale}×</span></label>
                <label className="grid grid-cols-[64px_1fr_42px] items-center gap-2 text-xs"><span>亮度</span><input type="range" min="70" max="150" value={brightness} onChange={(event) => setBrightness(Number(event.target.value))} /><span>{brightness}%</span></label>
                <label className="grid grid-cols-[64px_1fr_42px] items-center gap-2 text-xs"><span>对比度</span><input type="range" min="80" max="220" value={contrast} onChange={(event) => setContrast(Number(event.target.value))} /><span>{contrast}%</span></label>
                <label className="grid grid-cols-[64px_1fr_42px] items-center gap-2 text-xs"><span>锐化</span><input type="range" min="0" max="1" step="0.05" value={sharpen} onChange={(event) => setSharpen(Number(event.target.value))} /><span>{sharpen.toFixed(2)}</span></label>
                <div className="flex flex-wrap gap-3 pt-1 text-xs"><label className="inline-flex items-center gap-1.5"><input type="checkbox" checked={grayscale} onChange={(event) => setGrayscale(event.target.checked)} />转黑白</label><label className="inline-flex items-center gap-1.5"><input type="checkbox" checked={backgroundClean} onChange={(event) => setBackgroundClean(event.target.checked)} />去灰底</label></div>
                {backgroundClean && <label className="grid grid-cols-[64px_1fr_42px] items-center gap-2 text-xs"><span>白底阈值</span><input type="range" min="180" max="252" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} /><span>{threshold}</span></label>}
              </div></fieldset>
              {error && image && <div className="rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}
            </div>
          </div>
        </div>
        <footer className="flex items-center justify-between border-t border-slate-200 px-5 py-3"><span className="text-xs text-slate-500">输出：{mode === 'split' ? '4 张 PNG，并写入 A/B/C/D' : '1 张增强 PNG'}</span><div className="flex gap-2"><button type="button" onClick={onClose} className="rounded-md border border-slate-300 px-4 py-2 text-sm">取消</button><button type="button" disabled={busy || !image} onClick={() => void apply()} className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? '正在生成…' : '生成并应用'}</button></div></footer>
      </section>
    </div>
  );
}
