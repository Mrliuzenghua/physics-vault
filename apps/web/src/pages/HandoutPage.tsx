import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { useNavigate } from 'react-router-dom';

import { PagedHandoutDocument, getHandoutPaginationReport } from '../components/handout/HandoutDocument';
import PrintPreflightPanel from '../components/handout/PrintPreflightPanel';
import HandoutStylePresetPanel from '../components/handout/HandoutStylePresetPanel';
import DocumentPreviewModal from '../components/import/DocumentPreviewModal';
import LessonPackageTree from '../components/lesson/LessonPackageTree';
import { DEFAULT_CONFIG as DEFAULT_HF_CONFIG } from '../components/handout/HandoutHeaderFooterConfigPanel';
import HandoutHeaderFooterConfigPanel from '../components/handout/HandoutHeaderFooterConfigPanel';
import { DEFAULT_STYLE_CONFIG } from '../components/handout/handoutStylePresets';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { Input } from '../components/ui/Input';
import {
  deleteSavedLessonPackage,
  createLessonFolder,
  deleteLessonFolder,
  listSavedLessonPackages,
  listLessonFolders,
  loadSavedLessonPackage,
  loadCurrentLessonPackage,
  saveCurrentLessonPackage,
  saveLessonPackageToLibrary,
  moveSavedLessonPackage,
  renameLessonFolder,
} from '../services/lessonPackage';
import { layoutModelToHandoutItems, lessonPackageToLayoutModel } from '../services/lessonLayoutModel';
import { getOrCreateTeachingProject, hydrateTeachingProject, saveHandoutArtifact } from '../services/teachingProject';
import { buildWordFormatSpec, exportLessonAsWord, validateLessonPackage } from '../services/lessonExport';
import { listSavedHandoutVersions, restoreSavedHandoutVersion, saveSavedLessonPackage } from '../services/api';
import type {
  HandoutConfig,
  HandoutItem,
  LessonPackage,
  PreflightRiskItem,
} from '../types';
import type { TeachingArtifactStatus } from '../types/teachingProject';
import { parseLessonPackage } from '../services/lessonPackageSchema';

type SyncStatus = 'idle' | 'syncing' | 'synced' | 'error';

function markHandoutEdited(status: TeachingArtifactStatus): TeachingArtifactStatus {
  if (status === 'published') return 'changed_after_publish';
  if (status === 'draft') return 'ready';
  return status;
}

function handoutStatusLabel(status: string | undefined) {
  switch (status) {
    case 'published': return '已发布';
    case 'changed_after_publish': return '发布后有修改';
    case 'stale': return '内容有更新';
    case 'ready': return '可发布';
    default: return '草稿';
  }
}

function normalizeHandoutConfig(config: Partial<HandoutConfig> | null | undefined, pkg: LessonPackage | null): HandoutConfig {
  return {
    title: config?.title ?? pkg?.title ?? '物理讲义预览',
    subtitle: config?.subtitle ?? pkg?.subtitle ?? '题目与知识点一体化讲义',
    showAnswers: config?.showAnswers ?? true,
    showAnalysis: config?.showAnalysis ?? true,
    headerFooter: {
      ...DEFAULT_HF_CONFIG,
      ...(pkg?.headerFooter || {}),
      ...(config?.headerFooter || {}),
    },
    styleConfig: {
      ...DEFAULT_STYLE_CONFIG,
      ...(pkg?.styleConfig || {}),
      ...(config?.styleConfig || {}),
    },
  };
}

function splitIntoPages(items: HandoutItem[]): HandoutItem[][] {
  const pages: HandoutItem[][] = [];
  let current: HandoutItem[] = [];

  for (const item of items) {
    if (item.type === 'page_break' && current.length > 0) {
      pages.push(current);
      current = [];
      continue;
    }
    current.push(item);
  }

  if (current.length > 0) {
    pages.push(current);
  }

  return pages.length > 0 ? pages : [[]];
}

