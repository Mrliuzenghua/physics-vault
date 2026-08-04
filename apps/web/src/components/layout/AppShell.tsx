import { Outlet, useLocation } from 'react-router-dom';
import { lazy, Suspense, useState, useCallback, useEffect, useRef } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import { GripHorizontal, X } from 'lucide-react';
import TopToolbar from './TopToolbar';
import SideNav from './SideNav';
import StatusBar from './StatusBar';
import { useTheme } from '../../hooks/useTheme';
import { useBasket } from '../../hooks/useBasket';
import { getSettings, saveSettings, searchQuestions, fetchProcessingRuns, fetchMcpStatus, fetchMcpRuntimeConfig, getMcpConfig, pushMcpConfigToBackend } from '../../services/api';
import type { McpRuntimeStatus, TaskLog } from '../../types';

const PersistentAiChatPage = lazy(() => import('../../pages/AiChatPage'));
const AI_WINDOW_MARGIN = 12;
const AI_WINDOW_TOP_MARGIN = 52;
const AI_WINDOW_WIDTH = 480;
const AI_WINDOW_HEIGHT = 900;
const AI_WINDOW_POSITION_KEY = 'physics_vault.ai_assistant.window_position.v3';

interface AiWindowPosition {
  x: number;
  y: number;
}

function clampAiPosition(position: AiWindowPosition): AiWindowPosition {
  if (typeof window === 'undefined') return position;
  const maxX = Math.max(AI_WINDOW_MARGIN, window.innerWidth - Math.min(AI_WINDOW_WIDTH, window.innerWidth - AI_WINDOW_MARGIN * 2) - AI_WINDOW_MARGIN);
  const maxY = Math.max(AI_WINDOW_TOP_MARGIN, window.innerHeight - Math.min(AI_WINDOW_HEIGHT, window.innerHeight - AI_WINDOW_TOP_MARGIN - AI_WINDOW_MARGIN) - AI_WINDOW_MARGIN);
  return {
    x: Math.min(maxX, Math.max(AI_WINDOW_MARGIN, position.x)),
    y: Math.min(maxY, Math.max(AI_WINDOW_TOP_MARGIN, position.y)),
  };
}

function defaultAiPosition(): AiWindowPosition {
  if (typeof window === 'undefined') return { x: 320, y: 96 };
  return clampAiPosition({
    x: window.innerWidth - Math.min(AI_WINDOW_WIDTH, window.innerWidth - AI_WINDOW_MARGIN * 2) - AI_WINDOW_MARGIN,
    y: Math.max(AI_WINDOW_TOP_MARGIN, window.innerHeight - Math.min(AI_WINDOW_HEIGHT, window.innerHeight - AI_WINDOW_TOP_MARGIN - AI_WINDOW_MARGIN) - 60),
  });
}

function readAiPosition(): AiWindowPosition {
  if (typeof window === 'undefined') return defaultAiPosition();
  try {
    const parsed = JSON.parse(window.localStorage.getItem(AI_WINDOW_POSITION_KEY) || 'null');
    if (parsed && typeof parsed.x === 'number' && typeof parsed.y === 'number') {
      return clampAiPosition(parsed);
    }
  } catch {
    // Ignore invalid local storage.
  }
  return defaultAiPosition();
}

