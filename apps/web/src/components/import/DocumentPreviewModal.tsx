import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy } from 'pdfjs-dist';

interface Props {
  file: File;
  onClose: () => void;
  onConfirm?: () => void;
  confirmLabel?: string;
}

function extension(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot >= 0 ? name.slice(dot).toLowerCase() : '';
}

export default function DocumentPreviewModal({ file, onClose, onConfirm, confirmLabel = '确认使用' }: Props) {
  const ext = extension(file.name);
  const isPdf = ext === '.pdf';
  const isWord = ext === '.docx';
  const isImage = file.type.startsWith('image/') || ['.png', '.jpg', '.jpeg', '.webp'].includes(ext);

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/65 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={`预览 ${file.name}`}>
      <button type="button" className="absolute inset-0 cursor-default" aria-label="关闭预览" onClick={onClose} />
      <div className="relative z-10 flex max-h-[min(900px,calc(100vh-32px))] w-[min(1200px,calc(100vw-32px))] flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] shadow-2xl">
        <header className="flex shrink-0 items-center justify-between border-b border-[var(--color-border)] bg-white px-4 py-3">
          <div className="min-w-0 truncate text-sm font-bold text-[var(--color-text-main)]">{file.name}</div>
          <div className="flex items-center gap-2">
            <button type="button" onClick={onClose} className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]">关闭</button>
            {onConfirm && <button type="button" onClick={onConfirm} className="rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[var(--color-accent-dark)]">{confirmLabel}</button>}
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-auto bg-[#eef3f8] p-5">
          {isPdf && <PdfPreview file={file} />}
          {isWord && <WordPreview file={file} />}
          {isImage && <ImagePreview file={file} />}
          {!isPdf && !isWord && !isImage && <div className="py-20 text-center text-sm text-[var(--color-text-muted)]">当前文件类型暂不支持在线预览。</div>}
        </div>
      </div>
    </div>
  );
}

function ImagePreview({ file }: { file: File }) {
  const [src, setSrc] = useState('');
  const imageRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    const next = URL.createObjectURL(file);
    setSrc(next);
    return () => URL.revokeObjectURL(next);
  }, [file]);

  useEffect(() => {
    if (!imageRef.current || !src) return undefined;
    let viewer: { destroy: () => void } | null = null;
    let active = true;
    void import('viewerjs').then(({ default: Viewer }) => {
      if (!active || !imageRef.current) return;
      viewer = new Viewer(imageRef.current, { navbar: false, toolbar: true, title: false });
    });
    return () => {
      active = false;
      viewer?.destroy();
    };
  }, [src]);

  return <div className="flex min-h-[420px] items-center justify-center"><img ref={imageRef} src={src} alt={file.name} className="max-h-[72vh] max-w-full rounded-lg bg-white object-contain shadow-lg" /></div>;
}

function WordPreview({ file }: { file: File }) {
  const previewRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [structuredHtml, setStructuredHtml] = useState<string | null>(null);
  const [view, setView] = useState<'layout' | 'structured'>('layout');

  useEffect(() => {
    let active = true;
    void file.arrayBuffer().then(async (buffer) => {
      if (!active || !previewRef.current) return;
      previewRef.current.replaceChildren();
      const [{ renderAsync }, mammoth] = await Promise.all([
        import('docx-preview'),
        import('mammoth'),
      ]);
      const [rendered] = await Promise.all([
        renderAsync(buffer, previewRef.current, undefined, { inWrapper: true, ignoreWidth: false, ignoreHeight: false }),
        mammoth.convertToHtml({ arrayBuffer: buffer }).then((result) => {
          if (active) setStructuredHtml(result.value);
        }),
      ]);
      return rendered;
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : 'Word 预览失败');
    });
    return () => {
      active = false;
    };
  }, [file]);

  if (error) return <div className="py-20 text-center text-sm text-[var(--color-danger)]">{error}</div>;
  return (
    <div className="mx-auto max-w-[980px]">
      <div className="mb-3 flex items-center gap-2">
        <button type="button" onClick={() => setView('layout')} className={`rounded-md px-3 py-1.5 text-xs font-semibold ${view === 'layout' ? 'bg-[var(--color-accent)] text-white' : 'bg-white text-[var(--color-text-secondary)]'}`}>
          版式预览
        </button>
        <button type="button" onClick={() => setView('structured')} className={`rounded-md px-3 py-1.5 text-xs font-semibold ${view === 'structured' ? 'bg-[var(--color-accent)] text-white' : 'bg-white text-[var(--color-text-secondary)]'}`}>
          结构化文本
        </button>
      </div>
      {view === 'layout' ? (
        <div ref={previewRef} className="rounded bg-white p-8 shadow-lg" />
      ) : structuredHtml ? (
        <article className="prose mx-auto max-w-none rounded bg-white p-8 text-[var(--color-text)] shadow-lg" dangerouslySetInnerHTML={{ __html: structuredHtml }} />
      ) : (
        <div className="rounded bg-white py-20 text-center text-sm text-[var(--color-text-muted)]">正在提取结构化文本...</div>
      )}
    </div>
  );
}

function PdfPreview({ file }: { file: File }) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [page, setPage] = useState(1);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    let active = true;
    void Promise.all([
      import('pdfjs-dist'),
      import('pdfjs-dist/build/pdf.worker.mjs?url'),
      file.arrayBuffer(),
    ]).then(([pdfjs, worker, buffer]) => {
      pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
      return pdfjs.getDocument({ data: buffer }).promise;
    }).then((document) => {
      if (active) setPdf(document);
      else setPdf(null);
    }).catch(() => setPdf(null));
    return () => { active = false; };
  }, [file]);

  useEffect(() => {
    if (!pdf || !canvasRef.current) return;
    let active = true;
    void pdf.getPage(page).then((currentPage) => {
      const viewport = currentPage.getViewport({ scale: 1.35 });
      const canvas = canvasRef.current;
      if (!canvas || !active) return;
      const context = canvas.getContext('2d');
      if (!context) return;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      return currentPage.render({ canvas, canvasContext: context, viewport }).promise;
    });
    return () => { active = false; };
  }, [page, pdf]);

  if (!pdf) return <div className="py-20 text-center text-sm text-[var(--color-text-muted)]">正在加载 PDF…</div>;
  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-white px-3 py-1.5 text-xs shadow-sm">
        <button type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)} className="disabled:opacity-35">上一页</button>
        <span>{page} / {pdf.numPages}</span>
        <button type="button" disabled={page >= pdf.numPages} onClick={() => setPage((value) => value + 1)} className="disabled:opacity-35">下一页</button>
      </div>
      <canvas ref={canvasRef} className="max-w-full bg-white shadow-lg" />
    </div>
  );
}
