import { useCallback, useEffect, useState } from 'react';

import {
  DEFAULT_AI_CONFIG,
  fetchMcpStatus,
  getMcpConfig,
  pushMcpConfigToBackend,
  saveMcpConfig,
  testMcpConnection,
} from '../services/api';
import type { McpConfig, McpConnectionTestResponse, McpRuntimeStatus } from '../types';

const STATUS_LABEL: Record<string, string> = {
  http: '真实 API 模式',
  mock: '模拟模式',
  stdio: '本地 MCP 进程模式',
  disabled: '已关闭 AI',
};

function withDefaultProviders(config: McpConfig): McpConfig {
  return {
    ...config,
    vl: { ...DEFAULT_AI_CONFIG.vl, api_key: config.vl?.api_key || '' },
    llm: { ...DEFAULT_AI_CONFIG.llm, api_key: config.llm?.api_key || '' },
  };
}

export default function McpSettingsPage() {
  const [config, setConfig] = useState<McpConfig>(() => withDefaultProviders(getMcpConfig()));
  const [backendStatus, setBackendStatus] = useState<McpRuntimeStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedText, setSavedText] = useState<string | null>(null);
  const [testingTarget, setTestingTarget] = useState<'vl' | 'llm' | null>(null);
  const [testResult, setTestResult] = useState<McpConnectionTestResponse | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const loadStatus = useCallback(async () => {
    setLoadingStatus(true);
    setStatusError(null);
    try {
      setBackendStatus(await fetchMcpStatus());
    } catch (err) {
      setStatusError((err as Error).message || '后端状态读取失败');
    } finally {
      setLoadingStatus(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const saveAndPush = useCallback(async () => {
    const next = withDefaultProviders(config);
    setSaving(true);
    setSavedText(null);
    setTestResult(null);
    setTestError(null);
    try {
      saveMcpConfig(next);
      const result = await pushMcpConfigToBackend(next);
      setConfig(next);
      setSavedText(result.mode === 'http' ? '已保存，并切换为真实 AI API 模式' : '已保存，但还缺少 API Key，当前仍是模拟模式');
      await loadStatus();
    } catch (err) {
      setSavedText(null);
      setStatusError((err as Error).message || '保存失败，请确认后端已启动');
    } finally {
      setSaving(false);
    }
  }, [config, loadStatus]);

  const testConnection = useCallback(async (target: 'vl' | 'llm') => {
    setTestingTarget(target);
    setTestResult(null);
    setTestError(null);
    try {
      await saveAndPush();
      setTestResult(await testMcpConnection(target));
    } catch (err) {
      setTestError((err as Error).message || '连接测试失败');
    } finally {
      setTestingTarget(null);
    }
  }, [saveAndPush]);

  const updateKey = (target: 'vl' | 'llm', apiKey: string) => {
    setConfig((prev) => ({
      ...prev,
      [target]: { ...prev[target], api_key: apiKey.trim() },
    }));
    setSavedText(null);
  };

  const updateAdvanced = (target: 'vl' | 'llm', patch: Partial<McpConfig['vl']>) => {
    setConfig((prev) => ({
      ...prev,
      [target]: { ...prev[target], ...patch },
    }));
    setSavedText(null);
  };

  const mode = backendStatus?.mode || 'unknown';
  const isHttpMode = mode === 'http' || Boolean(backendStatus && (backendStatus as unknown as Record<string, unknown>).http_mode);

  return (
    <div className="h-full overflow-y-auto bg-[#eef4fb] px-6 py-6 text-[#18243a]">
      <div className="mx-auto max-w-5xl space-y-5">
        <section className="rounded-[28px] bg-white p-7 shadow-[0_18px_45px_rgba(25,48,84,0.10)]">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <p className="mb-2 text-sm font-semibold tracking-[0.24em] text-[#2c75d6]">MCP AI SETTINGS</p>
              <h1 className="text-3xl font-black text-[#152238]">默认 AI 接入</h1>
              <p className="mt-3 max-w-2xl text-base leading-8 text-[#687891]">
                系统默认使用阿里千问处理图片/PDF 识别，使用 DeepSeek 处理文本清洗、题目结构化、解析和知识点生成。
                你只需要填 API Key，地址和模型名已经内置。
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => void loadStatus()}
                disabled={loadingStatus}
                className="rounded-2xl border border-[#d8e2f0] bg-white px-5 py-3 font-semibold text-[#40506a] disabled:opacity-60"
              >
                {loadingStatus ? '刷新中...' : '刷新状态'}
              </button>
              <button
                onClick={() => void saveAndPush()}
                disabled={saving}
                className="rounded-2xl bg-[#2673d9] px-6 py-3 font-semibold text-white shadow-[0_12px_28px_rgba(38,115,217,0.28)] disabled:opacity-60"
              >
                {saving ? '保存中...' : '保存配置'}
              </button>
            </div>
          </div>

          <div className="mt-6 grid gap-3 md:grid-cols-3">
            <StatusTile label="后端模式" value={STATUS_LABEL[mode] || mode} active={isHttpMode} />
            <StatusTile label="视觉服务" value={backendStatus?.vl_available ? '可用' : '未接通'} active={Boolean(backendStatus?.vl_available)} />
            <StatusTile label="文本服务" value={backendStatus?.llm_available ? '可用' : '未接通'} active={Boolean(backendStatus?.llm_available)} />
          </div>

          {statusError && <Notice tone="danger" text={statusError} />}
          {savedText && <Notice tone="success" text={savedText} />}
          {testError && <Notice tone="danger" text={testError} />}
          {testResult && (
            <Notice
              tone={testResult.reachable ? 'success' : 'warning'}
              text={`${testResult.target.toUpperCase()}：${testResult.message}`}
            />
          )}
        </section>

        <div className="grid gap-5 xl:grid-cols-2">
          <ProviderCard
            title="视觉识别：阿里千问"
            subtitle="用于图片、扫描 PDF、题图识别和版面解析"
            badge="VL"
            provider={DEFAULT_AI_CONFIG.vl.service_type}
            baseUrl={config.vl.base_url}
            model={config.vl.model_name}
            apiKey={config.vl.api_key}
            placeholder="粘贴阿里百炼 DashScope API Key"
            testing={testingTarget === 'vl'}
            onApiKeyChange={(value) => updateKey('vl', value)}
            onTest={() => void testConnection('vl')}
          />

          <ProviderCard
            title="文本生成：DeepSeek"
            subtitle="用于 Word/Markdown 清洗、题目 JSON 结构化、解析和知识点生成"
            badge="LLM"
            provider={DEFAULT_AI_CONFIG.llm.service_type}
            baseUrl={config.llm.base_url}
            model={config.llm.model_name}
            apiKey={config.llm.api_key}
            placeholder="粘贴 DeepSeek API Key"
            testing={testingTarget === 'llm'}
            onApiKeyChange={(value) => updateKey('llm', value)}
            onTest={() => void testConnection('llm')}
          />
        </div>

        <section className="rounded-[24px] bg-white p-5 shadow-[0_14px_35px_rgba(25,48,84,0.08)]">
          <button
            onClick={() => setShowAdvanced((value) => !value)}
            className="flex w-full items-center justify-between text-left"
          >
            <div>
              <h2 className="text-lg font-black text-[#18243a]">高级配置</h2>
              <p className="mt-1 text-sm text-[#7b8ba3]">一般不用改；只有模型升级或供应商地址变化时再打开。</p>
            </div>
            <span className="rounded-full bg-[#edf4ff] px-4 py-2 text-sm font-semibold text-[#2d72d9]">
              {showAdvanced ? '收起' : '展开'}
            </span>
          </button>

          {showAdvanced && (
            <div className="mt-5 grid gap-5 xl:grid-cols-2">
              <AdvancedFields
                title="阿里千问 VL"
                config={config.vl}
                onChange={(patch) => updateAdvanced('vl', patch)}
              />
              <AdvancedFields
                title="DeepSeek LLM"
                config={config.llm}
                onChange={(patch) => updateAdvanced('llm', patch)}
              />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function StatusTile({ label, value, active }: { label: string; value: string; active: boolean }) {
  return (
    <div className={`rounded-2xl border px-5 py-4 ${active ? 'border-[#bfe5d1] bg-[#f0fff6]' : 'border-[#dde6f3] bg-[#f7faff]'}`}>
      <div className="text-sm font-semibold text-[#7a8aa3]">{label}</div>
      <div className={`mt-2 text-xl font-black ${active ? 'text-[#14985d]' : 'text-[#3f506b]'}`}>{value}</div>
    </div>
  );
}

function Notice({ tone, text }: { tone: 'success' | 'warning' | 'danger'; text: string }) {
  const classes = {
    success: 'border-[#bfe5d1] bg-[#f0fff6] text-[#118352]',
    warning: 'border-[#f3d69a] bg-[#fff8e8] text-[#946817]',
    danger: 'border-[#ffc9c9] bg-[#fff1f1] text-[#d73535]',
  }[tone];
  return <div className={`mt-4 rounded-2xl border px-4 py-3 text-sm font-semibold ${classes}`}>{text}</div>;
}

function ProviderCard({
  title,
  subtitle,
  badge,
  provider,
  baseUrl,
  model,
  apiKey,
  placeholder,
  testing,
  onApiKeyChange,
  onTest,
}: {
  title: string;
  subtitle: string;
  badge: string;
  provider: string;
  baseUrl: string;
  model: string;
  apiKey: string;
  placeholder: string;
  testing: boolean;
  onApiKeyChange: (value: string) => void;
  onTest: () => void;
}) {
  return (
    <section className="rounded-[24px] bg-white p-6 shadow-[0_14px_35px_rgba(25,48,84,0.08)]">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="inline-flex rounded-full bg-[#eef5ff] px-3 py-1 text-xs font-black tracking-[0.18em] text-[#2d72d9]">
            {badge}
          </div>
          <h2 className="mt-4 text-xl font-black text-[#18243a]">{title}</h2>
          <p className="mt-2 text-sm leading-7 text-[#718199]">{subtitle}</p>
        </div>
      </div>

      <div className="mt-5 rounded-2xl border border-[#e0e8f4] bg-[#f8fbff] p-4 text-sm">
        <InfoRow label="服务" value={provider} />
        <InfoRow label="模型" value={model} />
        <InfoRow label="地址" value={baseUrl} />
      </div>

      <label className="mt-5 block">
        <span className="mb-2 block text-sm font-bold text-[#40506a]">API Key</span>
        <input
          type="password"
          value={apiKey}
          onChange={(event) => onApiKeyChange(event.target.value)}
          placeholder={placeholder}
          className="h-14 w-full rounded-2xl border border-[#d7e2f0] bg-white px-4 text-base outline-none transition focus:border-[#2d72d9] focus:ring-4 focus:ring-[#2d72d9]/10"
        />
      </label>

      <button
        onClick={onTest}
        disabled={testing}
        className="mt-5 h-12 rounded-2xl bg-[#172a49] px-5 font-semibold text-white shadow-[0_12px_24px_rgba(23,42,73,0.18)] disabled:opacity-60"
      >
        {testing ? '测试中...' : '保存并测试连接'}
      </button>
    </section>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-3 py-1">
      <span className="w-12 shrink-0 font-semibold text-[#7b8ba3]">{label}</span>
      <span className="break-all font-mono text-[#243750]">{value}</span>
    </div>
  );
}

function AdvancedFields({
  title,
  config,
  onChange,
}: {
  title: string;
  config: McpConfig['vl'];
  onChange: (patch: Partial<McpConfig['vl']>) => void;
}) {
  return (
    <div className="rounded-2xl border border-[#e0e8f4] bg-[#f8fbff] p-4">
      <h3 className="mb-4 font-black text-[#22344f]">{title}</h3>
      <div className="grid gap-3">
        <Field label="Base URL" value={config.base_url} onChange={(value) => onChange({ base_url: value })} />
        <Field label="模型名" value={config.model_name} onChange={(value) => onChange({ model_name: value })} />
        <Field label="超时秒数" value={String(config.timeout_seconds)} onChange={(value) => onChange({ timeout_seconds: Number(value) || 120 })} />
        <Field label="最大重试次数" value={String(config.max_retries)} onChange={(value) => onChange({ max_retries: Number(value) || 2 })} />
        <Field label="并发数" value={String(config.concurrency)} onChange={(value) => onChange({ concurrency: Number(value) || 1 })} />
      </div>
    </div>
  );
}

function Field({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-bold text-[#687891]">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-11 w-full rounded-xl border border-[#d7e2f0] bg-white px-3 text-sm outline-none focus:border-[#2d72d9]"
      />
    </label>
  );
}
