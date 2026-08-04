import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import LessonPackageTree from '../components/lesson/LessonPackageTree';
import SlideViewer from '../components/slides/SlideViewer';
import SlidesToolbar from '../components/slides/SlidesToolbar';
import TeachingSlidePage from '../components/teaching/TeachingSlidePage';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import {
  deleteSavedLessonPackage,
  listSavedLessonPackages,
  loadCurrentLessonPackage,
  loadSavedLessonPackage,
  saveCurrentLessonPackage,
  saveLessonPackageToLibrary,
} from '../services/lessonPackage';
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

export default function SlidesPage() {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const [lessonPackage, setLessonPackage] = useState<LessonPackage | null>(() => loadCurrentLessonPackage());
  const [savedPackages, setSavedPackages] = useState(() => listSavedLessonPackages());
  const pages = useMemo(() => (lessonPackage ? buildMixedPages(lessonPackage) : []), [lessonPackage]);
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

  const goTo = useCallback(
    (index: number) => {
      setCurrentIndex(Math.max(0, Math.min(pages.length - 1, index)));
      setRevealStep(0);
    },
    [pages.length],
  );

  const handleModeChange = useCallback((mode: SlidesDisplayMode) => {
    setDisplayMode(mode);
    setRevealStep(0);
  }, []);

  const onFullscreen = useCallback(() => {
    const node = containerRef.current;
    if (!node) return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => undefined);
      return;
    }
    node.requestFullscreen().catch(() => undefined);
  }, []);

  const openSavedPackage = useCallback((id: string) => {
    const pkg = loadSavedLessonPackage(id);
    if (!pkg) return;
    setLessonPackage(pkg);
    saveCurrentLessonPackage(pkg);
    setCurrentIndex(0);
  }, []);

  const handleSaveCurrent = useCallback(() => {
    if (!lessonPackage) return;
    saveLessonPackageToLibrary(lessonPackage);
    setSavedPackages(listSavedLessonPackages());
  }, [lessonPackage]);

  const handleDeleteSaved = useCallback((id: string) => {
    deleteSavedLessonPackage(id);
    setSavedPackages(listSavedLessonPackages());
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const tagName = (event.target as HTMLElement)?.tagName;
      if (tagName === 'INPUT' || tagName === 'TEXTAREA' || tagName === 'SELECT') return;

      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        goPrev();
      }
      if (event.key === 'ArrowRight' || event.key === ' ') {
        event.preventDefault();
        goNext();
      }
      if (event.key === 'Home') {
        event.preventDefault();
        goTo(0);
      }
      if (event.key === 'End') {
        event.preventDefault();
        goTo(pages.length - 1);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [goNext, goPrev, goTo, pages.length]);

  useEffect(() => {
    const syncFullscreenState = () => setIsFullscreen(document.fullscreenElement === containerRef.current);
    document.addEventListener('fullscreenchange', syncFullscreenState);
    return () => document.removeEventListener('fullscreenchange', syncFullscreenState);
  }, []);

  if (!lessonPackage || pages.length === 0) {
    return (
      <EmptyState
        icon="🖥️"
        title="还没有可播放的幻灯内容"
        description="先去组卷工作台选择题目和知识点，系统会自动组织成讲授顺序。"
        action={{ label: '前往组卷工作台', onClick: () => navigate('/compose') }}
      />
    );
  }

  return (
    <div ref={containerRef} className={`relative flex ${isFullscreen ? 'h-screen bg-[#0b1220]' : 'h-full bg-[var(--color-bg)]'} flex-col`}>
      {!isFullscreen && (
        <SlidesToolbar
          title={lessonPackage.title || '课堂幻灯预览'}
          displayMode={displayMode}
          onModeChange={handleModeChange}
          zoomLevel={zoomLevel}
          onZoomIn={() => setZoomLevel((prev) => Math.min(2, +(prev + 0.1).toFixed(1)))}
          onZoomOut={() => setZoomLevel((prev) => Math.max(0.6, +(prev - 0.1).toFixed(1)))}
          onZoomReset={() => setZoomLevel(1)}
          onFullscreen={onFullscreen}
          questionCount={questionCount}
        />
      )}

      <div className="flex min-h-0 flex-1">
        {!isFullscreen && (
          <LessonPackageTree
            packages={savedPackages}
            activeId={lessonPackage.id}
            title="幻灯文件树"
            emptyText="保存一次后，这里会长期保留你的幻灯作品。"
            onOpen={openSavedPackage}
            onDelete={handleDeleteSaved}
            onSaveCurrent={handleSaveCurrent}
          />
        )}

        <div className={`flex min-w-0 flex-1 flex-col ${isFullscreen ? 'bg-[#0b1220]' : ''}`}>
          {!isFullscreen && (
            <div className="border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-[var(--color-text)]">幻灯链路已接通</div>
                <div className="text-xs text-[var(--color-text-muted)]">
                  当前幻灯页直接读取组卷工作台生成的教学包，不再单独维护一套页面数据。
                </div>
              </div>
              <div className="flex flex-wrap gap-2 text-xs text-[var(--color-text-secondary)]">
                <span className="pv-chip">{lessonPackage.knowledgeCards.length} 个知识点</span>
                <span className="pv-chip">{lessonPackage.questions.length} 道题</span>
                <span className="pv-chip">{pages.length} 页幻灯</span>
                <Button variant="outline" size="sm" onClick={handleSaveCurrent}>保存当前</Button>
              </div>
            </div>
            </div>
          )}

          <div className={`min-h-0 flex-1 ${isFullscreen ? 'overflow-hidden bg-[#0b1220]' : 'overflow-auto bg-[var(--color-bg-hover)] px-5 py-5'}`}>
            {currentPage.kind === 'knowledge' ? (
              <TeachingSlidePage data={currentPage.slide} fitToViewport={isFullscreen} />
            ) : (
              <SlideViewer
                question={currentPage.question!}
                index={pages.slice(0, currentIndex + 1).filter((page) => page.kind === 'question').length - 1}
                total={questionCount}
                displayMode={displayMode}
                zoomLevel={isFullscreen ? 1 : zoomLevel}
                fitToViewport={isFullscreen}
                revealStep={revealStep}
              />
            )}
          </div>
        </div>

        {!isFullscreen && <aside className="w-72 border-l border-[var(--color-border)] bg-[var(--color-bg-card)]">
          <div className="border-b border-[var(--color-border)] px-4 py-4">
            <div className="text-sm font-semibold text-[var(--color-text)]">播放目录</div>
            <div className="mt-1 text-xs text-[var(--color-text-muted)]">
              先讲知识点，再讲题目，授课和预览保持同一顺序。
            </div>
          </div>
          <div className="max-h-full overflow-auto px-3 py-3">
            <div className="space-y-2">
              {pages.map((page, index) => {
                const active = index === currentIndex;
                const label = page.kind === 'knowledge'
                  ? page.slide.title
                  : `题目 ${page.question?.question_id || index + 1}`;

                return (
                  <button
                    key={page.slide.id}
                    type="button"
                    onClick={() => goTo(index)}
                    className="w-full rounded-md border px-3 py-2.5 text-left transition"
                    style={{
                      borderColor: active ? 'var(--color-accent)' : 'var(--color-border)',
                      background: active ? 'var(--color-accent-light)' : 'var(--color-bg-card)',
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs text-[var(--color-text-muted)]">
                        {page.kind === 'knowledge' ? `知识点 ${index + 1}` : `幻灯 ${index + 1}`}
                      </span>
                      {active && (
                        <span className="rounded bg-[var(--color-accent)] px-2 py-0.5 text-[10px] text-white">
                          当前
                        </span>
                      )}
                    </div>
                    <div className="mt-1 line-clamp-2 text-sm font-medium text-[var(--color-text)]">
                      {label}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </aside>}
      </div>

      {!isFullscreen && <div className="flex items-center justify-between border-t border-[var(--color-border)] bg-[var(--color-bg-card)] px-5 py-3">
        <div className="text-sm text-[var(--color-text-secondary)]">
          第 {currentIndex + 1} / {pages.length} 页
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={goPrev} disabled={currentIndex === 0 && revealStep === 0}>
            上一页
          </Button>
          <Button onClick={goNext} disabled={currentIndex === pages.length - 1 && revealStep >= maxRevealStep}>
            下一页
          </Button>
        </div>
      </div>}

      {isFullscreen && (
        <div className="absolute inset-x-0 bottom-0 z-20 flex items-center justify-between bg-gradient-to-t from-black/70 to-transparent px-6 pb-5 pt-12 text-white opacity-0 transition-opacity hover:opacity-100 focus-within:opacity-100">
          <span className="text-sm font-medium">第 {currentIndex + 1} / {pages.length} 页</span>
          <div className="flex items-center gap-2">
            <button type="button" onClick={goPrev} disabled={currentIndex === 0 && revealStep === 0} className="rounded bg-white/15 px-3 py-1.5 text-sm disabled:opacity-30">上一页</button>
            <button type="button" onClick={goNext} disabled={currentIndex === pages.length - 1 && revealStep >= maxRevealStep} className="rounded bg-white/15 px-3 py-1.5 text-sm disabled:opacity-30">下一页</button>
            <button type="button" onClick={onFullscreen} className="rounded bg-white px-3 py-1.5 text-sm font-semibold text-[#10233f]">退出全屏</button>
          </div>
        </div>
      )}
    </div>
  );
}
