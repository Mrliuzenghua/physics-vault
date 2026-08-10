import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import SlideViewer from '../components/slides/SlideViewer';
import TeachingSlidePage from '../components/teaching/TeachingSlidePage';
import { EmptyState } from '../components/ui/EmptyState';
import { loadCurrentLessonPackage } from '../services/lessonPackage';
import { getOrCreateTeachingProject, hydrateTeachingProject } from '../services/teachingProject';
import { generateClassroomReflectionAdvice, hydrateClassroomReflections, loadLatestClassroomReflection, saveClassroomReflection, syncClassroomReflection, type ClassroomReflection, type ClassroomReflectionAdvice } from '../services/classroomReflection';
import type { LessonPackage, Question, SlidesDisplayMode } from '../types';
import type { SlideDeck, SlidePage } from '../types/slides';

interface MixedPage {
  kind: 'knowledge' | 'question';
  slide: SlidePage;
  question?: Question;
}

interface ClassroomSession {
  currentIndex: number;
  displayMode: SlidesDisplayMode;
  revealStep: number;
  zoomLevel: number;
  timerSeconds: number;
  timerRunning: boolean;
  teacherNotes: string;
  annotations: Record<string, string>;
  updatedAt: string;
}

function classroomSessionKey(projectId: string) {
  return `physics-vault.classroom-session.${projectId}`;
}

function formatSessionTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0');
  const remainder = (seconds % 60).toString().padStart(2, '0');
  return `${minutes}:${remainder}`;
}

function loadClassroomSession(projectId: string | null): ClassroomSession | null {
  if (!projectId || typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(classroomSessionKey(projectId));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<ClassroomSession>;
    if (!value || typeof value !== 'object') return null;
    return {
      currentIndex: Number.isFinite(value.currentIndex) ? Math.max(0, Number(value.currentIndex)) : 0,
      displayMode: value.displayMode === 'stem_answer' || value.displayMode === 'full' ? value.displayMode : 'stem_only',
      revealStep: Number.isFinite(value.revealStep) ? Math.max(0, Number(value.revealStep)) : 0,
      zoomLevel: Number.isFinite(value.zoomLevel) ? Math.min(2, Math.max(0.6, Number(value.zoomLevel))) : 1,
      timerSeconds: Number.isFinite(value.timerSeconds) ? Math.max(0, Number(value.timerSeconds)) : 0,
      timerRunning: value.timerRunning === true,
      teacherNotes: typeof value.teacherNotes === 'string' ? value.teacherNotes : '',
      annotations: value.annotations && typeof value.annotations === 'object' ? value.annotations as Record<string, string> : {},
      updatedAt: typeof value.updatedAt === 'string' ? value.updatedAt : '',
    };
  } catch {
    return null;
  }
}

function buildMixedPages(lessonPackage: LessonPackage, deck: SlideDeck): MixedPage[] {
  const questionMap = new Map(lessonPackage.questions.map((question) => [question.question_id, question]));

  return deck.pages.map((slide) => {
    const questionId = slide.id.startsWith('q-') ? slide.id.slice(2) : null;
    const question = questionId ? questionMap.get(questionId) : undefined;

    return question
      ? { kind: 'question', slide, question }
      : { kind: 'knowledge', slide };
  });
}

