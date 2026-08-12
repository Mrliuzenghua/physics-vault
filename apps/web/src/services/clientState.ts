import type { BasketItem, McpConfig, SystemSettings } from '../types';
import { request } from './apiClient.ts';
import {
  isRecord,
  readJsonStorage,
  readSessionJsonStorage,
  readStorageValue,
  writeJsonStorage,
  writeSessionJsonStorage,
  writeStorageValue,
} from './safeStorage.ts';

const BASKET_KEY = 'physics_vault_basket';
const SETTINGS_KEY = 'physics_vault_settings';
const MCP_KEY = 'physics_vault_mcp';
const MCP_SESSION_SECRETS_KEY = 'physics_vault_mcp_session_secrets';
const BASKET_EVENT = 'physics-vault-basket-changed';
const LEGACY_DASHSCOPE_VL_MODELS = new Set(['qwen-vl-max']);

let basketCache: BasketItem[] | null = null;
let mcpSecretMemory = { vl_api_key: '', llm_api_key: '' };

function asRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? value : {};
}

function persistMcpConfig(config: McpConfig): void {
  mcpSecretMemory = {
    vl_api_key: config.vl.api_key,
    llm_api_key: config.llm.api_key,
  };
  writeSessionJsonStorage(MCP_SESSION_SECRETS_KEY, mcpSecretMemory);
  writeJsonStorage(MCP_KEY, {
    ...config,
    vl: { ...config.vl, api_key: '' },
    llm: { ...config.llm, api_key: '' },
  });
}

export const DEFAULT_AI_CONFIG = {
  vl: {
    service_type: 'Alibaba DashScope',
    base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    api_key: '',
    model_name: 'qwen3.5-ocr',
    timeout_seconds: 120,
    max_retries: 2,
    concurrency: 1,
  },
  llm: {
    service_type: 'DeepSeek',
    base_url: 'https://api.deepseek.com',
    api_key: '',
    model_name: 'deepseek-v4-pro',
    timeout_seconds: 120,
    max_retries: 2,
    concurrency: 2,
  },
} satisfies Pick<McpConfig, 'vl' | 'llm'>;

function emitBasketChanged(): void {
  if (typeof window === 'undefined' || typeof window.dispatchEvent !== 'function') return;
  try {
    window.dispatchEvent(new CustomEvent(BASKET_EVENT));
  } catch {
    // Some embedded runtimes expose window without DOM event constructors.
  }
}

export function getBasket(): BasketItem[] {
  if (basketCache !== null) {
    return basketCache;
  }

  const stored = readJsonStorage<unknown>(BASKET_KEY, []);
  basketCache = Array.isArray(stored)
    ? stored.filter((item): item is BasketItem => {
        const candidate = asRecord(item);
        return typeof candidate.question_id === 'string' && typeof candidate.added_at === 'string';
      })
    : [];

  return basketCache ?? [];
}

export function addToBasket(questionId: string): BasketItem[] {
  const basket = getBasket();
  if (basket.find((item) => item.question_id === questionId)) {
    return basket;
  }

  const updated = [...basket, { question_id: questionId, added_at: new Date().toISOString() }];
  basketCache = updated;
  writeJsonStorage(BASKET_KEY, updated);
  emitBasketChanged();
  return updated;
}

export function removeFromBasket(questionId: string): BasketItem[] {
  const updated = getBasket().filter((item) => item.question_id !== questionId);
  basketCache = updated;
  writeJsonStorage(BASKET_KEY, updated);
  emitBasketChanged();
  return updated;
}

export function moveBasketItem(questionId: string, direction: 'up' | 'down'): BasketItem[] {
  const basket = [...getBasket()];
  const index = basket.findIndex((item) => item.question_id === questionId);
  const target = direction === 'up' ? index - 1 : index + 1;
  if (index < 0 || target < 0 || target >= basket.length) return basket;
  [basket[index], basket[target]] = [basket[target], basket[index]];
  basketCache = basket;
  writeJsonStorage(BASKET_KEY, basket);
  emitBasketChanged();
  return basket;
}

export function clearBasket(): void {
  basketCache = [];
  writeJsonStorage(BASKET_KEY, []);
  emitBasketChanged();
}

