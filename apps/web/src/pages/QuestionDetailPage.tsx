import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import {
  fetchQuestion,
  fetchQuestionImages,
  fetchQuestionKnowledgePoints,
  fetchQuestionVersionDetail,
  fetchQuestionVersions,
  fetchSimilarQuestions,
  deleteQuestionImage,
  markMistake,
  rollbackQuestionVersion,
  unmarkMistake,
  updateQuestionImage,
  updateQuestion,
} from '../services/api';
import AnnotationPanel from '../components/question/AnnotationPanel';
import AnswerAnalysisCard from '../components/question/AnswerAnalysisCard';
import QuestionContentCard from '../components/question/QuestionContentCard';
import type {
  KnowledgePoint,
  Question,
  QuestionImageDetail,
  QuestionVersionDetail,
  QuestionVersionSummary,
  SimilarQuestionItem,
} from '../types';
import { extractErrorMessage } from '../utils/error';
import { imageFileUrl } from '../utils/imageUrl';

const TYPE_OPTIONS = [
  { value: 'single_choice', label: '单选题' },
  { value: 'multi_choice', label: '多选题' },
  { value: 'fill', label: '填空题' },
  { value: 'experiment', label: '实验题' },
  { value: 'calculation', label: '计算题' },
] as const;

const TYPE_LABELS: Record<string, string> = Object.fromEntries(
  TYPE_OPTIONS.map((item) => [item.value, item.label]),
);

const DIFFICULTY_OPTIONS = [1, 2, 3, 4, 5] as const;

