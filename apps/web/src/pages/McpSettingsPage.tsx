import { useCallback, useEffect, useState } from 'react';

import {
  DEFAULT_AI_CONFIG,
  getMcpConfig,
  pushMcpConfigToBackend,
  saveMcpConfig,
} from '../services/api';
import {
  fetchAgentConfig,
  fetchMcpRuntimeConfig,
  fetchMcpStatus,
  saveAgentConfig,
  testClaudeCodeAgent,
  testMcpConnection,
} from '../services/aiApi';
import type {
  AgentConfig,
  AgentConfigResponse,
  AgentTestResponse,
  McpConfig,
  McpConnectionTestResponse,
  McpRuntimeStatus,
} from '../types';

const STATUS_LABEL: Record<string, string> = {
  http: '真实 API 模式',
  mock: '模拟模式',
  stdio: '本地 MCP 进程模式',
  disabled: '已关闭 AI',
};

const DEFAULT_AGENT_CONFIG: AgentConfig = {
  claude_code_path: '',
  enabled: false,
  timeout_seconds: 90,
};

function withDefaultProviders(config: McpConfig): McpConfig {
  return {
    ...config,
    vl: { ...DEFAULT_AI_CONFIG.vl, ...(config.vl || {}) },
    llm: { ...DEFAULT_AI_CONFIG.llm, ...(config.llm || {}) },
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
  const [agentConfig, setAgentConfig] = useState<AgentConfig>(DEFAULT_AGENT_CONFIG);
  const [agentStatus, setAgentStatus] = useState<AgentConfigResponse | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentSaving, setAgentSaving] = useState(false);
  const [agentTesting, setAgentTesting] = useState(false);
  const [agentSavedText, setAgentSavedText] = useState<string | null>(null);
  const [agentTestResult, setAgentTestResult] = useState<AgentTestResponse | null>(null);
  const [agentError, setAgentError] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    setLoadingStatus(true);
    setStatusError(null);
    try {
      const [status, runtimeConfig] = await Promise.all([
        fetchMcpStatus(),
        fetchMcpRuntimeConfig().catch(() => null),
      ]);
      if (runtimeConfig && (runtimeConfig.vl_configured || runtimeConfig.llm_configured)) {
        const localConfig = getMcpConfig();
        const next = withDefaultProviders({
          ...localConfig,
          vl: { ...runtimeConfig.vl, api_key: localConfig.vl.api_key },
          llm: { ...runtimeConfig.llm, api_key: localConfig.llm.api_key },
        });
        setConfig(next);
        saveMcpConfig(next);
      }
      setBackendStatus(status);
    } catch (err) {
      setStatusError((err as Error).message || '后端状态读取失败');
    } finally {
      setLoadingStatus(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const loadAgentConfig = useCallback(async () => {
    setAgentLoading(true);
    setAgentError(null);
    try {
      const result = await fetchAgentConfig();
      setAgentStatus(result);
      setAgentConfig(result.config);
    } catch (err) {
      setAgentError((err as Error).message || '智能体配置读取失败');
    } finally {
      setAgentLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAgentConfig();
  }, [loadAgentConfig]);

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

  const updateAgentConfig = (patch: Partial<AgentConfig>) => {
    setAgentConfig((prev) => ({ ...prev, ...patch }));
    setAgentSavedText(null);
    setAgentTestResult(null);
  };

  const saveAgentSettings = useCallback(async () => {
    setAgentSaving(true);
    setAgentError(null);
    setAgentSavedText(null);
    setAgentTestResult(null);
    try {
      const result = await saveAgentConfig({
        ...agentConfig,
        claude_code_path: agentConfig.claude_code_path.trim(),
        timeout_seconds: Number(agentConfig.timeout_seconds) || DEFAULT_AGENT_CONFIG.timeout_seconds,
      });
      setAgentConfig(result.config);
      setAgentStatus(result);
      setAgentSavedText(result.available ? 'Claude Code 路径已保存，智能体可用' : `路径已保存，但暂不可用：${result.message}`);
    } catch (err) {
      setAgentError((err as Error).message || '智能体配置保存失败');
    } finally {
      setAgentSaving(false);
    }
  }, [agentConfig]);

  const testAgentSettings = useCallback(async () => {
    setAgentTesting(true);
    setAgentError(null);
    setAgentSavedText(null);
    try {
      const saved = await saveAgentConfig({
        ...agentConfig,
        claude_code_path: agentConfig.claude_code_path.trim(),
        timeout_seconds: Number(agentConfig.timeout_seconds) || DEFAULT_AGENT_CONFIG.timeout_seconds,
      });
      setAgentConfig(saved.config);
      setAgentStatus(saved);
      setAgentTestResult(await testClaudeCodeAgent());
    } catch (err) {
      setAgentError((err as Error).message || 'Claude Code 测试失败');
    } finally {
      setAgentTesting(false);
    }
  }, [agentConfig]);

  const mode = backendStatus?.mode || 'unknown';
  const isHttpMode = mode === 'http' || Boolean(backendStatus && (backendStatus as unknown as Record<string, unknown>).http_mode);

  return (
    <div className="h-full overflow-y-auto bg-[#f3f6fa] px-3 py-3 text-[#18243a] sm:px-5 sm:py-4">
      <div className="mx-auto max-w-[1180px] space-y-4">
        <section className="rounded-lg border border-[#dce3ec] bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <h1 className="text-lg font-bold text-[#152238]">AI 服务配置</h1>
              <p className="mt-1 max-w-2xl text-xs leading-5 text-[#687891]">
                配置 OCR、文本模型与本地智能体连接。
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => void loadStatus()}
                disabled={loadingStatus}
                className="h-9 rounded-md border border-[#d8e2f0] bg-white px-3 text-sm font-semibold text-[#40506a] disabled:opacity-60"
              >
                {loadingStatus ? '刷新中...' : '刷新状态'}
              </button>
              <button
                onClick={() => void saveAndPush()}
                disabled={saving}
                className="h-9 rounded-md bg-[#2673d9] px-4 text-sm font-semibold text-white disabled:opacity-60"
              >
                {saving ? '保存中...' : '保存配置'}
              </button>
            </div>
          </div>

          <div className="mt-4 grid gap-2 md:grid-cols-3">
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

        <div className="grid gap-4 xl:grid-cols-2">
          <ProviderCard
            title="文字提取：Qwen-OCR"
            subtitle="用于图片、扫描 PDF、题干和公式 OCR 识别"
            badge="OCR"
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

        <section className="rounded-lg border border-[#dce3ec] bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-bold text-[#18243a]">本地智能体</h2>
              <p className="mt-1 max-w-3xl text-xs leading-5 text-[#718199]">
                可选：使用 Claude Code 读取题库候选上下文并完成选题。
              </p>
            </div>
            <StatusPill active={Boolean(agentStatus?.available)} text={agentStatus?.available ? '可用' : '未接通'} />
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_180px]">
            <label className="block">
              <span className="mb-2 block text-sm font-bold text-[#40506a]">Claude Code 路径</span>
              <input
                value={agentConfig.claude_code_path}
                onChange={(event) => updateAgentConfig({ claude_code_path: event.target.value })}
                placeholder="例如：claude、claude.cmd 或 C:\Users\...\claude.cmd"
                className="h-10 w-full rounded-md border border-[#d7e2f0] bg-white px-3 text-sm outline-none transition focus:border-[#2d72d9] focus:ring-2 focus:ring-[#2d72d9]/10"
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-bold text-[#40506a]">超时秒数</span>
              <input
                type="number"
                min={10}
                max={600}
                value={agentConfig.timeout_seconds}
                onChange={(event) => updateAgentConfig({ timeout_seconds: Number(event.target.value) || 90 })}
                className="h-10 w-full rounded-md border border-[#d7e2f0] bg-white px-3 text-sm outline-none transition focus:border-[#2d72d9] focus:ring-2 focus:ring-[#2d72d9]/10"
              />
            </label>
          </div>

          <label className="mt-3 flex items-center gap-3 rounded-md border border-[#e0e8f4] bg-[#f8fbff] px-3 py-2.5">
            <input
              type="checkbox"
              checked={agentConfig.enabled}
              onChange={(event) => updateAgentConfig({ enabled: event.target.checked })}
              className="h-4 w-4"
            />
            <span className="text-sm font-semibold text-[#40506a]">启用 Claude Code 作为对话选题智能体</span>
          </label>

          <div className="mt-5 flex flex-wrap gap-3">
            <button
              onClick={() => void saveAgentSettings()}
              disabled={agentSaving || agentLoading}
              className="h-9 rounded-md bg-[#2673d9] px-4 text-sm font-semibold text-white disabled:opacity-60"
            >
              {agentSaving ? '保存中...' : '保存智能体配置'}
            </button>
            <button
              onClick={() => void testAgentSettings()}
              disabled={agentTesting || agentLoading}
              className="h-9 rounded-md border border-[#d8e2f0] bg-white px-4 text-sm font-semibold text-[#40506a] disabled:opacity-60"
            >
              {agentTesting ? '测试中...' : '保存并测试 Claude Code'}
            </button>
          </div>

          {agentError && <Notice tone="danger" text={agentError} />}
          {agentSavedText && <Notice tone={agentStatus?.available ? 'success' : 'warning'} text={agentSavedText} />}
          {agentTestResult && (
            <Notice
              tone={agentTestResult.ok ? 'success' : 'warning'}
              text={`${agentTestResult.ok ? 'Claude Code 可用' : 'Claude Code 不可用'}：${agentTestResult.message}`}
            />
          )}
        </section>

        <section className="rounded-lg border border-[#dce3ec] bg-white p-4 shadow-sm">
          <button
            onClick={() => setShowAdvanced((value) => !value)}
            className="flex w-full items-center justify-between text-left"
          >
            <div>
              <h2 className="text-base font-bold text-[#18243a]">高级配置</h2>
              <p className="mt-1 text-xs text-[#7b8ba3]">模型名称、服务地址与超时参数</p>
            </div>
            <span className="rounded-md bg-[#edf4ff] px-3 py-1.5 text-xs font-semibold text-[#2d72d9]">
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
    <div className={`rounded-md border px-3 py-2.5 ${active ? 'border-[#bfe5d1] bg-[#f0fff6]' : 'border-[#dde6f3] bg-[#f7faff]'}`}>
      <div className="text-sm font-semibold text-[#7a8aa3]">{label}</div>
      <div className={`mt-1 text-base font-bold ${active ? 'text-[#14985d]' : 'text-[#3f506b]'}`}>{value}</div>
    </div>
  );
}

function StatusPill({ active, text }: { active: boolean; text: string }) {
  return (
    <span className={`rounded-full px-4 py-2 text-sm font-bold ${
      active ? 'bg-[#e8fff2] text-[#118352]' : 'bg-[#fff8e8] text-[#946817]'
    }`}>
      {text}
    </span>
  );
}

function Notice({ tone, text }: { tone: 'success' | 'warning' | 'danger'; text: string }) {
  const classes = {
    success: 'border-[#bfe5d1] bg-[#f0fff6] text-[#118352]',
    warning: 'border-[#f3d69a] bg-[#fff8e8] text-[#946817]',
    danger: 'border-[#ffc9c9] bg-[#fff1f1] text-[#d73535]',
  }[tone];
  return <div className={`mt-3 rounded-md border px-3 py-2 text-sm font-semibold ${classes}`}>{text}</div>;
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
    <section className="rounded-lg border border-[#dce3ec] bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="inline-flex rounded-full bg-[#eef5ff] px-3 py-1 text-xs font-black tracking-[0.18em] text-[#2d72d9]">
            {badge}
          </div>
          <h2 className="mt-2 text-base font-bold text-[#18243a]">{title}</h2>
          <p className="mt-2 text-sm leading-7 text-[#718199]">{subtitle}</p>
        </div>
      </div>

      <div className="mt-3 rounded-md border border-[#e0e8f4] bg-[#f8fbff] p-3 text-sm">
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
          className="h-10 w-full rounded-md border border-[#d7e2f0] bg-white px-3 text-sm outline-none transition focus:border-[#2d72d9] focus:ring-2 focus:ring-[#2d72d9]/10"
        />
        <span className="mt-2 block text-xs leading-5 text-[#718199]">
          密钥仅保留在当前浏览器会话中，关闭浏览器后需要重新填写。
        </span>
      </label>

      <button
        onClick={onTest}
        disabled={testing}
        className="mt-3 h-9 rounded-md bg-[#172a49] px-4 text-sm font-semibold text-white disabled:opacity-60"
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
    <div className="rounded-md border border-[#e0e8f4] bg-[#f8fbff] p-3">
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
