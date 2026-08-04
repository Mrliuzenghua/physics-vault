import { useCallback, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArchiveRestore, Download, Save } from 'lucide-react';
import { downloadExportPackage, getSettings, restorePackage, saveSettings } from '../services/api';
import type { RestorePackageResponse, SystemSettings } from '../types';

export default function SettingsPage() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState<SystemSettings>(getSettings);
  const [saved, setSaved] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  // ── Restore state ──
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [restoreResult, setRestoreResult] = useState<RestorePackageResponse | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);

  const update = (patch: Partial<SystemSettings>) => {
    setSettings(prev => ({ ...prev, ...patch }));
    setSaved(false);
  };

  const handleSave = () => {
    saveSettings(settings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleExport = useCallback(async () => {
    setExporting(true);
    setExportMsg('正在打包导出…');
    try {
      await downloadExportPackage();
      setExportMsg('导出成功');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '导出失败';
      setExportMsg(`导出失败: ${message}`);
    } finally {
      setExporting(false);
      setTimeout(() => setExportMsg(null), 4000);
    }
  }, []);

  const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
    <section className="mb-4 rounded-lg border border-[var(--color-border)] bg-white p-4 shadow-sm">
      <h2 className="mb-3 border-b border-[var(--color-border)] pb-2 text-sm font-semibold text-[var(--color-text)]">
        {title}
      </h2>
      {children}
    </section>
  );

  const Field = ({ label, value, onChange, type = 'text', placeholder }: {
    label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string;
  }) => (
    <div className="mb-2.5">
      <label className="mb-1 block text-xs font-medium text-[var(--color-text-secondary)]">{label}</label>
      <input
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-9 w-full rounded-md border border-[var(--color-border)] bg-white px-3 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent-light)]"
      />
    </div>
  );

  const Toggle = ({ label, value, onChange, hint }: {
    label: string; value: boolean; onChange: (v: boolean) => void; hint?: string;
  }) => (
    <div className="flex items-center justify-between mb-2 py-1">
      <div>
        <span className="text-sm" style={{ color: 'var(--color-text)' }}>{label}</span>
        {hint && <span className="text-xs ml-2" style={{ color: 'var(--color-text-muted)' }}>({hint})</span>}
      </div>
      <button
        onClick={() => onChange(!value)}
        className="relative w-10 h-5 rounded-full cursor-pointer border-none transition-colors"
        style={{ background: value ? 'var(--color-green)' : 'var(--color-border)' }}
      >
        <span
          className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform shadow"
          style={{ left: value ? '22px' : '2px' }}
        />
      </button>
    </div>
  );

  return (
    <div className="h-full overflow-y-auto bg-[#f3f6fa] p-3 sm:p-5">
      <div className="mx-auto max-w-4xl">
      <div className="mb-4 flex items-center justify-between">
        <div><h1 className="text-lg font-bold text-[#1d3148]">系统设置</h1><p className="mt-1 text-xs text-[var(--color-text-muted)]">本地存储、显示、日志与数据迁移</p></div>
        <div className="flex gap-2">
          <button
            onClick={handleSave}
            className="flex h-9 cursor-pointer items-center gap-1.5 rounded-md border-none px-4 text-sm font-medium text-white"
            style={{ background: saved ? 'var(--color-green)' : 'var(--color-accent)' }}
          >
            <Save size={15} />{saved ? '已保存' : '保存设置'}
          </button>
        </div>
      </div>

      {/* 数据存储 */}
      <Section title="数据存储">
        <Field label="数据库路径" value={settings.db_path} onChange={v => update({ db_path: v })} />
        <Field label="素材目录" value={settings.assets_path} onChange={v => update({ assets_path: v })} />
        <Field label="导入批次目录" value={settings.import_batches_path} onChange={v => update({ import_batches_path: v })} />
        <Field label="缓存目录" value={settings.cache_path} onChange={v => update({ cache_path: v })} />
        <Field label="导出目录" value={settings.exports_path} onChange={v => update({ exports_path: v })} />
        <Field label="日志目录" value={settings.logs_path} onChange={v => update({ logs_path: v })} />
      </Section>

      {/* AI 设置 */}
      <Section title="AI 设置">
        <Toggle label="全局 AI 开关" value={settings.ai_enabled} onChange={v => update({ ai_enabled: v })} />
        <Toggle
          label="离线模式"
          value={settings.offline_mode}
          onChange={v => update({ offline_mode: v })}
          hint="启用后将禁止所有外部 AI 请求"
        />
        <button
          onClick={() => navigate('/settings/mcp')}
          className="mt-2 px-3 py-1.5 rounded text-sm cursor-pointer border"
          style={{ borderColor: 'var(--color-accent)', color: 'var(--color-accent)', background: 'transparent' }}
        >
          配置 AI 与 MCP
        </button>
      </Section>

      {/* 显示设置 */}
      <Section title="显示设置">
        <div className="mb-2">
          <label className="text-xs font-medium block mb-1" style={{ color: 'var(--color-text-secondary)' }}>主题</label>
          <div className="flex gap-2">
            {(['light', 'dark', 'system'] as const).map(t => (
              <button
                key={t}
                onClick={() => update({ theme: t })}
                className="px-3 py-1.5 rounded text-sm cursor-pointer border transition-colors"
                style={{
                  background: settings.theme === t ? 'var(--color-accent)' : 'var(--color-bg-card)',
                  color: settings.theme === t ? '#fff' : 'var(--color-text-secondary)',
                  borderColor: settings.theme === t ? 'var(--color-accent)' : 'var(--color-border)',
                }}
              >
                {t === 'light' ? '浅色' : t === 'dark' ? '深色' : '跟随系统'}
              </button>
            ))}
          </div>
        </div>
        <div className="mb-2">
          <label className="text-xs font-medium block mb-1" style={{ color: 'var(--color-text-secondary)' }}>每页显示题数</label>
          <select
            value={settings.page_size}
            onChange={e => update({ page_size: Number(e.target.value) })}
            className="px-3 py-1.5 rounded text-sm border outline-none"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)', color: 'var(--color-text)' }}
          >
            {[10, 20, 50, 100].map(n => <option key={n} value={n}>{n} 题/页</option>)}
          </select>
        </div>
      </Section>

      {/* 日志 */}
      <Section title="日志">
        <div className="mb-2">
          <label className="text-xs font-medium block mb-1" style={{ color: 'var(--color-text-secondary)' }}>日志级别</label>
          <select
            value={settings.log_level}
            onChange={e => update({ log_level: e.target.value as SystemSettings['log_level'] })}
            className="px-3 py-1.5 rounded text-sm border outline-none"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)', color: 'var(--color-text)' }}
          >
            {['DEBUG', 'INFO', 'WARNING', 'ERROR'].map(l => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
      </Section>

      {/* 数据迁移与备份 */}
      <Section title="数据导出">
        <p className="mb-3 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          将数据库文件和素材目录打包为一个 .zip 文件下载，方便迁移到其他设备或备份存档。
          导出包内含：数据库文件、素材目录、导出说明文件。
        </p>
        <div className="flex items-center gap-3">
          <button
            onClick={handleExport}
            disabled={exporting}
            className="px-4 py-2 rounded-lg text-sm font-medium cursor-pointer border-none text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ background: 'var(--color-accent)' }}
          >
            <span className="inline-flex items-center gap-1.5"><Download size={15} />{exporting ? '正在打包导出…' : '导出题库包'}</span>
          </button>
          {exportMsg && (
            <span
              className="text-xs"
              style={{
                color: exportMsg.includes('失败')
                  ? 'var(--color-red)'
                  : exportMsg === '正在打包导出…'
                    ? 'var(--color-text-muted)'
                    : 'var(--color-green)',
              }}
            >
              {exportMsg}
            </span>
          )}
        </div>
      </Section>

      {/* 导入恢复题库包 */}
      <Section title="数据恢复">
        <p className="mb-3 text-xs" style={{ color: 'var(--color-text-muted)' }}>
          选择之前导出的 .zip 迁移包，将数据库和素材恢复到当前系统。
          恢复前会自动备份当前数据，失败时当前数据不会被覆盖。
        </p>

        {/* Risk warning */}
        <div
          className="mb-3 rounded border p-2 text-xs"
          style={{
            borderColor: 'var(--color-orange)',
            background: 'var(--color-orange-light)',
            color: 'var(--color-orange)',
          }}
        >
          恢复将覆盖当前题库数据。系统会在恢复前自动创建旧数据备份，仍建议先手动导出当前数据。
        </div>

        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".zip"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setRestoreFile(f);
            setRestoreResult(null);
            setRestoreError(null);
          }}
          className="hidden"
        />

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={restoring}
            className="cursor-pointer rounded border px-4 py-1.5 text-sm font-medium transition-colors disabled:opacity-40"
            style={{
              borderColor: 'var(--color-accent)',
              color: 'var(--color-accent)',
              background: 'transparent',
            }}
          >
            选择恢复包
          </button>

          {restoreFile && (
            <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              {restoreFile.name} ({(restoreFile.size / 1024).toFixed(1)} KB)
            </span>
          )}

          <button
            onClick={async () => {
              if (!restoreFile) return;
              setRestoring(true);
              setRestoreResult(null);
              setRestoreError(null);
              try {
                const res = await restorePackage(restoreFile);
                setRestoreResult(res);
              } catch (err: unknown) {
                const msg = err instanceof Error ? err.message : '恢复失败';
                setRestoreError(msg);
              } finally {
                setRestoring(false);
              }
            }}
            disabled={!restoreFile || restoring}
            className="cursor-pointer rounded-lg border-none px-4 py-1.5 text-sm font-semibold text-white transition-colors disabled:opacity-40"
            style={{ background: 'var(--color-accent)' }}
          >
            <span className="inline-flex items-center gap-1.5"><ArchiveRestore size={15} />{restoring ? '恢复中...' : '开始恢复'}</span>
          </button>
        </div>

        {/* Success feedback */}
        {restoreResult && (
          <div
            className="mt-3 rounded border p-3 text-sm space-y-1"
            style={{
              borderColor: 'var(--color-green)',
              background: 'var(--color-green-light)',
              color: 'var(--color-green)',
            }}
          >
            <p className="font-semibold">恢复成功</p>
            <p>数据库文件：{restoreResult.database_file || '—'}</p>
            <p>素材数量：{restoreResult.asset_count} 个</p>
            {restoreResult.backup_path && (
              <p>旧数据备份：{restoreResult.backup_path}</p>
            )}
            {restoreResult.warnings.length > 0 && (
              <div style={{ color: 'var(--color-orange)' }}>
                {restoreResult.warnings.map((w, i) => (
                  <p key={i}>{w}</p>
                ))}
              </div>
            )}
            <p className="mt-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
              建议重启后端服务以确保数据库连接正确切换到恢复后的数据库。
            </p>
          </div>
        )}

        {/* Error feedback */}
        {restoreError && (
          <div
            className="mt-3 rounded border p-3 text-sm"
            style={{
              borderColor: 'var(--color-red)',
              background: 'var(--color-red-light)',
              color: 'var(--color-red)',
            }}
          >
            <p className="font-semibold">恢复失败</p>
            <p>{restoreError}</p>
            <p className="mt-1 text-xs">
              当前数据未被修改。请检查导入包是否完整，然后重试。
            </p>
          </div>
        )}
      </Section>

      {/* 关于 */}
      <Section title="关于">
        <div className="text-sm space-y-1" style={{ color: 'var(--color-text-secondary)' }}>
          <p>Physics Vault 版本：1.0.0</p>
          <p>数据库版本：20260721</p>
          <p>技术栈：React + TypeScript + Vite + Python FastAPI + SQLite</p>
        </div>
      </Section>
      </div>
    </div>
  );
}