function isDirty(a: unknown, b: unknown): boolean {
  if (typeof a === 'number' && typeof b === 'number') return a !== b;
  return String(a ?? '') !== String(b ?? '');
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function normalizeStatusLabel(status?: string): string {
  if (!status) return '待处理';
  if (status.includes('审核') || status.includes('已审')) return '已审核';
  if (status.includes('入库')) return '已入库';
  if (status.includes('草稿')) return '草稿';
  return status;
}

function getStatusTone(status: string): { background: string; color: string } {
  if (status === '已审核' || status === '已入库') {
    return { background: '#dcfce7', color: '#15803d' };
  }
  if (status === '草稿') {
    return { background: '#fef3c7', color: '#b45309' };
  }
  return { background: '#dbeafe', color: '#1d4ed8' };
}

export default function QuestionDetailPage() {
  const { questionId } = useParams<{ questionId: string }>();
  const navigate = useNavigate();
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [question, setQuestion] = useState<Question | null>(null);
  const [questionImages, setQuestionImages] = useState<QuestionImageDetail[]>([]);
  const [knowledgePoints, setKnowledgePoints] = useState<KnowledgePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [form, setForm] = useState<Partial<Question>>({});
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [mistakeMarking, setMistakeMarking] = useState(false);
  const [imageMessage, setImageMessage] = useState<string | null>(null);

  const [showVersions, setShowVersions] = useState(false);
  const [versions, setVersions] = useState<QuestionVersionSummary[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState<QuestionVersionDetail | null>(null);
  const [rollbackVersionId, setRollbackVersionId] = useState<string | null>(null);
  const [rollbackConfirm, setRollbackConfirm] = useState(false);
  const [rollbackMsg, setRollbackMsg] = useState<string | null>(null);

  const [similarQuestions, setSimilarQuestions] = useState<SimilarQuestionItem[]>([]);
  const [similarLoading, setSimilarLoading] = useState(false);
  const [similarError, setSimilarError] = useState<string | null>(null);

  const dirtyFields = useMemo(() => {
    if (!question) return new Set<string>();
    const dirty = new Set<string>();
    const fields: (keyof Question)[] = [
      'title',
      'question_type',
      'difficulty',
      'year',
      'source',
      'answer',
      'analysis',
      'tags',
      'model_type',
      'knowledge_point',
    ];

    for (const field of fields) {
      if (isDirty(form[field], question[field])) dirty.add(field);
    }
    return dirty;
  }, [form, question]);

  const hasChanges = dirtyFields.size > 0;

  const loadVersions = useCallback(async () => {
    if (!questionId) return;
    setVersionsLoading(true);
    try {
      const data = await fetchQuestionVersions(questionId);
      setVersions(data);
    } catch {
      setVersions([]);
    } finally {
      setVersionsLoading(false);
    }
  }, [questionId]);

  const handleToggleVersions = useCallback(async () => {
    const next = !showVersions;
    setShowVersions(next);
    setSelectedVersion(null);
    setRollbackConfirm(false);
    setRollbackMsg(null);
    if (next) {
      await loadVersions();
    }
  }, [loadVersions, showVersions]);

  const handleViewVersion = useCallback(async (versionId: string) => {
    if (!questionId) return;
    try {
      const detail = await fetchQuestionVersionDetail(questionId, versionId);
      setSelectedVersion(detail);
      setRollbackVersionId(versionId);
    } catch {
      setSelectedVersion(null);
    }
  }, [questionId]);

  const handleRollback = useCallback(async () => {
    if (!questionId || !rollbackVersionId) return;
    try {
      const result = await rollbackQuestionVersion(questionId, rollbackVersionId);
      setRollbackMsg(result.message || '回退成功');
      setRollbackConfirm(false);
      const refreshed = await fetchQuestion(questionId);
      setQuestion(refreshed);
      setForm(refreshed);
      await loadVersions();
    } catch (err: unknown) {
      setRollbackMsg(`回退失败：${extractErrorMessage(err, '未知错误')}`);
    }
  }, [loadVersions, questionId, rollbackVersionId]);

  useEffect(() => {
    if (!questionId) return;
    let cancelled = false;
    setSimilarLoading(true);
    setSimilarError(null);

    fetchSimilarQuestions(questionId, 10)
      .then((response) => {
        if (!cancelled) {
          setSimilarQuestions(response.items ?? []);
          setSimilarLoading(false);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setSimilarError(err.message || '加载失败');
          setSimilarLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [questionId]);

  useEffect(() => {
    if (!questionId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      fetchQuestion(questionId).catch(() => null),
      fetchQuestionKnowledgePoints(questionId).catch(() => []),
      fetchQuestionImages(questionId).then((result) => result.images).catch(() => []),
    ]).then(([questionData, knowledgeData, imageData]) => {
      if (cancelled) return;
      if (!questionData) {
        setError('题目不存在或加载失败');
        setLoading(false);
        return;
      }
      setQuestion(questionData as Question);
      setQuestionImages(imageData as QuestionImageDetail[]);
      setKnowledgePoints(knowledgeData as KnowledgePoint[]);
      setForm(questionData as Question);
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, [questionId]);

  const handleToggleMistake = useCallback(async () => {
    if (!questionId || !question) return;
    setMistakeMarking(true);
    try {
      if (question.is_mistake) {
        await unmarkMistake(questionId);
      } else {
        await markMistake(questionId);
      }
      setQuestion((prev) => (prev ? { ...prev, is_mistake: !prev.is_mistake } : prev));
    } catch (err: unknown) {
      alert(`错题标记失败：${extractErrorMessage(err, '操作失败')}`);
    } finally {
      setMistakeMarking(false);
    }
  }, [question, questionId]);

  const updateField = useCallback((field: string, value: unknown) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setSaveState('idle');
  }, []);

  const addTag = useCallback((tag: string) => {
    const nextTag = tag.trim();
    if (!nextTag) return;
    setForm((prev) => {
      const existing = (prev.tags as string[]) || [];
      if (existing.includes(nextTag)) return prev;
      return { ...prev, tags: [...existing, nextTag] };
    });
    setSaveState('idle');
  }, []);

  const removeTag = useCallback((tag: string) => {
    setForm((prev) => ({
      ...prev,
      tags: ((prev.tags as string[]) || []).filter((item) => item !== tag),
    }));
    setSaveState('idle');
  }, []);

  const handleImageRoleChange = useCallback(async (assetId: string, role: string) => {
    if (!questionId) return;
    setImageMessage(null);
    try {
      await updateQuestionImage(questionId, assetId, { role });
      setQuestionImages((prev) => prev.map((img) => (img.asset_id === assetId ? { ...img, role } : img)));
      setImageMessage('图片信息已更新');
    } catch (err: unknown) {
      setImageMessage(extractErrorMessage(err, '图片更新失败'));
    }
  }, [questionId]);

  const handleImageDelete = useCallback(async (assetId: string, placeholderKey?: string | null) => {
    if (!questionId) return;
    if (!window.confirm('确定从本题移除这张图片吗？素材文件不会被删除。')) return;
    setImageMessage(null);
    try {
      await deleteQuestionImage(questionId, assetId);
      setQuestionImages((prev) => prev.filter((img) => img.asset_id !== assetId));
      const refs = [placeholderKey, assetId].filter(Boolean) as string[];
      if (refs.length > 0) {
        setForm((prev) => {
          const currentTitle = String(prev.title ?? question?.title ?? '');
          const nextTitle = refs.reduce(
            (text, ref) => text.replace(new RegExp(`!\\[fig:${escapeRegExp(ref)}\\]`, 'g'), ''),
            currentTitle,
          ).replace(/\n{3,}/g, '\n\n').trim();
          return nextTitle === currentTitle ? prev : { ...prev, title: nextTitle };
        });
      }
      setSaveState('idle');
      setImageMessage('图片已从本题移除');
    } catch (err: unknown) {
      setImageMessage(extractErrorMessage(err, '图片删除失败'));
    }
  }, [question?.title, questionId]);

  const validate = useCallback((): string | null => {
    if (!form.title || !String(form.title).trim()) return '题干不能为空';
    const qt = form.question_type;
    if (qt && !TYPE_OPTIONS.some((option) => option.value === qt)) return `题型不合法：${qt}`;
    const difficulty = form.difficulty;
    if (difficulty != null && (typeof difficulty !== 'number' || difficulty < 1 || difficulty > 5)) {
      return '难度必须在 1 到 5 之间';
    }
    return null;
  }, [form]);

  const handleSave = useCallback(async () => {
    if (!questionId) return;
    const validationError = validate();
    if (validationError) {
      setSaveError(validationError);
      setSaveState('error');
      return;
    }

    setSaveState('saving');
    setSaveError(null);

    try {
      const updated = await updateQuestion(questionId, form);
      setQuestion(updated);
      setForm(updated);
      setEditMode(false);
      setSaveState('saved');
      window.dispatchEvent(
        new CustomEvent('physics-vault-question-updated', {
          detail: { questionId, updated },
        }),
      );
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => setSaveState('idle'), 2500);
    } catch (err: unknown) {
      setSaveError(extractErrorMessage(err, '保存失败'));
      setSaveState('error');
    }
  }, [form, questionId, validate]);

  const handleCancel = useCallback(() => {
    setEditMode(false);
    if (question) setForm({ ...question });
    setSaveState('idle');
    setSaveError(null);
  }, [question]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 's') {
        event.preventDefault();
        if (editMode) handleSave();
      }
      if (event.key === 'Escape' && editMode) {
        event.preventDefault();
        handleCancel();
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [editMode, handleCancel, handleSave]);

  useEffect(() => () => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
  }, []);

  if (loading) {
    return (
      <div className="space-y-4 p-6">
        <div className="animate-pulse space-y-3">
          <div className="h-6 w-48 rounded" style={{ background: 'var(--color-border)' }} />
          <div className="h-32 rounded" style={{ background: 'var(--color-border)' }} />
          <div className="h-20 rounded" style={{ background: 'var(--color-border)' }} />
        </div>
      </div>
    );
  }

  if (error || !question) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="text-center">
          <div className="mb-3 text-4xl">×</div>
          <p style={{ color: 'var(--color-red)' }}>{error || '题目未找到'}</p>
          <button
            onClick={() => navigate('/browse')}
            className="mt-3 cursor-pointer rounded-full border-none px-4 py-2 text-sm text-white"
            style={{ background: '#2f76dd' }}
          >
            返回题库
          </button>
        </div>
      </div>
    );
  }

  const currentQuestion = editMode ? form : question;
  const previewQuestion = {
    ...question,
    ...form,
    options: (form.options as Question['options'] | undefined) ?? question.options,
    sub_questions: (form.sub_questions as Question['sub_questions'] | undefined) ?? question.sub_questions,
    figures: question.figures || [],
    tags: (form.tags as string[] | undefined) ?? question.tags ?? [],
    question_type: (form.question_type as Question['question_type'] | undefined) ?? question.question_type,
    difficulty: Number(form.difficulty ?? question.difficulty ?? 0),
    title: String(form.title ?? question.title ?? ''),
    answer: String(form.answer ?? question.answer ?? ''),
    analysis: String(form.analysis ?? question.analysis ?? ''),
    source: String(form.source ?? question.source ?? ''),
    knowledge_point: String(form.knowledge_point ?? question.knowledge_point ?? ''),
  } as Question;
  const statusLabel = normalizeStatusLabel(currentQuestion.status as string | undefined);
  const statusTone = getStatusTone(statusLabel);

  return (
    <div className="flex h-full bg-[#eef3f8]">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1380px] px-6 py-6">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <button
                onClick={() => navigate('/browse')}
                className="cursor-pointer rounded-full px-3 py-1.5 text-sm font-medium"
                style={{ background: '#ffffff', color: '#64748b', border: '1px solid #dbe5f0' }}
              >
                返回
              </button>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="truncate text-[28px] font-bold" style={{ color: '#0f172a' }}>
                    题目详情 · {question.question_id}
                  </h1>
                  <span
                    className="rounded-full px-3 py-1 text-xs font-semibold"
                    style={{ background: statusTone.background, color: statusTone.color }}
                  >
                    {statusLabel}
                  </span>
                  {saveState === 'saved' && (
                    <span className="rounded-full px-3 py-1 text-xs font-semibold" style={{ background: '#dcfce7', color: '#15803d' }}>
                      已保存
                    </span>
                  )}
                  {saveState === 'saving' && (
                    <span className="rounded-full px-3 py-1 text-xs font-semibold" style={{ background: '#dbeafe', color: '#1d4ed8' }}>
                      保存中…
                    </span>
                  )}
                  {saveState === 'error' && (
                    <span className="rounded-full px-3 py-1 text-xs font-semibold" style={{ background: '#fee2e2', color: '#dc2626' }}>
                      保存失败
                    </span>
                  )}
                  {editMode && hasChanges && saveState === 'idle' && (
                    <span className="rounded-full px-3 py-1 text-xs font-semibold" style={{ background: '#fef3c7', color: '#b45309' }}>
                      未保存 {dirtyFields.size} 项
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm" style={{ color: '#94a3b8' }}>
                  更接近阅读页的展示风格，题目与解析分区更清晰
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={handleToggleMistake}
                disabled={mistakeMarking}
                className="cursor-pointer rounded-full border px-4 py-2 text-sm font-medium disabled:opacity-50"
                style={{
                  background: question.is_mistake ? '#fee2e2' : '#ffffff',
                  color: question.is_mistake ? '#dc2626' : '#475569',
                  borderColor: question.is_mistake ? '#fca5a5' : '#dbe5f0',
                }}
              >
                {mistakeMarking ? '处理中…' : question.is_mistake ? '取消错题' : '标记为错题'}
              </button>
              <button
                onClick={() => setEditMode(!editMode)}
                className="cursor-pointer rounded-full border px-4 py-2 text-sm font-medium"
                style={{
                  background: editMode ? '#16a34a' : '#ffffff',
                  color: editMode ? '#ffffff' : '#2f76dd',
                  borderColor: editMode ? '#16a34a' : '#93c5fd',
                }}
              >
                {editMode ? '编辑中' : '编辑'}
              </button>
              <button
                onClick={handleToggleVersions}
                className="cursor-pointer rounded-full border px-4 py-2 text-sm font-medium"
                style={{
                  background: showVersions ? '#2f76dd' : '#ffffff',
                  color: showVersions ? '#ffffff' : '#475569',
                  borderColor: showVersions ? '#2f76dd' : '#dbe5f0',
                }}
              >
                历史版本
              </button>
            </div>
          </div>

          {showVersions && (
            <div
              className="mb-5 rounded-[24px] border p-5"
              style={{
                borderColor: 'rgba(148, 163, 184, 0.18)',
                background: '#ffffff',
                boxShadow: '0 18px 40px rgba(15, 23, 42, 0.06)',
              }}
            >
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-base font-semibold" style={{ color: '#0f172a' }}>
                  历史版本
                </h3>
                <button
                  onClick={handleToggleVersions}
                  className="cursor-pointer rounded-full border px-3 py-1 text-xs"
                  style={{ borderColor: '#dbe5f0', color: '#64748b', background: '#ffffff' }}
                >
                  关闭
                </button>
              </div>

              {versionsLoading ? (
                <div className="text-sm" style={{ color: '#94a3b8' }}>加载中…</div>
              ) : versions.length === 0 ? (
                <div className="text-sm" style={{ color: '#94a3b8' }}>暂无历史版本记录</div>
              ) : (
                <div className="flex gap-4">
                  <div className="max-h-72 w-64 flex-shrink-0 space-y-2 overflow-y-auto pr-1">
                    {versions.map((version) => (
                      <button
                        key={version.version_id}
                        onClick={() => handleViewVersion(version.version_id)}
                        className="w-full cursor-pointer rounded-[18px] border px-3 py-3 text-left"
                        style={{
                          borderColor: selectedVersion?.version_id === version.version_id ? '#93c5fd' : '#e2e8f0',
                          background: selectedVersion?.version_id === version.version_id ? '#eff6ff' : '#ffffff',
                        }}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-semibold" style={{ color: '#0f172a' }}>
                            v{version.version_number}
                          </span>
                          <span
                            className="rounded-full px-2 py-0.5 text-[11px]"
                            style={{
                              background: version.source === 'auto' ? '#f1f5f9' : '#dbeafe',
                              color: version.source === 'auto' ? '#64748b' : '#1d4ed8',
                            }}
                          >
                            {version.source === 'auto' ? '自动' : '人工'}
                          </span>
                        </div>
                        <div className="mt-1 truncate text-xs" style={{ color: '#64748b' }}>
                          {version.change_summary || '内容更新'}
                        </div>
                        <div className="mt-1 text-[11px]" style={{ color: '#94a3b8' }}>
                          {new Date(version.created_at).toLocaleString('zh-CN')}
                        </div>
                      </button>
                    ))}
                  </div>

                  <div className="min-w-0 flex-1">
                    {selectedVersion ? (
                      <div className="space-y-4 text-sm">
                        <div>
                          <span style={{ color: '#94a3b8' }}>版本 </span>
                          <span className="font-semibold" style={{ color: '#0f172a' }}>
                            v{selectedVersion.version_number}
                          </span>
                          <span className="ml-2 text-xs" style={{ color: '#94a3b8' }}>
                            {new Date(selectedVersion.created_at).toLocaleString('zh-CN')}
                          </span>
                        </div>

                        <div className="grid gap-3 lg:grid-cols-3">
                          {(['stem_text', 'answer', 'analysis'] as const).map((key) => {
                            const value = selectedVersion.snapshot?.[key];
                            if (value == null) return null;
                            const label = key === 'stem_text' ? '题干' : key === 'answer' ? '答案' : '解析';
                            const text = String(value).slice(0, 240);
                            return (
                              <div key={key} className="rounded-[18px] border p-3" style={{ borderColor: '#e2e8f0', background: '#fbfdff' }}>
                                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: '#94a3b8' }}>
                                  {label}
                                </div>
                                <div className="max-h-28 overflow-y-auto whitespace-pre-wrap text-sm leading-6" style={{ color: '#334155' }}>
                                  {text}
                                  {String(value).length > 240 ? '…' : ''}
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        <div className="flex flex-wrap gap-4 text-sm" style={{ color: '#475569' }}>
                          {selectedVersion.snapshot?.difficulty != null && <span>难度：{String(selectedVersion.snapshot.difficulty)}</span>}
                          {selectedVersion.snapshot?.knowledge_point != null && <span>知识点：{String(selectedVersion.snapshot.knowledge_point)}</span>}
                        </div>

                        {!rollbackConfirm ? (
                          <button
                            onClick={() => {
                              setRollbackVersionId(selectedVersion.version_id);
                              setRollbackConfirm(true);
                              setRollbackMsg(null);
                            }}
                            className="cursor-pointer rounded-full border px-4 py-2 text-sm font-medium"
                            style={{ borderColor: '#fca5a5', color: '#dc2626', background: '#ffffff' }}
                          >
                            回退到此版本
                          </button>
                        ) : (
                          <div className="rounded-[18px] border p-4" style={{ borderColor: '#fecaca', background: '#fef2f2' }}>
                            <p className="text-sm font-medium" style={{ color: '#b91c1c' }}>
                              确认回退到版本 v{selectedVersion.version_number}？回退后会生成一条新的历史记录。
                            </p>
                            <div className="mt-3 flex gap-2">
                              <button
                                onClick={handleRollback}
                                className="cursor-pointer rounded-full border-none px-4 py-2 text-sm font-medium text-white"
                                style={{ background: '#dc2626' }}
                              >
                                确认回退
                              </button>
                              <button
                                onClick={() => {
                                  setRollbackConfirm(false);
                                  setRollbackMsg(null);
                                }}
                                className="cursor-pointer rounded-full border px-4 py-2 text-sm"
                                style={{ borderColor: '#dbe5f0', color: '#64748b', background: '#ffffff' }}
                              >
                                取消
                              </button>
                            </div>
                          </div>
                        )}

                        {rollbackMsg && (
                          <div className="rounded-[16px] px-4 py-3 text-sm" style={{ background: '#dcfce7', color: '#15803d' }}>
                            {rollbackMsg}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-sm" style={{ color: '#94a3b8' }}>
                        选择左侧版本查看详情
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {saveError && (
            <div className="mb-4 rounded-[18px] border px-4 py-3 text-sm" style={{ borderColor: '#fecaca', background: '#fef2f2', color: '#dc2626' }}>
              {saveError}
            </div>
          )}

          {!editMode && (
            <section
              className="mb-5 rounded-[16px] border px-5 py-4"
              style={{
                borderColor: 'rgba(148, 163, 184, 0.22)',
                background: '#ffffff',
                boxShadow: '0 10px 24px rgba(15, 23, 42, 0.05)',
              }}
            >
              <div className="mb-3 flex items-center gap-2">
                <span className="rounded-md px-2.5 py-1 text-xs font-semibold" style={{ background: '#f1f5f9', color: '#475569' }}>
                  基本信息
                </span>
              </div>
              <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
                <MetaChip label="题号" value={question.question_id} />
                <MetaChip
                  label="题型"
                  value={TYPE_LABELS[currentQuestion.question_type || ''] || currentQuestion.question_type || '-'}
                />
                <MetaChip
                  label="难度"
                  value={currentQuestion.difficulty ? '★'.repeat(currentQuestion.difficulty as number) : '-'}
                />
                <MetaChip label="来源" value={currentQuestion.source || '-'} />
                <MetaChip label="年份" value={currentQuestion.year ? String(currentQuestion.year) : '-'} />
                <MetaChip label="物理模型" value={question.model_type || '-'} />
              </div>
            </section>
          )}

          {editMode ? (
            <SimpleQuestionEditWorkspace
              question={previewQuestion}
              images={questionImages}
              dirtyFields={dirtyFields}
              imageMessage={imageMessage}
              onUpdateField={updateField}
              onAddTag={addTag}
              onRemoveTag={removeTag}
              onImageRoleChange={handleImageRoleChange}
              onImageDelete={handleImageDelete}
            />
          ) : (
            <>
              <QuestionContentCard
                question={question}
                editMode={false}
                images={questionImages}
              />

              <AnswerAnalysisCard
                question={question}
                editMode={false}
              />

              <div className="mb-5 grid gap-5 xl:grid-cols-2">
                <section
                  className="rounded-[24px] border px-6 py-5"
                  style={{
                    borderColor: 'rgba(148, 163, 184, 0.18)',
                    background: '#ffffff',
                    boxShadow: '0 18px 40px rgba(15, 23, 42, 0.06)',
                  }}
                >
                  <div className="mb-3 flex items-center gap-2">
                    <span className="rounded-full px-3 py-1 text-xs font-semibold" style={{ background: '#f1f5f9', color: '#475569' }}>
                      标签
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(currentQuestion.tags || []).map((tag, index) => (
                      <span
                        key={`${tag}-${index}`}
                        className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-sm"
                        style={{ background: '#f8fafc', color: '#475569' }}
                      >
                        {tag}
                      </span>
                    ))}
                    {(currentQuestion.tags || []).length === 0 && (
                      <span className="text-sm" style={{ color: '#94a3b8' }}>
                        暂无标签
                      </span>
                    )}
                  </div>
                </section>

                <section
                  className="rounded-[24px] border px-6 py-5"
                  style={{
                    borderColor: 'rgba(148, 163, 184, 0.18)',
                    background: '#ffffff',
                    boxShadow: '0 18px 40px rgba(15, 23, 42, 0.06)',
                  }}
                >
                  <div className="mb-3 flex items-center gap-2">
                    <span className="rounded-full px-3 py-1 text-xs font-semibold" style={{ background: '#eff6ff', color: '#2563eb' }}>
                      知识点
                    </span>
                  </div>
                  {knowledgePoints.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {knowledgePoints.map((point) => (
                        <span
                          key={point.rank}
                          className="rounded-full px-3 py-1 text-sm"
                          style={{ background: '#eef4ff', color: '#2f76dd' }}
                        >
                          {point.topic3_name || point.topic2_name || point.topic1_name}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-sm" style={{ color: '#94a3b8' }}>
                      暂无知识点标注
                    </span>
                  )}
                </section>
              </div>
            </>
          )}

          <section
            className="rounded-[24px] border px-6 py-5"
            style={{
              borderColor: 'rgba(148, 163, 184, 0.18)',
              background: '#ffffff',
              boxShadow: '0 18px 40px rgba(15, 23, 42, 0.06)',
            }}
          >
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="rounded-full px-3 py-1 text-xs font-semibold" style={{ background: '#f8fafc', color: '#475569' }}>
                  相似题
                </span>
                {!similarLoading && similarQuestions.length > 0 && (
                  <span className="text-xs" style={{ color: '#94a3b8' }}>
                    共 {similarQuestions.length} 条
                  </span>
                )}
              </div>
            </div>

            {similarLoading && (
              <div className="space-y-3">
                {[1, 2, 3].map((item) => (
                  <div
                    key={item}
                    className="animate-pulse rounded-[18px] border p-4"
                    style={{ borderColor: '#e2e8f0', background: '#fbfdff' }}
                  >
                    <div className="mb-2 h-4 w-3/4 rounded" style={{ background: '#e2e8f0' }} />
                    <div className="flex gap-3">
                      <div className="h-3 w-12 rounded" style={{ background: '#e2e8f0' }} />
                      <div className="h-3 w-10 rounded" style={{ background: '#e2e8f0' }} />
                      <div className="h-3 w-20 rounded" style={{ background: '#e2e8f0' }} />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!similarLoading && similarError && (
              <div className="rounded-[18px] border p-5 text-center" style={{ borderColor: '#e2e8f0', background: '#fbfdff' }}>
                <p className="text-sm font-medium" style={{ color: '#475569' }}>
                  相似题暂时无法加载
                </p>
                <p className="mt-1 text-xs" style={{ color: '#94a3b8' }}>
                  请稍后重试
                </p>
              </div>
            )}

            {!similarLoading && !similarError && similarQuestions.length === 0 && (
              <div className="rounded-[18px] border p-5 text-center" style={{ borderColor: '#e2e8f0', background: '#fbfdff' }}>
                <p className="text-sm" style={{ color: '#94a3b8' }}>
                  暂无相似题
                </p>
              </div>
            )}

            {!similarLoading && similarQuestions.length > 0 && (
              <div className="space-y-3">
                {similarQuestions.map((item) => {
                  const score = Math.round((item.similarity_score ?? 0) * 100) / 100;
                  const scorePercent = item.similarity_score != null
                    ? `${Math.round(score * (score <= 1 ? 100 : 1))}%`
                    : null;

                  return (
                    <button
                      key={item.question_id}
                      onClick={() => navigate(`/question/${item.question_id}`)}
                      className="w-full cursor-pointer rounded-[18px] border p-4 text-left transition-colors"
                      style={{ borderColor: '#e2e8f0', background: '#ffffff' }}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = '#93c5fd'; }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = '#e2e8f0'; }}
                    >
                      <div className="mb-2 flex items-start justify-between gap-3">
                        <span className="line-clamp-2 text-sm font-medium leading-7" style={{ color: '#0f172a' }}>
                          {item.title || item.question_id}
                        </span>
                        {scorePercent && (
                          <span
                            className="rounded-full px-2.5 py-1 text-[11px] font-semibold tabular-nums"
                            style={{
                              background: score >= 0.7 ? '#dcfce7' : score >= 0.4 ? '#dbeafe' : '#f1f5f9',
                              color: score >= 0.7 ? '#15803d' : score >= 0.4 ? '#1d4ed8' : '#64748b',
                            }}
                          >
                            {scorePercent}
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color: '#64748b' }}>
                        {item.question_type && (
                          <span className="rounded-full px-2 py-0.5" style={{ background: '#f8fafc' }}>
                            {TYPE_LABELS[item.question_type] || item.question_type}
                          </span>
                        )}
                        {item.difficulty != null && (
                          <span className="rounded-full px-2 py-0.5" style={{ background: '#f8fafc' }}>
                            {'★'.repeat(Math.max(1, Math.min(5, Number(item.difficulty) || 1)))}
                          </span>
                        )}
                        {item.module && (
                          <span className="rounded-full px-2 py-0.5" style={{ background: '#f8fafc' }}>
                            {item.module}
                          </span>
                        )}
                        {item.topic3 && (
                          <span className="truncate rounded-full px-2 py-0.5" style={{ background: '#f8fafc', maxWidth: 150 }}>
                            {item.topic3}
                          </span>
                        )}
                        {item.has_media && (
                          <span className="rounded-full px-2 py-0.5" style={{ background: '#eff6ff', color: '#2563eb' }}>
                            含图
                          </span>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          {editMode && (
            <div className="mt-5 flex flex-wrap items-center gap-3 border-t pt-5" style={{ borderColor: '#dbe5f0' }}>
              <button
                onClick={handleSave}
                disabled={saveState === 'saving'}
                className="cursor-pointer rounded-full border-none px-5 py-2.5 text-sm font-medium text-white disabled:opacity-60"
                style={{ background: saveState === 'saved' ? '#16a34a' : '#2f76dd' }}
              >
                {saveState === 'saving' ? '保存中…' : saveState === 'saved' ? '已保存' : `保存${hasChanges ? `（${dirtyFields.size}）` : ''}`}
              </button>
              <button
                onClick={handleCancel}
                className="cursor-pointer rounded-full border px-5 py-2.5 text-sm"
                style={{ borderColor: '#dbe5f0', background: '#ffffff', color: '#64748b' }}
              >
                取消
              </button>
              <span className="text-xs" style={{ color: '#94a3b8' }}>
                Ctrl+S 保存 · Esc 取消
              </span>
            </div>
          )}
        </div>
      </div>

      <aside className="hidden w-[320px] flex-shrink-0 overflow-hidden border-l bg-white xl:block" style={{ borderColor: '#dbe5f0' }}>
        <AnnotationPanel questionId={question.question_id} />
      </aside>
    </div>
  );
}

const SIMPLE_IMAGE_SCALE_KEY = 'physics-vault.question-edit-image-scale';

function loadSimpleImageScale(assetId: string): number {
  try {
    const value = Number(localStorage.getItem(`${SIMPLE_IMAGE_SCALE_KEY}.${assetId}`));
    if (value >= 25 && value <= 100) return value;
  } catch {
    // Local storage can be blocked in embedded shells.
  }
  return 72;
}

function saveSimpleImageScale(assetId: string, scale: number): void {
  try {
    localStorage.setItem(`${SIMPLE_IMAGE_SCALE_KEY}.${assetId}`, String(scale));
  } catch {
    // Scaling still works for the current session.
  }
}

function SimpleQuestionEditWorkspace({
  question,
  images,
  dirtyFields,
  imageMessage,
  onUpdateField,
  onAddTag,
  onRemoveTag,
  onImageRoleChange,
  onImageDelete,
}: {
  question: Question;
  images: QuestionImageDetail[];
  dirtyFields: Set<string>;
  imageMessage: string | null;
  onUpdateField: (field: string, value: unknown) => void;
  onAddTag: (tag: string) => void;
  onRemoveTag: (tag: string) => void;
  onImageRoleChange: (assetId: string, role: string) => void;
  onImageDelete: (assetId: string, placeholderKey?: string | null) => void;
}) {
  const options = question.options?.length
    ? question.options
    : [
        { opt: 'A', content: '' },
        { opt: 'B', content: '' },
        { opt: 'C', content: '' },
        { opt: 'D', content: '' },
      ];

  const updateOption = (index: number, field: 'opt' | 'content', value: string) => {
    const next = [...options];
    next[index] = { ...next[index], [field]: value };
    onUpdateField('options', next);
  };

  const addOption = () => {
    const nextLetter = String.fromCharCode(65 + options.length);
    onUpdateField('options', [...options, { opt: nextLetter, content: '' }]);
  };

  const removeOption = (index: number) => {
    if (options.length <= 1) return;
    onUpdateField('options', options.filter((_, itemIndex) => itemIndex !== index));
  };

  return (
    <div className="mb-5 grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
      <section className="overflow-hidden rounded-lg border bg-white shadow-sm" style={{ borderColor: '#d4deea' }}>
        <div className="flex items-center justify-between border-b px-5 py-3" style={{ borderColor: '#dbe4ef', background: '#f8fafc' }}>
          <div>
            <div className="text-[15px] font-semibold" style={{ color: '#0f172a' }}>试题内容</div>
            <div className="mt-0.5 text-xs" style={{ color: '#64748b' }}>只保留高频编辑项，图片在右侧直接处理。</div>
          </div>
          {dirtyFields.size > 0 && (
            <span className="rounded px-2 py-1 text-xs font-semibold" style={{ background: '#fff7ed', color: '#b45309' }}>
              {dirtyFields.size} 项未保存
            </span>
          )}
        </div>

        <div className="space-y-4 p-5">
          <SimpleField label="题干" dirty={dirtyFields.has('title')}>
            <textarea
              value={question.title || ''}
              onChange={(event) => onUpdateField('title', event.target.value)}
              rows={9}
              className="w-full rounded-md border px-3 py-2 text-sm leading-7 outline-none focus:border-[#1f5fb8]"
              style={{ borderColor: '#cfd9e6', color: '#0f172a', resize: 'vertical' }}
            />
          </SimpleField>

          <SimpleField label="选项">
            <div className="space-y-2">
              {options.map((option, index) => (
                <div key={`${option.opt}-${index}`} className="grid gap-2 sm:grid-cols-[44px_minmax(0,1fr)_32px]">
                  <input
                    value={option.opt}
                    onChange={(event) => updateOption(index, 'opt', event.target.value.toUpperCase().slice(0, 2))}
                    className="rounded border px-2 py-2 text-center text-sm font-semibold outline-none focus:border-[#1f5fb8]"
                    style={{ borderColor: '#cfd9e6', color: '#1f5fb8' }}
                  />
                  <textarea
                    value={option.content}
                    onChange={(event) => updateOption(index, 'content', event.target.value)}
                    rows={1}
                    className="min-h-[38px] rounded border px-3 py-2 text-sm leading-6 outline-none focus:border-[#1f5fb8]"
                    style={{ borderColor: '#cfd9e6', color: '#0f172a', resize: 'vertical' }}
                  />
                  <button
                    type="button"
                    onClick={() => removeOption(index)}
                    disabled={options.length <= 1}
                    className="rounded border text-sm font-semibold disabled:opacity-40"
                    style={{ borderColor: '#fecaca', color: '#dc2626', background: '#fff' }}
                    title="删除选项"
                  >
                    ×
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={addOption}
                className="rounded border px-3 py-1.5 text-xs font-semibold"
                style={{ borderColor: '#b7c9e4', background: '#eef5ff', color: '#1f5fb8' }}
              >
                添加选项
              </button>
            </div>
          </SimpleField>

          <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
            <SimpleField label="答案" dirty={dirtyFields.has('answer')}>
              <textarea
                value={question.answer || ''}
                onChange={(event) => onUpdateField('answer', event.target.value)}
                rows={4}
                className="w-full rounded-md border px-3 py-2 text-sm leading-7 outline-none focus:border-[#1f5fb8]"
                style={{ borderColor: '#cfd9e6', color: '#0f172a', resize: 'vertical' }}
              />
            </SimpleField>

            <SimpleField label="解析" dirty={dirtyFields.has('analysis')}>
              <textarea
                value={question.analysis || ''}
                onChange={(event) => onUpdateField('analysis', event.target.value)}
                rows={6}
                className="w-full rounded-md border px-3 py-2 text-sm leading-7 outline-none focus:border-[#1f5fb8]"
                style={{ borderColor: '#cfd9e6', color: '#0f172a', resize: 'vertical' }}
              />
            </SimpleField>
          </div>
        </div>
      </section>

      <aside className="space-y-4 xl:sticky xl:top-5">
        <section className="rounded-lg border bg-white p-4 shadow-sm" style={{ borderColor: '#d4deea' }}>
          <div className="mb-3 text-sm font-semibold" style={{ color: '#0f172a' }}>基本信息</div>
          <div className="space-y-3">
            <SimpleField label="来源" dirty={dirtyFields.has('source')}>
              <input value={question.source || ''} onChange={(event) => onUpdateField('source', event.target.value)} className="w-full rounded border px-2 py-1.5 text-sm outline-none focus:border-[#1f5fb8]" style={{ borderColor: '#cfd9e6' }} />
            </SimpleField>
            <div className="grid grid-cols-2 gap-2">
              <SimpleField label="题型" dirty={dirtyFields.has('question_type')}>
                <select value={question.question_type || 'single_choice'} onChange={(event) => onUpdateField('question_type', event.target.value)} className="w-full rounded border bg-white px-2 py-1.5 text-sm outline-none focus:border-[#1f5fb8]" style={{ borderColor: '#cfd9e6' }}>
                  {TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </SimpleField>
              <SimpleField label="难度" dirty={dirtyFields.has('difficulty')}>
                <select value={String(question.difficulty || 0)} onChange={(event) => onUpdateField('difficulty', Number(event.target.value))} className="w-full rounded border bg-white px-2 py-1.5 text-sm outline-none focus:border-[#1f5fb8]" style={{ borderColor: '#cfd9e6' }}>
                  <option value={0}>未设置</option>
                  {DIFFICULTY_OPTIONS.map((difficulty) => <option key={difficulty} value={difficulty}>{difficulty}</option>)}
                </select>
              </SimpleField>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <SimpleField label="年份" dirty={dirtyFields.has('year')}>
                <input type="number" value={question.year ?? ''} onChange={(event) => onUpdateField('year', event.target.value ? Number(event.target.value) : undefined)} className="w-full rounded border px-2 py-1.5 text-sm outline-none focus:border-[#1f5fb8]" style={{ borderColor: '#cfd9e6' }} />
              </SimpleField>
              <SimpleField label="模型" dirty={dirtyFields.has('model_type')}>
                <input value={question.model_type || ''} onChange={(event) => onUpdateField('model_type', event.target.value)} className="w-full rounded border px-2 py-1.5 text-sm outline-none focus:border-[#1f5fb8]" style={{ borderColor: '#cfd9e6' }} />
              </SimpleField>
            </div>
            <SimpleField label="知识点" dirty={dirtyFields.has('knowledge_point')}>
              <textarea value={question.knowledge_point || ''} onChange={(event) => onUpdateField('knowledge_point', event.target.value)} rows={2} className="w-full rounded border px-2 py-1.5 text-sm leading-6 outline-none focus:border-[#1f5fb8]" style={{ borderColor: '#cfd9e6', resize: 'vertical' }} />
            </SimpleField>
            <SimpleField label="标签" dirty={dirtyFields.has('tags')}>
              <div className="mb-2 flex min-h-7 flex-wrap gap-1.5">
                {(question.tags || []).map((tag, index) => (
                  <span key={`${tag}-${index}`} className="inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs" style={{ borderColor: '#c9d7ea', background: '#f6f9fd', color: '#1f5fb8' }}>
                    {tag}
                    <button type="button" onClick={() => onRemoveTag(tag)} className="border-none bg-transparent text-xs leading-none" style={{ color: '#dc2626' }}>×</button>
                  </span>
                ))}
                {(question.tags || []).length === 0 && <span className="text-xs" style={{ color: '#94a3b8' }}>暂无标签</span>}
              </div>
              <input
                placeholder="输入后回车添加"
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    onAddTag((event.target as HTMLInputElement).value);
                    (event.target as HTMLInputElement).value = '';
                  }
                }}
                className="w-full rounded border px-2 py-1.5 text-sm outline-none focus:border-[#1f5fb8]"
                style={{ borderColor: '#cfd9e6' }}
              />
            </SimpleField>
          </div>
        </section>

        <section className="rounded-lg border bg-white p-4 shadow-sm" style={{ borderColor: '#d4deea' }}>
          <div className="mb-3 flex items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold" style={{ color: '#0f172a' }}>图片</div>
              <div className="text-xs" style={{ color: '#64748b' }}>直接调大小、改用途或移除。</div>
            </div>
            <span className="rounded bg-[#eef5ff] px-2 py-1 text-xs font-semibold text-[#1f5fb8]">{images.length} 张</span>
          </div>
          {imageMessage && <div className="mb-3 rounded border px-2 py-1.5 text-xs" style={{ borderColor: '#c9d7ea', background: '#f8fafc', color: '#475569' }}>{imageMessage}</div>}
          {images.length === 0 ? (
            <div className="rounded border border-dashed px-3 py-6 text-center text-xs" style={{ borderColor: '#cfd9e6', color: '#94a3b8' }}>本题暂无图片</div>
          ) : (
            <div className="space-y-3">
              {images.map((image, index) => (
                <DirectEditableImageCard
                  key={image.asset_id || image.link_id || index}
                  image={image}
                  index={index}
                  onRoleChange={onImageRoleChange}
                  onDelete={onImageDelete}
                />
              ))}
            </div>
          )}
        </section>
      </aside>
    </div>
  );
}

function SimpleField({
  label,
  dirty,
  children,
}: {
  label: string;
  dirty?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 flex items-center gap-1.5 text-xs font-semibold" style={{ color: '#526274' }}>
        {label}
        {dirty && <span className="h-1.5 w-1.5 rounded-full" style={{ background: '#f59e0b' }} />}
      </span>
      {children}
    </label>
  );
}

function DirectEditableImageCard({
  image,
  index,
  onRoleChange,
  onDelete,
}: {
  image: QuestionImageDetail;
  index: number;
  onRoleChange: (assetId: string, role: string) => void;
  onDelete: (assetId: string, placeholderKey?: string | null) => void;
}) {
  const [scale, setScale] = useState(() => loadSimpleImageScale(image.asset_id));
  const [broken, setBroken] = useState(false);
  const src = imageFileUrl(image.file_path || image.filename);
  const placeholder = image.placeholder_key || image.asset_id;

  useEffect(() => {
    setScale(loadSimpleImageScale(image.asset_id));
    setBroken(false);
  }, [image.asset_id]);

  const updateScale = (value: number) => {
    const next = Math.min(100, Math.max(25, value));
    setScale(next);
    saveSimpleImageScale(image.asset_id, next);
  };

  const copyPlaceholder = () => {
    void navigator.clipboard?.writeText(`![fig:${placeholder}]`);
  };

  return (
    <div className="overflow-hidden rounded-md border" style={{ borderColor: '#dbe4ef', background: '#fbfdff' }}>
      <div className="flex min-h-[120px] items-center justify-center bg-white p-2">
        {src && !broken ? (
          <img
            src={src}
            alt={image.filename || image.asset_id}
            onError={() => setBroken(true)}
            style={{ width: `${scale}%`, maxHeight: 260, objectFit: 'contain' }}
          />
        ) : (
          <div className="py-8 text-center text-xs" style={{ color: '#dc2626' }}>图片加载失败</div>
        )}
      </div>
      <div className="space-y-2 border-t p-2" style={{ borderColor: '#edf2f7' }}>
        <div className="flex items-center justify-between gap-2 text-xs">
          <span className="truncate font-medium" style={{ color: '#334155' }}>#{index + 1} {image.filename || image.asset_id}</span>
          <button type="button" onClick={copyPlaceholder} className="rounded border px-2 py-1 font-semibold" style={{ borderColor: '#c9d7ea', color: '#1f5fb8', background: '#fff' }}>占位符</button>
        </div>
        <div className="grid grid-cols-[1fr_54px] items-center gap-2">
          <input type="range" min={25} max={100} value={scale} onChange={(event) => updateScale(Number(event.target.value))} style={{ accentColor: '#1f5fb8' }} />
          <span className="text-right text-xs tabular-nums" style={{ color: '#64748b' }}>{scale}%</span>
        </div>
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <select
            value={image.role || 'stem'}
            onChange={(event) => onRoleChange(image.asset_id, event.target.value)}
            className="rounded border bg-white px-2 py-1.5 text-xs outline-none"
            style={{ borderColor: '#cfd9e6', color: '#334155' }}
          >
            <option value="stem">题干图</option>
            <option value="answer">答案图</option>
            <option value="analysis">解析图</option>
            <option value="step">步骤图</option>
          </select>
          <button type="button" onClick={() => onDelete(image.asset_id, placeholder)} className="rounded border px-2 py-1.5 text-xs font-semibold" style={{ borderColor: '#fecaca', color: '#dc2626', background: '#fff' }}>删除</button>
        </div>
      </div>
    </div>
  );
}

export function QuestionEditWorkspace({
  question,
  images,
  dirtyFields,
  onUpdateField,
  onAddTag,
  onRemoveTag,
}: {
  question: Question;
  images: QuestionImageDetail[];
  dirtyFields: Set<string>;
  onUpdateField: (field: string, value: unknown) => void;
  onAddTag: (tag: string) => void;
  onRemoveTag: (tag: string) => void;
}) {
  const options = question.options?.length
    ? question.options
    : [
        { opt: 'A', content: '' },
        { opt: 'B', content: '' },
        { opt: 'C', content: '' },
        { opt: 'D', content: '' },
      ];

  const updateOption = (index: number, field: 'opt' | 'content', value: string) => {
    const next = [...options];
    next[index] = { ...next[index], [field]: value };
    onUpdateField('options', next);
  };

  const addOption = () => {
    const nextLetter = String.fromCharCode(65 + options.length);
    onUpdateField('options', [...options, { opt: nextLetter, content: '' }]);
  };

  const removeOption = (index: number) => {
    if (options.length <= 1) return;
    onUpdateField('options', options.filter((_, itemIndex) => itemIndex !== index));
  };

  return (
    <div className="mb-5 grid items-start gap-5 xl:grid-cols-[minmax(0,0.96fr)_minmax(420px,1.04fr)]">
      <section
        className="overflow-hidden rounded-[24px] border bg-white"
        style={{
          borderColor: 'rgba(148, 163, 184, 0.18)',
          boxShadow: '0 18px 40px rgba(15, 23, 42, 0.06)',
        }}
      >
        <div className="border-b px-6 py-4" style={{ borderColor: '#e2e8f0', background: '#fbfdff' }}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-lg font-bold" style={{ color: '#0f172a' }}>试题编辑</div>
              <div className="mt-1 text-xs" style={{ color: '#64748b' }}>
                题干、选项、答案和解析集中编辑；右侧同步预览图片尺寸。
              </div>
            </div>
            {dirtyFields.size > 0 && (
              <span className="rounded-full px-3 py-1 text-xs font-semibold" style={{ background: '#fef3c7', color: '#b45309' }}>
                {dirtyFields.size} 项未保存
              </span>
            )}
          </div>
        </div>

        <div className="space-y-5 px-6 py-6">
          <div className="grid gap-3 lg:grid-cols-5">
            <EditBlock label="来源" dirty={dirtyFields.has('source')}>
              <input
                value={question.source || ''}
                onChange={(event) => onUpdateField('source', event.target.value)}
                className="w-full rounded-[12px] border px-3 py-2.5 text-sm outline-none"
                style={{ borderColor: '#dbe5f0', color: '#0f172a' }}
              />
            </EditBlock>

            <EditBlock label="题型" dirty={dirtyFields.has('question_type')}>
              <select
                value={question.question_type || 'single_choice'}
                onChange={(event) => onUpdateField('question_type', event.target.value)}
                className="w-full rounded-[12px] border px-3 py-2.5 text-sm outline-none"
                style={{ borderColor: '#dbe5f0', color: '#0f172a', background: '#fff' }}
              >
                {TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </EditBlock>

            <EditBlock label="难度" dirty={dirtyFields.has('difficulty')}>
              <select
                value={String(question.difficulty || 0)}
                onChange={(event) => onUpdateField('difficulty', Number(event.target.value))}
                className="w-full rounded-[12px] border px-3 py-2.5 text-sm outline-none"
                style={{ borderColor: '#dbe5f0', color: '#0f172a', background: '#fff' }}
              >
                <option value={0}>未设置</option>
                {DIFFICULTY_OPTIONS.map((difficulty) => (
                  <option key={difficulty} value={difficulty}>
                    {'★'.repeat(difficulty)}
                  </option>
                ))}
              </select>
            </EditBlock>

            <EditBlock label="年份" dirty={dirtyFields.has('year')}>
              <input
                type="number"
                value={question.year ?? ''}
                onChange={(event) => onUpdateField('year', event.target.value ? Number(event.target.value) : undefined)}
                className="w-full rounded-[12px] border px-3 py-2.5 text-sm outline-none"
                style={{ borderColor: '#dbe5f0', color: '#0f172a' }}
              />
            </EditBlock>

            <EditBlock label="物理模型" dirty={dirtyFields.has('model_type')}>
              <input
                value={question.model_type || ''}
                onChange={(event) => onUpdateField('model_type', event.target.value)}
                className="w-full rounded-[12px] border px-3 py-2.5 text-sm outline-none"
                style={{ borderColor: '#dbe5f0', color: '#0f172a' }}
              />
            </EditBlock>
          </div>

          <EditBlock label="题干" dirty={dirtyFields.has('title')}>
            <textarea
              value={question.title || ''}
              onChange={(event) => onUpdateField('title', event.target.value)}
              rows={10}
              className="w-full rounded-[14px] border px-4 py-3 text-sm leading-7 outline-none"
              style={{ borderColor: '#dbe5f0', color: '#0f172a', resize: 'vertical' }}
            />
          </EditBlock>

          <EditBlock label="选项">
            <div className="space-y-3">
              {options.map((option, index) => (
                <div key={`${option.opt}-${index}`} className="grid gap-2 sm:grid-cols-[64px_minmax(0,1fr)_40px]">
                  <input
                    value={option.opt}
                    onChange={(event) => updateOption(index, 'opt', event.target.value.toUpperCase().slice(0, 2))}
                    className="rounded-[12px] border px-3 py-2 text-center text-sm font-semibold outline-none"
                    style={{ borderColor: '#dbe5f0', color: '#2563eb' }}
                  />
                  <textarea
                    value={option.content}
                    onChange={(event) => updateOption(index, 'content', event.target.value)}
                    rows={2}
                    className="min-h-[44px] rounded-[12px] border px-3 py-2 text-sm leading-6 outline-none"
                    style={{ borderColor: '#dbe5f0', color: '#0f172a', resize: 'vertical' }}
                  />
                  <button
                    type="button"
                    onClick={() => removeOption(index)}
                    disabled={options.length <= 1}
                    className="rounded-[12px] border text-sm font-semibold disabled:opacity-40"
                    style={{ borderColor: '#fee2e2', color: '#dc2626', background: '#fff' }}
                    title="删除选项"
                  >
                    ×
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={addOption}
                className="rounded-[12px] border px-3 py-2 text-sm font-semibold"
                style={{ borderColor: '#bfdbfe', background: '#eff6ff', color: '#2563eb' }}
              >
                添加选项
              </button>
            </div>
          </EditBlock>

          <div className="grid gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
            <EditBlock label="答案" dirty={dirtyFields.has('answer')}>
              <textarea
                value={question.answer || ''}
                onChange={(event) => onUpdateField('answer', event.target.value)}
                rows={5}
                className="w-full rounded-[14px] border px-4 py-3 text-sm leading-7 outline-none"
                style={{ borderColor: '#dbe5f0', color: '#0f172a', resize: 'vertical' }}
              />
            </EditBlock>

            <EditBlock label="解析" dirty={dirtyFields.has('analysis')}>
              <textarea
                value={question.analysis || ''}
                onChange={(event) => onUpdateField('analysis', event.target.value)}
                rows={8}
                className="w-full rounded-[14px] border px-4 py-3 text-sm leading-7 outline-none"
                style={{ borderColor: '#dbe5f0', color: '#0f172a', resize: 'vertical' }}
              />
            </EditBlock>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <EditBlock label="知识点" dirty={dirtyFields.has('knowledge_point')}>
              <textarea
                value={question.knowledge_point || ''}
                onChange={(event) => onUpdateField('knowledge_point', event.target.value)}
                rows={3}
                className="w-full rounded-[14px] border px-4 py-3 text-sm leading-7 outline-none"
                style={{ borderColor: '#dbe5f0', color: '#0f172a', resize: 'vertical' }}
              />
            </EditBlock>

            <EditBlock label="标签" dirty={dirtyFields.has('tags')}>
              <div className="mb-3 flex min-h-9 flex-wrap gap-2">
                {(question.tags || []).map((tag, index) => (
                  <span
                    key={`${tag}-${index}`}
                    className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-sm"
                    style={{ background: '#eef4ff', color: '#2563eb' }}
                  >
                    {tag}
                    <button
                      type="button"
                      onClick={() => onRemoveTag(tag)}
                      className="border-none bg-transparent text-sm leading-none"
                      style={{ color: '#dc2626' }}
                    >
                      ×
                    </button>
                  </span>
                ))}
                {(question.tags || []).length === 0 && <span className="text-sm" style={{ color: '#94a3b8' }}>暂无标签</span>}
              </div>
              <input
                placeholder="输入标签后按回车"
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    onAddTag((event.target as HTMLInputElement).value);
                    (event.target as HTMLInputElement).value = '';
                  }
                }}
                className="w-full rounded-[14px] border px-4 py-2.5 text-sm outline-none"
                style={{ borderColor: '#dbe5f0', color: '#0f172a' }}
              />
            </EditBlock>
          </div>
        </div>
      </section>

      <div className="xl:sticky xl:top-5">
        <div className="mb-3 flex items-center justify-between rounded-[18px] border bg-white px-4 py-3" style={{ borderColor: '#e2e8f0' }}>
          <div>
            <div className="text-sm font-bold" style={{ color: '#0f172a' }}>实时预览</div>
            <div className="mt-0.5 text-xs" style={{ color: '#64748b' }}>图片右上角或悬浮控件可以调整大小。</div>
          </div>
          <span className="rounded-full px-2.5 py-1 text-xs font-semibold" style={{ background: '#ecfeff', color: '#0f766e' }}>
            可缩放图片
          </span>
        </div>
        <QuestionContentCard question={question} editMode={false} images={images} />
        <AnswerAnalysisCard question={question} editMode={false} />
      </div>
    </div>
  );
}

function EditBlock({
  label,
  dirty,
  children,
}: {
  label: string;
  dirty?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-semibold" style={{ color: '#334155' }}>{label}</span>
        {dirty && <span className="h-2 w-2 rounded-full" style={{ background: '#f59e0b' }} title="已修改" />}
      </div>
      {children}
    </section>
  );
}

function MetaChip({
  label,
  value,
  dirty,
  children,
}: {
  label: string;
  value: string;
  dirty?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div
      className="rounded-[18px] border px-4 py-3"
      style={{ borderColor: '#e2e8f0', background: '#fbfdff' }}
    >
      <label className="mb-1 block text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: '#94a3b8' }}>
        {label}
        {dirty && (
          <span
            className="ml-2 inline-block h-2 w-2 rounded-full align-middle"
            style={{ background: '#f59e0b' }}
            title="已修改"
          />
        )}
      </label>
      {children || (
        <div className="text-sm font-medium" style={{ color: '#0f172a' }}>
          {value || '-'}
        </div>
      )}
    </div>
  );
}
