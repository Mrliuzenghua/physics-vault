import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import SmartRecognitionDialog from '../components/studio/SmartRecognitionDialog';
import LatexRenderer from '../components/render/LatexRenderer';
import { Dialog } from '../components/ui/Dialog';
import {
  createImportBatch,
  extractBatchImages,
  importQuestion,
  runImportBatchAiRefine,
  runImportBatchRecognize,
} from '../services/api';
import type { ImportMediaAsset, Question as QuestionRecord } from '../types';

type StudioTab = 'smart' | 'quick' | 'figure' | 'extract';
type OptionLayout = 'one' | 'single-column' | 'double-column';
type FigurePlacement =
  | 'question-bottom'
  | 'question-left'
  | 'question-right'
  | 'option-left'
  | 'option-right'
  | 'option-bottom';

interface LocalFigure {
  id: string;
  name: string;
  url: string;
}

const FIGURE_CACHE_KEY = 'physics-vault-question-studio-figure-cache';
const MAX_CACHED_FIGURES = 24;

interface DraftOption {
  opt: string;
  content: string;
}

interface SmartSegment {
  id: number;
  status: 'recognized' | 'retry' | 'pending';
  title?: string;
  text: string;
  question?: QuestionRecord | null;
}

const TABS: Array<{ key: StudioTab; label: string }> = [
  { key: 'smart', label: '智能识别' },
  { key: 'quick', label: '快速录入' },
  { key: 'figure', label: '配图' },
  { key: 'extract', label: '提取配图' },
];

const YEARS = Array.from({ length: 12 }, (_, index) => 2026 - index);
const QUICK_ENTRY_PROMPT = `请把下面这道高中物理题整理成结构化文本，并严格按以下格式输出，不要添加解释。

标题：
来源：
题目：
选项：
A. ...
B. ...
C. ...
D. ...
答案：
解析：
知识点：
- 
标签：
- 
选项排版：两列

要求：
1. 如果原文没有某项内容，保留该字段标题并留空。
2. 选项支持 A. / A．/ A) / （A） 这几种形式。
3. 数学公式统一使用 LaTeX 行内格式：$...$，不要使用 \\( \\)。
4. 知识点和标签每项单独占一行，并以“- ”开头。
5. 如果题目或解析中需要插图，请把图片写成单独一行的短引用格式：![img:图片文件名]。
6. 不要输出“题目配图”字段，不要输出 JSON，不要输出额外说明。

输出样例：
标题：匀变速直线运动判断
来源：2026 深圳一模
题目：一物体沿直线运动，其速度随时间变化如图所示，下列说法正确的是（ ）
![img:image6.png]
选项：
A. 0~2s 内加速度恒定
B. 2s 末速度方向改变
C. 2~4s 内物体处于静止状态
D. 4s 末回到出发点
答案：A
解析：根据 v-t 图像斜率表示加速度，0~2s 内斜率不变，因此加速度恒定。
![img:image9.png]
知识点：
- 匀变速直线运动
- v-t 图像
标签：
- 高一
- 单选
选项排版：两列`;
const QUICK_ENTRY_PLACEHOLDER = `把 AI 返回的结构化文本粘贴到这里，右侧会立即回填并预览。

支持格式示例：
标题：匀变速直线运动判断
题目：一物体沿直线运动，其速度随时间变化如图所示，下列说法正确的是（ ）
选项：
A. 0~2s 内加速度恒定
B. 2s 末速度方向改变
C. 2~4s 内物体处于静止状态
D. 4s 末回到出发点
答案：A
解析：根据 v-t 图像斜率表示加速度，0~2s 内斜率不变，因此加速度恒定。
知识点：
- 匀变速直线运动
- v-t 图像
标签：
- 高一
- 单选
配图提示：如图所示
选项排版：两列`;

function createEmptyDraft() {
  return {
    title: '',
    sourceText: '',
    stem: '',
    options: [
      { opt: 'A', content: '' },
      { opt: 'B', content: '' },
      { opt: 'C', content: '' },
      { opt: 'D', content: '' },
    ] as DraftOption[],
    answer: '',
    analysis: '',
    knowledgeText: '',
    tagText: '',
    year: String(new Date().getFullYear()),
    questionNo: '',
    figurePlacement: 'question-bottom' as FigurePlacement,
    optionLayout: 'double-column' as OptionLayout,
  };
}

function readFileAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '');
    reader.onerror = () => reject(new Error(`读取图片失败：${file.name}`));
    reader.readAsDataURL(file);
  });
}

function safeParseCachedFigures(value: string | null) {
  if (!value) return [] as LocalFigure[];
  try {
    const parsed = JSON.parse(value);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item.id === 'string' && typeof item.name === 'string' && typeof item.url === 'string')
      .slice(0, MAX_CACHED_FIGURES) as LocalFigure[];
  } catch {
    return [];
  }
}

function normalizeQuickLines(text: string) {
  return text.replace(/\r\n?/g, '\n').split('\n');
}

function normalizeInlineLatex(text: string) {
  return text
    .replace(/\\\(/g, '$')
    .replace(/\\\)/g, '$')
    .replace(/\\\[/g, '$$')
    .replace(/\\\]/g, '$$')
    .replace(/([A-Za-z])_\\text\{([A-Za-z0-9]+)\}/g, '$1_$2')
    .replace(/\$+\s*/g, (match) => match.trim())
    .replace(/\s+\$/g, '$');
}

function splitInlineSections(text: string) {
  return text
    .replace(/(知识点\s*[：:]\s*)(?=\S)/g, '\n$1')
    .replace(/(标签\s*[：:]\s*)(?=\S)/g, '\n$1')
    .replace(/(配图提示\s*[：:]\s*)(?=\S)/g, '\n$1')
    .replace(/(选项排版\s*[：:]\s*)(?=\S)/g, '\n$1')
    .replace(/(答案\s*[：:]\s*)(?=\S)/g, '\n$1')
    .replace(/(解析标题\s*[：:]\s*)(?=\S)/g, '\n$1')
    .replace(/(解析\s*[：:]\s*)(?=\S)/g, '\n$1');
}

