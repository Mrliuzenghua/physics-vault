import type { HandoutItem, LessonPackage, Question } from '../types';
import type {
  LessonDocumentPageSetup,
  LessonDocumentV2,
} from '../types/lessonDocument';
import type { SlideDeck } from '../types/slides';
import { lessonDocumentToLessonPackage, lessonPackageToDocumentV2 } from './lessonDocument';
import { buildSlideDeckFromLessonPackage } from './lessonPackage';

export type LessonLayoutBlock =
  | { id: string; type: 'question'; question: Question }
  | {
      id: string;
      type: 'knowledge';
      knowledgeId: string;
      title: string;
      content?: string;
      summary: string;
      points: string[];
      relatedQuestionIds: string[];
    }
  | {
      id: string;
      type: 'text';
      title: string;
      content: string;
      document: Record<string, unknown>;
      blockKind?: LessonPackage['textBlocks'][number]['blockKind'];
      style?: LessonPackage['textBlocks'][number]['style'];
    }
  | { id: string; type: 'page_break'; title?: string };

/** Canonical, output-neutral representation consumed by every preview and exporter. */
export interface LessonLayoutModel {
  id: string;
  revision: number;
  title: string;
  subtitle: string;
  source: LessonPackage['source'];
  pageSetup: LessonDocumentPageSetup;
  blocks: LessonLayoutBlock[];
  createdAt: string;
  updatedAt: string;
}

export function buildLessonLayoutModel(document: LessonDocumentV2): LessonLayoutModel {
  return {
    id: document.id,
    revision: document.revision,
    title: document.meta.title,
    subtitle: document.meta.subtitle,
    source: document.meta.source,
    pageSetup: document.pageSetup,
    blocks: document.nodes.map((node): LessonLayoutBlock => {
      if (node.type === 'question') {
        return {
          id: node.id,
          type: 'question',
          question: { ...node.snapshot, ...node.overrides, question_id: node.questionId },
        };
      }
      if (node.type === 'knowledgeCard') {
        return {
          id: node.id,
          type: 'knowledge',
          knowledgeId: node.knowledgeId,
          title: node.title,
          content: node.content,
          summary: node.summary,
          points: node.points,
          relatedQuestionIds: node.relatedQuestionIds,
        };
      }
      if (node.type === 'richText') {
        return {
          id: node.id,
          type: 'text',
          title: node.title,
          content: node.plainText,
          document: node.content,
          blockKind: node.blockKind,
          style: node.style,
        };
      }
      return { id: node.id, type: 'page_break', title: node.title };
    }),
    createdAt: document.createdAt,
    updatedAt: document.updatedAt,
  };
}

export function lessonPackageToLayoutModel(pkg: LessonPackage, revision = 0): LessonLayoutModel {
  return buildLessonLayoutModel(lessonPackageToDocumentV2(pkg, revision));
}

export function layoutModelToLessonPackage(model: LessonLayoutModel): LessonPackage {
  const document = lessonPackageToDocumentV2({
    id: model.id,
    title: model.title,
    subtitle: model.subtitle,
    source: model.source,
    questions: model.blocks.flatMap((block) => block.type === 'question' ? [block.question] : []),
    knowledgeCards: model.blocks.flatMap((block) => block.type === 'knowledge' ? [{
      id: block.knowledgeId,
      title: block.title,
      content: block.content,
      summary: block.summary,
      points: block.points,
      relatedQuestionIds: block.relatedQuestionIds,
    }] : []),
    textBlocks: model.blocks.flatMap((block) => block.type === 'text' ? [{
      id: block.id,
      title: block.title,
      content: block.content,
      document: block.document,
      blockKind: block.blockKind,
      style: block.style,
    }] : []),
    nodes: model.blocks.map((block) => {
      if (block.type === 'question') return { type: 'question' as const, id: block.id, questionId: block.question.question_id };
      if (block.type === 'knowledge') return { type: 'knowledge' as const, id: block.id, knowledgeId: block.knowledgeId };
      if (block.type === 'text') return { type: 'text' as const, id: block.id, textBlockId: block.id };
      return { type: 'page_break' as const, id: block.id, title: block.title };
    }),
    headerFooter: model.pageSetup.headerFooter,
    styleConfig: model.pageSetup.style,
    slideTemplate: model.pageSetup.slideTemplate,
    createdAt: model.createdAt,
    updatedAt: model.updatedAt,
  }, model.revision);

  return lessonDocumentToLessonPackage(document);
}

export function layoutModelToHandoutItems(model: LessonLayoutModel): HandoutItem[] {
  return model.blocks.map((block): HandoutItem => {
    if (block.type === 'question') return { id: block.id, type: 'question', question: block.question };
    if (block.type === 'knowledge') return {
      id: block.id,
      type: 'knowledge',
      title: block.title,
      summary: block.summary,
      points: block.points,
    };
    if (block.type === 'text') return {
      id: block.id,
      type: 'text',
      title: block.title,
      content: block.content,
      blockKind: block.blockKind,
      style: block.style,
    };
    return { id: block.id, type: 'page_break', title: block.title };
  });
}

export function layoutModelToSlideDeck(model: LessonLayoutModel): SlideDeck {
  return buildSlideDeckFromLessonPackage(layoutModelToLessonPackage(model));
}

export function normalizeLessonPackageForOutput(pkg: LessonPackage): LessonPackage {
  return layoutModelToLessonPackage(lessonPackageToLayoutModel(pkg));
}
