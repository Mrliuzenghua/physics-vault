import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import LessonPackageTree from '../components/lesson/LessonPackageTree';
import SlidesToolbar from '../components/slides/SlidesToolbar';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import {
  deleteSavedLessonPackage,
  createLessonFolder,
  deleteLessonFolder,
  listLessonFolders,
  listSavedLessonPackages,
  loadCurrentLessonPackage,
  loadSavedLessonPackage,
  saveCurrentLessonPackage,
  saveLessonPackageToLibrary,
  moveSavedLessonPackage,
  renameLessonFolder,
} from '../services/lessonPackage';
import { layoutModelToSlideDeck, lessonPackageToLayoutModel } from '../services/lessonLayoutModel';
import { getOrCreateTeachingProject, hydrateTeachingProject, isArtifactStale, saveSlideArtifact } from '../services/teachingProject';
import type { LessonPackage, Question, SlidesDisplayMode } from '../types';
import type { SlideDeck, SlidePage } from '../types/slides';

const SlideViewer = lazy(() => import('../components/slides/SlideViewer'));
const TeachingSlidePage = lazy(() => import('../components/teaching/TeachingSlidePage'));

interface MixedPage {
  kind: 'knowledge' | 'question';
  slide: SlidePage;
  question?: Question;
}

function markSlidesEdited(status: 'draft' | 'ready' | 'stale' | 'changed_after_publish' | 'published') {
  if (status === 'published') return 'changed_after_publish' as const;
  if (status === 'draft') return 'ready' as const;
  return status;
}

