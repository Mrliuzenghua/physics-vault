import type PptxGenJS from 'pptxgenjs';
import type { LessonKnowledgeCard, LessonPackage, Question } from '../types';
import { imageFileUrl } from '../utils/imageUrl';
import { extractLatexFragments, latexToSvgDataUri } from '../utils/mathSvg';
import { getQuestionSourceLabel } from '../utils/questionSource';
import { normalizeLessonPackageForOutput } from './lessonLayoutModel';
import { requestResponse } from './apiClient';

export interface LessonExportOptions {
  includeAnswers: boolean;
  includeAnalysis: boolean;
  answerPosition?: 'after_question' | 'end';
  download?: boolean;
}

/** Keep browser previews and server Word exports on the same format contract. */
export function buildWordFormatSpec(pkg: LessonPackage, options: LessonExportOptions): Record<string, unknown> {
  const style = (pkg.styleConfig || {}) as Record<string, unknown>;
  const existing = pkg.formatSpec && typeof pkg.formatSpec === 'object' ? pkg.formatSpec : {};
  const existingStyle = existing.styleConfig && typeof existing.styleConfig === 'object' ? existing.styleConfig as Record<string, unknown> : {};
  const existingHeaderFooter = existing.headerFooter && typeof existing.headerFooter === 'object' ? existing.headerFooter as Record<string, unknown> : {};
  const existingOutput = existing.output && typeof existing.output === 'object' ? existing.output as Record<string, unknown> : {};
  const rawFigureScale = Number(style.figureScale ?? 1);
  const figureScale = rawFigureScale <= 2 ? rawFigureScale * 60 : rawFigureScale;

  return {
    ...existing,
    schema: 'physics-vault/word-export-format/v1',
    styleConfig: {
      ...existingStyle,
      ...style,
      figureScale: Math.min(100, Math.max(25, figureScale || 60)),
    },
    headerFooter: {
      ...existingHeaderFooter,
      ...(pkg.headerFooter || {}),
    },
    output: {
      ...existingOutput,
      includeAnswers: options.includeAnswers,
      includeAnalysis: options.includeAnalysis,
      answerPosition: options.answerPosition || 'after_question',
    },
  };
}

export interface LessonExportIssue {
  code: 'missing_question' | 'missing_figure' | 'malformed_formula';
  message: string;
  nodeId?: string;
  questionId?: string;
}

function formulaDelimitersAreBalanced(value: string): boolean {
  const source = String(value || '');
  const dollars = source.match(/\$/g)?.length || 0;
  const bracketBlocks = (source.match(/\\\[/g)?.length || 0) === (source.match(/\\\]/g)?.length || 0)
    && (source.match(/\\\(/g)?.length || 0) === (source.match(/\\\)/g)?.length || 0);
  return dollars % 2 === 0 && bracketBlocks;
}

export function validateLessonPackage(pkg: LessonPackage): LessonExportIssue[] {
  const issues: LessonExportIssue[] = [];
  const questions = new Map(pkg.questions.map((question) => [question.question_id, question]));

  for (const node of pkg.nodes) {
    if (node.type !== 'question') continue;
    const question = questions.get(node.questionId);
    if (!question) {
      issues.push({ code: 'missing_question', message: `题目 ${node.questionId} 不存在，无法导出`, nodeId: node.id, questionId: node.questionId });
      continue;
    }
    const figureIds = new Set((question.figures || []).map((figure) => figure.fig_uuid));
    const fields = [question.title, ...(question.options || []).map((option) => option.content), question.answer, question.analysis];
    for (const field of fields) {
      if (!formulaDelimitersAreBalanced(field)) {
        issues.push({ code: 'malformed_formula', message: `题目 ${question.question_id} 存在未闭合公式标记`, questionId: question.question_id });
        break;
      }
      for (const match of String(field || '').matchAll(/!\[fig:([^\]]+)\]/g)) {
        if (!figureIds.has(match[1])) {
          issues.push({ code: 'missing_figure', message: `题目 ${question.question_id} 引用了不存在的题图 ${match[1]}`, questionId: question.question_id });
        }
      }
    }
  }
  return issues;
}

function assertLessonPackageExportable(pkg: LessonPackage): void {
  const issues = validateLessonPackage(pkg);
  if (issues.length === 0) return;
  throw new Error(`导出前检查未通过：${issues.slice(0, 3).map((issue) => issue.message).join('；')}`);
}

const COLORS = {
  ink: '10233F',
  muted: '53647A',
  blue: '2567B8',
  blueSoft: 'E8F1FB',
  paper: 'F7F9FC',
  line: 'D6E1EE',
  answer: '0E7A58',
};

