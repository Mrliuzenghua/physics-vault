import { DEFAULT_CONFIG as DEFAULT_HEADER_FOOTER } from '../components/handout/HandoutHeaderFooterConfigPanel';
import { DEFAULT_STYLE_CONFIG } from '../components/handout/handoutStylePresets';
import type { LessonPackage, Question } from '../types';
import type {
  LessonDocumentAsset,
  LessonDocumentNode,
  LessonDocumentV2,
} from '../types/lessonDocument';
import { LESSON_DOCUMENT_SCHEMA } from '../types/lessonDocument';
import { isRecord, readJsonStorage, writeJsonStorage } from './safeStorage.ts';

const CURRENT_DOCUMENT_KEY = 'physics-vault.current-lesson-document.v2';

function plainTextDocument(value: string): Record<string, unknown> {
  const paragraphs = String(value || '').split(/\n+/).map((text) => ({
    type: 'paragraph',
    content: text ? [{ type: 'text', text }] : [],
  }));
  return { type: 'doc', content: paragraphs.length > 0 ? paragraphs : [{ type: 'paragraph' }] };
}

function questionWithOverrides(node: Extract<LessonDocumentNode, { type: 'question' }>): Question {
  return { ...node.snapshot, ...node.overrides, question_id: node.questionId };
}

function normalizeDisplayScale(value: unknown): number {
  const scale = Number(value);
  return Number.isFinite(scale) ? Math.min(100, Math.max(25, Math.round(scale))) : 60;
}

export function lessonPackageToDocumentV2(pkg: LessonPackage, revision = 0): LessonDocumentV2 {
  const questionMap = new Map(pkg.questions.map((question) => [question.question_id, question]));
  const knowledgeMap = new Map(pkg.knowledgeCards.map((card) => [card.id, card]));
  const textMap = new Map(pkg.textBlocks.map((block) => [block.id, block]));
  const assets: Record<string, LessonDocumentAsset> = {};

  for (const question of pkg.questions) {
    for (const figure of question.figures || []) {
      assets[figure.fig_uuid] = {
        id: figure.fig_uuid,
        kind: 'figure',
        questionId: question.question_id,
        src: figure.local_path || undefined,
        displayScale: normalizeDisplayScale(figure.display_scale),
        metadata: { ...figure },
      };
    }
  }

  const nodes = pkg.nodes.flatMap<LessonDocumentNode>((node) => {
    if (node.type === 'question') {
      const question = questionMap.get(node.questionId);
      return question ? [{ id: node.id, type: 'question', questionId: node.questionId, snapshot: question, overrides: {} }] : [];
    }
    if (node.type === 'knowledge') {
      const card = knowledgeMap.get(node.knowledgeId);
      return card ? [{
        id: node.id,
        type: 'knowledgeCard',
        knowledgeId: card.id,
        title: card.title,
        content: card.content,
        summary: card.summary,
        points: card.points,
        relatedQuestionIds: card.relatedQuestionIds,
      }] : [];
    }
    if (node.type === 'text') {
      const block = textMap.get(node.textBlockId);
      return block ? [{
        id: node.id,
        type: 'richText',
        title: block.title,
        content: block.document || plainTextDocument(block.content),
        plainText: block.content,
        blockKind: block.blockKind,
        style: block.style,
      }] : [];
    }
    return [{ id: node.id, type: 'pageBreak', title: node.title }];
  });

  return {
    schema: LESSON_DOCUMENT_SCHEMA,
    id: pkg.id,
    revision,
    meta: { title: pkg.title, subtitle: pkg.subtitle, source: pkg.source },
    nodes,
    assets,
    pageSetup: {
      style: pkg.styleConfig || DEFAULT_STYLE_CONFIG,
      headerFooter: pkg.headerFooter || DEFAULT_HEADER_FOOTER,
      slideTemplate: pkg.slideTemplate || 'teach_practice_teach',
    },
    outputProfiles: {
      student: { showAnswers: false, showAnalysis: false },
      teacher: { showAnswers: true, showAnalysis: true },
    },
    createdAt: pkg.createdAt,
    updatedAt: pkg.updatedAt,
  };
}

export function lessonDocumentToLessonPackage(document: LessonDocumentV2): LessonPackage {
  const questions: Question[] = [];
  const knowledgeCards: LessonPackage['knowledgeCards'] = [];
  const textBlocks: LessonPackage['textBlocks'] = [];
  const nodes: LessonPackage['nodes'] = [];

  for (const node of document.nodes) {
    if (node.type === 'question') {
      questions.push(questionWithOverrides(node));
      nodes.push({ type: 'question', id: node.id, questionId: node.questionId });
    } else if (node.type === 'knowledgeCard') {
      knowledgeCards.push({
        id: node.knowledgeId,
        title: node.title,
        content: node.content,
        summary: node.summary,
        points: node.points,
        relatedQuestionIds: node.relatedQuestionIds,
      });
      nodes.push({ type: 'knowledge', id: node.id, knowledgeId: node.knowledgeId });
    } else if (node.type === 'richText') {
      textBlocks.push({ id: node.id, title: node.title, content: node.plainText, document: node.content, blockKind: node.blockKind, style: node.style });
      nodes.push({ type: 'text', id: node.id, textBlockId: node.id });
    } else {
      nodes.push({ type: 'page_break', id: node.id, title: node.title });
    }
  }

  return {
    id: document.id,
    title: document.meta.title,
    subtitle: document.meta.subtitle,
    source: document.meta.source,
    questions,
    knowledgeCards,
    textBlocks,
    nodes,
    headerFooter: document.pageSetup.headerFooter,
    styleConfig: document.pageSetup.style,
    slideTemplate: document.pageSetup.slideTemplate,
    createdAt: document.createdAt,
    updatedAt: document.updatedAt,
  };
}

export function saveCurrentLessonDocument(document: LessonDocumentV2): void {
  writeJsonStorage(CURRENT_DOCUMENT_KEY, document);
}

export function loadCurrentLessonDocument(): LessonDocumentV2 | null {
  const value = readJsonStorage<unknown>(CURRENT_DOCUMENT_KEY, null);
  return isRecord(value)
    && value.schema === LESSON_DOCUMENT_SCHEMA
    && typeof value.id === 'string'
    && typeof value.revision === 'number'
    && isRecord(value.meta)
    && Array.isArray(value.nodes)
    && isRecord(value.assets)
    && isRecord(value.pageSetup)
    ? value as unknown as LessonDocumentV2
    : null;
}