function buildPreflightRisks(items: HandoutItem[], config: HandoutConfig): PreflightRiskItem[] {
  const pages = splitIntoPages(items);
  const risks: PreflightRiskItem[] = [];
  let globalQuestionIndex = 0;

  pages.forEach((pageItems, pageIndex) => {
    let pageQuestionCount = 0;

    pageItems.forEach((item) => {
      if (item.type !== 'question' || !item.question) {
        return;
      }

      globalQuestionIndex += 1;
      pageQuestionCount += 1;

      const textLength =
        (item.question.title || '').length +
        (config.showAnswers ? (item.question.answer || '').length : 0) +
        (config.showAnalysis ? (item.question.analysis || '').length : 0);

      if (textLength > 1400) {
        risks.push({
          pageIndex,
          pageLabel: `第 ${pageIndex + 1} 页`,
          questionIndex: globalQuestionIndex,
          questionId: item.question.question_id,
          severity: 'danger',
          message: `第 ${globalQuestionIndex} 题内容过长，打印时可能跨页截断，请重点检查。`,
        });
      } else if (textLength > 900) {
        risks.push({
          pageIndex,
          pageLabel: `第 ${pageIndex + 1} 页`,
          questionIndex: globalQuestionIndex,
          questionId: item.question.question_id,
          severity: 'warning',
          message: `第 ${globalQuestionIndex} 题内容偏长，建议核对题干、答案和解析的排版密度。`,
        });
      }

      if ((item.question.figures || []).length > 0) {
        risks.push({
          pageIndex,
          pageLabel: `第 ${pageIndex + 1} 页`,
          questionIndex: globalQuestionIndex,
          questionId: item.question.question_id,
          severity: 'warning',
          message: `第 ${globalQuestionIndex} 题含有图片，请确认图片大小和页边距是否协调。`,
        });
      }
    });

    if (pageQuestionCount >= 5) {
      risks.push({
        pageIndex,
        pageLabel: `第 ${pageIndex + 1} 页`,
        severity: 'warning',
        message: '本页题量较多，建议预览打印效果，避免视觉过于拥挤。',
      });
    }
  });

  return risks;
}

