const IMAGE_EXTENSIONS = /\.(png|jpe?g|gif|webp|svg)(\?.*)?$/i;
const PROJECT_ROOT_SEGMENTS = /^(apps|config|data|docs|output|packages|scripts|tests)\//;

export function normalizeProjectImagePath(path?: string | null, fallbackDir = 'data/assets/questions'): string | null {
  let value = String(path || '').trim();
  if (!value) return null;

  if (/^(https?:|data:|blob:)/i.test(value)) return value;

  value = value.replace(/\\/g, '/');
  value = value.replace(/^file:\/\/\/?/i, '');

  const projectMatch = value.match(/(?:^|\/)physics-vault\/(.+)$/i);
  if (projectMatch) value = projectMatch[1];

  value = value.replace(/^\/+/, '').replace(/^\.?\//, '');

  if (value.startsWith('files/')) {
    value = value.slice('files/'.length);
  }

  if (value.startsWith('assets/questions/')) {
    value = `data/${value}`;
  } else if (value.startsWith('import-batches/')) {
    value = `data/${value}`;
  } else if (!PROJECT_ROOT_SEGMENTS.test(value) && IMAGE_EXTENSIONS.test(value)) {
    value = `${fallbackDir.replace(/\/+$/, '')}/${value}`;
  }

  return value;
}

export function imageFileUrl(path?: string | null, fallbackDir?: string): string | null {
  const normalized = normalizeProjectImagePath(path, fallbackDir);
  if (!normalized) return null;
  if (/^(https?:|data:|blob:)/i.test(normalized)) return normalized;
  return `/files/${encodeURI(normalized)}`;
}

export function imageThumbnailUrl(path?: string | null, width = 720, fallbackDir?: string): string | null {
  const normalized = normalizeProjectImagePath(path, fallbackDir);
  if (!normalized) return null;
  if (/^(https?:|data:|blob:)/i.test(normalized)) return normalized;
  const safeWidth = Math.min(1600, Math.max(120, Math.round(width)));
  return `/thumbs/${encodeURI(normalized)}?w=${safeWidth}`;
}
