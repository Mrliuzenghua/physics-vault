export interface ClassroomReflection {
  id: string;
  projectId: string;
  projectTitle?: string;
  rating: 1 | 2 | 3 | 4 | 5;
  completed: boolean;
  highlights: string;
  followUp: string;
  completedFollowUpTaskIds?: string[];
  attendedPages: number;
  createdAt: string;
  updatedAt: string;
  remoteUpdatedAt?: string;
  remoteSyncState?: 'pending' | 'synced' | 'conflict' | 'offline';
}

export interface ClassroomReflectionAdvice {
  reply: string;
  aiUsed: boolean;
  warnings: string[];
}

export interface ClassroomFollowUpTask {
  id: string;
  projectId: string;
  projectTitle: string;
  title: string;
  detail: string;
  priority: 'high' | 'medium' | 'low';
}

const STORAGE_PREFIX = 'physics-vault.classroom-reflections.';
const TASK_STATE_KEY = 'physics-vault.classroom-follow-up-task-state.v1';

function storageKey(projectId: string) {
  return `${STORAGE_PREFIX}${projectId}`;
}

function getStorage(): Storage | null {
  return typeof window === 'undefined' ? null : window.localStorage;
}

function loadTaskState(): Record<string, boolean> {
  const storage = getStorage();
  if (!storage) return {};
  try {
    const parsed = JSON.parse(storage.getItem(TASK_STATE_KEY) || '{}');
    if (!parsed || typeof parsed !== 'object') return {};
    return Object.fromEntries(Object.entries(parsed).filter(([, value]) => typeof value === 'boolean')) as Record<string, boolean>;
  } catch {
    return {};
  }
}

export function setClassroomFollowUpTaskCompleted(taskId: string, completed: boolean): void {
  const storage = getStorage();
  if (!storage || !taskId) return;
  const state = loadTaskState();
  if (completed) state[taskId] = true;
  else delete state[taskId];
  storage.setItem(TASK_STATE_KEY, JSON.stringify(state));

  const reflection = listClassroomReflections().find((item) => taskId.startsWith(`${item.id}-`));
  if (!reflection) return;
  const completedIds = new Set(reflection.completedFollowUpTaskIds || []);
  if (completed) completedIds.add(taskId);
  else completedIds.delete(taskId);
  const next = {
    ...reflection,
    completedFollowUpTaskIds: [...completedIds],
    updatedAt: new Date().toISOString(),
    remoteSyncState: 'pending' as const,
  };
  saveClassroomReflection(next);
  void syncClassroomReflection(next);
}

export function loadClassroomReflections(projectId: string): ClassroomReflection[] {
  const storage = getStorage();
  if (!storage) return [];
  try {
    const raw = storage.getItem(storageKey(projectId));
    const parsed = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is ClassroomReflection => Boolean(
      item && typeof item === 'object' && item.projectId === projectId && typeof item.id === 'string',
    ));
  } catch {
    return [];
  }
}

export function loadLatestClassroomReflection(projectId: string): ClassroomReflection | null {
  return loadClassroomReflections(projectId).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))[0] || null;
}

export function listClassroomReflections(): ClassroomReflection[] {
  const storage = getStorage();
  if (!storage) return [];
  const reflections: ClassroomReflection[] = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (!key?.startsWith(STORAGE_PREFIX)) continue;
    const projectId = key.slice(STORAGE_PREFIX.length);
    reflections.push(...loadClassroomReflections(projectId));
  }
  return reflections.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export function buildClassroomFollowUpTasks(reflections: ClassroomReflection[]): ClassroomFollowUpTask[] {
  const tasks: ClassroomFollowUpTask[] = [];
  const taskState = loadTaskState();
  for (const reflection of reflections) {
    const projectTitle = reflection.projectTitle || reflection.projectId;
    if (!reflection.completed) {
      tasks.push({ id: `${reflection.id}-complete`, projectId: reflection.projectId, projectTitle, title: '补齐未完成内容', detail: '回到课件或讲义，补齐本次未完成的核心知识点。', priority: 'high' });
    }
    if (reflection.rating <= 2) {
      tasks.push({ id: `${reflection.id}-review`, projectId: reflection.projectId, projectTitle, title: '复查授课节奏', detail: '本次评分偏低，建议重新检查难点讲解、课堂节奏和互动安排。', priority: 'high' });
    } else if (reflection.rating === 3) {
      tasks.push({ id: `${reflection.id}-practice`, projectId: reflection.projectId, projectTitle, title: '补充针对性练习', detail: '本次授课基本完成，建议增加一道针对卡顿点的练习题。', priority: 'medium' });
    }
    if (reflection.followUp.trim()) {
      tasks.push({ id: `${reflection.id}-follow-up`, projectId: reflection.projectId, projectTitle, title: '执行复盘行动', detail: reflection.followUp.trim(), priority: 'medium' });
    }
  }
  const completedRemoteIds = new Set(reflections.flatMap((reflection) => reflection.completedFollowUpTaskIds || []));
  return tasks.filter((task) => !taskState[task.id] && !completedRemoteIds.has(task.id)).slice(0, 12);
}