function preprocessQuickInput(text: string) {
  return splitInlineSections(normalizeInlineLatex(text))
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function extractListValue(value: string) {
  const seen = new Set<string>();
  return value
    .split(/[\n,，;；]/)
    .map((item) => item.replace(/^[-*•\s]+/, '').trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

function parseOptionLine(line: string) {
  const match = line.match(/^\s*[（(]?([A-H])[)）.．、:：]\s*(.+?)\s*$/);
  if (!match) return null;
  return { opt: match[1], content: match[2].trim() };
}

function extractOptionsFromText(lines: string[]) {
  const joined = lines
    .join('\n')
    .replace(/\n+/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();

  if (!joined) return new Map<string, string>();

  const normalized = joined
    .replace(/([A-H])[.．、:：]\s*(?=\$?[A-H][.．、:：])/g, '$1. ')
    .replace(/\s*([（(]?[A-H][)）.．、:：])/g, ' $1')
    .trim();

  const pattern = /(?:^|\s)[（(]?([A-H])[)）.．、:：]\s*/g;
  const segments: Array<{ opt: string; start: number; end: number }> = [];
  let match: RegExpExecArray | null = null;

  while ((match = pattern.exec(normalized)) !== null) {
    segments.push({ opt: match[1], start: match.index + match[0].length, end: normalized.length });
  }

  for (let index = 0; index < segments.length - 1; index += 1) {
    segments[index].end = segments[index + 1].start - segments[index + 1].opt.length - 3;
  }

  const optionMap = new Map<string, string>();

  if (segments.length === 0) {
    for (const line of lines) {
      const parsed = parseOptionLine(line);
      if (parsed) optionMap.set(parsed.opt, parsed.content);
    }
    return optionMap;
  }

  segments.forEach((segment, index) => {
    const nextMarkerIndex = index < segments.length - 1
      ? normalized.slice(segment.start).search(/\s[（(]?[A-H][)）.．、:：]\s*/)
      : -1;
    const rawContent = nextMarkerIndex >= 0 && index < segments.length - 1
      ? normalized.slice(segment.start, segment.start + nextMarkerIndex)
      : normalized.slice(segment.start);
    const content = rawContent.trim();
    if (content) optionMap.set(segment.opt, content);
  });

  return optionMap;
}

function parseOptionLayout(value: string): OptionLayout {
  if (value.includes('一行')) return 'one';
  if (value.includes('一列')) return 'single-column';
  return 'double-column';
}

function stringifyOptions(options: DraftOption[]) {
  return options
    .filter((option) => option.content.trim())
    .map((option) => `${option.opt}. ${option.content.trim()}`)
    .join('\n');
}

function parseQuickDraft(raw: string, prev: ReturnType<typeof createEmptyDraft>) {
  const next = {
    ...createEmptyDraft(),
    year: prev.year,
    questionNo: prev.questionNo,
    figurePlacement: prev.figurePlacement,
    optionLayout: prev.optionLayout,
  };
  const trimmed = preprocessQuickInput(raw);
  if (!trimmed) return next;

  const lines = normalizeQuickLines(trimmed);
  const sectionMap: Array<{ key: 'title' | 'sourceText' | 'stem' | 'options' | 'answer' | 'analysis' | 'knowledge' | 'tags' | 'figureHint' | 'optionLayout'; pattern: RegExp }> = [
    { key: 'title', pattern: /^(标题|题目标题)\s*[：:]\s*(.*)$/ },
    { key: 'sourceText', pattern: /^(来源|出处)\s*[：:]\s*(.*)$/ },
    { key: 'stem', pattern: /^(题目|题干)\s*[：:]\s*(.*)$/ },
    { key: 'options', pattern: /^选项\s*[：:]\s*(.*)$/ },
    { key: 'answer', pattern: /^(答案|参考答案)\s*[：:]\s*(.*)$/ },
    { key: 'analysis', pattern: /^(解析|解答|答案解析)\s*[：:]\s*(.*)$/ },
    { key: 'knowledge', pattern: /^(知识点|考点)\s*[：:]\s*(.*)$/ },
    { key: 'tags', pattern: /^(标签|标记)\s*[：:]\s*(.*)$/ },
    { key: 'figureHint', pattern: /^(配图提示|图片提示|图示说明)\s*[：:]\s*(.*)$/ },
    { key: 'optionLayout', pattern: /^选项排版\s*[：:]\s*(.*)$/ },
  ];

  const buckets: Record<string, string[]> = {
    title: [],
    sourceText: [],
    stem: [],
    options: [],
    answer: [],
    analysis: [],
    knowledge: [],
    tags: [],
    figureHint: [],
    optionLayout: [],
  };

  let currentSection: keyof typeof buckets | 'stem' = 'stem';
  let seenExplicitSection = false;

  for (const line of lines) {
    const labelMatch = sectionMap.find((item) => item.pattern.test(line));
    if (labelMatch) {
      const matched = line.match(labelMatch.pattern);
      currentSection = labelMatch.key;
      seenExplicitSection = true;
      if (matched?.[2]?.trim()) {
        buckets[labelMatch.key].push(matched[2].trim());
      }
      continue;
    }

    const optionMatch = parseOptionLine(line);
    if (optionMatch) {
      buckets.options.push(`${optionMatch.opt}. ${optionMatch.content}`);
      continue;
    }

    if (!seenExplicitSection) {
      buckets.stem.push(line);
      continue;
    }

    buckets[currentSection].push(line);
  }

  const optionMap = extractOptionsFromText(buckets.options);

  const answerText = buckets.answer.join('\n').trim();
  const figureHint = buckets.figureHint.join('\n').trim();
  const rawAllText = lines.join('\n');
  const needFigure = /如图|图示|如右图|如下图|见图/.test(rawAllText) || Boolean(figureHint);

  next.title = buckets.title.join('\n').trim();
  next.sourceText = buckets.sourceText.join('\n').trim();
  next.stem = buckets.stem.join('\n').trim();
  next.options = Array.from({ length: Math.max(4, optionMap.size || 4) }, (_, index) => {
    const opt = String.fromCharCode(65 + index);
    return { opt, content: optionMap.get(opt) || '' };
  });
  next.answer = answerText.replace(/^选\s*/u, '').trim();
  next.analysis = buckets.analysis.join('\n').trim();
  next.knowledgeText = extractListValue(buckets.knowledge.join('\n')).join('\n');
  next.tagText = extractListValue(buckets.tags.join('\n')).join('\n');
  next.figurePlacement = needFigure ? 'question-bottom' : prev.figurePlacement;
  next.optionLayout = buckets.optionLayout.join('\n').trim()
    ? parseOptionLayout(buckets.optionLayout.join('\n'))
    : prev.optionLayout;

  if (!next.stem && !optionMap.size && !answerText && !buckets.analysis.length) {
    next.stem = trimmed;
  }

  return next;
}

function buildFigureReference(figure: LocalFigure) {
  return `![img:${figure.name}]`;
}

function normalizeFileUrl(path: string) {
  const trimmed = path.trim();
  if (!trimmed) return '';
  if (/^(data:|https?:\/\/)/i.test(trimmed)) return trimmed;
  if (trimmed.startsWith('/files/')) return trimmed;
  return `/files/${trimmed.replace(/^\.?\//, '')}`;
}

function mediaAssetToLocalFigure(asset: ImportMediaAsset): LocalFigure {
  return {
    id: asset.image_id,
    name: asset.filename,
    url: normalizeFileUrl(asset.relative_path),
  };
}

function questionFigureToLocalFigure(question: QuestionRecord, index: number): LocalFigure | null {
  const figure = question.figures[index];
  if (!figure?.local_path) return null;
  return {
    id: figure.fig_uuid || `${question.question_id}-fig-${index + 1}`,
    name: figure.local_path.split('/').pop() || `fig-${index + 1}`,
    url: normalizeFileUrl(figure.local_path),
  };
}

function buildSmartSegments(questions: QuestionRecord[]): SmartSegment[] {
  return questions.map((question, index) => ({
    id: index + 1,
    status: question.title?.trim() ? 'recognized' : 'pending',
    title: question.canonical_title?.trim() || `第 ${index + 1} 题`,
    text: question.title?.trim() || '识别完成，但题干为空',
    question,
  }));
}

function questionToDraft(question: QuestionRecord, currentYear: string): ReturnType<typeof createEmptyDraft> {
  const draft = createEmptyDraft();
  const analysisText = (question.analysis || '').trim();
  const analysisLines = analysisText ? normalizeQuickLines(analysisText).filter(Boolean) : [];
  const knowledgeText = question.knowledge_points?.length
    ? question.knowledge_points.map((item) => item.topic3_name).filter(Boolean).join('\n')
    : question.knowledge_point || '';

  return {
    ...draft,
    title: question.canonical_title || '',
    stem: question.title || '',
    options: question.options?.length
      ? question.options.map((item) => ({ opt: item.opt, content: item.content }))
      : draft.options,
    answer: question.answer || '',
    analysis: analysisLines.length > 1 ? analysisLines.slice(1).join('\n') : analysisText,
    sourceText: question.source || '',
    knowledgeText,
    tagText: (question.tags || []).join('\n'),
    year: question.year ? String(question.year) : currentYear,
    questionNo: question.primary_question_no || '',
    figurePlacement: question.figures?.length ? 'question-bottom' : draft.figurePlacement,
    optionLayout: question.options && question.options.length > 2 ? 'double-column' : 'single-column',
  };
}

function resolveFigureReference(value: string, figures: LocalFigure[]) {
  const trimmed = value.trim();
  const refMatch = trimmed.match(/^!\[img:([^\]]+)\]$/);
  if (!refMatch) return null;
  const key = refMatch[1].trim();
  return figures.find((figure) => figure.name === key || figure.id === key) || null;
}

function isImageSource(value: string) {
  const trimmed = value.trim();
  return /^data:image\/[a-zA-Z0-9.+-]+;base64,/.test(trimmed)
    || /^https?:\/\/\S+\.(png|jpe?g|gif|webp|svg)(\?\S*)?$/i.test(trimmed)
    || /^\/files\/\S+\.(png|jpe?g|gif|webp|svg)(\?\S*)?$/i.test(trimmed)
    || /^[A-Za-z]:[\\/].+\.(png|jpe?g|gif|webp|svg)$/i.test(trimmed)
    || /^\.{0,2}[\\/].+\.(png|jpe?g|gif|webp|svg)$/i.test(trimmed);
}

function normalizeImageSource(value: string) {
  const trimmed = value.trim();
  if (/^[A-Za-z]:[\\/]/.test(trimmed)) {
    return trimmed.replace(/\\/g, '/');
  }
  return trimmed;
}

function renderInlineRichText(text: string, emptyText: string, keyPrefix: string, figures: LocalFigure[]) {
  if (!text.trim()) {
    return <span className="text-[#a3afc0]">{emptyText}</span>;
  }

  const lines = normalizeQuickLines(text);

  return (
    <div className="space-y-3">
      {lines.map((line, index) => {
        const trimmed = line.trim();
        const referencedFigure = resolveFigureReference(trimmed, figures);
        const markdownImageMatch = trimmed.match(/^!\[[^\]]*]\((.+)\)$/);
        const imageSource = referencedFigure?.url
          || markdownImageMatch?.[1]?.trim()
          || (isImageSource(trimmed) ? trimmed : null);

        if (imageSource) {
          const src = normalizeImageSource(imageSource);
          return (
            <figure
              key={`${keyPrefix}-img-${index}`}
              className="overflow-hidden rounded-2xl border border-[#d7e2f0] bg-white p-3 shadow-sm"
            >
              <img src={src} alt={`inline-${index}`} className="mx-auto max-h-[320px] w-full object-contain" />
              <figcaption className="mt-2 truncate text-xs text-[#8090a8]">
                {referencedFigure ? buildFigureReference(referencedFigure) : src}
              </figcaption>
            </figure>
          );
        }

        if (!trimmed) {
          return <div key={`${keyPrefix}-space-${index}`} className="h-2" />;
        }

        return <LatexRenderer key={`${keyPrefix}-text-${index}`} text={line} />;
      })}
    </div>
  );
}

export default function QuestionStudioPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState(createEmptyDraft);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [attachedFigures, setAttachedFigures] = useState<LocalFigure[]>([]);
  const [figureLibrary, setFigureLibrary] = useState<LocalFigure[]>([]);
  const [smartModalOpen, setSmartModalOpen] = useState(false);
  const [quickPanelOpen, setQuickPanelOpen] = useState(false);
  const [extractModalOpen, setExtractModalOpen] = useState(false);
  const [quickPasteText, setQuickPasteText] = useState(QUICK_ENTRY_PLACEHOLDER);
  const [smartSourceName, setSmartSourceName] = useState('');
  const [smartSourcePreviewUrl, setSmartSourcePreviewUrl] = useState('');
  const [smartLoading, setSmartLoading] = useState(false);
  const [smartError, setSmartError] = useState<string | null>(null);
  const [smartSegments, setSmartSegments] = useState<SmartSegment[]>([]);
  const [smartSelectedIndex, setSmartSelectedIndex] = useState(0);
  const [smartWarnings, setSmartWarnings] = useState<string[]>([]);
  const [smartBatchId, setSmartBatchId] = useState<string | null>(null);
  const [smartRefining, setSmartRefining] = useState(false);
  const smartFileInputRef = useRef<HTMLInputElement | null>(null);

  const activeTab = (searchParams.get('tab') as StudioTab) || 'smart';

  const tags = useMemo(
    () => draft.tagText.split(/[\n,，;；]+/).map((item) => item.trim()).filter(Boolean),
    [draft.tagText],
  );
  const knowledgePoints = useMemo(
    () => draft.knowledgeText.split(/[\n,，;；]+/).map((item) => item.trim()).filter(Boolean),
    [draft.knowledgeText],
  );
  const smartSelectedSegment = smartSegments[smartSelectedIndex] || null;
  const smartSelectedQuestion = smartSelectedSegment?.question || null;
  const allFigures = useMemo(() => {
    const map = new Map<string, LocalFigure>();
    [...attachedFigures, ...figureLibrary].forEach((figure) => {
      map.set(figure.id, figure);
      map.set(figure.name, figure);
    });
    return Array.from(map.values());
  }, [attachedFigures, figureLibrary]);

  useEffect(() => {
    const cached = safeParseCachedFigures(window.localStorage.getItem(FIGURE_CACHE_KEY));
    if (cached.length > 0) {
      setFigureLibrary(cached);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(FIGURE_CACHE_KEY, JSON.stringify(figureLibrary.slice(0, MAX_CACHED_FIGURES)));
  }, [figureLibrary]);

  const changeTab = (tab: StudioTab) => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', tab);
    setSearchParams(next, { replace: true });
  };

  const openTabAction = (tab: StudioTab) => {
    changeTab(tab);
    if (tab === 'smart') {
      setSmartModalOpen(true);
      setQuickPanelOpen(false);
      setExtractModalOpen(false);
      return;
    }
    if (tab === 'quick') {
      setQuickPanelOpen((prev) => !prev);
      setSmartModalOpen(false);
      setExtractModalOpen(false);
      return;
    }
    if (tab === 'extract') {
      setExtractModalOpen(true);
      setQuickPanelOpen(false);
      setSmartModalOpen(false);
      return;
    }
    setQuickPanelOpen(false);
  };

  const mergeFiguresIntoLibrary = (figures: LocalFigure[]) => {
    if (figures.length === 0) return;
    setFigureLibrary((prev) => {
      const map = new Map<string, LocalFigure>();
      [...figures, ...prev].forEach((figure) => {
        map.set(figure.id, figure);
      });
      return Array.from(map.values()).slice(0, MAX_CACHED_FIGURES);
    });
  };

  const applyRecognizedQuestionToEditor = (question: QuestionRecord | null) => {
    if (!question) return;
    setDraft(questionToDraft(question, draft.year));
    const figures = (question.figures || [])
      .map((_, index) => questionFigureToLocalFigure(question, index))
      .filter(Boolean) as LocalFigure[];
    setAttachedFigures(figures);
    mergeFiguresIntoLibrary(figures);
    setSaveMessage(`已载入识别结果：${question.question_id || '当前题目'}`);
  };

  const resetSmartRecognition = () => {
    setSmartSourceName('');
    setSmartSourcePreviewUrl('');
    setSmartLoading(false);
    setSmartError(null);
    setSmartWarnings([]);
    setSmartSelectedIndex(0);
    setSmartSegments([]);
    setSmartBatchId(null);
    setSmartRefining(false);
    if (smartFileInputRef.current) {
      smartFileInputRef.current.value = '';
    }
  };

  const runSmartRecognition = async (file: File) => {
    setSmartLoading(true);
    setSmartError(null);
    setSmartWarnings([]);
    setSmartSourceName(file.name);

    if (file.type.startsWith('image/')) {
      try {
        setSmartSourcePreviewUrl(await readFileAsDataUrl(file));
      } catch {
        setSmartSourcePreviewUrl('');
      }
    } else {
      setSmartSourcePreviewUrl('');
    }

    try {
      const batch = await createImportBatch(file);
      setSmartBatchId(batch.batch_id);
      const recognizeResult = await runImportBatchRecognize(batch.batch_id);
      const questions = (recognizeResult.questions || []) as QuestionRecord[];
      const segments = buildSmartSegments(questions);
      setSmartSegments(segments);
      setSmartSelectedIndex(0);
      setSmartWarnings(recognizeResult.warnings || []);

      const recognizedFigures = (recognizeResult.media_assets || []).map(mediaAssetToLocalFigure);
      mergeFiguresIntoLibrary(recognizedFigures);

      try {
        const extractResult = await extractBatchImages(batch.batch_id);
        const extractedFigures = (extractResult.media_assets || []).map(mediaAssetToLocalFigure);
        mergeFiguresIntoLibrary(extractedFigures);
        if (extractResult.warnings?.length) {
          setSmartWarnings((prev) => [...prev, ...extractResult.warnings]);
        }
      } catch (error) {
        setSmartWarnings((prev) => [
          ...prev,
          error instanceof Error ? `配图缓存补充失败：${error.message}` : '配图缓存补充失败',
        ]);
      }

      if (questions[0]) {
        applyRecognizedQuestionToEditor(questions[0]);
      }

      setSaveMessage(`识别完成，共返回 ${questions.length} 道题。`);
    } catch (error) {
      const message = error instanceof Error ? error.message : '智能识别失败';
      setSmartError(message);
      setSmartSegments([
        { id: 1, status: 'retry', title: '识别失败', text: message, question: null },
      ]);
      setSaveMessage(message);
    } finally {
      setSmartLoading(false);
    }
  };

  const handleRefineSelectedRecognition = async () => {
    const batchId = smartBatchId || smartSelectedQuestion?.import_batch_id || '';
    if (!batchId || !smartSelectedQuestion) {
      setSaveMessage('请先完成切片识别，再清洗选中的题目。');
      setSmartWarnings((prev) => [
        '当前识别结果缺少批次号，请重新点一次“开始识别”后再清洗。',
        ...prev,
      ]);
      return;
    }
    setSmartRefining(true);
    setSmartError(null);
    setSaveMessage('正在调用 DeepSeek 清洗当前题目...');
    try {
      const result = await runImportBatchAiRefine(
        batchId,
        [smartSelectedQuestion as unknown as Record<string, unknown>],
      );
      const refinedQuestion = result.questions?.[0] as unknown as QuestionRecord | undefined;
      if (!refinedQuestion) {
        setSaveMessage('DeepSeek 没有返回可用的清洗结果。');
        return;
      }
      setSmartSegments((prev) => prev.map((segment, index) => (
        index === smartSelectedIndex
          ? {
              ...buildSmartSegments([refinedQuestion])[0],
              id: segment.id,
            }
          : segment
      )));
      applyRecognizedQuestionToEditor(refinedQuestion);
      if (result.warnings?.length) {
        setSmartWarnings((prev) => [...prev, ...result.warnings]);
      }
      setSaveMessage(`DeepSeek 已清洗当前题目，模型：${result.refined_by || 'DeepSeek'}。`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'DeepSeek 清洗当前题目失败';
      setSmartError(message);
      setSaveMessage(message);
    } finally {
      setSmartRefining(false);
    }
  };

  const handleRefineAllRecognition = async () => {
    const questions = smartSegments
      .map((segment) => segment.question)
      .filter(Boolean) as QuestionRecord[];
    const batchId = smartBatchId || questions[0]?.import_batch_id || '';
    if (!batchId || questions.length === 0) {
      setSaveMessage('请先完成切片识别，再批量清洗。');
      setSmartWarnings((prev) => [
        '当前识别结果缺少批次号，请重新点一次“开始识别”后再批量清洗。',
        ...prev,
      ]);
      return;
    }
    setSmartRefining(true);
    setSmartError(null);
    setSaveMessage('正在调用 DeepSeek 批量清洗...');
    try {
      const result = await runImportBatchAiRefine(
        batchId,
        questions as unknown as Record<string, unknown>[],
      );
      const refinedQuestions = (result.questions || []) as unknown as QuestionRecord[];
      const nextSegments = buildSmartSegments(refinedQuestions);
      setSmartSegments(nextSegments);
      const nextIndex = Math.min(smartSelectedIndex, Math.max(nextSegments.length - 1, 0));
      setSmartSelectedIndex(nextIndex);
      if (nextSegments[nextIndex]?.question) {
        applyRecognizedQuestionToEditor(nextSegments[nextIndex].question);
      }
      if (result.warnings?.length) {
        setSmartWarnings((prev) => [...prev, ...result.warnings]);
      }
      setSaveMessage(`DeepSeek 已清洗 ${result.refined_count ?? refinedQuestions.length} 道题，并已导入当前选中题到编辑区。`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'DeepSeek 批量清洗失败';
      setSmartError(message);
      setSaveMessage(message);
    } finally {
      setSmartRefining(false);
    }
  };

  const handleSmartFileChange = async (fileList: FileList | null) => {
    const file = fileList?.[0];
    if (!file) return;
    await runSmartRecognition(file);
  };

  const handleApplySelectedRecognition = () => {
    if (!smartSelectedQuestion) {
      setSaveMessage('请先在右侧选择一道已识别的题目。');
      setSmartWarnings((prev) => ['请先选择一道已识别的题目，再导入编辑区。', ...prev]);
      return;
    }
    applyRecognizedQuestionToEditor(smartSelectedQuestion);
    setSmartModalOpen(false);
    setSaveMessage(`已导入编辑区：${smartSelectedQuestion.question_id || '当前题目'}`);
  };

  const handleCopySelectedRecognition = async () => {
    if (!smartSelectedQuestion) {
      setSaveMessage('当前没有可复制的识别结果。');
      return;
    }
    const payload = [
      `题目：${smartSelectedQuestion.title || ''}`,
      ...((smartSelectedQuestion.options || []).map((option) => `${option.opt}. ${option.content}`)),
      smartSelectedQuestion.answer ? `答案：${smartSelectedQuestion.answer}` : '',
      smartSelectedQuestion.analysis ? `解析：${smartSelectedQuestion.analysis}` : '',
    ].filter(Boolean).join('\n');
    try {
      await navigator.clipboard.writeText(payload);
      setSaveMessage('已复制当前识别结果。');
    } catch {
      setSaveMessage('复制识别结果失败。');
    }
  };

  const updateDraft = <K extends keyof ReturnType<typeof createEmptyDraft>>(key: K, value: ReturnType<typeof createEmptyDraft>[K]) => {
    setDraft((prev) => ({ ...prev, [key]: value }));
  };

  const applyQuickPasteText = (value: string) => {
    setQuickPasteText(value);
    setDraft((prev) => parseQuickDraft(value, prev));
  };

  const handleOptionTextChange = (value: string) => {
    const optionMap = extractOptionsFromText(normalizeQuickLines(value));
    setDraft((prev) => ({
      ...prev,
      options: Array.from({ length: Math.max(4, optionMap.size || 4) }, (_, index) => {
        const opt = String.fromCharCode(65 + index);
        return { opt, content: optionMap.get(opt) || '' };
      }),
    }));
  };

  const handleLocalFigureUpload = async (fileList: FileList | null) => {
    if (!fileList) return;
    try {
      const next = await Promise.all(
        Array.from(fileList).map(async (file, index) => ({
          id: `${Date.now()}-${index}-${file.name}`,
          name: file.name,
          url: await readFileAsDataUrl(file),
        })),
      );
      setFigureLibrary((prev) => [...next, ...prev].slice(0, MAX_CACHED_FIGURES));
      setSaveMessage(`已加入图片缓存，共 ${Math.min(figureLibrary.length + next.length, MAX_CACHED_FIGURES)} 张。`);
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : '图片缓存失败');
    }
  };

  const handleCopyFigureReference = async (figure: LocalFigure) => {
    try {
      await navigator.clipboard.writeText(buildFigureReference(figure));
      setSaveMessage(`已复制图片短引用：${buildFigureReference(figure)}`);
    } catch {
      setSaveMessage(`复制图片短引用失败：${figure.name}`);
    }
  };

  const handleCopyQuickPrompt = async () => {
    try {
      await navigator.clipboard.writeText(QUICK_ENTRY_PROMPT);
      setSaveMessage('快速录入提示词已复制，可以直接发给 AI。');
    } catch {
      setSaveMessage('复制提示词失败，请手动复制。');
    }
  };

  const handlePasteFromClipboard = async (mode: 'replace' | 'append') => {
    try {
      const text = await navigator.clipboard.readText();
      if (!text.trim()) {
        setSaveMessage('剪贴板里没有可用文本。');
        return;
      }
      const nextText = mode === 'append' && quickPasteText.trim()
        ? `${quickPasteText.trim()}\n${text}`
        : text;
      applyQuickPasteText(nextText);
      setSaveMessage(mode === 'append' ? '已追加剪贴板内容，并同步更新预览。' : '已覆盖剪贴板内容，并同步更新预览。');
    } catch {
      setSaveMessage('读取剪贴板失败，请直接粘贴到文本框。');
    }
  };

  const handleOptimize = () => {
    if (!draft.answer && draft.options.some((option) => option.content)) {
      const firstOption = draft.options.find((option) => option.content.trim());
      if (firstOption) {
        updateDraft('answer', firstOption.opt);
      }
    }
    if (!draft.analysis && draft.stem) {
      updateDraft('analysis', '本题可先从已知条件入手，判断物理过程，再选择对应规律建立关系式。');
    }
    setSaveMessage('已按当前内容做一次本地优化，可继续修改。');
  };

  const saveCurrentQuestion = async (resetAfterSave: boolean) => {
    if (!draft.stem.trim()) {
      setSaveMessage('题目不能为空。');
      return;
    }

    setSaving(true);
    setSaveMessage(null);
    try {
      const response = await importQuestion({
        classification: {
          module: '高中物理',
          topic3: knowledgePoints[0] || null,
          question_type: draft.options.some((option) => option.content.trim()) ? 'single_choice' : 'calculation',
          difficulty: 3,
        },
        source: {
          paper_id: draft.sourceText.trim() || 'MANUAL',
          question_no: draft.questionNo || null,
          year: Number(draft.year) || null,
        },
        content: {
          stem: draft.stem,
          options: draft.options
            .filter((option) => option.content.trim())
            .map((option) => ({ label: option.opt, text: option.content })),
          answer: draft.answer,
          analysis: draft.analysis,
        },
        knowledge_points: knowledgePoints.map((item) => ({ topic3_name: item })),
        metadata: {
          title: draft.title,
          tags,
          entry_mode: activeTab,
        },
        note: '前端录题工作台提交',
      });

      setSaveMessage(`已保存：${response.question_id}`);
      if (resetAfterSave) {
        setDraft(createEmptyDraft());
      }
    } catch (error) {
      setSaveMessage(error instanceof Error ? error.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex h-full overflow-hidden bg-[#f4f6fb]">
      {quickPanelOpen && (
        <div className="absolute left-2 top-2 z-30 w-[390px] overflow-hidden rounded-[14px] border border-[#445a77] bg-white shadow-[0_18px_40px_rgba(26,45,88,0.22)]">
          <div className="flex items-center justify-between bg-[#445a77] px-4 py-2 text-white">
            <div className="text-[14px] font-semibold">快速录入</div>
            <div className="flex items-center gap-4 text-xs text-white/90">
              <button
                onClick={() => {
                  applyQuickPasteText('');
                  setSaveMessage('已清空快速录入内容。');
                }}
                className="hover:text-white"
              >
                清空
              </button>
              <button onClick={() => void handlePasteFromClipboard('replace')} className="hover:text-white">粘贴覆盖</button>
              <button onClick={() => void handlePasteFromClipboard('append')} className="hover:text-white">粘贴追加</button>
              <button onClick={() => void handleCopyQuickPrompt()} className="hover:text-white">复制提示词</button>
              <button onClick={() => setQuickPanelOpen(false)} className="text-lg leading-none hover:text-white">×</button>
            </div>
          </div>
          <div className="p-3">
            <textarea
              value={quickPasteText}
              onChange={(event) => applyQuickPasteText(event.target.value)}
              placeholder="把 AI 返回的结构化文本粘贴到这里，右侧会立即生成预览。"
              className="h-[68vh] w-full resize-none rounded-[10px] border border-[#d4deeb] p-3 text-[14px] leading-7 text-[#73839c] outline-none"
            />
            <div className="mt-2 text-xs leading-6 text-[#8191a7]">
              支持直接粘贴“标题 / 题目 / 选项 / 答案 / 解析 / 知识点 / 标签”结构化文本，右侧表单和预览会实时更新。
            </div>
          </div>
        </div>
      )}

      <div className="flex min-w-0 flex-1">
        <section className="flex min-w-0 flex-[0_0_54%] flex-col border-r border-[#e3e8f2] bg-white">
          <div className="border-b border-[#edf1f7] px-4 py-2">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-3">
                <button className="rounded-[10px] bg-[#f5f7fb] px-4 py-2 text-sm font-semibold text-[#54647d]">
                  目录管理
                </button>
                <button className="rounded-[10px] bg-[#f39a3d] px-3 py-2 text-white">⚙</button>
                <select
                  value={draft.year}
                  onChange={(event) => updateDraft('year', event.target.value)}
                  className="rounded-[10px] border border-[#e3e8f2] bg-white px-3 py-2 text-sm text-[#7a879b] outline-none"
                >
                  {YEARS.map((year) => (
                    <option key={year} value={year}>{year} 年</option>
                  ))}
                </select>
                <input
                  value={draft.questionNo}
                  onChange={(event) => updateDraft('questionNo', event.target.value)}
                  placeholder="题号"
                  className="w-20 rounded-[10px] border border-[#e3e8f2] px-3 py-2 text-sm text-[#7a879b] outline-none"
                />

                {TABS.map((tab) => (
                  <button
                    key={tab.key}
                    onClick={() => openTabAction(tab.key)}
                    className={`rounded-[10px] px-4 py-2 text-sm font-semibold ${
                      activeTab === tab.key
                        ? 'bg-[#7e42f5] text-white shadow-[0_8px_18px_rgba(126,66,245,0.3)]'
                        : 'border border-[#e3e8f2] bg-[#f7f9fc] text-[#5d6f88]'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-2">
                <button onClick={handleOptimize} className="rounded-[10px] bg-[#77d52a] px-4 py-2 text-sm font-semibold text-white">
                  优化
                </button>
                <button onClick={() => void saveCurrentQuestion(false)} disabled={saving} className="rounded-[10px] bg-[#2cb9b1] px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
                  {saving ? '保存中...' : '保存'}
                </button>
                <button onClick={() => void saveCurrentQuestion(true)} disabled={saving} className="rounded-[10px] bg-[#15b8a6] px-4 py-2 text-sm font-semibold text-white disabled:opacity-60">
                  录下一题
                </button>
                <button onClick={() => navigate(-1)} className="rounded-[10px] border border-[#dce5f0] bg-white px-4 py-2 text-sm font-semibold text-[#566983]">
                  返回
                </button>
              </div>
            </div>
          </div>

          {saveMessage && (
            <div className="border-b border-[#eef3f8] bg-[#f8fbff] px-5 py-2 text-sm text-[#5f7695]">
              {saveMessage}
            </div>
          )}

          <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
            <div className="space-y-2.5">
              <StudioField label="标题">
                <input
                  value={draft.title}
                  onChange={(event) => updateDraft('title', event.target.value)}
                  placeholder="请输入..."
                  className="w-full rounded-[10px] border border-[#e6ebf3] px-4 py-2.5 text-sm text-[#607089] outline-none"
                />
              </StudioField>

              <StudioField label="来源" actions={['历史数据']}>
                <input
                  value={draft.sourceText}
                  onChange={(event) => updateDraft('sourceText', event.target.value)}
                  placeholder="如：2026 深圳一模 / 校本练习 / 手工录入"
                  className="w-full rounded-[10px] border border-[#e6ebf3] px-4 py-2.5 text-sm text-[#607089] outline-none"
                />
              </StudioField>

              <StudioField
                label="题目"
                actions={['替换', '粘贴图片短引用', '选择选项并解析']}
              >
                <textarea
                  value={draft.stem}
                  onChange={(event) => updateDraft('stem', event.target.value)}
                  placeholder="请输入..."
                  className="h-28 w-full resize-none rounded-[10px] border border-[#e6ebf3] px-4 py-2.5 text-sm leading-7 text-[#607089] outline-none"
                />
              </StudioField>

              <StudioField label="选项" actions={['A/B/C/D 连续粘贴', '自动拆分']}>
                <textarea
                  value={stringifyOptions(draft.options)}
                  onChange={(event) => handleOptionTextChange(event.target.value)}
                  placeholder={`A. ...\nB. ...\nC. ...\nD. ...`}
                  className="h-24 w-full resize-none rounded-[10px] border border-[#e6ebf3] px-4 py-2.5 text-sm leading-7 text-[#607089] outline-none"
                />
                <div className="mt-2 flex gap-2">
                  <SmallSwitchButton active={draft.optionLayout === 'one'} onClick={() => updateDraft('optionLayout', 'one')}>一行</SmallSwitchButton>
                  <SmallSwitchButton active={draft.optionLayout === 'single-column'} onClick={() => updateDraft('optionLayout', 'single-column')}>一列</SmallSwitchButton>
                  <SmallSwitchButton active={draft.optionLayout === 'double-column'} onClick={() => updateDraft('optionLayout', 'double-column')}>两列</SmallSwitchButton>
                </div>
              </StudioField>

              <StudioField label="知识点" actions={['历史数据']}>
                <textarea
                  value={draft.knowledgeText}
                  onChange={(event) => updateDraft('knowledgeText', event.target.value)}
                  placeholder="知识点，一行一个"
                  className="h-12 w-full resize-none rounded-[10px] border border-[#e6ebf3] px-4 py-2.5 text-sm text-[#607089] outline-none"
                />
              </StudioField>

              <StudioField label="标签" actions={['历史数据']}>
                <textarea
                  value={draft.tagText}
                  onChange={(event) => updateDraft('tagText', event.target.value)}
                  placeholder="标签，一行一个"
                  className="h-12 w-full resize-none rounded-[10px] border border-[#e6ebf3] px-4 py-2.5 text-sm text-[#607089] outline-none"
                />
              </StudioField>

              <StudioField label="答案（结果）" actions={['替换', 'A', 'B', 'C', 'D']}>
                <textarea
                  value={draft.answer}
                  onChange={(event) => updateDraft('answer', event.target.value)}
                  placeholder="请输入..."
                  className="h-12 w-full resize-none rounded-[10px] border border-[#e6ebf3] px-4 py-2.5 text-sm text-[#607089] outline-none"
                />
              </StudioField>

              <StudioField label="解析（解答过程）" actions={['替换', '添加新解']}>
                <textarea
                  value={draft.analysis}
                  onChange={(event) => updateDraft('analysis', event.target.value)}
                  placeholder="请输入..."
                  className="h-20 w-full resize-none rounded-[10px] border border-[#e6ebf3] px-4 py-2.5 text-sm leading-7 text-[#607089] outline-none"
                />
              </StudioField>
            </div>
          </div>
        </section>

        <section className="flex min-w-0 flex-1 bg-[#f5f7fb]">
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="border-b border-[#edf1f7] bg-white px-3 py-2">
              <div className="rounded-[14px] border border-[#e8edf4] bg-white px-4 py-4 text-[#8b98ab]">
                <div className="mb-2 text-sm font-semibold text-[#909db0]">题目</div>
                <div className="text-[16px] leading-8 text-[#1f3353]">
                  {renderInlineRichText(draft.stem, ' ', 'header-stem', allFigures)}
                </div>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
              <div className="min-h-full rounded-[18px] border border-[#e7ecf4] bg-[#f7f9fd] p-4">
                {draft.title && (
                  <div className="mb-4 inline-flex rounded-full bg-[#eef5ff] px-3 py-1 text-sm font-semibold text-[#3f75b7]">
                    {draft.title}
                  </div>
                )}

                <div className="text-[17px] leading-9 text-[#1d2f4d]">
                  {renderInlineRichText(draft.stem, '右侧预览区', 'preview-stem', allFigures)}
                </div>

                {draft.options.some((option) => option.content.trim()) && (
                  <div className={`mt-6 grid gap-4 ${draft.optionLayout === 'double-column' ? 'md:grid-cols-2' : 'grid-cols-1'}`}>
                    {draft.options.filter((option) => option.content.trim()).map((option) => (
                      <div key={option.opt} className="flex gap-3 text-[18px] leading-8 text-[#233858]">
                        <span className="font-semibold">{option.opt}.</span>
                        <div className="flex-1">
                          <LatexRenderer text={option.content} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {tags.length > 0 && (
                  <div className="mt-6 flex flex-wrap gap-2">
                    {tags.map((tag) => (
                      <span key={tag} className="rounded-full bg-[#f3efff] px-3 py-1 text-xs text-[#8755d5]">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                {(draft.answer || draft.analysis) && (
                  <div className="mt-8 rounded-[18px] border border-[#dbe8dc] bg-[#eff9f0] p-5">
                    {draft.answer && (
                      <div className="mb-4">
                        <div className="mb-2 text-sm font-semibold text-[#26a15f]">答案</div>
                        <div className="text-[16px] leading-8 text-[#28513c]">
                          <LatexRenderer text={draft.answer} />
                        </div>
                      </div>
                    )}
                    {draft.analysis && (
                      <div>
                        <div className="mb-2 text-sm font-semibold text-[#5e728c]">解析</div>
                        <div className="text-[16px] leading-8 text-[#415672]">
                          {renderInlineRichText(draft.analysis, ' ', 'preview-analysis', allFigures)}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>

          <aside className="w-[180px] shrink-0 border-l border-[#e3e8f2] bg-white px-3 py-4">
            <label className="block">
              <span className="mb-2 inline-flex rounded-[10px] bg-[#4aa0ff] px-4 py-2 text-sm font-semibold text-white">
                上传剪贴板图片
              </span>
              <input
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={(event) => handleLocalFigureUpload(event.target.files)}
              />
            </label>
            <p className="text-center text-sm leading-7 text-[#8b98ab]">
              直接拖动图片到此处
            </p>
            <button
              onClick={() => {
                setFigureLibrary([]);
                setSaveMessage('已清空图片缓存。');
              }}
              className="mt-3 inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[#dce5f0] text-[#68b055]"
            >
              🗑
            </button>

            {figureLibrary.length > 0 && (
              <div className="mt-4 space-y-3">
                {figureLibrary.map((figure) => (
                  <div key={figure.id} className="overflow-hidden rounded-xl border border-[#e3e8f2] bg-white">
                    <img src={figure.url} alt={figure.name} className="h-24 w-full object-cover" />
                      <div className="space-y-2 px-2 py-2">
                        <div className="truncate text-xs text-[#7c8ca3]">{figure.name}</div>
                      <button
                        onClick={() => void handleCopyFigureReference(figure)}
                        className="w-full rounded-lg bg-[#eef5ff] px-2 py-1 text-xs font-semibold text-[#3f75b7]"
                      >
                        复制引用
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </aside>
        </section>
      </div>

      <SmartRecognitionDialog
        open={smartModalOpen}
        onClose={() => setSmartModalOpen(false)}
        sourceName={smartSourceName}
        sourcePreviewUrl={smartSourcePreviewUrl}
        loading={smartLoading}
        refining={smartRefining}
        error={smartError}
        warnings={smartWarnings}
        segments={smartSegments}
        selectedIndex={smartSelectedIndex}
        selectedQuestion={smartSelectedQuestion}
        fileInputRef={smartFileInputRef}
        onFileChange={handleSmartFileChange}
        onPickFile={() => smartFileInputRef.current?.click()}
        onSelect={(index) => {
          setSmartSelectedIndex(index);
          if (smartSegments[index]?.question) {
            applyRecognizedQuestionToEditor(smartSegments[index].question);
          }
        }}
        onApplySelected={handleApplySelectedRecognition}
        onRefineSelected={handleRefineSelectedRecognition}
        onRefineAll={handleRefineAllRecognition}
        onCopySelected={handleCopySelectedRecognition}
        onReset={resetSmartRecognition}
        resolveFigureUrl={normalizeFileUrl}
      />

      <Dialog open={extractModalOpen} onClose={() => setExtractModalOpen(false)} className="max-w-[1180px] rounded-[22px] border-[#dce6f2] bg-white">
        <div>
          <div className="flex items-center justify-between border-b border-[#edf1f7] px-5 py-4">
            <div>
              <div className="text-[18px] font-bold text-[#2a3d58]">提取配图 <span className="ml-2 text-sm font-normal text-[#9aa8bb]">支持 Word · PDF</span></div>
            </div>
            <button onClick={() => setExtractModalOpen(false)} className="rounded-[10px] bg-[#f5f7fb] px-4 py-2 text-sm text-[#73839b]">关闭</button>
          </div>
          <div className="p-6">
            <div className="flex h-[70vh] items-center justify-center rounded-[20px] border-2 border-dashed border-[#9cc4ff] bg-[#f4f9ff]">
              <div className="text-center">
                <div className="mb-4 text-5xl text-[#89a9d6]">🖼</div>
                <div className="text-[24px] font-semibold text-[#38567c]">拖拽或点击上传文件</div>
                <div className="mt-2 text-sm text-[#9aabbe]">自动提取文档中的配图，单文件最大 20MB</div>
                <div className="mt-4 flex items-center justify-center gap-3">
                  <span className="rounded-full bg-[#edf5ff] px-3 py-1 text-sm font-semibold text-[#4a76b5]">Word</span>
                  <span className="rounded-full bg-[#fff1eb] px-3 py-1 text-sm font-semibold text-[#ea7c56]">PDF</span>
                  <span className="rounded-full bg-[#eef8ef] px-3 py-1 text-sm font-semibold text-[#46a56d]">SVG</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Dialog>
    </div>
  );
}

function StudioField({
  label,
  actions,
  children,
}: {
  label: string;
  actions?: Array<string | { text: string; active?: boolean; onClick?: () => void }>;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[14px] bg-[#fafbfd]">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-t-[14px] bg-[#f3f5f8] px-4 py-2">
        <div className="text-[14px] font-semibold text-[#8b56eb]">{label}</div>
        {actions && (
          <div className="flex flex-wrap items-center gap-2">
            {actions.map((action) => {
              const item = typeof action === 'string' ? { text: action } : action;
              return (
                <button
                  key={item.text}
                  onClick={item.onClick}
                  className={`rounded-[8px] px-3 py-1 text-sm ${
                    item.active ? 'bg-[#ecf5ff] text-[#3182ea]' : 'bg-white text-[#5b95ed]'
                  }`}
                >
                  {item.text}
                </button>
              );
            })}
          </div>
        )}
      </div>
      <div className="rounded-b-[14px] border border-[#edf1f6] bg-white p-3">{children}</div>
    </section>
  );
}

function SmallSwitchButton({
  children,
  active,
  onClick,
}: {
  children: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`rounded-[10px] px-3 py-2 text-sm font-semibold ${
        active ? 'bg-[#4aa0ff] text-white' : 'bg-[#f3f5f8] text-[#536780]'
      }`}
    >
      {children}
    </button>
  );
}
