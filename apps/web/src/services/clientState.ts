import type { BasketItem, McpConfig, SystemSettings } from '../types';
import { request } from './apiClient';

const BASKET_KEY = 'physics_vault_basket';
const SETTINGS_KEY = 'physics_vault_settings';
const MCP_KEY = 'physics_vault_mcp';
const BASKET_EVENT = 'physics-vault-basket-changed';
const LEGACY_DASHSCOPE_VL_MODELS = new Set(['qwen-vl-max']);

let basketCache: BasketItem[] | null = null;

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
  window.dispatchEvent(new CustomEvent(BASKET_EVENT));
}

export function getBasket(): BasketItem[] {
  if (basketCache !== null) {
    return basketCache;
  }

  try {
    basketCache = JSON.parse(localStorage.getItem(BASKET_KEY) || '[]');
  } catch {
    basketCache = [];
  }

  return basketCache ?? [];
}

export function addToBasket(questionId: string): BasketItem[] {
  const basket = getBasket();
  if (basket.find((item) => item.question_id === questionId)) {
    return basket;
  }

  const updated = [...basket, { question_id: questionId, added_at: new Date().toISOString() }];
  basketCache = updated;
  localStorage.setItem(BASKET_KEY, JSON.stringify(updated));
  emitBasketChanged();
  return updated;
}

export function removeFromBasket(questionId: string): BasketItem[] {
  const updated = getBasket().filter((item) => item.question_id !== questionId);
  basketCache = updated;
  localStorage.setItem(BASKET_KEY, JSON.stringify(updated));
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
  localStorage.setItem(BASKET_KEY, JSON.stringify(basket));
  emitBasketChanged();
  return basket;
}

export function clearBasket(): void {
  basketCache = [];
  localStorage.setItem(BASKET_KEY, '[]');
  emitBasketChanged();
}

export function subscribeBasket(listener: () => void): () => void {
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

  try {
    return { ...defaults, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}') };
  } catch {
    return defaults;
  }
}

export function saveSettings(settings: SystemSettings): void {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
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
    const stored = JSON.parse(localStorage.getItem(MCP_KEY) || '{}') as Partial<McpConfig>;
    const storedVl: Partial<McpConfig['vl']> = stored.vl || {};
    const vlModel = LEGACY_DASHSCOPE_VL_MODELS.has(String(storedVl.model_name || '').toLowerCase())
      ? DEFAULT_AI_CONFIG.vl.model_name
      : storedVl.model_name;
    const vlBaseUrl =
      String(vlModel || '').toLowerCase() === DEFAULT_AI_CONFIG.vl.model_name &&
      String(storedVl.base_url || '').toLowerCase().includes('dashscope.aliyuncs.com/api/v1')
        ? DEFAULT_AI_CONFIG.vl.base_url
        : storedVl.base_url;
    return {
      ...defaults,
      ...stored,
      vl: {
        ...DEFAULT_AI_CONFIG.vl,
        ...storedVl,
        base_url: vlBaseUrl || DEFAULT_AI_CONFIG.vl.base_url,
        model_name: vlModel || DEFAULT_AI_CONFIG.vl.model_name,
      },
      llm: { ...DEFAULT_AI_CONFIG.llm, ...(stored.llm || {}) },
    };
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
  localStorage.setItem(MCP_KEY, JSON.stringify({
    ...config,
    vl: { ...DEFAULT_AI_CONFIG.vl, ...config.vl, base_url: vlBaseUrl, model_name: vlModel },
    llm: { ...DEFAULT_AI_CONFIG.llm, ...config.llm },
  }));
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
  return (localStorage.getItem('physics_vault_theme') as 'light' | 'dark' | 'system') || 'system';
}

export function saveTheme(theme: 'light' | 'dark' | 'system'): void {
  localStorage.setItem('physics_vault_theme', theme);
}
