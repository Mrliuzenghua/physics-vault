import { useCallback, useRef, useState } from 'react';
import type { ImportFileInfo } from '../../types';

const SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.jpg', '.jpeg', '.png', '.webp', '.txt', '.html', '.md'];

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getExtension(name: string): string {
  const dot = name.lastIndexOf('.');
  if (dot < 0) return '';
  return name.slice(dot).toLowerCase();
}

function isValidExtension(ext: string): boolean {
  return SUPPORTED_EXTENSIONS.includes(ext);
}

interface Props {
  files: ImportFileInfo[];
  onAddFiles: (newFiles: File[]) => void;
  onRemoveFile: (fileId: string) => void;
}

export default function FileSelector({ files, onAddFiles, onRemoveFile }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const dragCounterRef = useRef(0);
  const [isDragging, setIsDragging] = useState(false);
  const [rejectedNames, setRejectedNames] = useState<string[]>([]);

  // ── Button click: trigger hidden file input ──
  const handleSelect = () => {
    inputRef.current?.click();
  };

  // ── Shared file processing from FileList ──
  const processFileList = useCallback(
    (fileList: FileList) => {
      const valid: File[] = [];
      const invalid: string[] = [];

      for (let i = 0; i < fileList.length; i++) {
        const file = fileList[i];
        const ext = getExtension(file.name);
        if (isValidExtension(ext)) {
          valid.push(file);
        } else {
          invalid.push(file.name);
        }
      }

      if (valid.length > 0) {
        onAddFiles(valid);
      }

      if (invalid.length > 0) {
        setRejectedNames(invalid);
        setTimeout(() => setRejectedNames([]), 4000);
      }
    },
    [onAddFiles],
  );

  // ── File input onChange ──
  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files;
    if (!selected || selected.length === 0) return;
    processFileList(selected);
    // Reset so the same file can be re-selected
    if (inputRef.current) {
      inputRef.current.value = '';
    }
  };

  // ── Drag event handlers ──
  const handleDragEnter = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    dragCounterRef.current += 1;
    if (event.dataTransfer.items && event.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  };

  const handleDragOver = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
  };

  const handleDragLeave = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    dragCounterRef.current -= 1;
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0;
      setIsDragging(false);
    }
  };

  const handleDrop = (event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
    dragCounterRef.current = 0;

    const dropped = event.dataTransfer.files;
    if (dropped.length > 0) {
      processFileList(dropped);
    }
  };

  // ── Visual states ──
  const dropZoneBorderColor = isDragging ? 'var(--color-accent)' : 'var(--color-border)';
  const dropZoneBg = isDragging ? 'var(--color-accent-light)' : 'var(--color-bg-card)';
  const dropZoneStyle = isDragging ? 'dashed' : 'solid';

  return (
    <div
      className="rounded-lg border p-4 transition-colors"
      style={{
        background: dropZoneBg,
        borderColor: dropZoneBorderColor,
        borderStyle: dropZoneStyle,
        boxShadow: isDragging ? 'var(--shadow-lg)' : 'var(--shadow-card)',
      }}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <h3
        className="mb-1 text-xs font-semibold uppercase tracking-wider"
        style={{ color: 'var(--color-text-muted)' }}
      >
        文件导入区
      </h3>
      <p className="mb-3 text-xs" style={{ color: 'var(--color-text-muted)' }}>
        支持格式：{SUPPORTED_EXTENSIONS.join(' / ')}
      </p>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept={SUPPORTED_EXTENSIONS.join(',')}
        onChange={handleChange}
        className="hidden"
      />

      {/* Drop zone visual cue */}
      <div
        className="mb-3 flex flex-col items-center justify-center rounded-lg border-2 border-dashed py-6 transition-all"
        style={{
          borderColor: isDragging ? 'var(--color-accent)' : 'var(--color-border)',
          background: isDragging ? 'var(--color-accent-light)' : 'var(--color-bg)',
          opacity: isDragging ? 1 : 0.7,
        }}
      >
        <div className="mb-1.5 text-2xl">{isDragging ? '📥' : '📂'}</div>
        <p
          className="text-sm font-medium"
          style={{ color: isDragging ? 'var(--color-accent-dark)' : 'var(--color-text-secondary)' }}
        >
          {isDragging ? '松开以上传文件' : '拖拽文件到此处，或点击选择文件'}
        </p>
        <button
          onClick={handleSelect}
          className="mt-2 cursor-pointer rounded-lg border px-4 py-1.5 text-sm font-medium transition-colors"
          style={{
            borderColor: 'var(--color-accent)',
            background: 'var(--color-accent-light)',
            color: 'var(--color-accent-dark)',
          }}
        >
          选择文件
        </button>
      </div>

      {/* Rejected files toast */}
      {rejectedNames.length > 0 && (
        <div
          className="mb-3 rounded border p-2 text-xs"
          style={{
            borderColor: 'var(--color-orange)',
            background: 'var(--color-orange-light)',
            color: 'var(--color-orange)',
          }}
        >
          不支持的文件格式：
          {rejectedNames.map((name, index) => (
            <span key={name}>
              {index > 0 ? '、' : ''}
              {name}
            </span>
          ))}
        </div>
      )}

      {/* File list */}
      {files.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          暂未选择任何文件
        </p>
      ) : (
        <div className="space-y-2">
          {files.map((file) => (
            <div
              key={file.id}
              className="flex items-center gap-3 rounded border p-2 text-sm"
              style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}
            >
              <span className="text-base">{iconForType(file.extension)}</span>
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium" style={{ color: 'var(--color-text)' }}>
                  {file.name}
                </div>
                <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                  {formatSize(file.size)} · {file.extension || '未知类型'}
                </div>
              </div>
              <button
                onClick={() => onRemoveFile(file.id)}
                className="flex h-6 w-6 cursor-pointer items-center justify-center rounded-full border-none text-sm"
                style={{ background: 'var(--color-red-light)', color: 'var(--color-red)' }}
                title="移除"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function iconForType(ext: string): string {
  switch (ext) {
    case '.pdf':
      return '📄';
    case '.docx':
      return '📝';
    case '.jpg':
    case '.jpeg':
    case '.png':
    case '.webp':
      return '🖼️';
    case '.txt':
      return '📃';
    case '.html':
      return '🌐';
    case '.md':
      return '📋';
    default:
      return '📎';
  }
}
