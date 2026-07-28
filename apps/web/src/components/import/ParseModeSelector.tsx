import type { DocumentSourceType, ImportCleaningOptions, ImportMode } from '../../types';

const MODE_LABELS: { value: ImportMode; label: string; desc: string; acceptsType?: string[] }[] = [
  { value: 'convert_only', label: '仅转换', desc: '将文档转换为 Markdown / HTML / 纯文本' },
  { value: 'convert_clean', label: '转换 + 清洗', desc: '转换后自动清洗页眉页脚、规整公式、压缩空行' },
  { value: 'convert_clean_parse', label: '转换 + 清洗 + 切题', desc: '完整流程：转换 → 清洗 → 提取结构化题目' },
  { value: 'ai_parse', label: 'AI 识别', desc: 'AI 视觉模型直接识别 PDF/图片中的题目（OCR + 排版 + 结构化输出）', acceptsType: ['pdf', 'jpg', 'jpeg', 'png', 'webp'] },
];

const TYPE_OPTIONS: { value: DocumentSourceType; label: string }[] = [
  { value: 'pdf', label: 'PDF' },
  { value: 'docx', label: 'DOCX' },
  { value: 'image', label: '图片' },
  { value: 'txt', label: 'TXT / HTML / MD' },
  { value: 'markdown', label: 'Markdown' },
  { value: 'html', label: 'HTML' },
];

export interface AiParseOptions {
  enable_preprocess: boolean;
  enable_region_detection: boolean;
  enable_figure_extraction: boolean;
  enable_table_extraction: boolean;
  ignore_headers_footers: boolean;
}

interface Props {
  mode: ImportMode;
  onModeChange: (mode: ImportMode) => void;
  sourceType: DocumentSourceType | 'auto';
  onSourceTypeChange: (type: DocumentSourceType) => void;
  autoDetectType: boolean;
  onAutoDetectTypeChange: (auto: boolean) => void;
  cleaningOptions: ImportCleaningOptions;
  onCleaningOptionsChange: (options: ImportCleaningOptions) => void;
  showCleaningOptions: boolean;
  aiOptions: AiParseOptions;
  onAiOptionsChange: (options: AiParseOptions) => void;
}

