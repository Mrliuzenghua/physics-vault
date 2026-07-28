/**
 * Extract a human-readable error message from an unknown thrown value.
 *
 * Handles:
 *  - Error instances (uses `.message`)
 *  - String errors
 *  - FastAPI-style `{ detail: "..." | [...] | { msg, loc }[] }`
 *  - Pydantic validation error arrays
 *  - Plain objects / arrays (falls back to JSON.stringify)
 *  - Anything else (returns fallback)
 */
export function extractErrorMessage(err: unknown, fallback = '未知错误'): string {
  if (err == null) return fallback;

  // 1. Error instances
  if (err instanceof Error) {
    const m = err.message;
    if (m && m !== '[object Object]') return m;
    // Fallback: try to read .detail if it was attached
    const detail = (err as unknown as { detail?: unknown }).detail;
    if (detail != null) return extractErrorMessage(detail, fallback);
    return fallback;
  }

  // 2. Plain strings
  if (typeof err === 'string') {
    return err.trim() || fallback;
  }

  // 3. Objects (FastAPI / generic JSON)
  if (typeof err === 'object') {
    const obj = err as Record<string, unknown>;

    // FastAPI detail can be string | array | object
    if ('detail' in obj) {
      const detail = obj.detail;
      // Backend 500 shape: { message: "...", errors: [...] }
      if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
        const d = detail as Record<string, unknown>;
        const message = typeof d.message === 'string' ? d.message : '';
        const errors = Array.isArray(d.errors) ? d.errors : [];
        const errorStrs = errors
          .map((e) => (typeof e === 'string' ? e : extractErrorMessage(e, '')))
          .filter(Boolean);
        if (message && errorStrs.length > 0) {
          return `${message}：${errorStrs.join('; ')}`;
        }
        if (message) return message;
        if (errorStrs.length > 0) return errorStrs.join('; ');
      }
      const parsed = parseDetailField(detail);
      if (parsed) return parsed;
    }

    // Pydantic v2 error structure
    if ('message' in obj) {
      const m = parseDetailField(obj.message);
      if (m) return m;
    }

    // Generic error field
    if ('error' in obj) {
      const e = parseDetailField(obj.error);
      if (e) return e;
    }

    // Last resort: stringify (cap length to avoid huge UI)
    try {
      const json = JSON.stringify(err);
      if (json && json !== '{}') return json.slice(0, 500);
    } catch {
      /* ignore */
    }
  }

  return fallback;
}

function parseDetailField(detail: unknown): string | null {
  if (detail == null) return null;
  if (typeof detail === 'string') return detail.trim() || null;
  if (Array.isArray(detail)) {
    // Pydantic validation error list: [{loc: [...], msg: "...", type: "..."}]
    const parts: string[] = [];
    for (const item of detail) {
      if (item && typeof item === 'object') {
        const it = item as Record<string, unknown>;
        const loc = Array.isArray(it.loc) ? (it.loc as unknown[]).join('.') : '';
        const msg = typeof it.msg === 'string' ? it.msg : '';
        if (loc && msg) parts.push(`${loc}: ${msg}`);
        else if (msg) parts.push(msg);
      } else if (typeof item === 'string') {
        parts.push(item);
      }
    }
    if (parts.length > 0) return parts.join('; ');
    return null;
  }
  if (typeof detail === 'object') {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.msg === 'string') return obj.msg;
    if (typeof obj.message === 'string') return obj.message;
    try {
      const json = JSON.stringify(detail);
      if (json && json !== '{}') return json.slice(0, 500);
    } catch {
      /* ignore */
    }
  }
  return null;
}
