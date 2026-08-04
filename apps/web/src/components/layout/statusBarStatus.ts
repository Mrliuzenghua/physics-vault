import type { McpRuntimeStatus } from '../../types';

export type ServiceStatusKind = 'checking' | 'disabled' | 'online' | 'offline';

export interface ServiceStatusView {
  kind: ServiceStatusKind;
  text: string;
  colorToken: string;
  dotClass: string;
}

export function resolveServiceStatus(online: boolean, runtimeEnabled: boolean, lastCheckedAt: string | null | undefined): ServiceStatusView {
  if (!lastCheckedAt) {
    return {
      kind: 'checking',
      text: '检查中',
      colorToken: 'var(--color-text-muted)',
      dotClass: 'bg-[var(--color-text-muted)]',
    };
  }

  if (!runtimeEnabled) {
    return {
      kind: 'disabled',
      text: '未启用',
      colorToken: 'var(--color-orange)',
      dotClass: 'bg-[var(--color-orange)]',
    };
  }

  if (online) {
    return {
      kind: 'online',
      text: '在线',
      colorToken: 'var(--color-green)',
      dotClass: 'bg-[var(--color-green)]',
    };
  }

  return {
    kind: 'offline',
    text: '离线',
    colorToken: 'var(--color-red)',
    dotClass: 'bg-[var(--color-red)]',
  };
}

export function resolveMcpServiceStatuses(status: Pick<McpRuntimeStatus, 'enabled' | 'vl_available' | 'llm_available' | 'last_checked_at'>) {
  return {
    vl: resolveServiceStatus(status.vl_available, status.enabled, status.last_checked_at),
    llm: resolveServiceStatus(status.llm_available, status.enabled, status.last_checked_at),
  };
}