export default function ClassroomPage() {
  const lessonPackage = useMemo(() => loadCurrentLessonPackage(), []);
  const [project, setProject] = useState(() => (lessonPackage ? getOrCreateTeachingProject(lessonPackage) : null));
  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    void hydrateTeachingProject(project.id).then((remoteProject) => {
      if (!cancelled && remoteProject && remoteProject.updatedAt !== project.updatedAt) setProject(remoteProject);
    });
    return () => { cancelled = true; };
  }, [project?.id]);
  const publishedDeck = project?.slides.publishedSnapshot?.deck || null;
  const classroomPackage = project?.slides.publishedSnapshot?.lessonPackage || lessonPackage;
  const pages = useMemo(
    () => (classroomPackage && publishedDeck ? buildMixedPages(classroomPackage, publishedDeck) : []),
    [classroomPackage, publishedDeck],
  );
  const stageRef = useRef<HTMLDivElement>(null);
  const savedSession = useMemo(() => loadClassroomSession(project?.id || null), [project?.id]);
  const [currentIndex, setCurrentIndex] = useState(savedSession?.currentIndex || 0);
  const [displayMode, setDisplayMode] = useState<SlidesDisplayMode>(savedSession?.displayMode || 'stem_only');
  const [revealStep, setRevealStep] = useState(savedSession?.revealStep || 0);
  const [zoomLevel, setZoomLevel] = useState(savedSession?.zoomLevel || 1);
  const [timerSeconds, setTimerSeconds] = useState(savedSession?.timerSeconds || 0);
  const [timerRunning, setTimerRunning] = useState(savedSession?.timerRunning || false);
  const [teacherNotes, setTeacherNotes] = useState(savedSession?.teacherNotes || '');
  const [annotations, setAnnotations] = useState<Record<string, string>>(savedSession?.annotations || {});
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [reflectionOpen, setReflectionOpen] = useState(false);
  const [reflection, setReflection] = useState<ClassroomReflection | null>(() => project ? loadLatestClassroomReflection(project.id) : null);
  const [reflectionAdvice, setReflectionAdvice] = useState<ClassroomReflectionAdvice | null>(null);
  const [reflectionAdviceLoading, setReflectionAdviceLoading] = useState(false);

  useEffect(() => {
    if (!timerRunning) return;
    const timer = window.setInterval(() => setTimerSeconds((seconds) => seconds + 1), 1000);
    return () => window.clearInterval(timer);
  }, [timerRunning]);

  useEffect(() => {
    if (!project) return;
    void hydrateClassroomReflections(project.id).then((items) => {
      const latest = items.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0];
      if (latest) setReflection((current) => !current || latest.updatedAt > current.updatedAt ? latest : current);
    });
  }, [project]);

  const currentPage = pages[currentIndex];
  const questionCount = pages.filter((page) => page.kind === 'question').length;
  const maxRevealStep = currentPage?.kind === 'question'
    ? (displayMode === 'full' ? 2 : displayMode === 'stem_answer' ? 1 : 0)
    : 0;

  const goPrev = useCallback(() => {
    if (revealStep > 0) {
      setRevealStep((step) => step - 1);
      return;
    }
    setCurrentIndex((prev) => Math.max(0, prev - 1));
    setRevealStep(maxRevealStep);
  }, [maxRevealStep, revealStep]);
  const goNext = useCallback(
    () => {
      if (revealStep < maxRevealStep) {
        setRevealStep((step) => step + 1);
        return;
      }
      setCurrentIndex((prev) => Math.min(pages.length - 1, prev + 1));
      setRevealStep(0);
    },
    [maxRevealStep, pages.length, revealStep],
  );

  const setTeachingMode = useCallback((mode: SlidesDisplayMode) => {
    setDisplayMode(mode);
    setRevealStep(0);
  }, []);

  const toggleFullscreen = useCallback(() => {
    const node = stageRef.current;
    if (!node) return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => undefined);
      return;
    }
    node.requestFullscreen().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!project || typeof window === 'undefined') return;
    window.localStorage.setItem(classroomSessionKey(project.id), JSON.stringify({
      currentIndex,
      displayMode,
      revealStep,
      zoomLevel,
      timerSeconds,
      timerRunning,
      teacherNotes,
      annotations,
      updatedAt: new Date().toISOString(),
    } satisfies ClassroomSession));
  }, [annotations, currentIndex, displayMode, project, revealStep, teacherNotes, timerRunning, timerSeconds, zoomLevel]);

  const openReflection = useCallback(() => {
    if (!project) return;
    setReflection((current) => current || loadLatestClassroomReflection(project.id) || {
      id: `reflection-${project.id}-${Date.now()}`,
      projectId: project.id,
      projectTitle: lessonPackage?.title || project.title,
      rating: 4,
      completed: currentIndex >= pages.length - 1,
      highlights: '',
      followUp: '',
      attendedPages: Math.min(pages.length, currentIndex + 1),
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    setReflectionOpen(true);
  }, [currentIndex, lessonPackage, pages.length, project]);

  const saveReflection = useCallback(() => {
    if (!reflection) return;
    const next = { ...reflection, updatedAt: new Date().toISOString() };
    saveClassroomReflection(next);
    void syncClassroomReflection({ ...next, remoteSyncState: 'pending' });
    setReflection(next);
    setReflectionOpen(false);
  }, [reflection]);

  const generateAdvice = useCallback(async () => {
    if (!reflection || !lessonPackage) return;
    setReflectionAdviceLoading(true);
    try {
      setReflectionAdvice(await generateClassroomReflectionAdvice(reflection, lessonPackage.title));
    } finally {
      setReflectionAdviceLoading(false);
    }
  }, [lessonPackage, reflection]);

  useEffect(() => {
    if (pages.length === 0) return;
    setCurrentIndex((index) => Math.min(index, pages.length - 1));
  }, [pages.length]);

  useEffect(() => {
    const onFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === stageRef.current);
    };
    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        goPrev();
      }
      if (event.key === 'ArrowRight' || event.key === ' ') {
        event.preventDefault();
        goNext();
      }
      if (event.key === '1') setDisplayMode('stem_only');
      if (event.key === '2') setDisplayMode('stem_answer');
      if (event.key === '3') setDisplayMode('full');
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [goNext, goPrev]);

  if (!lessonPackage || !project?.slides.publishedSnapshot || pages.length === 0) {
    return (
      <EmptyState
        icon="🎓"
        title="课堂授课内容还没有准备好"
        description="请先在组卷工作台里完成题目与知识点编排，再进入授课模式。"
      />
    );
  }

  return (
    <div className="flex h-full bg-[#eaf3ff] text-[#173a6a]">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-white/10 bg-[#111c35] px-5 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-lg font-semibold">{classroomPackage?.title || lessonPackage.title}</div>
              <div className="mt-1 text-sm text-white/60">
                授课模式直接读取当前教学包，讲义预览、幻灯预览、课堂授课保持同一顺序。
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <ControlChip label="仅题干" active={displayMode === 'stem_only'} onClick={() => setTeachingMode('stem_only')} />
              <ControlChip label="题干 + 答案" active={displayMode === 'stem_answer'} onClick={() => setTeachingMode('stem_answer')} />
              <ControlChip label="完整解析" active={displayMode === 'full'} onClick={() => setTeachingMode('full')} />
              <ControlChip label={isFullscreen ? '退出全屏' : '全屏'} active={isFullscreen} onClick={toggleFullscreen} />
              <ControlChip label={`${timerRunning ? '暂停' : '开始'} ${formatSessionTime(timerSeconds)}`} active={timerRunning} onClick={() => setTimerRunning((running) => !running)} />
              <ControlChip label="课后复盘" active={reflectionOpen} onClick={openReflection} />
            </div>
          </div>
        </div>

        <div
          ref={stageRef}
          className={`min-h-0 flex-1 bg-[#12213f] ${isFullscreen ? 'flex items-center justify-center overflow-hidden p-0' : 'overflow-auto px-6 py-6'}`}
        >
          {currentPage.kind === 'knowledge' ? (
            <TeachingSlidePage data={currentPage.slide} fitToViewport={isFullscreen} />
          ) : (
            <SlideViewer
              question={currentPage.question!}
              index={pages.slice(0, currentIndex + 1).filter((page) => page.kind === 'question').length - 1}
              total={questionCount}
              displayMode={displayMode}
              zoomLevel={zoomLevel}
              fitToViewport={isFullscreen}
              revealStep={revealStep}
            />
          )}
        </div>

        <div className="flex items-center justify-between border-t border-white/10 bg-[#111c35] px-5 py-3">
          <div className="text-sm text-white/70">
            第 {currentIndex + 1} / {pages.length} 页
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setZoomLevel((prev) => Math.max(0.6, +(prev - 0.1).toFixed(1)))}
              className="rounded-md border border-white/10 px-3 py-2 text-sm text-white/80 transition hover:bg-white/5"
            >
              缩小
            </button>
            <button
              type="button"
              onClick={() => setZoomLevel(1)}
              className="rounded-md border border-white/10 px-3 py-2 text-sm text-white/80 transition hover:bg-white/5"
            >
              100%
            </button>
            <button
              type="button"
              onClick={() => setZoomLevel((prev) => Math.min(2, +(prev + 0.1).toFixed(1)))}
              className="rounded-md border border-white/10 px-3 py-2 text-sm text-white/80 transition hover:bg-white/5"
            >
              放大
            </button>
            <button
              type="button"
              onClick={goPrev}
              disabled={currentIndex === 0 && revealStep === 0}
              className="rounded-md border border-white/10 px-4 py-2 text-sm text-white transition hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
            >
              上一页
            </button>
            <button
              type="button"
              onClick={goNext}
              disabled={currentIndex === pages.length - 1 && revealStep >= maxRevealStep}
              className="rounded-md bg-[#2563eb] px-4 py-2 text-sm text-white transition hover:bg-[#1d4ed8] disabled:cursor-not-allowed disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </div>
      </div>

      <aside className="w-[300px] border-l border-white/10 bg-[#0d162b]">
        <div className="border-b border-white/10 px-4 py-4">
          <div className="text-sm font-semibold text-white">课堂目录</div>
          <div className="mt-1 text-xs text-white/55">
            知识点页和题目页统一编排，课堂中可直接逐页推进。
          </div>
        </div>
        <div className="overflow-auto px-3 py-3">
          <div className="space-y-2">
            {pages.map((page, index) => {
              const active = index === currentIndex;
              return (
                <button
                  key={page.slide.id}
                  type="button"
                  onClick={() => setCurrentIndex(index)}
                  className="w-full rounded-md border px-3 py-2.5 text-left transition"
                  style={{
                    borderColor: active ? '#60a5fa' : 'rgba(255,255,255,0.08)',
                    background: active ? 'rgba(37,99,235,0.18)' : 'rgba(255,255,255,0.02)',
                  }}
                >
                  <div className="text-[11px] text-white/50">
                    {page.kind === 'knowledge' ? `知识点 ${index + 1}` : `题目 ${index + 1}`}
                  </div>
                  <div className="mt-1 line-clamp-2 text-sm font-medium text-white">
                    {page.kind === 'knowledge'
                      ? page.slide.title
                      : page.question?.title || `题目 ${index + 1}`}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
        <div className="border-t border-white/10 px-3 py-3">
          <div className="mb-2 flex items-center justify-between text-xs font-semibold text-white">
            <span>教师备注</span>
            <button type="button" onClick={() => setTimerSeconds(0)} className="text-[10px] text-white/45 hover:text-white/80">计时归零</button>
          </div>
          <textarea value={teacherNotes} onChange={(event) => setTeacherNotes(event.target.value)} placeholder="记录本节课的提醒、节奏和课后任务" className="min-h-20 w-full rounded-md border border-white/10 bg-white/5 px-2.5 py-2 text-xs text-white outline-none placeholder:text-white/35 focus:border-blue-400" />
          <div className="mt-3 text-xs font-semibold text-white">当前页批注</div>
          <textarea
            value={currentPage ? annotations[currentPage.slide.id] || '' : ''}
            onChange={(event) => currentPage && setAnnotations((current) => ({ ...current, [currentPage.slide.id]: event.target.value }))}
            placeholder="为当前页面写下讲解提示"
            className="mt-2 min-h-16 w-full rounded-md border border-white/10 bg-white/5 px-2.5 py-2 text-xs text-white outline-none placeholder:text-white/35 focus:border-blue-400"
          />
        </div>
      </aside>

      {reflectionOpen && reflection && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-4" role="dialog" aria-modal="true" aria-label="课后复盘">
          <section className="w-full max-w-lg rounded-2xl border border-[#d4e1f0] bg-white p-5 text-[#173a6a] shadow-2xl">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold">课后复盘</h2>
                <p className="mt-1 text-xs text-slate-500">记录本次授课，内容会保存到当前教学项目。</p>
              </div>
              <button type="button" onClick={() => setReflectionOpen(false)} className="text-xs text-slate-500">关闭</button>
            </div>
            <div className="mt-4 space-y-4">
              <div>
                <div className="mb-2 text-xs font-semibold text-slate-600">本次授课评分</div>
                <div className="flex gap-2">
                  {[1, 2, 3, 4, 5].map((value) => (
                    <button key={value} type="button" onClick={() => setReflection((current) => current ? { ...current, rating: value as ClassroomReflection['rating'] } : current)} className={`rounded-lg px-3 py-2 text-sm ${reflection.rating === value ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'}`}>{value} 分</button>
                  ))}
                </div>
              </div>
              <label className="flex items-center gap-2 text-xs text-slate-600">
                <input type="checkbox" checked={reflection.completed} onChange={(event) => setReflection((current) => current ? { ...current, completed: event.target.checked } : current)} />
                本次授课已完成计划内容
              </label>
              <label className="block text-xs font-semibold text-slate-600">
                课堂亮点
                <textarea value={reflection.highlights} onChange={(event) => setReflection((current) => current ? { ...current, highlights: event.target.value } : current)} placeholder="哪些讲解、例题或互动效果最好？" className="mt-1 min-h-20 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-normal outline-none focus:border-blue-500" />
              </label>
              <label className="block text-xs font-semibold text-slate-600">
                下次改进
                <textarea value={reflection.followUp} onChange={(event) => setReflection((current) => current ? { ...current, followUp: event.target.value } : current)} placeholder="下次需要补讲、调整或跟进什么？" className="mt-1 min-h-20 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm font-normal outline-none focus:border-blue-500" />
              </label>
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs text-slate-400">已授课 {reflection.attendedPages} / {pages.length} 页</span>
                <div className="flex gap-2">
                  <button type="button" onClick={() => void generateAdvice()} disabled={reflectionAdviceLoading} className="rounded-lg border border-blue-200 px-3 py-2 text-xs font-semibold text-blue-700 disabled:opacity-50">{reflectionAdviceLoading ? '生成中…' : 'AI 生成建议'}</button>
                  <button type="button" onClick={saveReflection} className="rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-700">保存复盘</button>
                </div>
              </div>
              {reflectionAdvice && <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-3 text-xs leading-5 text-indigo-900">
                <div className="mb-1 font-semibold">{reflectionAdvice.aiUsed ? 'AI 复盘建议' : '本地复盘建议'}</div>
                <div className="whitespace-pre-wrap">{reflectionAdvice.reply}</div>
                {reflectionAdvice.warnings.length > 0 && <div className="mt-2 text-[10px] text-indigo-600">{reflectionAdvice.warnings.join('；')}</div>}
              </div>}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

function ControlChip({
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
      type="button"
      onClick={onClick}
      className="rounded-md px-3 py-1.5 transition"
      style={{
        background: active ? '#2563eb' : 'rgba(255,255,255,0.06)',
        color: '#fff',
      }}
    >
      {label}
    </button>
  );
}
