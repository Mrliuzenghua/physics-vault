import { DEFAULT_CONFIG as DEFAULT_HEADER_FOOTER } from '../components/handout/HandoutHeaderFooterConfigPanel';
import { DEFAULT_STYLE_CONFIG } from '../components/handout/handoutStylePresets';
import type { HandoutConfig, LessonPackage } from '../types';
import type { SlideDeckTemplate } from '../types/slides';
import type { HandoutArtifact, SlideArtifact, TeachingProject } from '../types/teachingProject';
import { lessonPackageToDocumentV2 } from './lessonDocument';
import { layoutModelToSlideDeck, lessonPackageToLayoutModel } from './lessonLayoutModel';
import { fetchTeachingProject, saveTeachingProjectSnapshot } from './api';
import { isRecord, readJsonStorage, writeJsonStorage } from './safeStorage.ts';

const TEACHING_PROJECT_KEY = 'physics-vault.teaching-projects.v1';

function now(): string {
  return new Date().toISOString();
}

function makeId(prefix: string, sourceId: string): string {
  return `${prefix}-${sourceId}`;
}

function contentSignature(pkg: LessonPackage): string {
  return JSON.stringify({
    title: pkg.title,
    subtitle: pkg.subtitle,
    questions: pkg.questions,
    knowledgeCards: pkg.knowledgeCards,
    textBlocks: pkg.textBlocks,
    nodes: pkg.nodes,
  });
}

function defaultHandoutConfig(pkg: LessonPackage): HandoutConfig {
  return {
    title: pkg.title || '物理讲义',
    subtitle: pkg.subtitle || '',
    showAnswers: false,
    showAnalysis: false,
    headerFooter: pkg.headerFooter || DEFAULT_HEADER_FOOTER,
    styleConfig: pkg.styleConfig || DEFAULT_STYLE_CONFIG,
  };
}

function readProjects(): TeachingProject[] {
  const value = readJsonStorage<unknown>(TEACHING_PROJECT_KEY, []);
  return Array.isArray(value)
    ? value.filter((item): item is TeachingProject => isRecord(item) && typeof item.id === 'string')
    : [];
}

function writeProjects(projects: TeachingProject[]): void {
  writeJsonStorage(TEACHING_PROJECT_KEY, projects);
}

function syncRemoteProject(project: TeachingProject): void {
  void saveTeachingProjectSnapshot(project, project.remoteUpdatedAt || null)
    .then((remoteProject) => {
      const projects = readProjects();
      const current = projects.find((item) => item.id === project.id);
      // Do not overwrite a newer local edit with a slower network response.
      if (!current || current.updatedAt !== project.updatedAt) return;
      writeProjects(projects.map((item) => item.id === project.id
        ? {
          ...item,
          remoteUpdatedAt: remoteProject.updatedAt,
          remoteSyncState: 'synced' as const,
        }
        : item));
    })
    .catch((error: unknown) => {
      const projects = readProjects();
      const current = projects.find((item) => item.id === project.id);
      if (!current || current.updatedAt !== project.updatedAt) return;
      const remoteSyncState = error instanceof Error && /409|conflict|冲突/i.test(error.message)
        ? 'conflict'
        : 'offline';
      writeProjects(projects.map((item) => item.id === project.id ? { ...item, remoteSyncState } : item));
    });
}

function markArtifactStale<T extends HandoutArtifact | SlideArtifact>(artifact: T): T {
  const status = artifact.status === 'published' ? 'changed_after_publish' : 'stale';
  return { ...artifact, status } as T;
}

