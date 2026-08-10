import type {
  HandoutHeaderFooterConfig,
  HandoutStyleConfig,
  HandoutTextBlockKind,
  HandoutTextBlockStyle,
  LessonPackage,
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
  content?: string;
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

export interface SavedHandoutSummary {
  id: string;
  title: string;
  subtitle: string;
  document_kind: 'saved_handout';
  source_workbench_id: string | null;
  created_at: string;
  updated_at: string;
  question_count: number;
  knowledge_count: number;
  node_count: number;
  format_template_id: string | null;
  current_version: number;
  version_count: number;
}

export interface SavedHandoutVersion {
  /** Compatibility index for the existing Handout page state; remove after that state is typed. */
  [field: string]: unknown;
  version: number;
  version_id: string;
  created_at: string;
  title: string;
  current: boolean;
}

export interface SavedHandoutDocument {
  id: string;
  title: string;
  subtitle: string;
  document_kind: 'saved_handout';
  sourceWorkbenchId?: string | null;
  createdAt: string;
  updatedAt: string;
  formatTemplateId?: string | null;
  currentVersion: number;
  lessonPackage: LessonPackage;
  summary?: SavedHandoutSummary;
  restoredFromVersion?: number;
}

export interface SavedHandoutListResponse {
  document_kind: 'saved_handout';
  items: SavedHandoutSummary[];
}

export interface SavedHandoutVersionListResponse {
  document_kind: 'saved_handout';
  document_id: string;
  items: SavedHandoutVersion[];
}
