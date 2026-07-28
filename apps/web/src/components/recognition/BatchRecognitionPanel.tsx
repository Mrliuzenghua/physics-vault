import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { Figure, QuestionType } from '../../types';
import LatexRenderer from '../render/LatexRenderer';

/* ── Types ── */

type PaperStatus = 'queued' | 'recognizing' | 'done' | 'failed';

interface PaperItem {
  id: string;
  name: string;
  size: number;       // bytes
  pageCount: number;
  status: PaperStatus;
  progress: number;   // 0-100
  questions: RecognizedQuestion[];
  errorMessage?: string;
}

interface RecognizedQuestion {
  qno: string;
  type: QuestionType;
  title: string;
  figures: Figure[];
}

/* ── Seed data (replaces real recognition pipeline for demo) ── */

const SEED_PAPERS: PaperItem[] = [
  {
    id: 'p1',
    name: '2025-2026学年深圳市第一高级中学高三物理10月月考.docx',
    size: 2_460_000,
    pageCount: 6,
    status: 'failed',
    progress: 0,
    errorMessage: 'AI 服务连接超时，请检查网络或稍后重试',
    questions: [],
  },
  {
    id: 'p2',
    name: '实验中学高一物理期中模拟卷.docx',
    size: 1_180_000,
    pageCount: 4,
    status: 'failed',
    progress: 0,
    errorMessage: 'AI 服务连接超时，请检查网络或稍后重试',
    questions: [],
  },
  {
    id: 'p3',
    name: '2026届高三一轮复习专题训练：牛顿运动定律.docx',
    size: 3_120_000,
    pageCount: 8,
    status: 'failed',
    progress: 0,
    errorMessage: 'AI 服务连接超时，请检查网络或稍后重试',
    questions: [],
  },
  {
    id: 'p4',
    name: '2024年高考物理全国甲卷真题（含答案）.docx',
    size: 4_580_000,
    pageCount: 12,
    status: 'done',
    progress: 100,
    questions: [
      { qno: '1', type: 'single_choice', title: '在光滑水平面上，质量为 $m$ 的物体受水平恒力 $F$ 作用，加速度大小为（　　）', figures: [] },
      { qno: '2', type: 'multi_choice', title: '关于牛顿第三定律，下列说法正确的是（　　）', figures: [] },
      { qno: '3', type: 'calculation', title: '一物体从静止开始做匀加速直线运动，加速度为 $a=2\\,\\text{m/s}^2$。求：\n(1) 第 3 s 末的速度；\n(2) 前 3 s 内的位移。', figures: [] },
    ],
  },
  {
    id: 'p5',
    name: '高二物理电场单元测试.docx',
    size: 1_960_000,
    pageCount: 6,
    status: 'queued',
    progress: 0,
    questions: [],
  },
  {
    id: 'p6',
    name: '高一力学综合周练.docx',
    size: 2_280_000,
    pageCount: 6,
    status: 'queued',
    progress: 0,
    questions: [],
  },
];

/* ── UI atoms ── */

const STATUS_LABEL: Record<PaperStatus, string> = {
  queued: '待识别',
  recognizing: '识别中',
  done: '已完成',
  failed: '失败',
};

function StatusBadge({ status, count }: { status: PaperStatus; count?: number }) {
  const styles: Record<PaperStatus, { bg: string; color: string; icon: ReactNode }> = {
    queued: {
      bg: 'var(--color-bg-code)',
      color: 'var(--color-text-muted)',
      icon: <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />,
    },
    recognizing: {
      bg: 'var(--color-accent-light)',
      color: 'var(--color-accent)',
      icon: <span className="animate-spin inline-block w-3 h-3 rounded-full border-2 border-current border-t-transparent" />,
    },
    done: {
      bg: 'var(--color-green-light)',
      color: 'var(--color-green)',
      icon: <span style={{ fontWeight: 700 }}>✓</span>,
    },
    failed: {
      bg: 'var(--color-red-light)',
      color: 'var(--color-red)',
      icon: <span style={{ fontWeight: 700 }}>!</span>,
    },
  };
  const s = styles[status];
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium"
      style={{ background: s.bg, color: s.color }}
    >
      {s.icon}
      {STATUS_LABEL[status]}
      {typeof count === 'number' && count > 0 && <span className="opacity-70">· {count}</span>}
    </span>
  );
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/* ── Main component ── */

interface Props {
  onClose?: () => void;
}