function cleanFileName(value: string, fallback: string): string {
  const name = value.trim().replace(/[\\/:*?"<>|]/g, '-').replace(/\s+/g, ' ');
  return name || fallback;
}

function questionKnowledge(question: Question): string {
  return question.knowledge_point
    || question.knowledge_points?.[0]?.topic3_name
    || question.knowledge_points?.[0]?.topic2_name
    || question.knowledge_points?.[0]?.topic1_name
    || '课堂练习';
}

function triggerDownload(content: BlobPart, fileName: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function toDocxAlignment(value: 'left' | 'center' | 'right', alignmentType: Record<string, string>): string {
  return alignmentType[value.toUpperCase()] || alignmentType.LEFT;
}

function stripFigurePlaceholders(value?: string | null): string {
  return String(value || '')
    .replace(/!\[fig:[^\]]+\]/g, '')
    .replace(/\r\n?/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n[ \t]*\n+/g, '\n')
    .trim();
}

function extractFigureIds(value?: string | null): string[] {
  return Array.from(String(value || '').matchAll(/!\[fig:([^\]]+)\]/g), (match) => match[1]);
}

function stripMarkdownFormatting(value: string): string {
  return value
    .replace(/^#{1,3}\s+/gm, '')
    .replace(/^>\s?/gm, '')
    .replace(/^\s*[-•]\s+/gm, '• ')
    .replace(/\*\*([^*\n]+?)\*\*/g, '$1')
    .replace(/~~([^~\n]+?)~~/g, '$1')
    .replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, '$1$2')
    .replace(/`([^`\n]+?)`/g, '$1');
}

/** Removes LaTex commands before Office export so raw source is never shown to students. */
function latexToDisplayText(value: string): string {
  let text = stripFigurePlaceholders(value);
  text = text.replace(/\$\$?/g, '');
  text = text.replace(/\\text\{([^{}]*)\}/g, '$1').replace(/\\mathrm\{([^{}]*)\}/g, '$1');
  text = text.replace(/\\left|\\right|\\!/g, '').replace(/\\times/g, '×').replace(/\\cdot/g, '·')
    .replace(/\\Delta/g, 'Δ').replace(/\\lambda/g, 'λ').replace(/\\nu/g, 'ν').replace(/\\mu/g, 'μ')
    .replace(/\\theta/g, 'θ').replace(/\\omega/g, 'ω').replace(/\\sqrt\{([^{}]*)\}/g, '√($1)');
  for (let index = 0; index < 4; index += 1) text = text.replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, '($1)/($2)');
  text = text.replace(/\^\{?(-?\d+)\}?/g, (_, exponent) => String(exponent)
    .replace(/-/g, '⁻').replace(/0/g, '⁰').replace(/1/g, '¹').replace(/2/g, '²').replace(/3/g, '³')
    .replace(/4/g, '⁴').replace(/5/g, '⁵').replace(/6/g, '⁶').replace(/7/g, '⁷').replace(/8/g, '⁸').replace(/9/g, '⁹'));
  return stripMarkdownFormatting(text.replace(/\\[a-zA-Z]+/g, '').replace(/[{}]/g, '')).replace(/\s{2,}/g, ' ').trim();
}

function docxFormattedTextRuns(
  docx: typeof import('docx'),
  value: string,
  options: { color?: string; bold?: boolean; font?: string; size?: number },
) {
  const runs: unknown[] = [];
  const cleaned = value
    .replace(/\r\n?/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n[ \t]*\n+/g, '\n')
    .replace(/^#{1,3}\s+/gm, '')
    .replace(/^>\s?/gm, '')
    .replace(/^\s*[-•]\s+/gm, '• ');
  const pattern = /(\*\*[^*\n]+?\*\*|~~[^~\n]+?~~|`[^`\n]+?`|\*[^*\n]+?\*)/g;
  let cursor = 0;
  for (const match of cleaned.matchAll(pattern)) {
    const start = match.index || 0;
    if (start > cursor) runs.push(new docx.TextRun({ text: cleaned.slice(cursor, start), ...options }));
    const token = match[0];
    const isBold = token.startsWith('**');
    const isStrike = token.startsWith('~~');
    const isCode = token.startsWith('`');
    const markerLength = isBold || isStrike ? 2 : 1;
    runs.push(new docx.TextRun({
      text: token.slice(markerLength, -markerLength),
      ...options,
      bold: options.bold || isBold,
      italics: !isBold && !isStrike && !isCode,
      strike: isStrike,
    }));
    cursor = start + token.length;
  }
  if (cursor < cleaned.length || runs.length === 0) {
    runs.push(new docx.TextRun({ text: cursor < cleaned.length ? cleaned.slice(cursor) : '', ...options }));
  }
  return runs;
}

const MATH_SYMBOLS: Record<string, string> = {
  alpha: 'α', beta: 'β', gamma: 'γ', Delta: 'Δ', delta: 'δ', epsilon: 'ε', theta: 'θ', lambda: 'λ', mu: 'μ', nu: 'ν', pi: 'π', rho: 'ρ', sigma: 'σ', phi: 'φ', omega: 'ω', times: '×', cdot: '·', leq: '≤', geq: '≥', neq: '≠', pm: '±', infty: '∞', degrees: '°',
};

function readMathGroup(source: string, start: number): [string, number] {
  if (source[start] !== '{') return [source[start] || '', start + 1];
  let depth = 0;
  for (let index = start; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}') depth -= 1;
    if (depth === 0) return [source.slice(start + 1, index), index + 1];
  }
  return [source.slice(start + 1), source.length];
}

