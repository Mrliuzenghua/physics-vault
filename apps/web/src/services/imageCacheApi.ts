import { request, requestForm } from './apiClient.ts';

export interface ImageCacheAsset {
  relative_path: string;
  filename: string;
  file_path: string;
  mime_type: string;
  size: number;
}

export async function fetchQuestionImageCache(keyword = '', limit = 200): Promise<ImageCacheAsset[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (keyword.trim()) params.set('keyword', keyword.trim());
  return request(`/api/questions/images/cache?${params.toString()}`);
}

export async function uploadQuestionImageCache(files: File[]): Promise<{ images: ImageCacheAsset[]; skipped: string[] }> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  return requestForm('/api/questions/images/cache-upload', formData);
}