export default function AppShell() {
  const location = useLocation();
  const isFocusedWorkspace = ['/compose', '/handout', '/slides', '/classroom'].some((path) => location.pathname.startsWith(path))
    || location.pathname.startsWith('/review/');
  useTheme();
  const { count: basketCount } = useBasket();
  const [settings, setSettings] = useState(getSettings);
  // On narrower laptops, preserve space for the actual teaching workspace.
  // The full navigation remains one click away in the header.
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => (
    typeof window !== 'undefined' && window.innerWidth < 1180
  ));
  const [aiAssistantOpen, setAiAssistantOpen] = useState(false);
  const [aiWindowPosition, setAiWindowPosition] = useState<AiWindowPosition>(() => readAiPosition());
  const [aiDragging, setAiDragging] = useState(false);
  const aiDragRef = useRef<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);

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
    http_mode: false,
    vl_model: null,
    llm_model: null,
    last_checked_at: null,
  });

  // Push locally-saved AI config to the backend on startup so AI features
  // keep working transparently after a backend restart.
  useEffect(() => {
    if (!settings.ai_enabled) return;
    let isCancelled = false;
    const syncRuntimeConfig = async () => {
      const localConfig = getMcpConfig();
      const backendConfig = await fetchMcpRuntimeConfig().catch(() => null);
      if (isCancelled) return;
      const sourceConfig = backendConfig && (backendConfig.vl_configured || backendConfig.llm_configured)
        ? { ...localConfig, vl: backendConfig.vl, llm: backendConfig.llm }
        : localConfig;
      const hasProviderKey = Boolean(sourceConfig?.vl?.api_key || sourceConfig?.llm?.api_key);
      if (!hasProviderKey) return;
      await pushMcpConfigToBackend(sourceConfig);
    };
    syncRuntimeConfig().catch(() => {
      // Backend not ready yet or config rejected; the periodic status poll
      // will surface the current state without blocking the shell.
    });
    return () => {
      isCancelled = true;
    };
    // Run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch stats periodically
  useEffect(() => {
    let isCancelled = false;

    const fetchStats = async () => {
      // Question total (just need the total, 1 item is enough)
      searchQuestions({ limit: 1 })
        .then((searchResult) => {
          if (!isCancelled) setQuestionCount(searchResult.total);
        })
        .catch(() => {
          // Keep the previous count when the backend is temporarily unavailable.
        });

      // Running task count
      fetchProcessingRuns()
        .then((runs: TaskLog[]) => {
          if (!isCancelled) {
            const running = runs.filter((r: TaskLog) => r.status === 'running' || r.status === 'pending').length;
            setRunningTaskCount(running);
          }
        })
        .catch(() => {
          // Task logs are optional for the status bar.
        });

      // MCP status is independent from question/task stats so unrelated API
      // failures cannot make the AI services look offline.
      if (settings.ai_enabled) {
        fetchMcpStatus()
          .then((status) => {
            if (!isCancelled) setMcpStatus(status);
          })
          .catch(() => {
            if (!isCancelled) {
              setMcpStatus((current) => ({
                ...current,
                last_checked_at: null,
              }));
            }
          });
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

  useEffect(() => {
    const openAssistant = () => setAiAssistantOpen(true);
    window.addEventListener('physics-vault:open-ai-assistant', openAssistant);
    return () => window.removeEventListener('physics-vault:open-ai-assistant', openAssistant);
  }, []);

  useEffect(() => {
    const handleResize = () => {
      setAiWindowPosition((prev) => {
        const next = clampAiPosition(prev);
        try {
          window.localStorage.setItem(AI_WINDOW_POSITION_KEY, JSON.stringify(next));
        } catch {
          // Storage is optional.
        }
        return next;
      });
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    if (!aiDragging) return;

    const handlePointerMove = (event: PointerEvent) => {
      const drag = aiDragRef.current;
      if (!drag) return;
      setAiWindowPosition(
        clampAiPosition({
          x: drag.originX + event.clientX - drag.startX,
          y: drag.originY + event.clientY - drag.startY,
        }),
      );
    };

    const handlePointerUp = () => {
      setAiDragging(false);
      aiDragRef.current = null;
      setAiWindowPosition((prev) => {
        const next = clampAiPosition(prev);
        try {
          window.localStorage.setItem(AI_WINDOW_POSITION_KEY, JSON.stringify(next));
        } catch {
          // Storage is optional.
        }
        return next;
      });
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
    };
  }, [aiDragging]);

  const handleAiDragStart = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      aiDragRef.current = {
        startX: event.clientX,
        startY: event.clientY,
        originX: aiWindowPosition.x,
        originY: aiWindowPosition.y,
      };
      setAiDragging(true);
    },
    [aiWindowPosition.x, aiWindowPosition.y],
  );

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[var(--color-bg)]">
      <TopToolbar
        aiEnabled={settings.ai_enabled}
        onToggleAi={handleToggleAi}
        basketCount={basketCount}
        taskCount={runningTaskCount}
        showSidebarToggle={!isFocusedWorkspace}
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={() => setSidebarCollapsed((current) => !current)}
      />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {!isFocusedWorkspace && <SideNav collapsed={sidebarCollapsed} />}
        <main className="min-w-0 flex-1 overflow-hidden bg-[var(--color-bg)]" id="main-content">
          <Suspense fallback={<MainLoading />}>
            <div className="h-full overflow-auto">
              <Outlet />
            </div>
          </Suspense>
        </main>
      </div>
      <StatusBar
        questionCount={questionCount}
        mcpVlOnline={mcpStatus.vl_available}
        mcpLlmOnline={mcpStatus.llm_available}
        mcpRuntimeEnabled={mcpStatus.enabled}
        mcpMode={mcpStatus.mode}
        mcpVlModel={mcpStatus.vl_model}
        mcpLlmModel={mcpStatus.llm_model}
        mcpLastCheckedAt={mcpStatus.last_checked_at}
        aiEnabled={settings.ai_enabled}
      />
      {location.pathname !== '/handout' && <div className="fixed bottom-5 right-5 z-50">
        {aiAssistantOpen ? (
          <section
            className={`fixed overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] shadow-[0_18px_54px_rgba(15,23,42,0.24)] ${
              aiDragging ? 'select-none ring-2 ring-slate-300' : ''
            }`}
            style={{
              left: aiWindowPosition.x,
              top: aiWindowPosition.y,
              width: `min(${AI_WINDOW_WIDTH}px, calc(100vw - ${AI_WINDOW_MARGIN * 2}px))`,
              height: `min(${AI_WINDOW_HEIGHT}px, calc(100vh - ${AI_WINDOW_TOP_MARGIN + AI_WINDOW_MARGIN}px))`,
            }}
          >
            <div
              className="flex h-9 cursor-move items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-hover)] px-3"
              onPointerDown={handleAiDragStart}
            >
              <div className="flex items-center gap-2 text-xs font-bold text-[var(--color-text-secondary)]">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-[var(--color-accent)] text-[10px] text-white">AI</span>
                AI 助手
                <GripHorizontal size={14} className="text-[var(--color-text-muted)]" />
              </div>
              <button
                type="button"
                onPointerDown={(event) => event.stopPropagation()}
                onClick={() => setAiAssistantOpen(false)}
                className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--color-text-muted)] hover:bg-[var(--color-bg-card)] hover:text-[var(--color-text)]"
                aria-label="收起 AI 助手"
                title="收起 AI 助手"
              >
                <X size={16} />
              </button>
            </div>
            <div className="ai-assistant-compact h-[calc(100%-36px)] min-h-0">
              <Suspense fallback={<MainLoading />}>
                <PersistentAiChatPage />
              </Suspense>
            </div>
          </section>
        ) : (
          <button
            type="button"
            onClick={() => setAiAssistantOpen(true)}
            className="flex h-12 items-center gap-2 rounded-full bg-[var(--color-accent)] px-5 text-sm font-bold text-white shadow-[0_14px_36px_rgba(15,23,42,0.28)] transition hover:bg-[var(--color-accent-dark)]"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-xs font-black text-[var(--color-accent)]">AI</span>
            AI 助手
          </button>
        )}
      </div>}
    </div>
  );
}

function MainLoading() {
  return (
    <div className="flex h-full items-center justify-center text-sm text-[var(--color-text-muted)]">
      Loading...
    </div>
  );
}