function mathComponents(docx: typeof import('docx'), value: string): unknown[] {
  const result: unknown[] = [];
  let text = '';
  const flush = () => { if (text) { result.push(new docx.MathRun(text)); text = ''; } };
  for (let index = 0; index < value.length;) {
    const char = value[index];
    if (char === '\\') {
      flush();
      const command = value.slice(index + 1).match(/^[A-Za-z]+/)?.[0] || value[index + 1] || '';
      index += command.length + 1;
      if (command === 'frac' || command === 'dfrac' || command === 'tfrac') {
        const [numerator, nextNumerator] = readMathGroup(value, index);
        const [denominator, nextDenominator] = readMathGroup(value, nextNumerator);
        result.push(new docx.MathFraction({ numerator: mathComponents(docx, numerator) as never, denominator: mathComponents(docx, denominator) as never }));
        index = nextDenominator;
      } else if (command === 'sqrt') {
        const [radicand, next] = readMathGroup(value, index);
        result.push(new docx.MathRadical({ children: mathComponents(docx, radicand) as never }));
        index = next;
      } else if (command === 'text' || command === 'mathrm' || command === 'mathbf' || command === 'operatorname') {
        const [content, next] = readMathGroup(value, index);
        result.push(new docx.MathRun(content));
        index = next;
      } else if (command === 'overrightarrow' || command === 'overline' || command === 'vec') {
        const [content, next] = readMathGroup(value, index);
        result.push(new docx.MathRun(command === 'overline' ? `${content}̅` : `${content}⃗`));
        index = next;
      } else if (command !== 'left' && command !== 'right' && command !== '!' && command !== ',' && command !== ';' && command !== 'quad' && command !== 'qquad') {
        result.push(new docx.MathRun(MATH_SYMBOLS[command] || command));
      }
      continue;
    }
    if (char === '^' || char === '_') {
      flush();
      const [script, next] = readMathGroup(value, index + 1);
      const base = result.pop() || new docx.MathRun('');
      const firstScript = mathComponents(docx, script) as never;
      const nextMarker = value[next];
      if ((nextMarker === '^' || nextMarker === '_') && nextMarker !== char) {
        const [secondScript, afterSecond] = readMathGroup(value, next + 1);
        const secondChildren = mathComponents(docx, secondScript) as never;
        result.push(new docx.MathSubSuperScript({
          children: [base] as never,
          subScript: (char === '_' ? firstScript : secondChildren) as never,
          superScript: (char === '^' ? firstScript : secondChildren) as never,
        }));
        index = afterSecond;
      } else {
        result.push(char === '^'
          ? new docx.MathSuperScript({ children: [base] as never, superScript: firstScript })
          : new docx.MathSubScript({ children: [base] as never, subScript: firstScript }));
        index = next;
      }
      continue;
    }
    if (char === '{' || char === '}') { index += 1; continue; }
    text += char;
    index += 1;
  }
  flush();
  return result;
}

function docxMathChildren(docx: typeof import('docx'), value: string, options: { color?: string; bold?: boolean; font?: string; size?: number } = {}) {
  const safeValue = stripFigurePlaceholders(value);
  const children: unknown[] = [];
  const pattern = /(\$\$[\s\S]+?\$\$|\$[^$]+\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\))/g;
  let cursor = 0;
  for (const match of safeValue.matchAll(pattern)) {
    const start = match.index || 0;
    if (start > cursor) children.push(...docxFormattedTextRuns(docx, safeValue.slice(cursor, start), options));
    const formula = match[0].replace(/^\$\$?|\$\$?$/g, '').replace(/^\\\[|\\\]$|^\\\(|\\\)$/g, '');
    children.push(new docx.Math({ children: mathComponents(docx, formula) as never }));
    cursor = start + match[0].length;
  }
  if (cursor < safeValue.length || children.length === 0) children.push(...docxFormattedTextRuns(docx, cursor < safeValue.length ? safeValue.slice(cursor) : '', options));
  return children;
}

async function fetchFigureData(
  path?: string | null,
  maxWidth = 420,
  maxHeight = 230,
): Promise<{ data: Uint8Array; type: 'png' | 'jpg' | 'gif'; width: number; height: number } | null> {
  const url = imageFileUrl(path);
  if (!url) return null;
  try {
    const response = await requestResponse(url);
    if (!response.ok) return null;
    const blob = await response.blob();
    let sourceWidth = maxWidth;
    let sourceHeight = maxHeight;
    try {
      const bitmap = await createImageBitmap(blob);
      sourceWidth = bitmap.width;
      sourceHeight = bitmap.height;
      bitmap.close();
    } catch {
      // Keep a conservative fallback size when browser image decoding is unavailable.
    }
    const scale = Math.min(maxWidth / sourceWidth, maxHeight / sourceHeight, 1);
    return {
      data: new Uint8Array(await blob.arrayBuffer()),
      type: blob.type.includes('png') ? 'png' : blob.type.includes('gif') ? 'gif' : 'jpg',
      width: Math.max(40, Math.round(sourceWidth * scale)),
      height: Math.max(40, Math.round(sourceHeight * scale)),
    };
  } catch { return null; }
}

