import { extractErrorMessage } from '../utils/error.ts';

export const API_BASE = '';

const browserTraceId = (() => {
  const generated = globalThis.crypto?.randomUUID?.();
  return generated || `web-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
})();

export function correlationHeaders(headers?: HeadersInit): Headers {
  const resolved = new Headers(headers);
  if (!resolved.has('X-Trace-ID')) {
    resolved.set('X-Trace-ID', browserTraceId);
  }
  return resolved;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export async function requestResponse(
  url: string,
  options?: RequestInit,
  acceptedErrorStatuses: readonly number[] = [],
): Promise<Response> {
  const headers = correlationHeaders(options?.headers);
  if (typeof options?.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers,
  });

  if (!res.ok && !acceptedErrorStatuses.includes(res.status)) {
    const payload = await res
      .json()
      .catch(() => ({ detail: res.statusText || `HTTP ${res.status}` }));
    const msg = extractErrorMessage(payload, `HTTP ${res.status}`);
    throw new ApiError(msg, res.status);
  }

  return res;
}

export async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await requestResponse(url, options);
  return response.json();
}

export async function requestForm<T>(url: string, formData: FormData): Promise<T> {
  const response = await requestResponse(url, {
    method: 'POST',
    body: formData,
  });
  return response.json();
}
