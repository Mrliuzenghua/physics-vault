import { useEffect, useRef, useState } from 'react';
import type { Option, Question, QuestionImageDetail } from '../../types';
import ImportStemRenderer from '../import/ImportStemRenderer';
import LatexRenderer from '../render/LatexRenderer';
import ImageManager from '../shared/ImageManager';
import StructuredTextEditor from './StructuredTextEditor';
import type { FigureInsertRequest } from './StructuredTextEditor';

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
  insertFigureRequest?: FigureInsertRequest | null;
  onRequestImage?: () => void;
}

type DraftSection = 'title' | 'options' | 'answer' | 'analysis';

function questionToDraft(question: Question): string {
  const parts = [
    '题干：',
    question.title || '',
    '',
  ];

  const isChoice = question.question_type === 'single_choice' || question.question_type === 'multi_choice';
  if (isChoice || (question.options || []).length > 0) {
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
    if (/^选项[:：]?$/.test(normalized)) {
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
  insertFigureRequest = null,
  onRequestImage,
}: Props) {
  const [draftText, setDraftText] = useState(() => questionToDraft(question));
  const loadedQuestionId = useRef(question.question_id);
  const options = question.options || [];
  const previewClass = compact ? 'text-[13px] leading-6' : 'text-[15px] leading-8';

  useEffect(() => {
    if (loadedQuestionId.current !== question.question_id) {
      loadedQuestionId.current = question.question_id;
      setDraftText(questionToDraft(question));
    }
  }, [question]);

  function handleDraftChange(value: string) {
    setDraftText(value);
    const previousRefs = new Set(Array.from(draftText.matchAll(/!\[fig:([^\]]+)\]/g), (match) => match[1]));
    const nextRefs = new Set(Array.from(value.matchAll(/!\[fig:([^\]]+)\]/g), (match) => match[1]));
    const removedRefs = new Set(Array.from(previousRefs).filter((figureId) => !nextRefs.has(figureId)));
    const patch = parseQuestionDraft(value, question);
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
    onChange({ ...parseQuestionDraft(nextDraft, question), figures: nextFigures });
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
            <button
              type="button"
              onClick={() => void onSave()}
              disabled={saving}
              className="rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-[var(--color-accent-dark)] disabled:cursor-not-allowed disabled:opacity-55"
            >
              {saving ? '保存中…' : saveLabel}
            </button>
          )}
        </div>
      )}

      <div className={`grid min-h-0 gap-5 ${compact || !showPreview ? 'grid-cols-1' : 'xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]'}`}>
        <div className="min-w-0">
          <div className="mb-1.5 text-[10px] font-bold tracking-wide text-[var(--color-text-muted)]">编辑内容</div>
          <StructuredTextEditor
            value={draftText}
            onChange={handleDraftChange}
            document={question.editor_document}
            onDocumentChange={(document) => onChange({ editor_document: document })}
            placeholder="输入题干、图片、选项和答案"
            figures={question.figures || []}
            onFigureScaleChange={(figureId, displayScale) => onChange({ figures: (question.figures || []).map((figure) => figure.fig_uuid === figureId ? { ...figure, display_scale: displayScale } : figure) })}
            onFigureAlignChange={(figureId, displayAlign) => onChange({ figures: (question.figures || []).map((figure) => figure.fig_uuid === figureId ? { ...figure, display_align: displayAlign } : figure) })}
            storageKey={`physics-vault.tiptap.${question.question_id}.full.v2`}
            minHeight={compact ? 190 : 520}
            compact={compact}
            insertFigureRequest={insertFigureRequest}
            onRequestImage={onRequestImage}
          />
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
            {options.length > 0 && (
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
    </div>
  );
}
