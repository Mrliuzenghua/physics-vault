export type DraftSaveState = 'idle' | 'pending' | 'saving' | 'saved' | 'error';

export interface DraftSavePresentation {
  label: string;
  title: string;
  color: string;
}

export function formatDraftSavedTime(value: string | null): string | null {
  if (!value) return null;
  // Paper-draft revisions may append a short uniqueness suffix to an ISO
  // timestamp (for example `...+00:00-a1b2c3`). It is not part of the time.
  const normalized = value.replace(/-[0-9a-f]{6,}$/i, '');
  const savedAt = new Date(normalized);
  if (Number.isNaN(savedAt.getTime())) return null;
  return savedAt.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

export function getDraftSavePresentation(
  state: DraftSaveState,
  lastSavedAt: string | null,
  error: string | null,
): DraftSavePresentation {
  const savedTime = formatDraftSavedTime(lastSavedAt);
  if (state === 'idle') {
    return { label: '等待编辑', title: '开始编辑后将自动保存', color: '#7b8794' };
  }
  if (state === 'saving') {
    return { label: '正在保存…', title: '正在同步到草稿库', color: '#3984c6' };
  }
  if (state === 'saved') {
    const label = savedTime ? `已保存 ${savedTime}` : '已保存';
    return { label, title: savedTime ? `最近保存于 ${savedTime}` : '已同步到草稿库', color: '#2f9e68' };
  }
  if (state === 'error') {
    return { label: '保存失败', title: error || '保存失败，可点击“重试保存”再次同步', color: '#c84545' };
  }
  return { label: '有未保存更改', title: '停止编辑后将自动保存', color: '#c47716' };
}