export default function BatchRecognitionPanel({ onClose }: Props) {
  const [papers, setPapers] = useState<PaperItem[]>(SEED_PAPERS);
  const [selectedId, setSelectedId] = useState<string | null>(papers[3]?.id ?? null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const selected = papers.find((p) => p.id === selectedId) ?? null;

  /* Stats summary */
  const stats = {
    total: papers.length,
    done: papers.filter((p) => p.status === 'done').length,
    failed: papers.filter((p) => p.status === 'failed').length,
    recognizing: papers.filter((p) => p.status === 'recognizing').length,
    queued: papers.filter((p) => p.status === 'queued').length,
  };
  const completion = stats.total > 0 ? Math.round(((stats.done + stats.failed) / stats.total) * 100) : 0;

  /* ── Actions ── */

  const updatePaper = useCallback((id: string, patch: Partial<PaperItem>) => {
    setPapers((prev) => prev.map((p) => (p.id === id ? { ...p, ...patch } : p)));
  }, []);

  const handleAddFiles = useCallback((files: FileList | File[]) => {
    const list = Array.from(files);
    const newPapers: PaperItem[] = list.map((f, i) => ({
      id: `new-${Date.now()}-${i}`,
      name: f.name,
      size: f.size,
      pageCount: Math.max(1, Math.round(f.size / 300_000)),
      status: 'queued',
      progress: 0,
      questions: [],
    }));
    setPapers((prev) => [...prev, ...newPapers]);
    if (!selectedId && newPapers[0]) setSelectedId(newPapers[0].id);
  }, [selectedId]);

  const handleStartAll = useCallback(() => {
    setPapers((prev) =>
      prev.map((p) =>
        p.status === 'queued' || p.status === 'failed'
          ? { ...p, status: 'recognizing', progress: 0, errorMessage: undefined }
          : p,
      ),
    );
  }, []);

  const handleRetryOne = useCallback((id: string) => {
    updatePaper(id, { status: 'recognizing', progress: 0, errorMessage: undefined });
  }, [updatePaper]);

  const handleRetryFailed = useCallback(() => {
    setPapers((prev) =>
      prev.map((p) =>
        p.status === 'failed' ? { ...p, status: 'recognizing', progress: 0, errorMessage: undefined } : p,
      ),
    );
  }, []);

  const hasRecognizingPaper = useMemo(
    () => papers.some((p) => p.status === 'recognizing'),
    [papers],
  );

  /* Simulated progress tick for any "recognizing" paper */
  useEffect(() => {
    if (!hasRecognizingPaper) return;
    const timer = setInterval(() => {
      setPapers((prev) =>
        prev.map((p) => {
          if (p.status !== 'recognizing') return p;
          const next = Math.min(100, p.progress + 5 + Math.random() * 8);
          if (next >= 100) {
            return { ...p, status: 'done', progress: 100, questions: SEED_PAPERS[3].questions };
          }
          return { ...p, progress: next };
        }),
      );
    }, 700);
    return () => clearInterval(timer);
  }, [hasRecognizingPaper]);

  /* ── Drag and drop ── */
  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const files = e.dataTransfer.files;
      if (files?.length) handleAddFiles(files);
    },
    [handleAddFiles],
  );

  return (
    <div
      className="flex flex-col rounded-2xl overflow-hidden"
      style={{
        background: 'var(--color-bg-card)',
        boxShadow: '0 20px 60px rgba(15, 30, 60, 0.18), 0 2px 8px rgba(15, 30, 60, 0.08)',
        border: '1px solid var(--color-border)',
      }}
    >
      {/* ── Header ── */}
      <div
        className="flex items-center gap-4 px-6 py-4 border-b"
        style={{ borderColor: 'var(--color-border)', background: 'linear-gradient(180deg, var(--color-bg-card) 0%, var(--color-bg) 100%)' }}
      >
        <div className="flex h-10 w-10 items-center justify-center rounded-xl" style={{ background: 'var(--color-accent-light)' }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="9" y1="13" x2="15" y2="13" /><line x1="9" y1="17" x2="13" y2="17" />
          </svg>
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-base font-bold" style={{ color: 'var(--color-text)' }}>
            批量智能识别
          </h2>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            上传多份试卷文档，自动识别题目、提取图片、生成可编辑草稿
          </p>
        </div>

        {/* Inline stats */}
        <div className="hidden md:flex items-center gap-3 mr-2">
          <StatChip color="green" label="已完成" value={stats.done} />
          <StatChip color="red" label="失败" value={stats.failed} />
          <StatChip color="accent" label="进行中" value={stats.recognizing} />
          <StatChip color="muted" label="待识别" value={stats.queued} />
        </div>

        {onClose && (
          <button
            onClick={onClose}
            className="cursor-pointer rounded-md border-none flex items-center justify-center"
            style={{ width: 32, height: 32, background: 'var(--color-bg-hover)', color: 'var(--color-text-muted)', fontSize: 20 }}
            title="关闭"
          >
            ×
          </button>
        )}
      </div>

      {/* ── Body: 3-column layout ── */}
      <div className="flex flex-1 min-h-0" style={{ minHeight: 480 }}>
        {/* Left: paper list (drop zone) */}
        <div
          className="flex flex-col w-72 flex-shrink-0 border-r"
          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-sidebar)' }}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--color-border)' }}>
            <span className="text-xs font-semibold uppercase" style={{ color: 'var(--color-text-muted)', letterSpacing: '0.06em' }}>
              文档列表 <span className="tabular-nums ml-1" style={{ color: 'var(--color-text-secondary)' }}>{stats.total}</span>
            </span>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="cursor-pointer rounded-md border-none px-2 py-0.5 text-xs"
              style={{ background: 'var(--color-accent-light)', color: 'var(--color-accent)' }}
            >
              + 添加
            </button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".docx,.doc,.pdf,.md"
              multiple
              className="hidden"
              onChange={(e) => e.target.files && handleAddFiles(e.target.files)}
            />
          </div>
          <div
            className="flex-1 overflow-y-auto p-2 space-y-1"
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            style={dragOver ? { background: 'var(--color-accent-light)' } : undefined}
          >
            {papers.map((p, i) => {
              const active = p.id === selectedId;
              return (
                <button
                  key={p.id}
                  onClick={() => setSelectedId(p.id)}
                  className="group relative w-full cursor-pointer rounded-lg border px-2.5 py-2 text-left transition-all"
                  style={{
                    borderColor: active ? 'var(--color-accent)' : 'var(--color-border)',
                    background: active ? 'var(--color-bg-card)' : 'var(--color-bg-card)',
                    boxShadow: active ? '0 0 0 1px var(--color-accent), 0 1px 3px rgba(47,111,221,0.12)' : 'none',
                  }}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md text-[11px] font-bold tabular-nums"
                      style={{
                        background: 'var(--color-bg-code)',
                        color: 'var(--color-text-secondary)',
                      }}
                    >
                      {i + 1}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="truncate text-[13px] font-medium" style={{ color: 'var(--color-text)' }} title={p.name}>
                        {p.name}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5 text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
                        <span>{fmtBytes(p.size)}</span>
                        <span>·</span>
                        <span>{p.pageCount} 页</span>
                      </div>
                    </div>
                  </div>
                  <div className="mt-1.5 flex items-center justify-between">
                    <StatusBadge status={p.status} count={p.questions.length} />
                    {p.status === 'recognizing' && (
                      <div className="h-1 flex-1 ml-2 rounded-full overflow-hidden" style={{ background: 'var(--color-bg-code)' }}>
                        <div
                          className="h-full transition-all duration-300"
                          style={{ width: `${p.progress}%`, background: 'var(--color-accent)' }}
                        />
                      </div>
                    )}
                  </div>
                </button>
              );
            })}
            {papers.length === 0 && (
              <div
                className="flex flex-col items-center justify-center h-full px-6 py-10 text-center text-sm"
                style={{ color: 'var(--color-text-muted)' }}
              >
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.4 }}>
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                <p className="mt-2">拖拽 Word/ PDF 试卷到此处，或点击"+ 添加"</p>
              </div>
            )}
          </div>
        </div>

        {/* Center: paper detail / preview */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {selected ? (
            <>
              {/* Detail header */}
              <div className="flex items-start gap-3 px-6 py-4 border-b" style={{ borderColor: 'var(--color-border)' }}>
                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg" style={{ background: 'var(--color-bg-code)' }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-secondary)" strokeWidth="1.8" strokeLinecap="round">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" />
                  </svg>
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold truncate" style={{ color: 'var(--color-text)' }} title={selected.name}>
                    {selected.name}
                  </h3>
                  <div className="flex items-center gap-3 mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                    <StatusBadge status={selected.status} />
                    <span>{fmtBytes(selected.size)}</span>
                    <span>· {selected.pageCount} 页</span>
                    {selected.questions.length > 0 && <span>· 识别出 {selected.questions.length} 题</span>}
                  </div>
                </div>
                {selected.status === 'failed' && (
                  <button
                    onClick={() => handleRetryOne(selected.id)}
                    className="cursor-pointer rounded-md border-none px-3 py-1.5 text-xs font-medium transition-all"
                    style={{ background: 'var(--color-accent)', color: '#fff' }}
                  >
                    重新识别
                  </button>
                )}
                {selected.status === 'done' && (
                  <button
                    className="cursor-pointer rounded-md border px-3 py-1.5 text-xs font-medium"
                    style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)', color: 'var(--color-text-secondary)' }}
                  >
                    查看结果
                  </button>
                )}
              </div>

              {/* Progress bar (only when recognizing) */}
              {selected.status === 'recognizing' && (
                <div className="px-6 py-3 border-b" style={{ borderColor: 'var(--color-border)' }}>
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span style={{ color: 'var(--color-text-muted)' }}>
                      正在识别第 <strong style={{ color: 'var(--color-accent)' }}>{Math.min(selected.pageCount, Math.floor((selected.progress / 100) * selected.pageCount) + 1)}</strong> / {selected.pageCount} 页
                    </span>
                    <span className="tabular-nums" style={{ color: 'var(--color-accent)' }}>{Math.round(selected.progress)}%</span>
                  </div>
                  <div className="h-1.5 w-full rounded-full overflow-hidden" style={{ background: 'var(--color-bg-code)' }}>
                    <div
                      className="h-full transition-all duration-300 rounded-full"
                      style={{
                        width: `${selected.progress}%`,
                        background: 'linear-gradient(90deg, var(--color-accent) 0%, #5b9def 100%)',
                      }}
                    />
                  </div>
                </div>
              )}

              {/* Error message */}
              {selected.status === 'failed' && selected.errorMessage && (
                <div className="mx-6 mt-4 flex items-start gap-3 rounded-lg px-3.5 py-3" style={{ background: 'var(--color-red-light)', border: '1px solid rgba(220,38,38,0.2)' }}>
                  <span
                    className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-xs font-bold"
                    style={{ background: 'var(--color-red)', color: '#fff' }}
                  >
                    !
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium" style={{ color: 'var(--color-red)' }}>识别失败</div>
                    <div className="text-xs mt-0.5" style={{ color: '#7f1d1d' }}>{selected.errorMessage}</div>
                  </div>
                </div>
              )}

              {/* Question preview */}
              <div className="flex-1 overflow-y-auto px-6 py-4">
                {selected.questions.length === 0 ? (
                  <div
                    className="flex flex-col items-center justify-center h-full text-center"
                    style={{ color: 'var(--color-text-muted)' }}
                  >
                    {selected.status === 'done' ? (
                      <p className="text-sm">此文档暂无识别结果</p>
                    ) : selected.status === 'failed' ? (
                      <>
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" style={{ opacity: 0.4 }}>
                          <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                        </svg>
                        <p className="mt-3 text-sm">点击"重新识别"恢复题目预览</p>
                      </>
                    ) : selected.status === 'recognizing' ? (
                      <p className="text-sm">识别进行中，题目会逐步显示在此处</p>
                    ) : (
                      <p className="text-sm">等待识别开始</p>
                    )}
                  </div>
                ) : (
                  <div className="space-y-3">
                    {selected.questions.map((q) => (
                      <div
                        key={q.qno}
                        className="rounded-lg border p-3"
                        style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}
                      >
                        <div className="flex items-center gap-2 mb-1.5">
                          <span
                            className="rounded-full px-2 py-0.5 text-[11px] font-semibold"
                            style={{ background: 'var(--color-accent-light)', color: 'var(--color-accent)' }}
                          >
                            {q.qno}
                          </span>
                          <span className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
                            {q.type === 'single_choice' ? '单选' :
                             q.type === 'multi_choice' ? '多选' :
                             q.type === 'fill' ? '填空' :
                             q.type === 'experiment' ? '实验' : '计算'}
                          </span>
                        </div>
                        <div className="text-sm leading-relaxed" style={{ color: 'var(--color-text)' }}>
                          <LatexRenderer text={q.title} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-sm" style={{ color: 'var(--color-text-muted)' }}>
              从左侧选择一份文档
            </div>
          )}
        </div>

        {/* Right: options / hints */}
        <div
          className="w-60 flex-shrink-0 border-l overflow-y-auto p-4 space-y-4"
          style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-sidebar)' }}
        >
          <SectionTitle>识别选项</SectionTitle>
          <div className="space-y-2">
            <ToggleRow label="提取图片" defaultChecked />
            <ToggleRow label="公式转 LaTeX" defaultChecked />
            <ToggleRow label="切分为单题" defaultChecked />
            <ToggleRow label="识别考点标签" defaultChecked />
          </div>

          <SectionTitle>提示</SectionTitle>
          <div className="rounded-lg p-3 text-xs leading-relaxed space-y-1.5" style={{ background: 'var(--color-bg-code)', color: 'var(--color-text-secondary)' }}>
            <p>· 支持 Word / PDF / Markdown</p>
            <p>· 单批最多 20 份文档</p>
            <p>· 单份最大 50 MB / 200 页</p>
            <p>· 失败可单独重试，不影响其他文档</p>
          </div>
        </div>
      </div>

      {/* ── Footer ── */}
      <div
        className="flex items-center justify-between px-6 py-3 border-t"
        style={{
          borderColor: 'var(--color-border)',
          background: 'var(--color-bg-sidebar)',
        }}
      >
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          总进度
          <div className="h-1.5 w-40 rounded-full overflow-hidden" style={{ background: 'var(--color-bg-code)' }}>
            <div
              className="h-full transition-all duration-300"
              style={{
                width: `${completion}%`,
                background: 'linear-gradient(90deg, var(--color-green) 0%, var(--color-accent) 100%)',
              }}
            />
          </div>
          <span className="tabular-nums" style={{ color: 'var(--color-text-secondary)' }}>{completion}%</span>
          <span className="ml-2">
            已完成 <strong className="tabular-nums" style={{ color: 'var(--color-green)' }}>{stats.done}</strong>
            · 失败 <strong className="tabular-nums" style={{ color: 'var(--color-red)' }}>{stats.failed}</strong>
            · 进行中 <strong className="tabular-nums" style={{ color: 'var(--color-accent)' }}>{stats.recognizing}</strong>
          </span>
        </div>

        <div className="flex items-center gap-2">
          {stats.failed > 0 && (
            <button
              onClick={handleRetryFailed}
              className="cursor-pointer rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors"
              style={{ borderColor: 'var(--color-red)', color: 'var(--color-red)', background: 'var(--color-bg-card)' }}
            >
              重试失败 ({stats.failed})
            </button>
          )}
          <button
            onClick={handleStartAll}
            disabled={stats.queued + stats.failed === 0}
            className="cursor-pointer rounded-lg border-none px-5 py-1.5 text-xs font-semibold text-white transition-all disabled:cursor-not-allowed disabled:opacity-40"
            style={{
              background: 'var(--color-accent)',
              boxShadow: '0 1px 2px rgba(20,50,110,0.22), inset 0 1px 0 rgba(255,255,255,0.12)',
            }}
          >
            {stats.recognizing > 0 ? '识别中…' : `开始批量识别 (${stats.queued + stats.failed})`}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Helper bits ── */

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[11px] font-semibold uppercase" style={{ color: 'var(--color-text-muted)', letterSpacing: '0.08em' }}>
      {children}
    </div>
  );
}

function StatChip({ color, label, value }: { color: 'green' | 'red' | 'accent' | 'muted'; label: string; value: number }) {
  const colors: Record<string, { bg: string; fg: string }> = {
    green: { bg: 'var(--color-green-light)', fg: 'var(--color-green)' },
    red: { bg: 'var(--color-red-light)', fg: 'var(--color-red)' },
    accent: { bg: 'var(--color-accent-light)', fg: 'var(--color-accent)' },
    muted: { bg: 'var(--color-bg-code)', fg: 'var(--color-text-muted)' },
  };
  const c = colors[color];
  return (
    <div className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs" style={{ background: c.bg, color: c.fg }}>
      <span style={{ fontWeight: 600 }} className="tabular-nums">{value}</span>
      <span className="opacity-75">{label}</span>
    </div>
  );
}

function ToggleRow({ label, defaultChecked }: { label: string; defaultChecked?: boolean }) {
  const [on, setOn] = useState(!!defaultChecked);
  return (
    <label className="flex items-center justify-between cursor-pointer select-none">
      <span className="text-[13px]" style={{ color: 'var(--color-text)' }}>{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        onClick={() => setOn(!on)}
        className="cursor-pointer border-none"
        style={{
          width: 30, height: 18, borderRadius: 999,
          background: on ? 'var(--color-accent)' : 'var(--color-border-strong)',
          position: 'relative', transition: 'background .2s',
          flexShrink: 0, padding: 0,
        }}
      >
        <span
          style={{
            position: 'absolute', top: 2, left: on ? 14 : 2,
            width: 14, height: 14, borderRadius: '50%',
            background: '#fff', transition: 'left .2s',
            boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
          }}
        />
      </button>
    </label>
  );
}