export default function ParseModeSelector({
  mode,
  onModeChange,
  sourceType,
  onSourceTypeChange,
  autoDetectType,
  onAutoDetectTypeChange,
  cleaningOptions,
  onCleaningOptionsChange,
  showCleaningOptions,
  aiOptions,
  onAiOptionsChange,
}: Props) {
  const toggleOption = (key: keyof ImportCleaningOptions) => {
    onCleaningOptionsChange({ ...cleaningOptions, [key]: !cleaningOptions[key] });
  };

  const toggleAiOption = (key: keyof AiParseOptions) => {
    onAiOptionsChange({ ...aiOptions, [key]: !aiOptions[key] });
  };

  const isAiMode = mode === 'ai_parse';
  const selectedMode = MODE_LABELS.find((m) => m.value === mode);

  // When AI mode is selected, only show PDF/image types
  const typeOptions =
    isAiMode && selectedMode?.acceptsType
      ? TYPE_OPTIONS.filter((opt) => selectedMode.acceptsType!.includes(opt.value))
      : TYPE_OPTIONS;

  return (
    <div
      className="rounded-lg border p-4"
      style={{ background: 'var(--color-bg-card)', borderColor: 'var(--color-border)', boxShadow: 'var(--shadow-card)' }}
    >
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--color-text-muted)' }}>
        解析模式
      </h3>

      {/* Mode Selection */}
      <div className="mt-2 space-y-2">
        {MODE_LABELS.map((item) => (
          <label
            key={item.value}
            className="flex cursor-pointer items-start gap-3 rounded border p-2.5 transition-colors"
            style={{
              borderColor: mode === item.value ? 'var(--color-accent)' : 'var(--color-border)',
              background: mode === item.value ? 'var(--color-accent-light)' : 'var(--color-bg)',
            }}
          >
            <input
              type="radio"
              name="importMode"
              value={item.value}
              checked={mode === item.value}
              onChange={() => {
                onModeChange(item.value);
                // Auto-switch source type when entering AI mode
                if (item.value === 'ai_parse' && item.acceptsType && !autoDetectType) {
                  const currentOk = item.acceptsType.includes(sourceType);
                  if (!currentOk) {
                    onSourceTypeChange(item.acceptsType[0] as DocumentSourceType);
                  }
                }
              }}
              className="mt-0.5"
            />
            <div className="flex-1">
              <div className="text-sm font-medium" style={{ color: 'var(--color-text)' }}>
                {item.label}
              </div>
              <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                {item.desc}
              </div>
            </div>
          </label>
        ))}
      </div>

      {/* Document Type */}
      <div className="mt-3 border-t pt-3" style={{ borderColor: 'var(--color-border)' }}>
        <div className="mb-2 text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          文档类型
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex cursor-pointer items-center gap-1.5 text-sm">
            <input
              type="checkbox"
              checked={autoDetectType}
              onChange={(event) => onAutoDetectTypeChange(event.target.checked)}
            />
            <span style={{ color: 'var(--color-text)' }}>自动检测</span>
          </label>
          {!autoDetectType && (
            <select
              value={sourceType === 'auto' ? (typeOptions[0]?.value ?? 'markdown') : sourceType}
              onChange={(event) => onSourceTypeChange(event.target.value as DocumentSourceType)}
              className="rounded border px-2 py-1 text-sm outline-none"
              style={{
                borderColor: 'var(--color-border)',
                background: 'var(--color-bg-card)',
                color: 'var(--color-text)',
              }}
            >
              {typeOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          )}
        </div>
      </div>

      {/* Cleaning Options (traditional modes only) */}
      {showCleaningOptions && (
        <div className="mt-3 border-t pt-3" style={{ borderColor: 'var(--color-border)' }}>
          <div className="mb-2 text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
            清洗选项
          </div>
          <div className="space-y-1.5">
            <ToggleOption
              label="清理页眉页脚"
              checked={cleaningOptions.strip_headers_footers}
              onChange={() => toggleOption('strip_headers_footers')}
            />
            <ToggleOption
              label="规整公式分隔符"
              checked={cleaningOptions.normalize_math_delimiters}
              onChange={() => toggleOption('normalize_math_delimiters')}
            />
            <ToggleOption
              label="压缩多余空行"
              checked={cleaningOptions.remove_blank_lines}
              onChange={() => toggleOption('remove_blank_lines')}
            />
          </div>
        </div>
      )}

      {/* AI Parse Options */}
      {isAiMode && (
        <div className="mt-3 border-t pt-3" style={{ borderColor: 'var(--color-border)' }}>
          <div className="mb-2 text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
            AI 识别选项
          </div>
          <div className="space-y-1.5">
            <ToggleOption
              label="预处理（去噪/纠偏）"
              checked={aiOptions.enable_preprocess}
              onChange={() => toggleAiOption('enable_preprocess')}
            />
            <ToggleOption
              label="区域检测"
              checked={aiOptions.enable_region_detection}
              onChange={() => toggleAiOption('enable_region_detection')}
            />
            <ToggleOption
              label="插图提取"
              checked={aiOptions.enable_figure_extraction}
              onChange={() => toggleAiOption('enable_figure_extraction')}
            />
            <ToggleOption
              label="表格提取"
              checked={aiOptions.enable_table_extraction}
              onChange={() => toggleAiOption('enable_table_extraction')}
            />
            <ToggleOption
              label="忽略页眉页脚"
              checked={aiOptions.ignore_headers_footers}
              onChange={() => toggleAiOption('ignore_headers_footers')}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function ToggleOption({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm">
      <input type="checkbox" checked={checked} onChange={onChange} />
      <span style={{ color: 'var(--color-text)' }}>{label}</span>
    </label>
  );
}
