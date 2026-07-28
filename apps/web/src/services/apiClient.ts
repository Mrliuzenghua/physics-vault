import { extractErrorMessage } from '../utils/error';

export const API_BASE = '';

export async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (options?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const payload = await res
      .json()
      .catch(() => ({ detail: res.statusText || `HTTP ${res.status}` }));
    const msg = extractErrorMessage(payload, `HTTP ${res.status}`);
    throw new Error(msg);
  }

  return res.json();
}

export async function requestForm<T>(url: string, formData: FormData): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const payload = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(extractErrorMessage(payload.detail || `HTTP ${res.status}`));
  }

  return res.json();
}