export function saveClassroomReflection(reflection: ClassroomReflection): ClassroomReflection[] {
  const reflections = loadClassroomReflections(reflection.projectId);
  const index = reflections.findIndex((item) => item.id === reflection.id);
  if (index >= 0) reflections[index] = reflection;
  else reflections.unshift(reflection);
  getStorage()?.setItem(storageKey(reflection.projectId), JSON.stringify(reflections.slice(0, 30)));
  return reflections;
}

function mergeRemoteReflection(reflection: ClassroomReflection): void {
  const local = loadClassroomReflections(reflection.projectId);
  const index = local.findIndex((item) => item.id === reflection.id);
  const existing = index >= 0 ? local[index] : null;
  if (existing && existing.updatedAt > reflection.updatedAt && existing.remoteSyncState === 'pending') return;
  const merged = { ...reflection, remoteUpdatedAt: reflection.updatedAt, remoteSyncState: 'synced' as const };
  if (index >= 0) local[index] = { ...local[index], ...merged };
  else local.unshift(merged);
  getStorage()?.setItem(storageKey(reflection.projectId), JSON.stringify(local.slice(0, 30)));
}

export async function syncClassroomReflection(reflection: ClassroomReflection): Promise<ClassroomReflection | null> {
  try {
    const { saveLessonReflection } = await import('./api.ts');
    const remote = await saveLessonReflection(reflection, reflection.remoteUpdatedAt || null);
    mergeRemoteReflection(remote);
    return remote;
  } catch (error: unknown) {
    const local = loadClassroomReflections(reflection.projectId);
    const index = local.findIndex((item) => item.id === reflection.id);
    if (index >= 0) {
      local[index] = {
        ...local[index],
        remoteSyncState: error instanceof Error && /409|conflict|冲突/i.test(error.message) ? 'conflict' : 'offline',
      };
      getStorage()?.setItem(storageKey(reflection.projectId), JSON.stringify(local.slice(0, 30)));
    }
    return null;
  }
}

export async function hydrateClassroomReflections(projectId: string): Promise<ClassroomReflection[]> {
  try {
    const { listLessonReflections } = await import('./api.ts');
    const remote = await listLessonReflections(projectId);
    remote.forEach(mergeRemoteReflection);
    return loadClassroomReflections(projectId);
  } catch {
    return loadClassroomReflections(projectId);
  }
}

export async function hydrateAllClassroomReflections(): Promise<ClassroomReflection[]> {
  try {
    const { listLessonReflections } = await import('./api.ts');
    const remote = await listLessonReflections();
    remote.forEach(mergeRemoteReflection);
    return listClassroomReflections();
  } catch {
    return listClassroomReflections();
  }
}

function buildLocalAdvice(reflection: ClassroomReflection): string {
  const parts = [
    reflection.rating <= 2 ? '本次授课评分偏低，建议优先复查节奏、难点讲解和学生反馈。' : reflection.rating === 3 ? '本次授课整体完成，建议针对卡顿环节做一次小幅调整。' : '本次授课整体顺利，可以保留有效的讲解和互动方式。',
    reflection.completed ? '计划内容已完成，下次可以增加针对性练习或拓展。' : '计划内容未完全完成，下次建议先补齐核心知识点，再压缩非关键拓展。',
  ];
  if (reflection.followUp.trim()) parts.push(`下次行动：${reflection.followUp.trim()}`);
  return parts.join('\n');
}

export async function generateClassroomReflectionAdvice(
  reflection: ClassroomReflection,
  projectTitle: string,
): Promise<ClassroomReflectionAdvice> {
  const prompt = [
    `教学项目：${projectTitle}`,
    `授课评分：${reflection.rating}/5`,
    `是否完成计划：${reflection.completed ? '是' : '否'}`,
    `已授课页数：${reflection.attendedPages}`,
    `课堂亮点：${reflection.highlights || '未填写'}`,
    `下次改进：${reflection.followUp || '未填写'}`,
  ].join('\n');
  try {
    const { sendAiAssistantChat } = await import('./api.ts');
    const result = await sendAiAssistantChat([
      { role: 'system', content: '你是教学复盘助手。请基于授课记录，输出简洁的“问题诊断、保留做法、下次行动、建议补充题型”四点建议，使用中文，不要编造学生数据。' },
      { role: 'user', content: prompt },
    ], { query: '生成课后复盘建议', contextLimit: 1, temperature: 0.25 });
    return { reply: result.reply, aiUsed: result.ai_used, warnings: result.warnings || [] };
  } catch {
    return { reply: buildLocalAdvice(reflection), aiUsed: false, warnings: ['AI 服务暂不可用，已切换为本地规则建议。'] };
  }
}