async function fetchFigureDataUri(path?: string | null): Promise<string | null> {
  const url = imageFileUrl(path);
  if (!url) return null;
  try {
    const response = await requestResponse(url);
    if (!response.ok) return null;
    const blob = await response.blob();
    return await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
  } catch { return null; }
}

export async function exportLessonAsWord(pkg: LessonPackage, options: LessonExportOptions): Promise<Blob> {
  assertLessonPackageExportable(pkg);
  pkg = normalizeLessonPackageForOutput(pkg);
  const docx = await import('docx');
  const style = pkg.styleConfig;
  const bodyFont = 'SimSun';
  const answerFont = 'KaiTi';
  const bodySize = 21;
  const titleSize = 32;
  const smallTitleSize = 28;
  const wordColor = '000000';
  const lineSpacingRatio = Math.min(1.55, Math.max(1.35, Number(style?.lineHeight || 1.45)));
  const lineSpacing = Math.round(lineSpacingRatio * 240);
  const questionMap = new Map(pkg.questions.map((question) => [question.question_id, question]));
  const knowledgeMap = new Map(pkg.knowledgeCards.map((card) => [card.id, card]));
  const textMap = new Map(pkg.textBlocks.map((block) => [block.id, block]));
  let questionIndex = 0;
  const children: InstanceType<typeof docx.Paragraph>[] = [];
  const trailingAnswerBlocks: Array<{ questionIndex: number; question: Question }> = [];

  for (const node of pkg.nodes) {
    if (node.type === 'page_break') {
      children.push(new docx.Paragraph({ children: [new docx.PageBreak()] }));
      continue;
    }
    if (node.type === 'knowledge') {
      const card = knowledgeMap.get(node.knowledgeId);
      if (!card) continue;
      children.push(new docx.Paragraph({
        heading: docx.HeadingLevel.HEADING_2,
        spacing: { before: 160, after: 60 },
        keepNext: true,
        children: docxMathChildren(docx, card.title, { color: wordColor, bold: true, font: bodyFont, size: smallTitleSize }) as never,
      }));
      children.push(new docx.Paragraph({ children: docxMathChildren(docx, card.summary, { color: wordColor, font: bodyFont, size: bodySize }) as never, spacing: { line: lineSpacing, after: 60 }, keepNext: true, keepLines: true }));
      card.points.forEach((point, pointIndex) => children.push(new docx.Paragraph({
        children: docxMathChildren(docx, point, { color: wordColor, font: bodyFont, size: bodySize }) as never,
        bullet: { level: 0 },
        indent: { left: 360, hanging: 160 },
        spacing: { line: lineSpacing, after: 40 },
        keepLines: true,
        keepNext: pointIndex < card.points.length - 1,
      })));
      continue;
    }
    if (node.type === 'text') {
      const block = textMap.get(node.textBlockId);
      if (!block) continue;
      const isHeading = block.blockKind === 'section_title' || block.blockKind === 'exam_title';
      const blockSize = block.blockKind === 'exam_title'
        ? titleSize
        : block.blockKind === 'section_title'
          ? smallTitleSize
          : bodySize;
      children.push(new docx.Paragraph({
        alignment: block.style?.textAlign ? toDocxAlignment(block.style.textAlign, docx.AlignmentType) as never : undefined,
        heading: isHeading ? (block.blockKind === 'exam_title' ? docx.HeadingLevel.TITLE : docx.HeadingLevel.HEADING_2) : undefined,
        spacing: { before: block.blockKind === 'exam_title' ? 0 : isHeading ? 220 : 100, after: block.blockKind === 'exam_title' ? 120 : 100 },
        keepNext: isHeading,
        keepLines: true,
        children: docxMathChildren(docx, block.content || block.title, { color: wordColor, bold: block.style?.fontWeight === 'bold' || isHeading, size: blockSize, font: bodyFont }) as never,
      }));
      continue;
    }
    const question = questionMap.get(node.questionId);
    if (!question) continue;
    questionIndex += 1;
    const questionSource = getQuestionSourceLabel(question, '未标注来源');
    children.push(new docx.Paragraph({
      indent: { left: 360, hanging: 360 },
      spacing: { before: 160, after: 70, line: lineSpacing },
      keepNext: Boolean((question.figures || []).length || (question.options || []).length),
      keepLines: true,
      children: [new docx.TextRun({ text: `${questionIndex}. `, font: bodyFont, size: bodySize }), ...docxMathChildren(docx, question.title || question.stem_text || '', { font: bodyFont, size: bodySize })] as never,
    }));
    children.push(new docx.Paragraph({
      spacing: { after: 70 },
      keepNext: Boolean((question.figures || []).length || (question.options || []).length),
      keepLines: true,
      children: [new docx.TextRun({ text: `来源：${questionSource}`, color: wordColor, font: bodyFont, size: 18 })],
    }));
    const figureById = new Map((question.figures || []).map((figure) => [figure.fig_uuid, figure]));
    const optionFigureIds = new Set((question.options || []).flatMap((option) => extractFigureIds(option.content)));
    const stemFigureIds = extractFigureIds(question.title || question.stem_text);
    const questionFigures = stemFigureIds.length > 0
      ? stemFigureIds.map((id) => figureById.get(id)).filter(Boolean)
      : (question.figures || []).filter((figure) => !optionFigureIds.has(figure.fig_uuid));
    const uniqueFigures = Array.from(new Map(questionFigures
      .filter((figure) => Boolean(figure?.local_path))
      .map((figure) => [figure!.local_path, figure!])).values());
    if (uniqueFigures.length > 0) {
      const figureMaxWidth = uniqueFigures.length > 1 ? 245 : 420;
      const figureMaxHeight = uniqueFigures.length > 1 ? 170 : 230;
      const figureRuns = [];
      for (const figure of uniqueFigures.slice(0, 3)) {
        const scale = Math.min(100, Math.max(25, Number(figure.display_scale ?? 60)));
        const image = await fetchFigureData(figure.local_path, Math.round(Math.min(figureMaxWidth, figureMaxWidth * (scale / 60))), figureMaxHeight);
        if (image) {
          figureRuns.push(new docx.ImageRun({
            data: image.data,
            type: image.type,
            transformation: { width: image.width, height: image.height },
          }));
          figureRuns.push(new docx.TextRun({ text: '   ' }));
        }
      }
      if (figureRuns.length > 0) {
        const figureAlignment = docx.AlignmentType.LEFT;
        children.push(new docx.Paragraph({
          alignment: figureAlignment,
          spacing: { after: 90 },
          keepNext: Boolean(question.options?.length),
          keepLines: true,
          children: figureRuns as never,
        }));
        if (uniqueFigures.length === 1 && uniqueFigures[0].caption) {
          children.push(new docx.Paragraph({
            alignment: figureAlignment,
            spacing: { after: 80 },
            children: [new docx.TextRun({ text: uniqueFigures[0].caption, color: wordColor, italics: true, font: bodyFont, size: Math.max(18, bodySize - 2) })],
          }));
        }
      }
    }
    for (let optionIndex = 0; optionIndex < (question.options || []).length; optionIndex += 1) {
      const option = question.options[optionIndex];
      const optionImages = extractFigureIds(option.content)
        .map((figureId) => figureById.get(figureId))
        .filter(Boolean);
      children.push(new docx.Paragraph({
        children: [new docx.TextRun({ text: `${option.opt}. `, font: bodyFont, size: bodySize }), ...docxMathChildren(docx, option.content, { font: bodyFont, size: bodySize })] as never,
        indent: { left: 560, hanging: 200 },
        spacing: { line: lineSpacing, after: optionImages.length > 0 ? 35 : 55 },
        keepLines: true,
        keepNext: optionImages.length > 0 || optionIndex < question.options.length - 1,
      }));
      for (const figure of optionImages) {
        const image = await fetchFigureData(figure!.local_path, 210, 135);
        if (!image) continue;
        children.push(new docx.Paragraph({
          alignment: docx.AlignmentType.LEFT,
          indent: { left: 720 },
          spacing: { after: 55 },
          keepLines: true,
          keepNext: optionIndex < question.options.length - 1,
          children: [new docx.ImageRun({ data: image.data, type: image.type, transformation: { width: image.width, height: image.height } })],
        }));
      }
    }
    if (options.answerPosition === 'end') {
      trailingAnswerBlocks.push({ questionIndex, question });
    } else {
      if (options.includeAnswers && question.answer) children.push(new docx.Paragraph({ shading: { fill: 'F2F2F2', type: docx.ShadingType.CLEAR }, spacing: { before: 90, after: 35, line: lineSpacing }, keepLines: true, children: [new docx.TextRun({ text: '【答案】 ', bold: true, color: wordColor, font: answerFont, size: bodySize }), ...docxMathChildren(docx, question.answer, { color: wordColor, font: answerFont, size: bodySize })] as never }));
      if (options.includeAnalysis && question.analysis) children.push(new docx.Paragraph({ shading: { fill: 'F2F2F2', type: docx.ShadingType.CLEAR }, spacing: { before: 0, after: 120, line: lineSpacing }, keepLines: true, children: [new docx.TextRun({ text: '【详解】 ', bold: true, color: wordColor, font: answerFont, size: bodySize }), ...docxMathChildren(docx, question.analysis, { color: wordColor, font: answerFont, size: bodySize })] as never }));
    }
  }

  if (trailingAnswerBlocks.length > 0 && (options.includeAnswers || options.includeAnalysis)) {
    children.push(new docx.Paragraph({ children: [new docx.PageBreak()] }));
    children.push(new docx.Paragraph({
      spacing: { after: 120 },
      children: [new docx.TextRun({ text: options.includeAnalysis ? '参考答案与解析' : '参考答案', bold: true, color: wordColor, font: bodyFont, size: smallTitleSize })],
    }));
    for (const item of trailingAnswerBlocks) {
      if (options.includeAnswers && item.question.answer) children.push(new docx.Paragraph({ shading: { fill: 'F2F2F2', type: docx.ShadingType.CLEAR }, spacing: { before: 90, after: 35, line: lineSpacing }, keepLines: true, children: [new docx.TextRun({ text: `${item.questionIndex}. 【答案】 `, bold: true, color: wordColor, font: answerFont, size: bodySize }), ...docxMathChildren(docx, item.question.answer, { color: wordColor, font: answerFont, size: bodySize })] as never }));
      if (options.includeAnalysis && item.question.analysis) children.push(new docx.Paragraph({ shading: { fill: 'F2F2F2', type: docx.ShadingType.CLEAR }, spacing: { before: 0, after: 120, line: lineSpacing }, keepLines: true, children: [new docx.TextRun({ text: item.question.answer ? '【详解】 ' : `${item.questionIndex}. 【详解】 `, bold: true, color: wordColor, font: answerFont, size: bodySize }), ...docxMathChildren(docx, item.question.analysis, { color: wordColor, font: answerFont, size: bodySize })] as never }));
    }
  }

  const headerText = pkg.headerFooter?.headerEnabled ? pkg.headerFooter.headerText : '';
  const footerText = pkg.headerFooter?.footerEnabled ? pkg.headerFooter.footerText : '';
  const footerChildren = [];
  if (footerText) footerChildren.push(new docx.TextRun({ text: footerText, color: wordColor, font: bodyFont, size: 18 }));
  if (pkg.headerFooter?.showPageNumber) {
    if (footerChildren.length > 0) footerChildren.push(new docx.TextRun({ text: '  ·  ', color: wordColor, font: bodyFont, size: 18 }));
    footerChildren.push(new docx.TextRun({ text: '第 ', color: wordColor, font: bodyFont, size: 18 }));
    footerChildren.push(new docx.TextRun({ children: [docx.PageNumber.CURRENT], color: wordColor, font: bodyFont, size: 18 }));
    footerChildren.push(new docx.TextRun({ text: ' 页', color: wordColor, font: bodyFont, size: 18 }));
  }
  const pageSize = style?.pageSize === 'A3'
    ? { width: 16838, height: 23811 }
    : { width: 11906, height: 16838 };
  const millimetersToTwips = (value: number | undefined, fallback: number) => Math.round((value ?? fallback) * 56.6929);
  const document = new docx.Document({
    creator: 'Physics Vault',
    title: pkg.title,
    description: pkg.subtitle,
    styles: {
      default: {
        document: {
          run: { font: bodyFont, size: bodySize, color: wordColor },
          paragraph: { spacing: { line: lineSpacing, after: 0 } },
        },
      },
      paragraphStyles: [
        {
          id: 'Title',
          name: 'Title',
          basedOn: 'Normal',
          next: 'Normal',
          quickFormat: true,
          run: { font: bodyFont, size: titleSize, bold: true, color: wordColor },
          paragraph: { alignment: docx.AlignmentType.CENTER, spacing: { before: 0, after: 160 }, keepNext: true },
        },
        {
          id: 'Heading2',
          name: 'Heading 2',
          basedOn: 'Normal',
          next: 'Normal',
          quickFormat: true,
          run: { font: bodyFont, size: smallTitleSize, bold: true, color: wordColor },
          paragraph: { spacing: { before: 220, after: 90 }, keepNext: true },
        },
      ],
    },
    sections: [{
      properties: {
        page: {
          size: {
            ...pageSize,
            orientation: style?.pageOrientation === 'landscape' ? docx.PageOrientation.LANDSCAPE : docx.PageOrientation.PORTRAIT,
          },
          margin: {
            top: millimetersToTwips(style?.pageMarginTop, 18),
            bottom: millimetersToTwips(style?.pageMarginBottom, 18),
            left: millimetersToTwips(Math.max(24, style?.pageMarginLeft || 24), 24),
            right: millimetersToTwips(Math.max(24, style?.pageMarginRight || 24), 24),
            header: 520,
            footer: 520,
          },
        },
        column: style?.layoutMode === 'paged-double'
          ? { count: 2, space: 680, separate: true, equalWidth: true }
          : { count: 1 },
      },
      headers: headerText ? { default: new docx.Header({ children: [new docx.Paragraph({ alignment: toDocxAlignment(pkg.headerFooter?.headerAlign || 'center', docx.AlignmentType) as never, children: [new docx.TextRun({ text: headerText, font: bodyFont, size: 18, color: wordColor })] })] }) } : undefined,
      footers: footerChildren.length > 0 ? { default: new docx.Footer({ children: [new docx.Paragraph({ alignment: toDocxAlignment(pkg.headerFooter?.footerAlign || 'center', docx.AlignmentType) as never, children: footerChildren as never })] }) } : undefined,
      children,
    }],
  });
  const blob = await docx.Packer.toBlob(document);
  if (options.download !== false) {
    triggerDownload(blob, `${cleanFileName(pkg.title, '物理学案')}.docx`, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
  }
  return blob;
}

function addFooter(slide: PptxGenJS.Slide, pkg: LessonPackage, page: number): void {
  slide.addShape('line', { x: 0.5, y: 7.06, w: 12.33, h: 0, line: { color: COLORS.line, width: 0.7 } });
  slide.addText(pkg.title || 'Physics Vault', { x: 0.55, y: 7.13, w: 4, h: 0.18, fontFace: 'Aptos', fontSize: 7.5, color: COLORS.muted, margin: 0 });
  slide.addText(String(page), { x: 12.25, y: 7.13, w: 0.35, h: 0.18, align: 'right', fontFace: 'Aptos', fontSize: 7.5, color: COLORS.muted, margin: 0 });
}

function addSlideTitle(slide: PptxGenJS.Slide, title: string, eyebrow: string): void {
  slide.background = { color: COLORS.paper };
  slide.addShape('rect', { x: 0, y: 0, w: 13.333, h: 0.16, line: { color: COLORS.blue, transparency: 100 }, fill: { color: COLORS.blue } });
  slide.addText(eyebrow, { x: 0.6, y: 0.48, w: 4.8, h: 0.24, fontFace: 'Aptos', fontSize: 9, bold: true, color: COLORS.blue, margin: 0 });
  slide.addText(title, { x: 0.6, y: 0.83, w: 12.1, h: 0.55, fontFace: 'Microsoft YaHei', fontSize: 25, bold: true, color: COLORS.ink, margin: 0 });
}

function asBullets(values: string[], max = 7): string[] {
  return values.slice(0, max).map((value) => `• ${value}`);
}

function addKnowledgeSlide(slide: PptxGenJS.Slide, card: LessonKnowledgeCard, pkg: LessonPackage, page: number): void {
  addSlideTitle(slide, latexToDisplayText(card.title), 'KNOWLEDGE MAP');
  slide.addText(latexToDisplayText(card.summary), { x: 0.7, y: 1.6, w: 11.8, h: 0.62, fontFace: 'Microsoft YaHei', fontSize: 15, color: COLORS.muted, margin: 0 });
  slide.addShape('roundRect', { x: 0.7, y: 2.5, w: 11.9, h: 3.82, rectRadius: 0.08, line: { color: COLORS.line, width: 1 }, fill: { color: 'FFFFFF' } });
  slide.addText(asBullets(card.points.map(latexToDisplayText)).join('\n'), { x: 1.05, y: 2.9, w: 11.1, h: 2.9, fontFace: 'Microsoft YaHei', fontSize: 18, color: COLORS.ink, margin: 0.02 });
  addFooter(slide, pkg, page);
}

function addTextSlide(slide: PptxGenJS.Slide, title: string, content: string, pkg: LessonPackage, page: number): void {
  addSlideTitle(slide, latexToDisplayText(title), 'TEACHING FLOW');
  slide.addShape('roundRect', { x: 0.7, y: 1.75, w: 11.9, h: 4.5, rectRadius: 0.08, line: { color: COLORS.line, width: 1 }, fill: { color: 'FFFFFF' } });
  slide.addText(asBullets(content.split('\n').map((line) => latexToDisplayText(line.trim())).filter(Boolean)).join('\n'), { x: 1.1, y: 2.2, w: 11.1, h: 3.5, fontFace: 'Microsoft YaHei', fontSize: 20, color: COLORS.ink, margin: 0.03 });
  addFooter(slide, pkg, page);
}

async function addFormulaStrip(slide: PptxGenJS.Slide, source: string, y: number): Promise<void> {
  const formulas = extractLatexFragments(source);
  if (formulas.length === 0) return;

  slide.addText('关键公式', { x: 0.98, y, w: 0.86, h: 0.24, fontFace: 'Microsoft YaHei', fontSize: 10, bold: true, color: COLORS.blue, margin: 0 });
  let x = 1.9;
  for (const formula of formulas) {
    const data = await latexToSvgDataUri(formula);
    if (!data) continue;
    const width = Math.min(3.2, Math.max(0.8, 0.42 + formula.length * 0.075));
    if (x + width > 12.15) break;
    slide.addImage({ data, x, y: y - 0.04, w: width, h: 0.34 });
    x += width + 0.22;
  }
}

async function addQuestionSlide(slide: PptxGenJS.Slide, question: Question, index: number, pkg: LessonPackage, page: number): Promise<void> {
  addSlideTitle(slide, `练习 ${index}`, questionKnowledge(question));
  slide.addShape('roundRect', { x: 0.66, y: 1.55, w: 12, h: 3.45, rectRadius: 0.06, line: { color: COLORS.line, width: 1 }, fill: { color: 'FFFFFF' } });
  const figureData = question.figures?.[0] ? await fetchFigureDataUri(question.figures[0].local_path) : null;
  const textWidth = figureData ? 7.3 : 11.35;
  slide.addText(latexToDisplayText(question.title), { x: 0.98, y: 1.88, w: textWidth, h: 1.45, fontFace: 'Microsoft YaHei', fontSize: 18, bold: true, color: COLORS.ink, margin: 0.02 });
  const optionText = question.options?.map((option) => `${option.opt}. ${latexToDisplayText(option.content)}`) || [];
  if (figureData) slide.addImage({ data: figureData, x: 8.75, y: 1.86, w: 3.2, h: 2.45, sizing: { type: 'contain', x: 8.75, y: 1.86, w: 3.2, h: 2.45 } });
  if (optionText.length > 0) slide.addText(optionText.join('\n'), { x: 1.02, y: 3.45, w: 11.2, h: 1.2, fontFace: 'Microsoft YaHei', fontSize: 14, color: COLORS.ink, margin: 0.02 });
  slide.addText(`来源：${getQuestionSourceLabel(question, '未标注来源')}`, { x: 0.98, y: 4.7, w: 11.2, h: 0.2, fontFace: 'SimSun', fontSize: 9, color: COLORS.muted, margin: 0.02, breakLine: false });
  await addFormulaStrip(slide, [question.title, ...(question.options || []).map((option) => option.content)].join('\n'), 3.05);
  addFooter(slide, pkg, page);
}

async function addAnswerSlide(slide: PptxGenJS.Slide, question: Question, index: number, pkg: LessonPackage, page: number, options: LessonExportOptions): Promise<void> {
  addSlideTitle(slide, `练习 ${index} · 讲解`, questionKnowledge(question));
  slide.addShape('roundRect', { x: 0.7, y: 1.62, w: 11.9, h: 4.72, rectRadius: 0.06, line: { color: 'BCE5D8', width: 1 }, fill: { color: 'F1FAF6' } });
  const fragments = [options.includeAnswers && question.answer ? `参考答案\n${latexToDisplayText(question.answer)}` : '', options.includeAnalysis && question.analysis ? `思路解析\n${latexToDisplayText(question.analysis)}` : ''].filter(Boolean);
  if (fragments.length > 0) {
    slide.addText(fragments.join('\n\n'), { x: 1.08, y: 2.0, w: 11, h: 3.8, fontFace: 'Microsoft YaHei', fontSize: 18, color: COLORS.answer, margin: 0.02 });
  }
  await addFormulaStrip(slide, [question.answer, question.analysis].filter(Boolean).join('\n'), 5.92);
  addFooter(slide, pkg, page);
}

export async function exportLessonAsPptx(pkg: LessonPackage, options: LessonExportOptions): Promise<void> {
  assertLessonPackageExportable(pkg);
  pkg = normalizeLessonPackageForOutput(pkg);
  const { default: PptxGenJS } = await import('pptxgenjs');
  const pptx = new PptxGenJS();
  pptx.layout = 'LAYOUT_WIDE';
  pptx.author = 'Physics Vault';
  pptx.company = 'Physics Vault';
  pptx.subject = pkg.subtitle;
  pptx.title = pkg.title;
  pptx.theme = { headFontFace: 'Microsoft YaHei', bodyFontFace: 'Microsoft YaHei' };
  const cover = pptx.addSlide();
  cover.background = { color: COLORS.paper };
  cover.addShape('rect', { x: 0, y: 0, w: 13.333, h: 7.5, line: { color: COLORS.blue, transparency: 100 }, fill: { color: COLORS.blueSoft } });
  cover.addShape('rect', { x: 0, y: 0, w: 0.22, h: 7.5, line: { color: COLORS.blue, transparency: 100 }, fill: { color: COLORS.blue } });
  cover.addText('PHYSICS VAULT · CLASSROOM KIT', { x: 0.92, y: 1.24, w: 7.4, h: 0.25, fontFace: 'Aptos', fontSize: 10, bold: true, color: COLORS.blue, margin: 0 });
  cover.addText(pkg.title || '未命名教学包', { x: 0.88, y: 1.82, w: 10.9, h: 1.05, fontFace: 'Microsoft YaHei', fontSize: 34, bold: true, color: COLORS.ink, margin: 0 });
  cover.addText(pkg.subtitle || '从题库到课堂的一套教学材料', { x: 0.92, y: 3.18, w: 9.6, h: 0.42, fontFace: 'Microsoft YaHei', fontSize: 17, color: COLORS.muted, margin: 0 });
  cover.addText(`${pkg.questions.length} 道题目  ·  ${pkg.nodes.length} 个教学节点`, { x: 0.92, y: 5.85, w: 4.5, h: 0.28, fontFace: 'Microsoft YaHei', fontSize: 12, color: COLORS.muted, margin: 0 });
  const questionMap = new Map(pkg.questions.map((question) => [question.question_id, question]));
  const knowledgeMap = new Map(pkg.knowledgeCards.map((card) => [card.id, card]));
  const textMap = new Map(pkg.textBlocks.map((block) => [block.id, block]));
  let page = 1;
  let questionIndex = 0;
  for (const node of pkg.nodes) {
    if (node.type === 'page_break') continue;
    const slide = pptx.addSlide();
    page += 1;
    if (node.type === 'knowledge') {
      const card = knowledgeMap.get(node.knowledgeId);
      if (card) addKnowledgeSlide(slide, card, pkg, page);
      continue;
    }
    if (node.type === 'text') {
      const block = textMap.get(node.textBlockId);
      if (block) addTextSlide(slide, block.title, block.content, pkg, page);
      continue;
    }
    const question = questionMap.get(node.questionId);
    if (question) {
      questionIndex += 1;
      await addQuestionSlide(slide, question, questionIndex, pkg, page);
      if ((options.includeAnswers && question.answer) || (options.includeAnalysis && question.analysis)) {
        const answerSlide = pptx.addSlide();
        page += 1;
        await addAnswerSlide(answerSlide, question, questionIndex, pkg, page, options);
      }
    }
  }
  await pptx.writeFile({ fileName: `${cleanFileName(pkg.title, '物理课堂课件')}.pptx` });
}
