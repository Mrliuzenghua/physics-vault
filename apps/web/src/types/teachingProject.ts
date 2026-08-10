import type { HandoutConfig, LessonPackage } from './index';
import type { LessonDocumentV2 } from './lessonDocument';
import type { SlideDeck, SlideDeckTemplate } from './slides';

export const TEACHING_PROJECT_SCHEMA = 'teaching-project/v1' as const;

export type TeachingArtifactStatus = 'draft' | 'ready' | 'stale' | 'changed_after_publish' | 'published';

export interface HandoutArtifact {
  id: string;
  projectId: string;
  title: string;
  sourceRevision: number;
  status: TeachingArtifactStatus;
  config: HandoutConfig;
  pageBreakAfterBlockIds: string[];
  publishedSnapshot?: {
    version: number;
    publishedAt: string;
    sourceRevision: number;
    config: HandoutConfig;
    pageBreakAfterBlockIds: string[];
  };
  updatedAt: string;
}

export interface SlideArtifact {
  id: string;
  projectId: string;
  title: string;
  sourceRevision: number;
  status: TeachingArtifactStatus;
  template: SlideDeckTemplate;
  deck: SlideDeck;
  /** Last deck generated from the shared content source; manual edits are compared against it. */
  generatedDeck?: SlideDeck;
  publishedSnapshot?: {
    version: number;
    publishedAt: string;
    sourceRevision: number;
    deck: SlideDeck;
    lessonPackage: LessonPackage;
  };
  updatedAt: string;
}

export interface TeachingProject {
  schema: typeof TEACHING_PROJECT_SCHEMA;
  id: string;
  title: string;
  contentRevision: number;
  contentSignature: string;
  content: LessonDocumentV2;
  projectType?: 'exam' | 'worksheet' | 'homework' | 'lesson' | 'review' | 'classroomExample';
  handout: HandoutArtifact;
  slides: SlideArtifact;
  createdAt: string;
  updatedAt: string;
  remoteUpdatedAt?: string;
  remoteSyncState?: 'pending' | 'synced' | 'conflict' | 'offline';
}

/** Lightweight server-side projection returned by the teaching-project list endpoint. */
export interface TeachingProjectSummary {
  id: string;
  title: string;
  projectType: NonNullable<TeachingProject['projectType']>;
  status: string;
  contentRevision: number;
  questionCount: number;
  handoutStatus: string;
  slidesStatus: string;
  createdAt: string;
  updatedAt: string;
  versionCount: number;
}

export interface TeachingProjectSource {
  package: LessonPackage;
  content: LessonDocumentV2;
}
