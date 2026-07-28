import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import {
  fetchQuestion,
  fetchQuestionImages,
  fetchQuestionKnowledgePoints,
  fetchQuestionVersionDetail,
  fetchQuestionVersions,
  fetchSimilarQuestions,
  markMistake,
  rollbackQuestionVersion,
  unmarkMistake,
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

          <section
            className="mb-5 rounded-[24px] border px-6 py-5"
            style={{
              borderColor: 'rgba(148, 163, 184, 0.18)',
              background: '#ffffff',
              boxShadow: '0 18px 40px rgba(15, 23, 42, 0.06)',
            }}
          >
            <div className="mb-4 flex items-center gap-2">
              <span className="rounded-full px-3 py-1 text-xs font-semibold" style={{ background: '#f1f5f9', color: '#475569' }}>
                基本信息
              </span>
              <span className="text-xs" style={{ color: '#94a3b8' }}>
                风格更接近阅读页面顶部的信息条
              </span>
            </div>
            <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
              <MetaChip label="题号" value={question.question_id} />
              <MetaChip
                label="题型"
                value={TYPE_LABELS[currentQuestion.question_type || ''] || currentQuestion.question_type || '-'}
                dirty={editMode ? dirtyFields.has('question_type') : undefined}
              >
                {editMode ? (
                  <select
                    value={String(form.question_type || '')}
                    onChange={(e) => updateField('question_type', e.target.value)}
                    className="mt-1 w-full rounded-xl border px-2 py-2 text-sm outline-none"
                    style={{ borderColor: '#dbe5f0', background: '#ffffff', color: '#0f172a' }}
                  >
                    {TYPE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : null}
              </MetaChip>
              <MetaChip
                label="难度"
                value={currentQuestion.difficulty ? '★'.repeat(currentQuestion.difficulty as number) : '-'}
                dirty={editMode ? dirtyFields.has('difficulty') : undefined}
              >
                {editMode ? (
                  <select
                    value={String(form.difficulty ?? 3)}
                    onChange={(e) => updateField('difficulty', Number(e.target.value))}
                    className="mt-1 w-full rounded-xl border px-2 py-2 text-sm outline-none"
                    style={{ borderColor: '#dbe5f0', background: '#ffffff', color: '#0f172a' }}
                  >
                    {DIFFICULTY_OPTIONS.map((difficulty) => (
                      <option key={difficulty} value={difficulty}>
                        {'★'.repeat(difficulty)}
                      </option>
                    ))}
                  </select>
                ) : null}
              </MetaChip>
              <MetaChip label="来源" value={currentQuestion.source || '-'} dirty={editMode ? dirtyFields.has('source') : undefined}>
                {editMode ? (
                  <input
                    value={(form.source as string) ?? ''}
                    onChange={(e) => updateField('source', e.target.value)}
                    className="mt-1 w-full rounded-xl border px-2 py-2 text-sm outline-none"
                    style={{ borderColor: '#dbe5f0', background: '#ffffff', color: '#0f172a' }}
                  />
                ) : null}
              </MetaChip>
              <MetaChip label="年份" value={currentQuestion.year ? String(currentQuestion.year) : '-'} dirty={editMode ? dirtyFields.has('year') : undefined}>
                {editMode ? (
                  <input
                    type="number"
                    value={(form.year as number) ?? ''}
                    onChange={(e) => updateField('year', e.target.value ? Number(e.target.value) : undefined)}
                    className="mt-1 w-full rounded-xl border px-2 py-2 text-sm outline-none"
                    style={{ borderColor: '#dbe5f0', background: '#ffffff', color: '#0f172a' }}
                  />
                ) : null}
              </MetaChip>
              <MetaChip label="物理模型" value={question.model_type || '-'} dirty={editMode ? dirtyFields.has('model_type') : undefined}>
                {editMode ? (
                  <input
                    value={(form.model_type as string) ?? ''}
                    onChange={(e) => updateField('model_type', e.target.value)}
                    className="mt-1 w-full rounded-xl border px-2 py-2 text-sm outline-none"
                    style={{ borderColor: '#dbe5f0', background: '#ffffff', color: '#0f172a' }}
                  />
                ) : null}
              </MetaChip>
            </div>
          </section>

          <QuestionContentCard
            question={question}
            editMode={editMode}
            form={form}
            onUpdateField={updateField}
            dirtyFields={dirtyFields}
            images={questionImages}
          />

          <AnswerAnalysisCard
            question={question}
            editMode={editMode}
            form={form}
            onUpdateField={updateField}
            dirtyFields={dirtyFields}
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
                {dirtyFields.has('tags') && <span className="inline-block h-2 w-2 rounded-full" style={{ background: '#f59e0b' }} />}
              </div>
              <div className="mb-3 flex flex-wrap gap-2">
                {(currentQuestion.tags || []).map((tag, index) => (
                  <span
                    key={`${tag}-${index}`}
                    className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-sm"
                    style={{ background: editMode ? '#eef4ff' : '#f8fafc', color: editMode ? '#2f76dd' : '#475569' }}
                  >
                    {tag}
                    {editMode && (
                      <button
                        onClick={() => removeTag(tag)}
                        className="cursor-pointer border-none bg-transparent text-sm leading-none"
                        style={{ color: '#ef4444' }}
                      >
                        ×
                      </button>
                    )}
                  </span>
                ))}
                {(currentQuestion.tags || []).length === 0 && (
                  <span className="text-sm" style={{ color: '#94a3b8' }}>
                    暂无标签
                  </span>
                )}
              </div>
              {editMode && (
                <input
                  placeholder="输入标签后按回车添加"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      addTag((e.target as HTMLInputElement).value);
                      (e.target as HTMLInputElement).value = '';
                    }
                  }}
                  className="w-full rounded-xl border px-3 py-2 text-sm outline-none"
                  style={{ borderColor: '#dbe5f0', background: '#ffffff', color: '#0f172a' }}
                />
              )}
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
