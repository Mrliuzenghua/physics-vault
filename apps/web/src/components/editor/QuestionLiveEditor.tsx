import { useEffect, useMemo, useRef, useState } from 'react';
import { FileText, WandSparkles } from 'lucide-react';
import type { Option, Question, QuestionImageDetail } from '../../types';
import { completeQuestionAnalysis, refineQuestionFormat } from '../../services/aiApi';
import { addCachedQuestionImage } from '../../services/assetsApi';
import ImportStemRenderer from '../import/ImportStemRenderer';
import LatexRenderer from '../render/LatexRenderer';
import ImageManager from '../shared/ImageManager';
import ImageCachePickerDialog from './ImageCachePickerDialog';
import type { CachedImageAsset } from './ImageCachePickerDialog';
import StructuredTextEditor from './StructuredTextEditor';
import type { FigureInsertRequest } from './StructuredTextEditor';
import { mergeExperimentStepsIntoTitle } from '../../utils/experimentQuestion';

interface Props {
  question: Question;
  onChange: (patch: Partial<Question>) => void;
  onSave?: () => void | Promise<void>;
  saving?: boolean;
  saveLabel?: string;
  compact?: boolean;
  showPreview?: boolean;
  showHeader?: boolean;
  showImageManager?: boolean;
  syncDocument?: boolean;
  insertFigureRequest?: FigureInsertRequest | null;
  onFigureInsertHandled?: (requestId: number) => void;
  onRequestImage?: () => void;
}

type DraftSection = 'title' | 'options' | 'answer' | 'analysis';
type FormatPatch = Pick<Question, 'title' | 'options' | 'answer' | 'analysis'>;

const QUESTION_TYPE_OPTIONS: Array<{ value: Question['question_type']; label: string }> = [
  { value: 'single_choice', label: '单选题' },
  { value: 'multi_choice', label: '多选题' },
  { value: 'fill', label: '填空题' },
  { value: 'experiment', label: '实验题' },
  { value: 'calculation', label: '计算题' },
];

function questionToDraft(question: Question): string {
  const parts = [
    '题干：',
    question.title || '',
    '',
  ];

  const isChoice = question.question_type === 'single_choice' || question.question_type === 'multi_choice';
  if (isChoice) {
    const optionLines = (question.options || []).length > 0
      ? (question.options || []).map((option) => `${option.opt}. ${option.content || ''}`)
      : ['A. ', 'B. ', 'C. ', 'D. '];
    parts.push(
      '选项：',
      ...optionLines,
      '',
    );
  }

  parts.push('答案：', question.answer || '', '');

  if (question.analysis) {
    parts.push('解析：', question.analysis);
  }

  return parts.join('\n').trimEnd();
}

function parseQuestionDraft(value: string, currentQuestion: Question): Partial<Question> {
  const sections: Record<DraftSection, string[]> = {
    title: [],
    options: [],
    answer: [],
    analysis: [],
  };
  let section: DraftSection = 'title';

  for (const line of value.replace(/\r\n?/g, '\n').split('\n')) {
    const normalized = line.trim();
    if (/^题干[:：]?$/.test(normalized)) {
      section = 'title';
      continue;
    }
    if (/^(?:选项|实验步骤)[:：]?$/.test(normalized)) {
      section = 'options';
      continue;
    }
    if (/^答案[:：]?$/.test(normalized)) {
      section = 'answer';
      continue;
    }
    if (/^解析[:：]?$/.test(normalized)) {
      section = 'analysis';
      continue;
    }
    sections[section].push(line);
  }

  const parsedOptions: Option[] = [];
  let activeOption: Option | null = null;
  for (const rawLine of sections.options) {
    const match = rawLine.match(/^\s*([A-Z])[.、．)]\s*(.*)$/i);
    if (match) {
      activeOption = { opt: match[1].toUpperCase(), content: match[2] || '' };
      parsedOptions.push(activeOption);
      continue;
    }
    if (activeOption && rawLine.trim()) {
      activeOption.content = `${activeOption.content}\n${rawLine.trim()}`.trim();
    }
  }

  return {
    title: sections.title.join('\n').trim(),
    options: parsedOptions.length > 0 ? parsedOptions : currentQuestion.options || [],
    answer: sections.answer.join('\n').trim(),
    analysis: sections.analysis.join('\n').trim(),
  };
}