export default function HandoutPage() {
  const navigate = useNavigate();
  const [lessonPackage, setLessonPackage] = useState<LessonPackage | null>(() => loadCurrentLessonPackage());
  const [project, setProject] = useState(() => {
    const pkg = loadCurrentLessonPackage();
    return pkg ? getOrCreateTeachingProject(pkg) : null;
  });
  const [savedPackages, setSavedPackages] = useState(() => listSavedLessonPackages());
  const [folders, setFolders] = useState(() => listLessonFolders());
  const [activeFolderId, setActiveFolderId] = useState<string | null>(() => lessonPackage?.folderId || null);
  const [preflightMode, setPreflightMode] = useState(false);
  const [pageBreakMode, setPageBreakMode] = useState(false);
  const [stylePanelOpen, setStylePanelOpen] = useState(false);
  const [previewZoom, setPreviewZoom] = useState(82);
  const [syncStatus, setSyncStatus] = useState<SyncStatus>('idle');
  const [versionPanelOpen, setVersionPanelOpen] = useState(false);
  const [versions, setVersions] = useState<Record<string, unknown>[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [wordPreviewFile, setWordPreviewFile] = useState<File | null>(null);
  const [wordPreviewLoading, setWordPreviewLoading] = useState(false);
  const [printPreparing, setPrintPreparing] = useState(false);
  const [renderedPageCount, setRenderedPageCount] = useState<number | null>(null);
  const printRequestedRef = useRef(false);
  const [config, setConfig] = useState<HandoutConfig>(() => normalizeHandoutConfig(null, lessonPackage));

  useEffect(() => {
    if (project) setConfig(normalizeHandoutConfig(project.handout.config, lessonPackage));
  }, [lessonPackage, project]);

  useEffect(() => {
    if (!project) return;
    let cancelled = false;
    void hydrateTeachingProject(project.id).then((remoteProject) => {
      if (!cancelled && remoteProject && remoteProject.updatedAt !== project.updatedAt) setProject(remoteProject);
    });
    return () => { cancelled = true; };
  }, [project?.id]);

  useEffect(() => {
    const localPackages = listSavedLessonPackages()
      .map((summary) => loadSavedLessonPackage(summary.id))
      .filter((pkg): pkg is LessonPackage => Boolean(pkg));
    if (localPackages.length === 0) return;
    setSyncStatus('syncing');
    void Promise.all(localPackages.map((pkg) => saveSavedLessonPackage(pkg, pkg.source === 'compose' ? pkg.id : undefined)))
      .then(() => setSyncStatus('synced'))
      .catch(() => setSyncStatus('error'));
  }, []);

  const items = useMemo(
    () => {
      if (!lessonPackage) return [];
      const baseItems = layoutModelToHandoutItems(lessonPackageToLayoutModel(lessonPackage));
      const breakAfter = new Set(project?.handout.pageBreakAfterBlockIds || []);
      return baseItems.flatMap((item) => (
        item.id && breakAfter.has(item.id)
          ? [item, { id: `output-break-${item.id}`, type: 'page_break' as const, title: '讲义分页' }]
          : [item]
      ));
    },
    [lessonPackage, project],
  );

  useEffect(() => {
    setRenderedPageCount(null);
  }, [config, items]);

  const paginationReport = useMemo(() => getHandoutPaginationReport(items, config), [items, config]);
  const pageCount = paginationReport.estimatedPageCount;
  const questionCount = useMemo(
    () => items.filter((item) => item.type === 'question').length,
    [items],
  );
  const knowledgeCount = lessonPackage?.knowledgeCards.length || 0;
  const risks = useMemo(() => buildPreflightRisks(items, config), [items, config]);

  const handlePrint = useCallback(() => {
    if (!lessonPackage) return;
    if (project) {
      const nextArtifact = {
        ...project.handout,
        title: config.title,
        config,
        sourceRevision: project.contentRevision,
        status: markHandoutEdited(project.handout.status),
        updatedAt: new Date().toISOString(),
      };
      saveHandoutArtifact(nextArtifact);
      setProject({ ...project, handout: nextArtifact });
    }
    printRequestedRef.current = true;
    setPrintPreparing(true);
  }, [config, lessonPackage, project]);

  const handlePagedPreviewReady = useCallback((nextPageCount: number) => {
    setRenderedPageCount(nextPageCount || null);
  }, []);

  const handlePagedPrintReady = useCallback((nextPageCount: number) => {
    setRenderedPageCount(nextPageCount || null);
    if (!printRequestedRef.current) return;
    // Paged.js has finished creating fixed-size pages, including margin boxes.
    // Let the browser paint them before opening its native print dialog.
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        if (printRequestedRef.current) window.print();
      });
    });
  }, []);

  useEffect(() => {
    const restorePreview = () => {
      printRequestedRef.current = false;
      setPrintPreparing(false);
    };
    window.addEventListener('afterprint', restorePreview);
    return () => window.removeEventListener('afterprint', restorePreview);
  }, []);

  const handleWordPreview = useCallback(async () => {
    if (!lessonPackage) return;
    const nextPackage: LessonPackage = {
      ...lessonPackage,
      title: config.title,
      subtitle: config.subtitle,
      headerFooter: config.headerFooter,
      styleConfig: config.styleConfig,
      updatedAt: new Date().toISOString(),
    };
    nextPackage.formatSpec = buildWordFormatSpec(nextPackage, {
      includeAnswers: config.showAnswers,
      includeAnalysis: config.showAnalysis,
      answerPosition: 'after_question',
      download: false,
    });
    const exportIssues = validateLessonPackage(nextPackage);
    if (exportIssues.length > 0) {
      window.alert(`导出预检未通过：${exportIssues.slice(0, 3).map((issue) => issue.message).join('；')}`);
      return;
    }
    setWordPreviewLoading(true);
    try {
      const blob = await exportLessonAsWord(nextPackage, {
        includeAnswers: config.showAnswers,
        includeAnalysis: config.showAnalysis,
        answerPosition: 'after_question',
        download: false,
      });
      setWordPreviewFile(new File([blob], `${config.title || '物理讲义'}.docx`, { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }));
    } catch (error) {
      window.alert(error instanceof Error ? error.message : 'Word 预览生成失败');
    } finally {
      setWordPreviewLoading(false);
    }
  }, [config, lessonPackage]);

  const openSavedPackage = useCallback((id: string) => {
    const pkg = loadSavedLessonPackage(id);
    if (!pkg) return;
    setLessonPackage(pkg);
    setProject(getOrCreateTeachingProject(pkg));
    setActiveFolderId(pkg.folderId || null);
    saveCurrentLessonPackage(pkg);
  }, []);

  const handleSaveCurrent = useCallback(() => {
    if (!lessonPackage) return;
    const nextPackage: LessonPackage = {
      ...lessonPackage,
      title: config.title,
      subtitle: config.subtitle,
      headerFooter: config.headerFooter,
      styleConfig: config.styleConfig,
      folderId: activeFolderId ?? lessonPackage.folderId ?? null,
      updatedAt: new Date().toISOString(),
    };
    nextPackage.formatSpec = buildWordFormatSpec(nextPackage, {
      includeAnswers: config.showAnswers,
      includeAnalysis: config.showAnalysis,
      answerPosition: 'after_question',
      download: false,
    });
    saveLessonPackageToLibrary(nextPackage);
    setSyncStatus('syncing');
    void saveSavedLessonPackage(nextPackage, nextPackage.source === 'compose' ? nextPackage.id : undefined)
      .then(() => setSyncStatus('synced'))
      .catch(() => setSyncStatus('error'));
    if (project) {
      const nextArtifact = {
        ...project.handout,
        title: config.title,
        config,
        sourceRevision: project.contentRevision,
        status: markHandoutEdited(project.handout.status),
        updatedAt: new Date().toISOString(),
      };
      saveHandoutArtifact(nextArtifact);
      setProject({ ...project, handout: nextArtifact });
    }
    setSavedPackages(listSavedLessonPackages());
  }, [activeFolderId, config, lessonPackage, project]);

  const handlePublish = useCallback(() => {
    if (!lessonPackage || !project) return;
    const nextPackage: LessonPackage = {
      ...lessonPackage,
      title: config.title,
      subtitle: config.subtitle,
      headerFooter: config.headerFooter,
      styleConfig: config.styleConfig,
      folderId: activeFolderId ?? lessonPackage.folderId ?? null,
      updatedAt: new Date().toISOString(),
    };
    nextPackage.formatSpec = buildWordFormatSpec(nextPackage, {
      includeAnswers: config.showAnswers,
      includeAnalysis: config.showAnalysis,
      answerPosition: 'after_question',
      download: false,
    });
    saveLessonPackageToLibrary(nextPackage);
    const publishedAt = new Date().toISOString();
    const nextArtifact = {
      ...project.handout,
      title: config.title,
      config,
      sourceRevision: project.contentRevision,
      status: 'published' as const,
      publishedSnapshot: {
        version: (project.handout.publishedSnapshot?.version || 0) + 1,
        publishedAt,
        sourceRevision: project.contentRevision,
        config: {
          ...config,
          headerFooter: { ...config.headerFooter },
          styleConfig: { ...config.styleConfig },
        },
        pageBreakAfterBlockIds: [...project.handout.pageBreakAfterBlockIds],
      },
      updatedAt: publishedAt,
    };
    saveHandoutArtifact(nextArtifact);
    setLessonPackage(nextPackage);
    setProject({ ...project, handout: nextArtifact });
    setSavedPackages(listSavedLessonPackages());
    setSyncStatus('syncing');
    void saveSavedLessonPackage(nextPackage, nextPackage.source === 'compose' ? nextPackage.id : undefined)
      .then(() => setSyncStatus('synced'))
      .catch(() => setSyncStatus('error'));
  }, [activeFolderId, config, lessonPackage, project]);

  const openVersions = useCallback(async () => {
    if (!lessonPackage) return;
    setVersionPanelOpen(true);
    setVersionsLoading(true);
    try {
      setVersions(await listSavedHandoutVersions(lessonPackage.id));
    } catch {
      setVersions([]);
    } finally {
      setVersionsLoading(false);
    }
  }, [lessonPackage]);

  const handleRestoreVersion = useCallback(async (version: number) => {
    if (!lessonPackage || !window.confirm(`确定恢复第 ${version} 个版本吗？当前内容会保留为新版本。`)) return;
    try {
      const result = await restoreSavedHandoutVersion(lessonPackage.id, version);
      const restored = parseLessonPackage(result.lessonPackage);
      if (!restored) throw new Error('恢复版本内容无效');
      saveLessonPackageToLibrary(restored);
      setLessonPackage(restored);
      setProject(getOrCreateTeachingProject(restored));
      setActiveFolderId(restored.folderId || null);
      setVersionPanelOpen(false);
      setSyncStatus('synced');
    } catch {
      setSyncStatus('error');
    }
  }, [lessonPackage]);

  const togglePageBreak = useCallback((itemId: string) => {
    if (!project) return;
    const current = project.handout.pageBreakAfterBlockIds || [];
    const pageBreakAfterBlockIds = current.includes(itemId)
      ? current.filter((id) => id !== itemId)
      : [...current, itemId];
    const nextArtifact = {
      ...project.handout,
      pageBreakAfterBlockIds,
      sourceRevision: project.contentRevision,
      status: markHandoutEdited(project.handout.status),
      updatedAt: new Date().toISOString(),
    };
    saveHandoutArtifact(nextArtifact);
    setProject({ ...project, handout: nextArtifact });
  }, [project]);

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
    if (!window.confirm('删除文件夹后，其中的讲义会移动到“未分类”，确定继续吗？')) return;
    deleteLessonFolder(id);
    setFolders(listLessonFolders());
    setSavedPackages(listSavedLessonPackages());
    if (activeFolderId === id) setActiveFolderId(null);
  }, [activeFolderId]);

  const handleMovePackage = useCallback((id: string, folderId: string | null) => {
    moveSavedLessonPackage(id, folderId);
    setSavedPackages(listSavedLessonPackages());
  }, []);

  if (!lessonPackage || items.length === 0) {
    return (
      <EmptyState
        icon="📄"
        title="还没有可预览的讲义内容"
        description="先在组卷工作台里选择题目和知识点，系统会自动生成讲义结构。"
        action={{ label: '前往组卷工作台', onClick: () => navigate('/compose') }}
      />
    );
  }

  return (
    <div className="handout-print-page flex h-full bg-[var(--color-bg)]">
      <div className="handout-screen-only handout-sidebar">
      <LessonPackageTree
        packages={savedPackages}
        folders={folders}
        activeId={lessonPackage.id}
        activeFolderId={activeFolderId}
        title="讲义文件树"
        emptyText="保存一次后，这里会长期保留你的讲义作品。"
        onOpen={openSavedPackage}
        onDelete={handleDeleteSaved}
        onFolderSelect={setActiveFolderId}
        onCreateFolder={handleCreateFolder}
        onRenameFolder={handleRenameFolder}
        onDeleteFolder={handleDeleteFolder}
        onMovePackage={handleMovePackage}
        onSaveCurrent={handleSaveCurrent}
      />
      </div>

      <div className="handout-print-shell flex min-w-0 flex-1 flex-col">
        <div className="handout-screen-only handout-editor-toolbar border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => setPageBreakMode((prev) => !prev)}>{pageBreakMode ? '关闭分页设置' : '分页设置'}</Button>
            <div className="min-w-[220px] flex-1">
              <Input label="讲义标题" value={config.title} onChange={(event) => setConfig((prev) => ({ ...prev, title: event.target.value }))} placeholder="输入讲义标题" />
            </div>
            <div className="min-w-[190px] flex-1">
              <Input label="副标题" value={config.subtitle} onChange={(event) => setConfig((prev) => ({ ...prev, subtitle: event.target.value }))} placeholder="输入副标题" />
            </div>
            <div className="flex items-end gap-1">
              <button type="button" onClick={() => setConfig((prev) => ({ ...prev, showAnswers: false, showAnalysis: false }))} className={`h-7 rounded px-2.5 text-xs font-semibold ${!config.showAnswers && !config.showAnalysis ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'}`}>学生版</button>
              <button type="button" onClick={() => setConfig((prev) => ({ ...prev, showAnswers: true, showAnalysis: true }))} className={`h-7 rounded px-2.5 text-xs font-semibold ${config.showAnswers && config.showAnalysis ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'}`}>教师版</button>
              <Button variant="secondary" size="sm" onClick={() => setPreflightMode((prev) => !prev)}>{preflightMode ? '返回预览' : '打印检查'}</Button>
              <Button variant="ghost" size="sm" onClick={() => setStylePanelOpen((prev) => !prev)}>排版设置</Button>
              <Button variant="outline" size="sm" onClick={handleSaveCurrent}>保存</Button>
              <Button size="sm" onClick={handlePublish}>
                {project?.handout.status === 'published' ? '重新发布' : project?.handout.status === 'changed_after_publish' ? '重新发布' : '发布版本'}
              </Button>
              <Button variant="ghost" size="sm" onClick={() => void openVersions()}>版本</Button>
              <Button variant="secondary" size="sm" onClick={() => void handleWordPreview()} disabled={wordPreviewLoading}>{wordPreviewLoading ? '生成中…' : 'Word预览'}</Button>
              <Button size="sm" onClick={handlePrint}>打印 / PDF</Button>
              <span className={`text-[11px] ${syncStatus === 'error' ? 'text-[var(--color-danger)]' : syncStatus === 'syncing' ? 'text-[var(--color-orange)]' : 'text-[var(--color-text-subtle)]'}`}>
                {syncStatus === 'syncing' ? '正在同步…' : syncStatus === 'error' ? '同步失败，可重试' : syncStatus === 'synced' ? '已同步' : ''}
              </span>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--color-border)] pt-2">
            <div className="flex flex-wrap gap-1.5 text-[11px] text-[var(--color-text-muted)]">
              <PreviewPill label={renderedPageCount ? '实际分页' : '正在计算'} value={renderedPageCount ? `${renderedPageCount} 页` : '…'} />
              <PreviewPill label="题目" value={`${questionCount} 题`} />
              <PreviewPill label="知识点" value={`${knowledgeCount} 个`} />
              <PreviewPill label="预估" value={`${pageCount} 页`} />
              <PreviewPill label="状态" value={handoutStatusLabel(project?.handout.status)} tone={project?.handout.status === 'changed_after_publish' || project?.handout.status === 'stale' ? 'warning' : undefined} />
              {paginationReport.nearCapacityPageCount > 0 && <PreviewPill label="接近满页" value={`${paginationReport.nearCapacityPageCount} 页`} tone="warning" />}
            </div>
            <div className="flex items-center gap-1">
              <button type="button" onClick={() => setPreviewZoom((value) => Math.max(55, value - 10))} className="h-6 w-6 rounded bg-[var(--color-bg-hover)] text-xs text-[var(--color-text-secondary)]" title="缩小">−</button>
              <button type="button" onClick={() => setPreviewZoom(82)} className="h-6 min-w-10 rounded px-1 text-[11px] font-semibold tabular-nums text-[var(--color-text-secondary)]">{previewZoom}%</button>
              <button type="button" onClick={() => setPreviewZoom((value) => Math.min(115, value + 10))} className="h-6 w-6 rounded bg-[var(--color-bg-hover)] text-xs text-[var(--color-text-secondary)]" title="放大">+</button>
            </div>
          </div>
        </div>

        <div className="handout-print-surface min-h-0 flex-1 overflow-auto bg-[var(--color-bg-hover)] px-5 py-5">
          <div className="mx-auto w-max min-w-full">
            <div className="handout-screen-only mb-3 flex items-center justify-center gap-2 text-[11px] text-[var(--color-text-subtle)]">
              <span>{config.showAnswers || config.showAnalysis ? '教师版讲义' : '学生版讲义'}</span>
              <span>·</span>
              <span>{lessonPackage.source === 'compose' ? '组卷工作台生成' : '当前教学包'}</span>
            </div>
            <div style={{ zoom: previewZoom / 100 } as CSSProperties}>
              <PagedHandoutDocument
                items={items}
                config={config}
                onReady={printPreparing ? handlePagedPrintReady : handlePagedPreviewReady}
              />
            </div>
          </div>
        </div>
      </div>

      {versionPanelOpen && (
        <div className="fixed right-5 top-20 z-30 w-[320px] rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4 shadow-xl">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-[var(--color-text)]">版本历史</h2>
              <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">恢复后会生成一个新的当前版本。</p>
            </div>
            <button type="button" className="text-xs text-[var(--color-text-muted)]" onClick={() => setVersionPanelOpen(false)}>关闭</button>
          </div>
          <div className="mt-3 max-h-64 space-y-1.5 overflow-auto">
            {versionsLoading && <div className="py-4 text-center text-xs text-[var(--color-text-muted)]">正在读取版本…</div>}
            {!versionsLoading && versions.length === 0 && <div className="py-4 text-center text-xs text-[var(--color-text-muted)]">暂无服务端版本</div>}
            {!versionsLoading && versions.map((item) => {
              const version = Number(item.version);
              const current = Boolean(item.current);
              return (
                <div key={`${version}-${String(item.version_id || '')}`} className="flex items-center gap-2 rounded-lg border border-[var(--color-border)] px-2.5 py-2">
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-semibold text-[var(--color-text)]">第 {version} 版 {current && <span className="ml-1 text-[var(--color-accent)]">当前</span>}</div>
                    <div className="mt-0.5 truncate text-[10px] text-[var(--color-text-muted)]">{String(item.title || '')}</div>
                  </div>
                  {!current && <button type="button" className="shrink-0 rounded bg-[var(--color-bg-hover)] px-2 py-1 text-[10px] text-[var(--color-text-secondary)]" onClick={() => void handleRestoreVersion(version)}>恢复</button>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {stylePanelOpen && (
        <div className="handout-screen-only fixed inset-y-0 right-0 z-40 w-[min(380px,92vw)] overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-bg-card)] p-4 shadow-xl lg:static lg:z-auto lg:h-full lg:w-[360px] lg:shrink-0 lg:rounded-none lg:border-y-0 lg:border-r-0 lg:shadow-none">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-[var(--color-text)]">打印排版设置</h2>
              <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">设置会立即作用于当前讲义预览和打印。</p>
            </div>
            <button type="button" className="text-xs text-[var(--color-text-muted)]" onClick={() => setStylePanelOpen(false)}>关闭</button>
          </div>
          <HandoutStylePresetPanel
            currentConfig={config.styleConfig}
            onApplyConfig={(styleConfig) => setConfig((current) => ({ ...current, styleConfig: { ...DEFAULT_STYLE_CONFIG, ...styleConfig } }))}
          />
          <div className="mt-4 border-t border-[var(--color-border)] pt-4">
            <HandoutHeaderFooterConfigPanel
              config={config.headerFooter}
              onChange={(headerFooter) => setConfig((current) => ({ ...current, headerFooter: { ...DEFAULT_HF_CONFIG, ...headerFooter } }))}
            />
          </div>
        </div>
      )}

      {preflightMode && (
        <PrintPreflightPanel
          config={config}
          pageCount={pageCount}
          questionCount={questionCount}
          risks={risks}
          sparsePageCount={paginationReport.sparsePageCount}
          oversizedItemCount={paginationReport.oversizedItemCount}
          onPrint={handlePrint}
          onBack={() => setPreflightMode(false)}
        />
      )}

      {pageBreakMode && (
        <aside className="w-[320px] border-l border-[var(--color-border)] bg-[var(--color-bg-card)]">
          <div className="border-b border-[var(--color-border)] px-4 py-3">
            <h2 className="text-sm font-semibold text-[var(--color-text)]">讲义分页设置</h2>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">只影响当前讲义，不会改变组卷内容和课件顺序。</p>
          </div>
          <div className="max-h-full overflow-auto p-3">
            <div className="space-y-1.5">
              {items.filter((item) => item.type !== 'page_break').map((item, index) => {
                const itemId = item.id || `item-${index}`;
                const active = project?.handout.pageBreakAfterBlockIds?.includes(itemId) || false;
                const label = item.type === 'question'
                  ? item.question?.title || `题目 ${index + 1}`
                  : item.title || (item.type === 'knowledge' ? '知识讲解' : '教学文本');
                return (
                  <div key={itemId} className="flex items-center gap-2 rounded border border-[var(--color-border)] px-2.5 py-2">
                    <span className="min-w-0 flex-1 truncate text-xs text-[var(--color-text-secondary)]">{index + 1}. {label}</span>
                    <button type="button" onClick={() => togglePageBreak(itemId)} className={`rounded px-2 py-1 text-[11px] font-semibold ${active ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'}`}>
                      {active ? '已分页' : '此处分'}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        </aside>
      )}

      {wordPreviewFile && <DocumentPreviewModal file={wordPreviewFile} onClose={() => setWordPreviewFile(null)} />}
    </div>
  );
}

function PreviewPill({ label, value, tone }: { label: string; value: string; tone?: 'warning' }) {
  return (
    <span className={`rounded border px-2 py-1 ${tone === 'warning' ? 'border-[var(--color-orange)]/30 bg-[var(--color-orange-light)] text-[var(--color-orange)]' : 'border-[var(--color-border)] bg-[var(--color-bg-hover)]'}`}>
      {label} <b className="ml-0.5 text-[var(--color-text-secondary)]">{value}</b>
    </span>
  );
}