export function subscribeBasket(listener: () => void): () => void {
  if (typeof window === 'undefined' || typeof window.addEventListener !== 'function') {
    return () => undefined;
  }
  const handleStorage = (event: StorageEvent) => {
    if (event.key === BASKET_KEY) {
      basketCache = null;
      listener();
    }
  };
  const handleCustom = () => listener();

  window.addEventListener('storage', handleStorage);
  window.addEventListener(BASKET_EVENT, handleCustom);

  return () => {
    window.removeEventListener('storage', handleStorage);
    window.removeEventListener(BASKET_EVENT, handleCustom);
  };
}

export function getSettings(): SystemSettings {
  const defaults: SystemSettings = {
    db_path: './data/app-db/physics_vault.sqlite3',
    assets_path: './data/assets/questions/',
    import_batches_path: './data/import-batches/',
    cache_path: './data/cache/',
    exports_path: './data/exports/',
    logs_path: './data/logs/',
    ai_enabled: true,
    offline_mode: false,
    theme: 'system',
    log_level: 'INFO',
    page_size: 20,
  };

  const stored = readJsonStorage<Record<string, unknown>>(SETTINGS_KEY, {}, isRecord);
  const theme = ['light', 'dark', 'system'].includes(String(stored.theme))
    ? stored.theme as SystemSettings['theme']
    : defaults.theme;
  const logLevel = ['DEBUG', 'INFO', 'WARNING', 'ERROR'].includes(String(stored.log_level))
    ? stored.log_level as SystemSettings['log_level']
    : defaults.log_level;
  const pageSize = Number(stored.page_size);
  return {
    db_path: typeof stored.db_path === 'string' ? stored.db_path : defaults.db_path,
    assets_path: typeof stored.assets_path === 'string' ? stored.assets_path : defaults.assets_path,
    import_batches_path: typeof stored.import_batches_path === 'string' ? stored.import_batches_path : defaults.import_batches_path,
    cache_path: typeof stored.cache_path === 'string' ? stored.cache_path : defaults.cache_path,
    exports_path: typeof stored.exports_path === 'string' ? stored.exports_path : defaults.exports_path,
    logs_path: typeof stored.logs_path === 'string' ? stored.logs_path : defaults.logs_path,
    ai_enabled: typeof stored.ai_enabled === 'boolean' ? stored.ai_enabled : defaults.ai_enabled,
    offline_mode: typeof stored.offline_mode === 'boolean' ? stored.offline_mode : defaults.offline_mode,
    theme,
    log_level: logLevel,
    page_size: Number.isInteger(pageSize) && pageSize >= 1 && pageSize <= 100 ? pageSize : defaults.page_size,
  };
}

export function saveSettings(settings: SystemSettings): void {
  writeJsonStorage(SETTINGS_KEY, settings);
}