export default function QuestionLiveEditor({
  question,
  onChange,
  onSave,
  saving = false,
  saveLabel = '保存题目',
  compact = false,
  showPreview = true,
  showHeader = true,
  showImageManager = true,
  syncDocument = true,
  insertFigureRequest = null,
  onFigureInsertHandled,
  onRequestImage,
}: Props) {
  const [draftText, setDraftText] = useState(() => questionToDraft(question));
  const [imageCacheOpen, setImageCacheOpen] = useState(false);
  const [imageCacheError, setImageCacheError] = useState<string | null>(null);
  const [busyImagePath, setBusyImagePath] = useState<string | null>(null);
  const [internalFigureRequest, setInternalFigureRequest] = useState<FigureInsertRequest | null>(null);
  const [formatRefining, setFormatRefining] = useState(false);
  const [analysisCompleting, setAnalysisCompleting] = useState(false);
  const [formatMessage, setFormatMessage] = useState<string | null>(null);
  const [formatUndo, setFormatUndo] = useState<{ questionId: string; patch: FormatPatch } | null>(null);
  const [editorRevision, setEditorRevision] = useState(0);
  const loadedQuestionId = useRef(question.question_id);
  const migratedExperimentQuestionIds = useRef(new Set<string>());
  // Keep the rich editor responsive to changes made outside the editor (for
  // example, an MCP update or the “规范格式” action), without resetting the
  // cursor for the normal parent echo caused by the editor itself.
  const lastEmittedQuestionText = useRef(questionToDraft(question));
  const options = useMemo(() => question.options || [], [question.options]);
  const isExperiment = question.question_type === 'experiment';
  const previewClass = compact ? 'text-[13px] leading-6' : 'text-[15px] leading-8';

  if (loadedQuestionId.current !== question.question_id) {
    const nextText = questionToDraft(question);
    lastEmittedQuestionText.current = nextText;
    loadedQuestionId.current = question.question_id;
    if (draftText !== nextText) setDraftText(nextText);
  }

  useEffect(() => {
    if (!isExperiment || options.length === 0 || migratedExperimentQuestionIds.current.has(question.question_id)) return;
    migratedExperimentQuestionIds.current.add(question.question_id);
    const title = mergeExperimentStepsIntoTitle(question.title || '', options);
    const nextText = questionToDraft({ ...question, title, options: [] });
    lastEmittedQuestionText.current = nextText;
    setDraftText(nextText);
    setEditorRevision((current) => current + 1);
    onChange({
      title,
      options: [],
    });
  }, [isExperiment, onChange, options, question, question.question_id, question.title]);

  function handleDraftChange(value: string) {
    setDraftText(value);
    const previousRefs = new Set(Array.from(draftText.matchAll(/!\[fig:([^\]]+)\]/g), (match) => match[1]));
    const nextRefs = new Set(Array.from(value.matchAll(/!\[fig:([^\]]+)\]/g), (match) => match[1]));
    const removedRefs = new Set(Array.from(previousRefs).filter((figureId) => !nextRefs.has(figureId)));
    const patch = parseQuestionDraft(value, question);
    lastEmittedQuestionText.current = questionToDraft({ ...question, ...patch });
    onChange(removedRefs.size > 0
      ? { ...patch, figures: (question.figures || []).filter((figure) => !removedRefs.has(figure.fig_uuid)) }
      : patch);
  }

  function handleImagesChanged(images: QuestionImageDetail[]) {
    const previousFigureMap = new Map((question.figures || []).map((figure) => [figure.fig_uuid, figure]));
    const previousRefs = new Set(previousFigureMap.keys());
    const nextFigures = images.map((image) => {
      const figureId = image.placeholder_key || image.asset_id;
      const previous = previousFigureMap.get(figureId);
      return {
        ...previous,
        fig_uuid: figureId,
        local_path: image.file_path || image.filename || previous?.local_path || '',
        display_scale: image.display_scale ?? previous?.display_scale ?? 60,
        display_align: previous?.display_align || 'center',
        caption: previous?.caption || '',
      };
    });
    const nextRefs = new Set(nextFigures.map((figure) => figure.fig_uuid));
    let nextDraft = draftText;

    for (const ref of previousRefs) {
      if (!nextRefs.has(ref)) nextDraft = nextDraft.split(`![fig:${ref}]`).join('');
    }

    for (const ref of nextRefs) {
      if (previousRefs.has(ref) || nextDraft.includes(`![fig:${ref}]`)) continue;
      const sectionIndex = nextDraft.search(/\n(?:选项|答案)[:：]/);
      const insertion = `\n![fig:${ref}]\n`;
      nextDraft = sectionIndex >= 0
        ? `${nextDraft.slice(0, sectionIndex)}${insertion}${nextDraft.slice(sectionIndex)}`
        : `${nextDraft}${insertion}`;
    }

    nextDraft = nextDraft.replace(/\n{3,}/g, '\n\n').trimEnd();
    setDraftText(nextDraft);
    const patch = { ...parseQuestionDraft(nextDraft, question), figures: nextFigures };
    lastEmittedQuestionText.current = questionToDraft({ ...question, ...patch });
    onChange(patch);
  }

  async function insertCachedImage(asset: CachedImageAsset) {
    setBusyImagePath(asset.relative_path);
    setImageCacheError(null);
    try {
      const existingFigure = (question.figures || []).find((figure) =>
        figure.local_path === asset.file_path,
      );
      let figure = existingFigure;
      if (!figure) {
        const binding = await addCachedQuestionImage(question.question_id, {
          relative_path: asset.relative_path,
          role: 'stem',
        });
        figure = {
          fig_uuid: binding.placeholder_key || binding.asset_id,
          local_path: binding.file_path || asset.file_path,
          display_scale: binding.display_scale ?? 60,
          display_align: 'center',
          caption: '',
        };
        onChange({ figures: [...(question.figures || []), figure] });
      }
      setInternalFigureRequest({ requestId: Date.now(), figure });
      setImageCacheOpen(false);
    } catch (insertError) {
      setImageCacheError(insertError instanceof Error ? insertError.message : '图片插入失败');
    } finally {
      setBusyImagePath(null);
    }
  }

  async function handleFormatRefinement() {
    setFormatRefining(true);
    setFormatMessage(null);
    try {
      const refined = await refineQuestionFormat(question);
      const patch: Partial<Question> = {
        ...(typeof refined.title === 'string' ? { title: refined.title } : {}),
        ...(Array.isArray(refined.options) ? { options: refined.options } : {}),
        ...(typeof refined.answer === 'string' ? { answer: refined.answer } : {}),
        ...(typeof refined.analysis === 'string' ? { analysis: refined.analysis } : {}),
      };
      const nextQuestion = { ...question, ...patch };
      const nextText = questionToDraft(nextQuestion);
      setFormatUndo({
        questionId: question.question_id,
        patch: {
          title: question.title,
          options: question.options,
          answer: question.answer,
          analysis: question.analysis,
        },
      });
      lastEmittedQuestionText.current = nextText;
      setDraftText(nextText);
      setEditorRevision((current) => current + 1);
      onChange(patch);
      setFormatMessage('已优化公式、转义与段落格式；题意和题图保持不变。');
    } catch (error) {
      setFormatMessage(error instanceof Error ? error.message : 'DeepSeek 格式优化失败，请检查模型配置。');
    } finally {
      setFormatRefining(false);
    }
  }

  async function handleAnalysisCompletion() {
    setAnalysisCompleting(true);
    setFormatMessage(null);
    try {
      const analysis = await completeQuestionAnalysis(question);
      const nextQuestion = { ...question, analysis };
      const nextText = questionToDraft(nextQuestion);
      setFormatUndo({
        questionId: question.question_id,
        patch: {
          title: question.title,
          options: question.options,
          answer: question.answer,
          analysis: question.analysis,
        },
      });
      lastEmittedQuestionText.current = nextText;
      setDraftText(nextText);
      setEditorRevision((current) => current + 1);
      onChange({ analysis });
      setFormatMessage('DeepSeek 已补全解析；请核对后再保存，可撤销本次修改。');
    } catch (error) {
      setFormatMessage(error instanceof Error ? error.message : 'DeepSeek 补全解析失败，请检查模型配置。');
    } finally {
      setAnalysisCompleting(false);
    }
  }

  function undoFormatRefinement() {
    if (!formatUndo || formatUndo.questionId !== question.question_id) return;
    const nextQuestion = { ...question, ...formatUndo.patch };
    const nextText = questionToDraft(nextQuestion);
    lastEmittedQuestionText.current = nextText;
    setDraftText(nextText);
    setEditorRevision((current) => current + 1);
    onChange(formatUndo.patch);
    setFormatUndo(null);
    setFormatMessage('已撤销本次 DeepSeek 修改。');
  }

  return (
    <div className={`question-live-editor ${compact ? 'question-live-editor--compact' : ''}`}>
      {showHeader && (
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-xs font-semibold tracking-wide text-[var(--color-accent)]">实时编辑</div>
            <div className="mt-1 text-[11px] text-[var(--color-text-muted)]">左侧输入，右侧即时查看公式、题图和选项排版</div>
          </div>
          {onSave && (
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1.5 text-xs font-semibold text-[var(--color-text-secondary)]">
                <span>题型</span>
                <select
                  value={QUESTION_TYPE_OPTIONS.some((item) => item.value === question.question_type) ? question.question_type : 'calculation'}
                  onChange={(event) => {
                    const questionType = event.target.value as Question['question_type'];
                    onChange(questionType === 'experiment' && options.length > 0
                      ? {
                          question_type: questionType,
                          title: mergeExperimentStepsIntoTitle(question.title || '', options),
                          options: [],
                        }
                      : { question_type: questionType });
                  }}
                  disabled={saving}
                  className="rounded-md border border-[var(--color-border)] bg-white px-2 py-1.5 text-xs font-semibold text-[var(--color-text-main)] outline-none focus:border-[var(--color-accent)]"
                  aria-label="题型"
                >
                  {QUESTION_TYPE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
              </label>
              <button
              type="button"
              onClick={() => void onSave()}
              disabled={saving}
              className="rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-[var(--color-accent-dark)] disabled:cursor-not-allowed disabled:opacity-55"
            >
              {saving ? '保存中…' : saveLabel}
              </button>
            </div>
          )}
        </div>
      )}

      <div className={`grid min-h-0 gap-5 ${compact || !showPreview ? 'grid-cols-1' : 'lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]'}`}>
        <div className="min-w-0">
          <div className="mb-1.5 flex items-center justify-between gap-3">
            <div className="text-[10px] font-bold tracking-wide text-[var(--color-text-muted)]">编辑内容</div>
            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => void handleAnalysisCompletion()}
                disabled={formatRefining || analysisCompleting}
                className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-teal)] bg-white px-2.5 py-1.5 text-[11px] font-semibold text-[var(--color-teal)] transition-colors hover:bg-[var(--color-teal-light)] disabled:cursor-not-allowed disabled:opacity-55"
                title="调用已配置的 DeepSeek，根据题干、选项和答案补全解析；不会自动保存"
              >
                <FileText size={14} />{analysisCompleting ? 'DeepSeek 补全中…' : 'DeepSeek 补全解析'}
              </button>
              <button
                type="button"
                onClick={() => void handleFormatRefinement()}
                disabled={formatRefining || analysisCompleting}
                className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-accent)] bg-white px-2.5 py-1.5 text-[11px] font-semibold text-[var(--color-accent)] transition-colors hover:bg-[var(--color-accent-light)] disabled:cursor-not-allowed disabled:opacity-55"
                title="调用已配置的 DeepSeek，仅优化公式、转义、空格与段落格式"
              >
                <WandSparkles size={14} />{formatRefining ? 'DeepSeek 优化中…' : 'DeepSeek 优化格式'}
              </button>
            </div>
          </div>
          <StructuredTextEditor
            key={`${question.question_id}:${editorRevision}`}
            value={draftText}
            onChange={handleDraftChange}
            document={question.editor_document}
            contentId={`${question.question_id}:${editorRevision}`}
            onDocumentChange={syncDocument ? (document) => onChange({ editor_document: document }) : undefined}
            placeholder="输入题干、图片、选项和答案"
            figures={question.figures || []}
            onFigureScaleChange={(figureId, displayScale) => onChange({ figures: (question.figures || []).map((figure) => figure.fig_uuid === figureId ? { ...figure, display_scale: displayScale } : figure) })}
            onFigureAlignChange={(figureId, displayAlign) => onChange({ figures: (question.figures || []).map((figure) => figure.fig_uuid === figureId ? { ...figure, display_align: displayAlign } : figure) })}
            storageKey={`physics-vault.tiptap.${question.question_id}.full.v2`}
            minHeight={compact ? 190 : 520}
            compact={compact}
            insertFigureRequest={insertFigureRequest || internalFigureRequest}
            onFigureInsertHandled={(requestId) => {
              if (internalFigureRequest?.requestId === requestId) setInternalFigureRequest(null);
              onFigureInsertHandled?.(requestId);
            }}
            onRequestImage={onRequestImage || (() => { setImageCacheError(null); setImageCacheOpen(true); })}
          />
          {(formatMessage || (formatUndo && formatUndo.questionId === question.question_id)) && (
            <div className="mt-2 flex items-center justify-between gap-3">
              {formatMessage ? <div className={`text-[11px] ${formatMessage.includes('失败') ? 'text-[var(--color-danger)]' : 'text-[var(--color-success)]'}`}>{formatMessage}</div> : <span />}
              {formatUndo?.questionId === question.question_id && (
                <button
                  type="button"
                  onClick={undoFormatRefinement}
                  disabled={formatRefining || analysisCompleting}
                  className="shrink-0 text-[11px] font-semibold text-[var(--color-accent)] hover:underline disabled:cursor-not-allowed disabled:opacity-55"
                >
                  撤销本次 AI 修改
                </button>
              )}
            </div>
          )}
          {showImageManager && (compact ? (
            <details className="mt-3 border-t border-[var(--color-border)] pt-3">
              <summary className="cursor-pointer text-[11px] font-semibold text-[var(--color-accent)]">管理题图与上传</summary>
              <div className="mt-3">
                <ImageManager questionId={question.question_id} stemText={question.title || ''} onImagesChanged={handleImagesChanged} />
              </div>
            </details>
          ) : (
            <div className="mt-4 border-t border-[var(--color-border)] pt-4">
              <ImageManager questionId={question.question_id} stemText={question.title || ''} onImagesChanged={handleImagesChanged} />
            </div>
          ))}
        </div>

        {showPreview && <div className="min-w-0 rounded-lg border border-[var(--color-border)] bg-white p-4 text-[#111827] shadow-[var(--shadow-sm)]">
          <div className="mb-3 flex items-center justify-between border-b border-[var(--color-border)] pb-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--color-text-muted)]">实时预览</span>
            <span className="text-[10px] text-[var(--color-text-subtle)]">{question.question_type || '题目'}</span>
          </div>
          <div className={`min-h-[180px] text-[#111827] ${previewClass}`}>
            <ImportStemRenderer
              title={question.title || '(无题干)'}
              figures={question.figures || []}
              maxImageHeight={compact ? 150 : 220}
              thumbnailWidth={720}
              questionId={question.question_id}
              onScaleChange={(figure, display_scale) => onChange({ figures: (question.figures || []).map((item) => item.fig_uuid === figure.fig_uuid ? { ...item, display_scale } : item) })}
              onLayoutChange={(figure, patch) => onChange({ figures: (question.figures || []).map((item) => item.fig_uuid === figure.fig_uuid ? { ...item, ...patch } : item) })}
            />
            {!isExperiment && options.length > 0 && (
              <div className="mt-5 space-y-3">
                {options.map((option) => (
                  <div key={option.opt} className="grid grid-cols-[24px_minmax(0,1fr)] items-start gap-2">
                    <span className="font-bold text-[var(--color-accent)]">{option.opt}</span>
                    <div className="min-w-0 flex-1"><ImportStemRenderer title={option.content} figures={question.figures || []} maxImageHeight={120} thumbnailWidth={520} questionId={question.question_id} /></div>
                  </div>
                ))}
              </div>
            )}
            {(question.answer || question.analysis) && (
              <div className="mt-5 space-y-3 border-t border-[var(--color-border)] pt-4 text-sm leading-7">
                {question.answer && <div><div className="mb-1 text-xs font-bold text-[var(--color-green)]">答案</div><LatexRenderer text={question.answer} /></div>}
                {question.analysis && <div><div className="mb-1 text-xs font-bold text-[var(--color-accent)]">解析</div><LatexRenderer text={question.analysis} /></div>}
              </div>
            )}
          </div>
        </div>}
      </div>
      <ImageCachePickerDialog
        open={imageCacheOpen}
        usedPaths={new Set((question.figures || []).map((figure) => figure.local_path))}
        busyPath={busyImagePath}
        error={imageCacheError}
        onClose={() => setImageCacheOpen(false)}
        onSelect={insertCachedImage}
      />
    </div>
  );
}
