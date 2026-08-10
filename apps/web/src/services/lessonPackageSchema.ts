import { z } from 'zod';
import type { LessonPackage, SavedLessonPackageSummary } from '../types';

const lessonNodeSchema = z.object({
  id: z.string().min(1),
  type: z.enum(['question', 'knowledge', 'text', 'page_break']),
}).passthrough();

export const lessonPackageSchema = z.object({
  id: z.string().min(1),
  title: z.string(),
  subtitle: z.string(),
  source: z.enum(['compose', 'basket', 'template', 'ai']),
  questions: z.array(z.record(z.string(), z.unknown())),
  knowledgeCards: z.array(z.object({
    id: z.string().min(1),
    title: z.string(),
    summary: z.string(),
    points: z.array(z.string()),
    relatedQuestionIds: z.array(z.string()),
  })),
  textBlocks: z.array(z.object({
    id: z.string().min(1),
    title: z.string(),
    content: z.string(),
  }).passthrough()),
  nodes: z.array(lessonNodeSchema),
  createdAt: z.string(),
  updatedAt: z.string(),
}).passthrough();

const savedPackageSummarySchema = z.object({
  id: z.string().min(1),
  title: z.string(),
  subtitle: z.string(),
  updatedAt: z.string(),
  questionCount: z.number(),
  knowledgeCount: z.number(),
  nodeCount: z.number(),
  folderId: z.string().nullable().optional(),
});

export function parseLessonPackage(value: unknown): LessonPackage | null {
  const result = lessonPackageSchema.safeParse(value);
  return result.success ? result.data as unknown as LessonPackage : null;
}

export function parseLessonPackageList(value: unknown): LessonPackage[] {
  const result = z.array(lessonPackageSchema).safeParse(value);
  return result.success ? result.data as unknown as LessonPackage[] : [];
}

export function parseSavedLessonPackageSummaryList(value: unknown): SavedLessonPackageSummary[] {
  const result = z.array(savedPackageSummarySchema).safeParse(value);
  return result.success ? result.data : [];
}
