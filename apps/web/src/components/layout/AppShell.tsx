import { Outlet } from 'react-router-dom';
import { Suspense, useState, useCallback, useEffect } from 'react';
import TopToolbar from './TopToolbar';
import SideNav from './SideNav';
import StatusBar from './StatusBar';
import { useTheme } from '../../hooks/useTheme';
import { useBasket } from '../../hooks/useBasket';
import { getSettings, saveSettings, searchQuestions, fetchProcessingRuns, fetchMcpStatus, getMcpConfig, pushMcpConfigToBackend } from '../../services/api';
import type { McpRuntimeStatus, TaskLog } from '../../types';

export default function AppShell() {
  const { toggleTheme } = useTheme();
  const { count: basketCount } = useBasket();
  const [settings, setSettings] = useState(getSettings);

  // Live stats from backend
  const [questionCount, setQuestionCount] = useState(0);
  const [runningTaskCount, setRunningTaskCount] = useState(0);
  const [mcpStatus, setMcpStatus] = useState<McpRuntimeStatus>({
    enabled: false,
    mode: '',
    working_directory: null,
    tools: {
      parse_document: 'unknown',
      detect_question_regions: 'unknown',
      parse_question_region: 'unknown',
      generate_analysis: 'unknown',
      generate_knowledge: 'unknown',
      generate_metadata: 'unknown',
    },
    vl_available: false,
    llm_available: false,
    last_checked_at: null,
  });

  // Push locally-saved AI config to the backend on startup so AI features
  // keep working transparently after a backend restart.
  useEffect(() => {
    if (!settings.ai_enabled) return;
    const config = getMcpConfig();
    if (!config?.llm?.base_url || !config?.llm?.api_key) return;
    pushMcpConfigToBackend(config).catch(() => {
      // Backend not ready yet or config rejected — silently ignore,
      // the periodic status poll will surface any real problem.
    });
    // Run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch stats periodically
  useEffect(() => {
    let isCancelled = false;

    const fetchStats = async () => {
      try {
        // Question total (just need the total, 1 item is enough)
        const searchResult = await searchQuestions({ limit: 1 });
        if (!isCancelled) {
          setQuestionCount(searchResult.total);
        }

        // Running task count
        const runs: TaskLog[] = await fetchProcessingRuns();
        if (!isCancelled) {
          const running = runs.filter((r: TaskLog) => r.status === 'running' || r.status === 'pending').length;
          setRunningTaskCount(running);
        }

        // MCP status
        if (settings.ai_enabled) {
          const status = await fetchMcpStatus();
          if (!isCancelled) {
            setMcpStatus(status);
          }
        }
      } catch {
        // Backend unavailable — that's fine, just show 0
      }
    };

    fetchStats();
    const interval = setInterval(fetchStats, 15_000);

    return () => {
      isCancelled = true;
      clearInterval(interval);
    };
  }, [settings.ai_enabled]);

  const handleToggleAi = useCallback(() => {
    const updated = { ...settings, ai_enabled: !settings.ai_enabled };
    setSettings(updated);
    saveSettings(updated);
  }, [settings]);

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <TopToolbar
        aiEnabled={settings.ai_enabled}
        onToggleAi={handleToggleAi}
        onToggleTheme={toggleTheme}
        basketCount={basketCount}
        taskCount={runningTaskCount}
      />
      <div className="flex flex-1 overflow-hidden">
        <SideNav />
        <main className="flex-1 overflow-auto bg-[var(--color-bg)]" id="main-content">
          <Suspense
            fallback={
              <div className="flex min-h-full items-center justify-center text-sm text-[var(--color-text-muted)]">
                Loading...
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </main>
      </div>
      <StatusBar
        questionCount={questionCount}
        mcpVlOnline={mcpStatus.vl_available}
        mcpLlmOnline={mcpStatus.llm_available}
        aiEnabled={settings.ai_enabled}
      />
    </div>
  );
}
