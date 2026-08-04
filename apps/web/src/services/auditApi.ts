import type {
  ChangeBatchDetailResponse,
  ChangeBatchListResponse,
  RollbackChangeBatchResponse,
} from '../types';
import { request } from './apiClient';

export interface ChangeBatchFilters {
  change_type?: string;
  status?: string;
  limit?: number;
}

export async function fetchChangeBatches(params: ChangeBatchFilters = {}): Promise<ChangeBatchListResponse> {
  const search = new URLSearchParams();
  if (params.change_type) search.set('change_type', params.change_type);
  if (params.status) search.set('status', params.status);
  search.set('limit', String(params.limit ?? 50));
  return request(`/api/audit/batches?${search.toString()}`);
}

export async function fetchChangeBatch(batchId: string): Promise<ChangeBatchDetailResponse> {
  return request(`/api/audit/batches/${encodeURIComponent(batchId)}`);
}

export async function rollbackChangeBatch(
  batchId: string,
  body: { dry_run?: boolean; reason?: string; allow_conflicts?: boolean },
): Promise<RollbackChangeBatchResponse> {
  return request(`/api/audit/batches/${encodeURIComponent(batchId)}/rollback`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