export function getMcpConfig(): McpConfig {
  const defaults: McpConfig = {
    vl: DEFAULT_AI_CONFIG.vl,
    llm: DEFAULT_AI_CONFIG.llm,
    scheduling: {
      queue_size: 100,
      request_interval_ms: 500,
      max_consecutive_failures: 5,
    },
    cleaning: {
      remove_markdown_wrapper: true,
      remove_extra_text: true,
      validate_json: true,
      auto_correct: true,
    },
    logging: {
      log_requests: true,
      log_responses: true,
      log_full_prompt: false,
      retention_days: 30,
    },
    capability_mapping: {
      recognition_ai: 'MCP-VL',
      generation_ai: 'MCP-LLM',
      annotation_ai: 'MCP-LLM',
    },
  };

  try {
    const stored = readJsonStorage<Record<string, unknown>>(MCP_KEY, {}, isRecord);
    const storedVl = asRecord(stored.vl) as Partial<McpConfig['vl']>;
    const storedLlm = asRecord(stored.llm) as Partial<McpConfig['llm']>;
    const sessionSecrets = readSessionJsonStorage<Record<string, unknown>>(
      MCP_SESSION_SECRETS_KEY,
      mcpSecretMemory,
      isRecord,
    );
    const legacyVlKey = typeof storedVl.api_key === 'string' ? storedVl.api_key : '';
    const legacyLlmKey = typeof storedLlm.api_key === 'string' ? storedLlm.api_key : '';
    const sessionVlKey = typeof sessionSecrets.vl_api_key === 'string' ? sessionSecrets.vl_api_key : '';
    const sessionLlmKey = typeof sessionSecrets.llm_api_key === 'string' ? sessionSecrets.llm_api_key : '';
    const vlApiKey = legacyVlKey || sessionVlKey;
    const llmApiKey = legacyLlmKey || sessionLlmKey;
    mcpSecretMemory = { vl_api_key: vlApiKey, llm_api_key: llmApiKey };
    const vlModel = LEGACY_DASHSCOPE_VL_MODELS.has(String(storedVl.model_name || '').toLowerCase())
      ? DEFAULT_AI_CONFIG.vl.model_name
      : storedVl.model_name;
    const vlBaseUrl =
      String(vlModel || '').toLowerCase() === DEFAULT_AI_CONFIG.vl.model_name &&
      String(storedVl.base_url || '').toLowerCase().includes('dashscope.aliyuncs.com/api/v1')
        ? DEFAULT_AI_CONFIG.vl.base_url
        : storedVl.base_url;
    const result = {
      ...defaults,
      vl: {
        ...DEFAULT_AI_CONFIG.vl,
        ...storedVl,
        api_key: vlApiKey,
        base_url: vlBaseUrl || DEFAULT_AI_CONFIG.vl.base_url,
        model_name: vlModel || DEFAULT_AI_CONFIG.vl.model_name,
      },
      llm: { ...DEFAULT_AI_CONFIG.llm, ...storedLlm, api_key: llmApiKey },
      scheduling: { ...defaults.scheduling, ...asRecord(stored.scheduling) },
      cleaning: { ...defaults.cleaning, ...asRecord(stored.cleaning) },
      logging: { ...defaults.logging, ...asRecord(stored.logging) },
      capability_mapping: { ...defaults.capability_mapping, ...asRecord(stored.capability_mapping) },
    } satisfies McpConfig;
    if (legacyVlKey || legacyLlmKey) persistMcpConfig(result);
    return result;
  } catch {
    return defaults;
  }
}

export function saveMcpConfig(config: McpConfig): void {
  const vlModel = LEGACY_DASHSCOPE_VL_MODELS.has(String(config.vl.model_name || '').toLowerCase())
    ? DEFAULT_AI_CONFIG.vl.model_name
    : config.vl.model_name;
  const vlBaseUrl =
    String(vlModel || '').toLowerCase() === DEFAULT_AI_CONFIG.vl.model_name &&
    String(config.vl.base_url || '').toLowerCase().includes('dashscope.aliyuncs.com/api/v1')
      ? DEFAULT_AI_CONFIG.vl.base_url
      : config.vl.base_url;
  persistMcpConfig({
    ...config,
    vl: { ...DEFAULT_AI_CONFIG.vl, ...config.vl, base_url: vlBaseUrl, model_name: vlModel },
    llm: { ...DEFAULT_AI_CONFIG.llm, ...config.llm },
  });
}

export async function pushMcpConfigToBackend(
  config: McpConfig,
): Promise<{ ok: boolean; mode: string; vl_configured: boolean; llm_configured: boolean }> {
  const mergedConfig = {
    ...config,
    vl: {
      ...DEFAULT_AI_CONFIG.vl,
      ...config.vl,
      base_url:
        String(config.vl.model_name || '').toLowerCase() === DEFAULT_AI_CONFIG.vl.model_name &&
        String(config.vl.base_url || '').toLowerCase().includes('dashscope.aliyuncs.com/api/v1')
          ? DEFAULT_AI_CONFIG.vl.base_url
          : config.vl.base_url,
      model_name: LEGACY_DASHSCOPE_VL_MODELS.has(String(config.vl.model_name || '').toLowerCase())
        ? DEFAULT_AI_CONFIG.vl.model_name
        : config.vl.model_name,
    },
    llm: { ...DEFAULT_AI_CONFIG.llm, ...config.llm },
  };
  return request('/api/mcp/config', {
    method: 'POST',
    body: JSON.stringify({ vl: mergedConfig.vl, llm: mergedConfig.llm }),
  });
}

export function getTheme(): 'light' | 'dark' | 'system' {
  try {
    const theme = readStorageValue('physics_vault_theme');
    return theme === 'light' || theme === 'dark' || theme === 'system' ? theme : 'system';
  } catch {
    return 'system';
  }
}

export function saveTheme(theme: 'light' | 'dark' | 'system'): void {
  writeStorageValue('physics_vault_theme', theme);
}
