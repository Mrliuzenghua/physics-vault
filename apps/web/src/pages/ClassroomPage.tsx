import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import SlideViewer from '../components/slides/SlideViewer';
import TeachingSlidePage from '../components/teaching/TeachingSlidePage';
import { EmptyState } from '../components/ui/EmptyState';
import { loadCurrentLessonPackage } from '../services/lessonPackage';
import { layoutModelToSlideDeck, lessonPackageToLayoutModel } from '../services/lessonLayoutModel';
import type { LessonPackage, Question, SlidesDisplayMode } from '../types';
import type { SlidePage } from '../types/slides';

interface MixedPage {
  kind: 'knowledge' | 'question';
  slide: SlidePage;
  question?: Question;
}

function buildMixedPages(lessonPackage: LessonPackage): MixedPage[] {
  const deck = layoutModelToSlideDeck(lessonPackageToLayoutModel(lessonPackage));
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
  const pages = useMemo(() => (lessonPackage ? buildMixedPages(lessonPackage) : []), [lessonPackage]);
  const stageRef = useRef<HTMLDivElement>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [displayMode, setDisplayMode] = useState<SlidesDisplayMode>('stem_only');
  const [revealStep, setRevealStep] = useState(0);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);

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

  if (!lessonPackage || pages.length === 0) {
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
              <div className="text-lg font-semibold">{lessonPackage.title}</div>
              <div className="mt-1 text-sm text-white/60">
                授课模式直接读取当前教学包，讲义预览、幻灯预览、课堂授课保持同一顺序。
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <ControlChip label="仅题干" active={displayMode === 'stem_only'} onClick={() => setTeachingMode('stem_only')} />
              <ControlChip label="题干 + 答案" active={displayMode === 'stem_answer'} onClick={() => setTeachingMode('stem_answer')} />
              <ControlChip label="完整解析" active={displayMode === 'full'} onClick={() => setTeachingMode('full')} />
              <ControlChip label={isFullscreen ? '退出全屏' : '全屏'} active={isFullscreen} onClick={toggleFullscreen} />
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
      </aside>
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
