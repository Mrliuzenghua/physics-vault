import type { RestorePackageResponse } from '../types';
import { requestForm, requestResponse } from './apiClient';
import { downloadResponse } from './fileDownload';

export async function downloadExportPackage(): Promise<void> {
  const response = await requestResponse('/api/system/export-package');
  await downloadResponse(response, 'physics-vault-export.zip');
}

export async function restorePackage(file: File): Promise<RestorePackageResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return requestForm('/api/system/restore-package', formData);
}
