import { useState } from 'react';
import { Button } from '../ui/Button';
import { ChevronDown, ChevronRight, FileText, Folder, FolderPlus, MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import type { LessonFolder, SavedLessonPackageSummary } from '../../types';

interface Props {
  packages: SavedLessonPackageSummary[];
  folders?: LessonFolder[];
  activeId?: string | null;
  activeFolderId?: string | null;
  title?: string;
  emptyText?: string;
  onOpen: (id: string) => void;
  onDelete?: (id: string) => void;
  onFolderSelect?: (id: string | null) => void;
  onCreateFolder?: () => void;
  onRenameFolder?: (id: string) => void;
  onDeleteFolder?: (id: string) => void;
  onMovePackage?: (id: string, folderId: string | null) => void;
  onSaveCurrent?: () => void;
}

export default function LessonPackageTree({
  packages,
  folders = [],
  activeId,
  activeFolderId,
  title = '已保存作品',
  emptyText = '还没有保存的讲义作品',
  onOpen,
  onDelete,
  onFolderSelect,
  onCreateFolder,
  onRenameFolder,
  onDeleteFolder,
  onMovePackage,
  onSaveCurrent,
}: Props) {
  const [openFolders, setOpenFolders] = useState<Record<string, boolean>>(() => Object.fromEntries(folders.map((folder) => [folder.id, true])));
  const [menuId, setMenuId] = useState<string | null>(null);
  const unfiled = packages.filter((pkg) => !pkg.folderId);
  const folderPackages = (folderId: string) => packages.filter((pkg) => pkg.folderId === folderId);

  const renderPackage = (pkg: SavedLessonPackageSummary) => {
    const active = pkg.id === activeId;
    return (
      <div key={pkg.id} className={`group rounded-md border px-2.5 py-2 ${active ? 'border-[var(--color-accent)] bg-[var(--color-accent-soft)]' : 'border-transparent hover:border-[var(--color-border)] hover:bg-[var(--color-bg-hover)]'}`}>
        <div className="flex items-start gap-2">
          <FileText size={15} className="mt-0.5 shrink-0 text-[var(--color-accent)]" />
          <button type="button" onClick={() => onOpen(pkg.id)} className="min-w-0 flex-1 text-left">
            <div className="truncate text-xs font-semibold text-[var(--color-text-main)]">{pkg.title}</div>
            <div className="mt-1 flex gap-2 text-[10px] text-[var(--color-text-subtle)]"><span>{pkg.questionCount} 题</span><span>{pkg.nodeCount} 节点</span></div>
          </button>
          {(onMovePackage || onDelete) && (
            <button type="button" aria-label={`管理 ${pkg.title}`} title="管理文件" className="rounded p-1 text-[var(--color-text-subtle)] hover:bg-[var(--color-bg-hover)]" onClick={() => setMenuId(menuId === pkg.id ? null : pkg.id)}><MoreHorizontal size={14} /></button>
          )}
        </div>
        {menuId === pkg.id && (
          <div className="mt-2 space-y-1 border-t border-[var(--color-border)] pt-2">
            {onMovePackage && <select aria-label="移动到文件夹" className="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-card)] px-2 py-1 text-[10px]" value={pkg.folderId || ''} onChange={(event) => { onMovePackage(pkg.id, event.target.value || null); setMenuId(null); }}><option value="">未分类</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select>}
            {onDelete && <button type="button" className="flex w-full items-center gap-1 px-1 py-1 text-left text-[10px] text-[var(--color-danger)]" onClick={() => { onDelete(pkg.id); setMenuId(null); }}><Trash2 size={12} />删除讲义</button>}
          </div>
        )}
      </div>
    );
  };

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-sidebar)] p-3">
      <div className="pv-panel flex min-h-0 flex-1 flex-col p-3">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div><div className="text-sm font-semibold text-[var(--color-text-main)]">{title}</div><div className="mt-0.5 text-[10px] text-[var(--color-text-subtle)]">{packages.length} 个文件 · {folders.length} 个文件夹</div></div>
          <div className="flex items-center gap-1">
            {onCreateFolder && <button type="button" aria-label="新建文件夹" title="新建文件夹" className="rounded p-1.5 text-[var(--color-accent)] hover:bg-[var(--color-bg-hover)]" onClick={onCreateFolder}><FolderPlus size={16} /></button>}
            {onSaveCurrent && <Button size="sm" onClick={onSaveCurrent}>保存当前</Button>}
          </div>
        </div>
        <div className="mb-2 flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]"><Folder size={15} className="text-[var(--color-accent)]" /><button type="button" className="flex-1 text-left" onClick={() => onFolderSelect?.(null)}>全部讲义</button><span className="text-[10px] text-[var(--color-text-subtle)]">{packages.length}</span></div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto">
          {folders.map((folder) => {
            const children = folderPackages(folder.id);
            const isOpen = openFolders[folder.id] ?? true;
            return <div key={folder.id}>
              <div className={`flex items-center gap-1 rounded-md px-1.5 py-1.5 ${activeFolderId === folder.id ? 'bg-[var(--color-accent-soft)]' : 'hover:bg-[var(--color-bg-hover)]'}`}>
                <button type="button" aria-label={isOpen ? '收起文件夹' : '展开文件夹'} className="p-0.5 text-[var(--color-text-subtle)]" onClick={() => setOpenFolders((prev) => ({ ...prev, [folder.id]: !isOpen }))}>{isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}</button>
                <Folder size={15} className="text-[var(--color-orange)]" /><button type="button" className="min-w-0 flex-1 truncate text-left text-xs font-semibold text-[var(--color-text-secondary)]" onClick={() => onFolderSelect?.(folder.id)}>{folder.name}</button><span className="text-[10px] text-[var(--color-text-subtle)]">{children.length}</span>
                {(onRenameFolder || onDeleteFolder) && <button type="button" aria-label={`管理文件夹 ${folder.name}`} title="管理文件夹" className="rounded p-1 text-[var(--color-text-subtle)] hover:bg-[var(--color-bg-card)]" onClick={() => setMenuId(menuId === folder.id ? null : folder.id)}><MoreHorizontal size={13} /></button>}
              </div>
              {menuId === folder.id && <div className="ml-7 flex gap-2 px-1 pb-1 text-[10px]"><button type="button" className="flex items-center gap-1 text-[var(--color-text-muted)]" onClick={() => { onRenameFolder?.(folder.id); setMenuId(null); }}><Pencil size={11} />重命名</button>{onDeleteFolder && <button type="button" className="flex items-center gap-1 text-[var(--color-danger)]" onClick={() => { onDeleteFolder(folder.id); setMenuId(null); }}><Trash2 size={11} />删除</button>}</div>}
              {isOpen && <div className="ml-4 space-y-0.5 border-l border-[var(--color-border)] pl-1">{children.map(renderPackage)}{children.length === 0 && <div className="px-2 py-1 text-[10px] text-[var(--color-text-subtle)]">空文件夹</div>}</div>}
            </div>;
          })}
          <div className="mt-2 border-t border-[var(--color-border)] pt-2"><div className="mb-1 px-2 text-[10px] font-semibold text-[var(--color-text-subtle)]">未分类</div>{unfiled.map(renderPackage)}{packages.length === 0 && <div className="rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-bg-hover)] px-3 py-5 text-xs text-[var(--color-text-subtle)]">{emptyText}</div>}</div>
        </div>
      </div>
    </aside>
  );
}