function createProject(pkg: LessonPackage): TeachingProject {
  const content = lessonPackageToDocumentV2(pkg, 0);
  const projectId = makeId('project', pkg.id);
  const createdAt = now();
  const handout: HandoutArtifact = {
    id: makeId('handout', pkg.id),
    projectId,
    title: pkg.title || '物理讲义',
    sourceRevision: content.revision,
    status: 'draft',
    config: defaultHandoutConfig(pkg),
    pageBreakAfterBlockIds: [],
    updatedAt: createdAt,
  };
  const generatedDeck = layoutModelToSlideDeck(lessonPackageToLayoutModel(pkg, content.revision));
  const slides: SlideArtifact = {
    id: makeId('slides', pkg.id),
    projectId,
    title: pkg.title || '物理课件',
    sourceRevision: content.revision,
    status: 'draft',
    template: pkg.slideTemplate || 'teach_practice_teach',
    deck: generatedDeck,
    generatedDeck,
    updatedAt: createdAt,
  };

  return {
    schema: 'teaching-project/v1',
    id: projectId,
    title: pkg.title || '未命名教学项目',
    projectType: 'lesson',
    contentRevision: content.revision,
    contentSignature: contentSignature(pkg),
    content,
    handout,
    slides,
    createdAt,
    updatedAt: createdAt,
  };
}

/**
 * Creates or refreshes the shared project shell without overwriting output edits.
 * A content change advances the source revision and leaves handout/slides stale.
 */
export function getOrCreateTeachingProject(pkg: LessonPackage): TeachingProject {
  const projects = readProjects();
  const projectId = makeId('project', pkg.id);
  const existing = projects.find((project) => project.id === projectId);
  if (!existing) {
    const created = createProject(pkg);
    saveTeachingProject(created);
    return created;
  }

  const nextSignature = contentSignature(pkg);
  if (existing.contentSignature === nextSignature) {
    // Migrate projects created by the previous local-only implementation on
    // the next visit without blocking the editor on network availability.
    if (!existing.remoteUpdatedAt) syncRemoteProject(existing);
    return existing;
  }

  const nextContent = lessonPackageToDocumentV2(pkg, existing.contentRevision + 1);

  const updated: TeachingProject = {
    ...existing,
    title: pkg.title || existing.title,
    contentRevision: nextContent.revision,
    contentSignature: nextSignature,
    content: nextContent,
    handout: markArtifactStale(existing.handout),
    slides: markArtifactStale(existing.slides),
    updatedAt: now(),
  };
  saveTeachingProject(updated);
  return updated;
}

export function saveTeachingProject(project: TeachingProject): void {
  const projects = readProjects();
  const next = { ...project, updatedAt: now(), remoteSyncState: 'pending' as const };
  const index = projects.findIndex((item) => item.id === project.id);
  if (index < 0) {
    writeProjects([...projects, next]);
    syncRemoteProject(next);
    return;
  }
  const updated = projects.slice();
  updated[index] = next;
  writeProjects(updated);
  syncRemoteProject(next);
}

/** Hydrate the local project cache from the durable server snapshot when it is newer. */
export async function hydrateTeachingProject(projectId: string): Promise<TeachingProject | null> {
  try {
    const remote = await fetchTeachingProject(projectId);
    if (!remote) return null;
    const projects = readProjects();
    const local = projects.find((item) => item.id === projectId);
    const remoteTime = Date.parse(remote.updatedAt || '');
    const localTime = Date.parse(local?.updatedAt || '');
    if (!local || (Number.isFinite(remoteTime) && remoteTime > localTime)) {
      writeProjects(projects.some((item) => item.id === projectId)
        ? projects.map((item) => item.id === projectId ? remote : item)
        : [...projects, remote]);
      return remote;
    }
    return local;
  } catch {
    return null;
  }
}

export function saveHandoutArtifact(artifact: HandoutArtifact): void {
  const projects = readProjects();
  const project = projects.find((item) => item.id === artifact.projectId);
  if (!project) return;
  saveTeachingProject({ ...project, handout: { ...artifact, updatedAt: now() } });
}

export function saveSlideArtifact(artifact: SlideArtifact): void {
  const projects = readProjects();
  const project = projects.find((item) => item.id === artifact.projectId);
  if (!project) return;
  saveTeachingProject({ ...project, slides: { ...artifact, updatedAt: now() } });
}

export function isArtifactStale(project: TeachingProject, sourceRevision: number): boolean {
  return sourceRevision !== project.contentRevision;
}

export function createHandoutArtifactConfig(pkg: LessonPackage): HandoutConfig {
  return defaultHandoutConfig(pkg);
}

export function normalizeSlideTemplate(value: unknown): SlideDeckTemplate {
  return value === 'teach_then_practice' || value === 'practice_only'
    ? value
    : 'teach_practice_teach';
}