function slidesStatusLabel(status: string | undefined) {
  switch (status) {
    case 'published': return '已发布';
    case 'changed_after_publish': return '发布后有修改';
    case 'stale': return '内容有更新';
    case 'ready': return '可发布';
    default: return '草稿';
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

function sameJson(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function mergeGeneratedDeck(current: SlideDeck, generated: SlideDeck, previousGenerated?: SlideDeck): SlideDeck {
  const currentById = new Map(current.pages.map((page) => [page.id, page]));
  const previousById = new Map((previousGenerated?.pages || []).map((page) => [page.id, page]));
  const generatedIds = new Set(generated.pages.map((page) => page.id));
  const pages = generated.pages.map((page) => {
    const existing = currentById.get(page.id);
    if (!existing) return page;
    const baseline = previousById.get(page.id);
    // Legacy projects have no baseline. Keep their current page conservatively
    // so the first sync can never erase an existing manual adjustment.
    if (!baseline) return existing;
    return !sameJson(existing, baseline) ? existing : page;
  });

  // Keep manually-created pages that have no generated counterpart instead of deleting them.
  current.pages.forEach((page) => {
    if (!generatedIds.has(page.id)) pages.push(page);
  });
  return { ...generated, pages };
}

function SlideLoading() {
  return <div className="grid h-full min-h-72 place-items-center text-sm text-[var(--color-text-muted)]">正在加载课件…</div>;
}

export default function SlidesPage() {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const [lessonPackage, setLessonPackage] = useState<LessonPackage | null>(() => loadCurrentLessonPackage());
  const [project, setProject] = useState(() => {
    const pkg = loadCurrentLessonPackage();
    return pkg ? getOrCreateTeachingProject(pkg) : null;
  });
  const [savedPackages, setSavedPackages] = useState(() => listSavedLessonPackages());
  const [folders, setFolders] = useState(() => listLessonFolders());
  const [activeFolderId, setActiveFolderId] = useState<string | null>(() => lessonPackage?.folderId || null);
  const projectId = project?.id;
  const projectUpdatedAt = project?.updatedAt;
  const pages = useMemo(() => (lessonPackage && project ? buildMixedPages(lessonPackage, project.slides.deck) : []), [lessonPackage, project]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [editMode, setEditMode] = useState(false);
  const [displayMode, setDisplayMode] = useState<SlidesDisplayMode>('stem_only');
  const [revealStep, setRevealStep] = useState(0);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    void hydrateTeachingProject(projectId).then((remoteProject) => {
      if (!cancelled && remoteProject && remoteProject.updatedAt !== projectUpdatedAt) setProject(remoteProject);
    });
    return () => { cancelled = true; };
  }, [projectId, projectUpdatedAt]);

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
    setProject(getOrCreateTeachingProject(pkg));
    setActiveFolderId(pkg.folderId || null);
    saveCurrentLessonPackage(pkg);
    setCurrentIndex(0);
  }, []);

  const handleSaveCurrent = useCallback(() => {
    if (!lessonPackage) return;
    saveLessonPackageToLibrary({ ...lessonPackage, folderId: activeFolderId ?? lessonPackage.folderId ?? null });
    if (project) {
      const nextArtifact = {
        ...project.slides,
        sourceRevision: project.contentRevision,
        status: markSlidesEdited(project.slides.status),
        updatedAt: new Date().toISOString(),
      };
      saveSlideArtifact(nextArtifact);
      setProject({ ...project, slides: nextArtifact });
    }
    setSavedPackages(listSavedLessonPackages());
  }, [activeFolderId, lessonPackage, project]);

  const handlePublish = useCallback(() => {
    if (!lessonPackage || !project) return;
    const nextPackage = { ...lessonPackage, folderId: activeFolderId ?? lessonPackage.folderId ?? null, updatedAt: new Date().toISOString() };
    saveLessonPackageToLibrary(nextPackage);
    const publishedAt = new Date().toISOString();
    const nextArtifact = {
      ...project.slides,
      sourceRevision: project.contentRevision,
      status: 'published' as const,
      publishedSnapshot: {
        version: (project.slides.publishedSnapshot?.version || 0) + 1,
        publishedAt,
        sourceRevision: project.contentRevision,
        deck: {
          ...project.slides.deck,
          pages: project.slides.deck.pages.map((page) => ({
            ...page,
            sections: page.sections.map((section) => ({
              ...section,
              items: section.items.map((item) => ({
                ...item,
                children: item.children?.map((child) => ({ ...child })),
              })),
            })),
          })),
        },
        lessonPackage: nextPackage,
      },
      updatedAt: publishedAt,
    };
    saveSlideArtifact(nextArtifact);
    setLessonPackage(nextPackage);
    setProject({ ...project, slides: nextArtifact });
    setSavedPackages(listSavedLessonPackages());
  }, [activeFolderId, lessonPackage, project]);

  const updateSlidePages = useCallback((pagesToSave: SlidePage[], nextIndex: number) => {
    if (!project) return;
    const nextArtifact = {
      ...project.slides,
      deck: { ...project.slides.deck, pages: pagesToSave },
      sourceRevision: project.contentRevision,
      status: markSlidesEdited(project.slides.status),
      updatedAt: new Date().toISOString(),
    };
    saveSlideArtifact(nextArtifact);
    setProject({ ...project, slides: nextArtifact });
    setCurrentIndex(Math.max(0, Math.min(pagesToSave.length - 1, nextIndex)));
    setRevealStep(0);
  }, [project]);

  const moveCurrentSlide = useCallback((delta: -1 | 1) => {
    if (!project || !pages[currentIndex]) return;
    const nextIndex = currentIndex + delta;
    if (nextIndex < 0 || nextIndex >= pages.length) return;
    const nextPages = project.slides.deck.pages.slice();
    const [current] = nextPages.splice(currentIndex, 1);
    nextPages.splice(nextIndex, 0, current);
    updateSlidePages(nextPages, nextIndex);
  }, [currentIndex, pages, project, updateSlidePages]);

  const duplicateCurrentSlide = useCallback(() => {
    if (!project || !pages[currentIndex]) return;
    const source = project.slides.deck.pages[currentIndex];
    const copy = { ...source, id: `${source.id}-copy-${Date.now()}` };
    const nextPages = project.slides.deck.pages.slice();
    nextPages.splice(currentIndex + 1, 0, copy);
    updateSlidePages(nextPages, currentIndex + 1);
  }, [currentIndex, pages, project, updateSlidePages]);

  const syncSlidesFromContent = useCallback(() => {
    if (!lessonPackage || !project) return;
    const generatedDeck = layoutModelToSlideDeck(lessonPackageToLayoutModel(lessonPackage, project.contentRevision));
    const deck = mergeGeneratedDeck(project.slides.deck, generatedDeck, project.slides.generatedDeck);
    const nextArtifact = {
      ...project.slides,
      deck,
      generatedDeck,
      sourceRevision: project.contentRevision,
      status: 'ready' as const,
      updatedAt: new Date().toISOString(),
    };
    saveSlideArtifact(nextArtifact);
    setProject({ ...project, slides: nextArtifact });
    setCurrentIndex(0);
    setRevealStep(0);
  }, [lessonPackage, project]);

  const handleDeleteSaved = useCallback((id: string) => {
    deleteSavedLessonPackage(id);
    setSavedPackages(listSavedLessonPackages());
  }, []);

  const handleCreateFolder = useCallback(() => {
    const name = window.prompt('请输入文件夹名称');
    if (!name) return;
    const folder = createLessonFolder(name);
    if (folder) {
      setFolders(listLessonFolders());
      setActiveFolderId(folder.id);
    }
  }, []);

  const handleRenameFolder = useCallback((id: string) => {
    const folder = folders.find((item) => item.id === id);
    const name = window.prompt('修改文件夹名称', folder?.name || '');
    if (!name) return;
    renameLessonFolder(id, name);
    setFolders(listLessonFolders());
  }, [folders]);

  const handleDeleteFolder = useCallback((id: string) => {
    if (!window.confirm('删除文件夹后，其中的作品会移动到“未分类”，确定继续吗？')) return;
    deleteLessonFolder(id);
    setFolders(listLessonFolders());
    setSavedPackages(listSavedLessonPackages());
    if (activeFolderId === id) setActiveFolderId(null);
  }, [activeFolderId]);

  const handleMovePackage = useCallback((id: string, folderId: string | null) => {
    moveSavedLessonPackage(id, folderId);
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

      {!isFullscreen && project && isArtifactStale(project, project.slides.sourceRevision) && (
        <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
          <button type="button" onClick={syncSlidesFromContent} className="mr-2 rounded bg-amber-700 px-2 py-1 font-semibold text-white">同步最新内容</button>
          当前课件基于内容版本 {project.slides.sourceRevision}，最新内容版本为 {project.contentRevision}。请确认同步后再发布，避免覆盖手动调整。
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        {!isFullscreen && (
          <LessonPackageTree
            packages={savedPackages}
            folders={folders}
            activeId={lessonPackage.id}
            activeFolderId={activeFolderId}
            title="幻灯文件树"
            emptyText="保存一次后，这里会长期保留你的幻灯作品。"
            onOpen={openSavedPackage}
            onDelete={handleDeleteSaved}
            onFolderSelect={setActiveFolderId}
            onCreateFolder={handleCreateFolder}
            onRenameFolder={handleRenameFolder}
            onDeleteFolder={handleDeleteFolder}
            onMovePackage={handleMovePackage}
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
                <Button variant="secondary" size="sm" onClick={() => setEditMode((value) => !value)}>{editMode ? '完成编辑' : '编辑课件'}</Button>
                {editMode && <>
                  <Button variant="outline" size="sm" onClick={() => moveCurrentSlide(-1)} disabled={currentIndex === 0}>上移</Button>
                  <Button variant="outline" size="sm" onClick={() => moveCurrentSlide(1)} disabled={currentIndex === pages.length - 1}>下移</Button>
                  <Button variant="outline" size="sm" onClick={duplicateCurrentSlide}>复制当前页</Button>
                </>}
                <span className="pv-chip">{lessonPackage.knowledgeCards.length} 个知识点</span>
                <span className="pv-chip">{lessonPackage.questions.length} 道题</span>
                <span className="pv-chip">{pages.length} 页幻灯</span>
                {project && <span className={`pv-chip ${project.slides.status === 'changed_after_publish' || project.slides.status === 'stale' ? 'text-amber-700' : ''}`}>状态：{slidesStatusLabel(project.slides.status)}</span>}
                <Button variant="outline" size="sm" onClick={handleSaveCurrent}>保存当前</Button>
                {project && <Button size="sm" onClick={handlePublish}>{project.slides.status === 'published' ? '重新发布' : '发布课件'}</Button>}
              </div>
            </div>
            </div>
          )}

          <div className={`min-h-0 flex-1 ${isFullscreen ? 'overflow-hidden bg-[#0b1220]' : 'overflow-auto bg-[var(--color-bg-hover)] px-5 py-5'}`}>
            <Suspense fallback={<SlideLoading />}>
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
            </Suspense>
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
