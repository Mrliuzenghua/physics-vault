import type {
  HandoutHeaderFooterConfig,
  HandoutStyleConfig,
  HandoutTextBlockKind,
  HandoutTextBlockStyle,
  Question,
} from './index';
import type { SlideDeckTemplate } from './slides';

export const LESSON_DOCUMENT_SCHEMA = 'lesson-document/v2' as const;

export interface LessonDocumentMeta {
  title: string;
  subtitle: string;
  source: 'compose' | 'basket' | 'template' | 'ai';
}

export interface LessonDocumentQuestionNode {
  id: string;
  type: 'question';
  questionId: string;
  snapshot: Question;
  overrides: Partial<Question>;
}

export interface LessonDocumentRichTextNode {
  id: string;
  type: 'richText';
  title: string;
  content: Record<string, unknown>;
  plainText: string;
  blockKind?: HandoutTextBlockKind;
  style?: HandoutTextBlockStyle;
}

export interface LessonDocumentKnowledgeNode {
  id: string;
  type: 'knowledgeCard';
  knowledgeId: string;
  title: string;
  summary: string;
  points: string[];
  relatedQuestionIds: string[];
}

export interface LessonDocumentPageBreakNode {
  id: string;
  type: 'pageBreak';
  title?: string;
}

export type LessonDocumentNode =
  | LessonDocumentQuestionNode
  | LessonDocumentRichTextNode
  | LessonDocumentKnowledgeNode
  | LessonDocumentPageBreakNode;

export interface LessonDocumentAsset {
  id: string;
  kind: 'figure';
  questionId: string;
  src?: string;
  displayScale: number;
  metadata: Record<string, unknown>;
}

export interface LessonDocumentPageSetup {
  style: HandoutStyleConfig;
  headerFooter: HandoutHeaderFooterConfig;
  slideTemplate: SlideDeckTemplate;
}

export interface LessonDocumentV2 {
  schema: typeof LESSON_DOCUMENT_SCHEMA;
  id: string;
  revision: number;
  meta: LessonDocumentMeta;
  nodes: LessonDocumentNode[];
  assets: Record<string, LessonDocumentAsset>;
  pageSetup: LessonDocumentPageSetup;
  outputProfiles: {
    student: { showAnswers: false; showAnalysis: false };
    teacher: { showAnswers: true; showAnalysis: true };
  };
  createdAt: string;
  updatedAt: string;
}
