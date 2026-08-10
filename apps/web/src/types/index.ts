export type QuestionType = 'single_choice' | 'multi_choice' | 'fill' | 'experiment' | 'calculation';

export type ReviewStatus = 'parsed' | 'reviewing' | 'approved' | 'rejected';

export type QuestionStatus = string;

export interface Option {
  opt: string;
  content: string;
}

export interface Figure {
  fig_uuid: string;
  local_path: string;
  display_scale?: number;
  display_align?: 'left' | 'center' | 'right';
  caption?: string;
}

export interface SubQuestion {
  sub_id: string;
  title: string;
  answer: string;
  analysis: string;
}

export interface KnowledgePoint {
  rank: number;
  topic1_id: string;
  topic1_name: string;
  topic2_id: string;
  topic2_name: string;
  topic3_id: string;
  topic3_name: string;
  source_chapter?: string;
  source?: string;
  confidence?: number;
  note?: string;
}

export interface Question {
  question_id: string;
  question_type: QuestionType;
  title: string;
  options: Option[];
  answer: string;
  analysis: string;
  editor_document?: Record<string, unknown>;
  sub_questions: SubQuestion[];
  figures: Figure[];
  difficulty: number;
  knowledge_point: string;
  knowledge_points: KnowledgePoint[];
  tags: string[];
  source: string;
  year?: number;
  import_batch_id?: string;
  origin_file?: string;
  origin_page?: number;
  review_status: ReviewStatus;
  review_comment?: string;
  is_mistake?: boolean;
  mistake_marked_at?: string | null;
  annotation_count?: number;
  status?: QuestionStatus;
  module?: string;
  topic2?: string;
  topic3?: string;
  primary_paper_id?: string;
  primary_question_no?: string;
  canonical_title?: string;
  has_media?: boolean;
  image_filenames?: string[];
  image_asset_ids?: string[];
  image_count?: number;
  stem_text?: string;
  model_type?: string;
  experiment_type?: string;
  created_at?: string;
  updated_at?: string;
  keyword_match?: boolean;
  similarity?: number | null;
  score?: number;
}

export interface SearchFilters {
  search_mode?: 'browse' | 'strict' | 'hybrid' | 'similar';
  query?: string;
  paper_id?: string;
  year?: number;
  region?: string;
  exam_type?: string;
  module?: string;
  topic2?: string;
  topic3?: string;
  topic1_id?: string;
  topic2_id?: string;
  topic3_id?: string;
  topic_rank?: number;
  difficulty?: string;
  question_type?: string;
  status?: string;
  has_media?: boolean;
  image_count_min?: number;
  is_mistake?: boolean;
  provider?: string;
  model?: string;
  vector_type?: string;
  limit?: number;
  offset?: number;
  candidate_limit?: number;
}

export interface FilterFacets {
  years: number[];
  regions: string[];
  exam_types: string[];
  modules: string[];
  question_types: string[];
  difficulties: string[];
  statuses: string[];
}

export interface KnowledgeTreeNode {
  topic1_id: string;
  topic1_name: string;
  children?: KnowledgeTreeLevel2[];
}

export interface KnowledgeTreeLevel2 {
  topic2_id: string;
  topic2_name: string;
  children?: KnowledgeTreeLevel3[];
}

export interface KnowledgeTreeLevel3 {
  topic3_id: string;
  topic3_name: string;
}

/** Flat knowledge-point row as returned by GET /knowledge-points. */
export interface KnowledgePointFlatItem {
  topic3_id: string;
  topic3_name: string;
  topic2_id: string;
  topic2_name: string;
  topic1_id: string;
  topic1_name: string;
  source_chapter?: string | null;
  status?: string;
  note?: string | null;
}

export interface Collection {
  id: string;
  name: string;
  parent_id: string | null;
  type: 'directory' | 'topic_collection' | 'paper_collection' | 'custom';
  question_count: number;
  children?: Collection[];
  created_at?: string;
  updated_at?: string;
}

export interface BasketItem {
  question_id: string;
  added_at: string;
  question?: Question;
}

// ── Compose / Composition Page Types ──

export interface ComposeQuestionItem {
  type: 'question';
  id: string;
  questionId: string;
  question?: Question;
}

export interface ComposeKnowledgeItem {
  type: 'knowledge';
  id: string;
  knowledgeId: string;
  title: string;
  content?: string;
  summary: string;
  points: string[];
}

export type HandoutTextBlockKind = 'body' | 'exam_title' | 'name_line' | 'section_title' | 'text_box';

export interface HandoutTextBlockStyle {
  fontFamily?: HandoutFontFamily;
  fontSize?: number;
  fontWeight?: 'normal' | 'bold';
  textAlign?: HeaderFooterAlignment;
}

export interface ComposeTextItem {
  type: 'text';
  id: string;
  title: string;
  content: string;
  document?: Record<string, unknown>;
  blockKind?: HandoutTextBlockKind;
  style?: HandoutTextBlockStyle;
}

export interface ComposeSeparatorItem {
  type: 'separator';
  id: string;
  title: string;
}

export type ComposeItem =
  | ComposeQuestionItem
  | ComposeKnowledgeItem
  | ComposeTextItem
  | ComposeSeparatorItem;

export interface LessonKnowledgeCard {
  id: string;
  title: string;
  content?: string;
  summary: string;
  points: string[];
  relatedQuestionIds: string[];
}

export interface LessonQuestionNode {
  type: 'question';
  id: string;
  questionId: string;
}

export interface LessonTextBlock {
  id: string;
  title: string;
  content: string;
  document?: Record<string, unknown>;
  blockKind?: HandoutTextBlockKind;
  style?: HandoutTextBlockStyle;
}

export interface LessonKnowledgeNode {
  type: 'knowledge';
  id: string;
  knowledgeId: string;
}

export interface LessonTextNode {
  type: 'text';
  id: string;
  textBlockId: string;
}

export interface LessonPageBreakNode {
  type: 'page_break';
  id: string;
  title?: string;
}

export type LessonPackageNode =
  | LessonQuestionNode
  | LessonKnowledgeNode
  | LessonTextNode
  | LessonPageBreakNode;

export interface LessonPackage {
  id: string;
  title: string;
  subtitle: string;
  source: 'compose' | 'basket' | 'template' | 'ai';
  questions: Question[];
  knowledgeCards: LessonKnowledgeCard[];
  textBlocks: LessonTextBlock[];
  nodes: LessonPackageNode[];
  headerFooter?: HandoutHeaderFooterConfig;
  styleConfig?: HandoutStyleConfig;
  formatSpec?: Record<string, unknown>;
  slideTemplate?: import('./slides').SlideDeckTemplate;
  folderId?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PaperDraftItem {
  id: string;
  type: 'question' | 'knowledge' | 'text' | 'separator' | 'page_break';
  position: number;
  question_id?: string | null;
  title?: string | null;
  section_title?: string | null;
  score?: number | null;
  payload?: Record<string, unknown>;
}

export interface PaperDraftSummary {
  id: string;
  title: string;
  subtitle?: string | null;
  source: string;
  status: string;
  question_count: number;
  item_count: number;
  total_score: number;
  created_at: string;
  updated_at: string;
}

export interface PaperDraft extends PaperDraftSummary {
  items: PaperDraftItem[];
  metadata: Record<string, unknown>;
  quality_report: Record<string, unknown>;
}

export interface PaperDraftListResponse {
  items: PaperDraftSummary[];
}

export interface SavedLessonPackageSummary {
  id: string;
  title: string;
  subtitle: string;
  updatedAt: string;
  questionCount: number;
  knowledgeCount: number;
  nodeCount: number;
  folderId?: string | null;
}

export interface LessonFolder {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
}

export type TemplateType = 'style' | 'layout' | 'handout' | 'teaching';
export type TemplateScope = 'all' | 'compose' | 'handout' | 'slides' | 'classroom';

export interface Template {
  id: string;
  name: string;
  type: TemplateType;
  scope?: TemplateScope;
  config: TemplateConfig;
  created_at?: string;
  updated_at?: string;
}

export interface TemplateConfig {
  knowledge_mode?: 'static' | 'ai';
  knowledge_style?: string;
  knowledge_length?: string;
  show_answer?: boolean;
  show_analysis?: boolean;
  question_number_style?: string;
  figure_scale?: string;
  font_family?: string;
  font_size?: string;
  line_height?: string;
  page_size?: 'A4' | 'A3';
  orientation?: 'portrait' | 'landscape';
  header?: string;
  footer?: string;
  sections?: string[];
  option_layout?: 'auto' | 'single' | 'double';
  keep_question_together?: boolean;
  keep_figure_with_stem?: boolean;
  start_long_question_on_new_page?: boolean;
  page_fill_percent?: number;
}

// ── Question Version History ──

export interface QuestionVersionSummary {
  version_id: string;
  question_id: string;
  version_number: number;
  change_summary: string | null;
  modified_by: string;
  source: string;
  created_at: string;
}

export interface QuestionVersionDetail extends QuestionVersionSummary {
  snapshot: Record<string, unknown>;
}

// ── Template Material Package ──

export type MaterialPackageType = 'question_bank' | 'example_set' | 'exercise_set' | 'training_set';
export type MaterialPackageSource = 'basket' | 'collection' | 'search';

export const MATERIAL_PACKAGE_TYPE_LABELS: Record<MaterialPackageType, string> = {
  question_bank: '题库素材',
  example_set: '例题区',
  exercise_set: '习题区',
  training_set: '训练区',
};

export interface TemplateMaterialPackage {
  id: string;
  name: string;
  type: MaterialPackageType;
  questions: Question[];
  questionIds: string[];
  source: MaterialPackageSource;
  sourceLabel: string;
  templateId?: string;
  config: TemplateConfig;
  created_at: string;
  updated_at: string;
}

export interface Layout {
  id: string;
  name: string;
  template_id?: string;
  items: LayoutItem[];
  pages: LayoutPage[];
  created_at?: string;
  updated_at?: string;
}

export interface LayoutItem {
  id: string;
  type: 'question' | 'text' | 'knowledge' | 'image' | 'separator';
  content: string;
  page_index: number;
  position_y: number;
  locked: boolean;
}

export interface LayoutPage {
  index: number;
  items: string[];
}

export interface ImportBatch {
  batch_id: string;
  files: string[];
  status: 'pending' | 'preprocessing' | 'cutting' | 'recognizing' | 'partial_failed' | 'completed' | 'cancelled';
  total_blocks: number;
  completed_blocks: number;
  failed_blocks: number;
  created_at: string;
}

export interface QuestionBlock {
  block_id: string;
  batch_id: string;
  page_number: number;
  status: string;
  rect?: { x: number; y: number; w: number; h: number };
  ocr_result?: Question;
  error?: string;
}

export interface AiBatchTask {
  task_id: string;
  type: string;
  status: 'pending' | 'running' | 'completed' | 'partial_failed' | 'failed';
  total_questions: number;
  success_count: number;
  fail_count: number;
  fields: string[];
  prompt_template: string;
  created_at: string;
  finished_at?: string;
}

export interface SystemSettings {
  db_path: string;
  assets_path: string;
  import_batches_path: string;
  cache_path: string;
  exports_path: string;
  logs_path: string;
  ai_enabled: boolean;
  offline_mode: boolean;
  theme: 'light' | 'dark' | 'system';
  log_level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
  page_size: number;
}

export interface McpConfig {
  vl: McpServiceConfig;
  llm: McpServiceConfig;
  scheduling: McpSchedulingConfig;
  cleaning: McpCleaningConfig;
  logging: McpLoggingConfig;
  capability_mapping: McpCapabilityMapping;
}

export interface McpServiceConfig {
  service_type: string;
  base_url: string;
  api_key: string;
  model_name: string;
  timeout_seconds: number;
  max_retries: number;
  concurrency: number;
}

export interface McpSchedulingConfig {
  queue_size: number;
  request_interval_ms: number;
  max_consecutive_failures: number;
}

export interface McpCleaningConfig {
  remove_markdown_wrapper: boolean;
  remove_extra_text: boolean;
  validate_json: boolean;
  auto_correct: boolean;
}

export interface McpLoggingConfig {
  log_requests: boolean;
  log_responses: boolean;
  log_full_prompt: boolean;
  retention_days: number;
}

export interface McpCapabilityMapping {
  recognition_ai: string;
  generation_ai: string;
  annotation_ai: string;
}

/** Keyed by the 6 standard MCP tool names. */
export type McpToolStatusMap = Record<
  | 'parse_document'
  | 'detect_question_regions'
  | 'parse_question_region'
  | 'generate_analysis'
  | 'generate_knowledge'
  | 'generate_metadata',
  string
>;

export interface McpRuntimeStatus {
  enabled: boolean;
  mode: string;
  working_directory: string | null;
  tools: McpToolStatusMap;
  vl_available: boolean;
  llm_available: boolean;
  http_mode?: boolean;
  vl_model?: string | null;
  llm_model?: string | null;
  last_checked_at: string | null;
}

export interface McpConnectionTestRequest {
  target: 'vl' | 'llm';
}

export interface McpConnectionTestResponse {
  ok: boolean;
  target: string;
  mode: string;
  reachable: boolean;
  message: string;
}

export interface AiChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface AiChatTestResponse {
  model: string;
  reply: string;
  usage?: Record<string, unknown> | null;
}

export interface AiAssistantQuestionContext {
  question_id: string;
  title: string;
  question_type?: string | null;
  difficulty?: string | null;
  knowledge_point?: string | null;
  source?: string | null;
  answer?: string | null;
  analysis?: string | null;
  tags: string[];
}

export interface AiAssistantCompositionSuggestion {
  title: string;
  rationale: string;
  question_ids: string[];
  estimated_score: number;
  difficulty_mix: Record<string, number>;
}

export interface AiAssistantResponse {
  reply: string;
  model: string;
  ai_used: boolean;
  query_used: string;
  context_questions: AiAssistantQuestionContext[];
  composition_suggestions: AiAssistantCompositionSuggestion[];
  warnings: string[];
  usage?: Record<string, unknown> | null;
}

export interface AgentConfig {
  claude_code_path: string;
  enabled: boolean;
  timeout_seconds: number;
}

export interface AgentConfigResponse {
  config: AgentConfig;
  available: boolean;
  message: string;
}

export interface AgentTestResponse {
  ok: boolean;
  message: string;
  version?: string | null;
}

export interface ReviewLatexCleanupResponse {
  ok: boolean;
  task_id?: string | null;
  dry_run: boolean;
  fast_path: boolean;
  changed_questions: number;
  replacement_count: number;
  elapsed_ms: number;
  items: Array<Record<string, unknown>>;
  error?: string | null;
  message: string;
}

export interface AgentAction {
  action_id: string;
  type: 'add_to_basket' | 'create_paper_draft' | 'open_questions';
  label: string;
  question_ids: string[];
  payload: Record<string, unknown>;
  requires_confirmation: boolean;
}

export interface AgentTraceStep {
  title: string;
  detail: string;
  status: 'done' | 'warning' | 'error';
}

export interface AgentStreamEvent {
  type: 'trace' | 'terminal' | 'warning' | 'error' | 'response';
  message?: string;
  step?: AgentTraceStep;
  response?: QuestionPickerAgentResponse;
}

export interface QuestionPickerAgentResponse {
  reply: string;
  agent_used: boolean;
  agent_name: string;
  session_id?: string | null;
  query_used: string;
  selected_questions: AiAssistantQuestionContext[];
  actions: AgentAction[];
  warnings: string[];
  trace: AgentTraceStep[];
  raw_agent_text?: string | null;
}

export interface TaskLog {
  run_id: string;
  pipeline_name: string;
  status: string;
  started_at: string;
  finished_at?: string;
  summary?: Record<string, unknown>;
  question_count?: number;
  success_count?: number;
  fail_count?: number;
}

export interface ChangeBatch {
  batch_id: string;
  change_type: string;
  reason?: string | null;
  source: string;
  status: string;
  target_count: number;
  changed_count: number;
  created_at: string;
  applied_at?: string | null;
  rolled_back_at?: string | null;
  rollback_reason?: string | null;
}

export interface ChangeItem {
  item_id: string;
  batch_id: string;
  entity_type: string;
  entity_id: string;
  field_name: string;
  status: string;
  risk_level: string;
  created_at: string;
  before_value: unknown;
  after_value: unknown;
}

export interface RollbackPreviewItem {
  question_id: string;
  field_name: string;
  current_value: unknown;
  rollback_to: unknown;
  expected_current: unknown;
  status: 'will_rollback' | 'already_rolled_back' | 'current_value_conflict' | string;
}

export interface ChangeBatchListResponse {
  ok: boolean;
  items: ChangeBatch[];
  total: number;
  limit: number;
  canonical_database_path?: string;
  review_database_path?: string;
}

export interface ChangeBatchDetailResponse {
  ok: boolean;
  batch: ChangeBatch;
  items: ChangeItem[];
  canonical_database_path?: string;
  review_database_path?: string;
}

export interface RollbackChangeBatchResponse {
  ok: boolean;
  batch_id: string;
  change_type: string;
  dry_run: boolean;
  requires_confirmation: boolean;
  rollbackable_count: number;
  changed_count: number;
  conflict_count: number;
  items: RollbackPreviewItem[];
  batch?: ChangeBatch;
}

export interface SearchResponse {
  items: Question[];
  total: number;
  limit: number;
  offset: number;
  search_mode: string;
  facets?: FilterFacets;
}

export interface ApiError {
  detail: string;
}

// ── Import Pipeline Types ──

export type ImportMode = 'convert_only' | 'convert_clean' | 'convert_clean_parse' | 'ai_parse';

export type ImportTaskStatus =
  | 'pending'
  | 'running'
  | 'retrying'
  | 'cancel_requested'
  | 'cancelled'
  | 'completed'
  | 'failed';

export type DocumentSourceType = 'pdf' | 'docx' | 'markdown' | 'html' | 'txt' | 'image';

export type TargetFormat = 'markdown' | 'html' | 'plain';

export type ImportTaskType = 'convert' | 'clean' | 'parse' | 'ai_parse';

export interface ConvertDocumentRequest {
  source_path: string;
  source_type: DocumentSourceType;
  target_format?: TargetFormat;
  output_path?: string;
}

export interface ConvertDocumentResponse {
  task: ImportPipelineTaskResponse;
}

export interface UploadImportFileResponse {
  original_name: string;
  stored_name: string;
  source_path: string;
  size: number;
}

export interface ImportMediaAsset {
  image_id: string;
  filename: string;
  relative_path: string;
  absolute_path: string;
  size: number;
}

export interface ImportBatchResponse {
  batch_id: string;
  original_filename: string;
  stored_filename: string;
  source_path: string;
  relative_source_path: string;
  status: string;
  created_at: string;
  content_version: number;
}

export interface PandocBatchResponse {
  task_id?: string | null;
  batch_id: string;
  status: string;
  markdown_path: string;
  relative_markdown_path: string;
  media_dir: string;
  relative_media_dir: string;
  image_count: number;
  images: ImportMediaAsset[];
  markdown_preview: string;
  text: string;
  output_path?: string;
}

export interface AiCleanBatchResponse {
  task_id?: string | null;
  batch_id: string;
  status: string;
  cleaned_markdown_path: string;
  relative_cleaned_markdown_path: string;
  cleaned_preview: string;
  text: string;
  cleaned_by: string;
  warnings: string[];
}

export interface AiStructureBatchResponse {
  task_id?: string | null;
  batch_id: string;
  status: string;
  question_count: number;
  questions: Question[];
  raw_json_path: string;
  normalized_json_path: string;
  structured_by: string;
  ai_refined_count?: number;
  media_assets?: ImportMediaAsset[];
}

export interface RecognizeBatchResponse {
  task_id?: string | null;
  batch_id: string;
  status: string;
  pipeline: 'word_pandoc_local' | 'word_pandoc_deepseek' | 'vision_qwen_ocr';
  source_type: string;
  question_count: number;
  questions: Question[];
  media_assets?: ImportMediaAsset[];
  markdown_preview?: string;
  structured_by?: string;
  ai_refined_count?: number;
  warnings?: string[];
}

export interface ExtractBatchImagesResponse {
  batch_id: string;
  status: string;
  source_type: string;
  image_count: number;
  media_dir: string;
  relative_media_dir: string;
  media_assets: ImportMediaAsset[];
  warnings: string[];
}

export interface AiRefineBatchResponse {
  batch_id: string;
  status: string;
  refined_count: number;
  questions: Record<string, unknown>[];
  refined_by: string;
  warnings: string[];
}

export interface CleanDocumentRequest {
  source_text: string;
  normalize_whitespace?: boolean;
  strip_headers_footers?: boolean;
  normalize_math_delimiters?: boolean;
  remove_blank_lines?: boolean;
}

export interface CleanDocumentResponse {
  task: ImportPipelineTaskResponse;
}

export interface ParseStructuredQuestionsRequest {
  source_text: string;
  import_batch_id: string;
  source_path?: string;
  source_type?: DocumentSourceType;
}

export interface ParseStructuredQuestionsResponse {
  task: ImportPipelineTaskResponse;
}

// ── AI Parse Types ──

export type AiParseFileType = 'pdf' | 'jpg' | 'jpeg' | 'png' | 'webp';
export type AiParseMode = 'auto' | 'native_document' | 'image_document';

export interface AiParseDocumentRequest {
  batch_id: string;
  file_path: string;
  file_type: AiParseFileType;
  mode?: AiParseMode;
  enable_preprocess?: boolean;
  enable_region_detection?: boolean;
  enable_figure_extraction?: boolean;
  enable_table_extraction?: boolean;
  formula_format?: 'latex';
  ignore_headers_footers?: boolean;
}

export interface AiParseDocumentResponse {
  task: ImportPipelineTaskResponse;
}

export interface ImportPipelineTaskResponse {
  task_id: string;
  trace_id?: string;
  task_type: ImportTaskType | 'word_export' | 'pptx_export' | `background_${string}`;
  status: ImportTaskStatus;
  created_at: string;
  updated_at: string;
  input_summary: Record<string, string | number | null>;
  result: Record<string, unknown> | null;
  error: string | null;
  progress?: number;
  current_step?: string | null;
  attempt?: number;
  max_attempts?: number;
  result_file_path?: string | null;
  error_info?: {
    error_type: string;
    message: string;
    technical_details: string | null;
    retryable: boolean;
  } | null;
}

export interface TaskCenterError {
  error_type: string;
  user_message: string;
  technical_detail: string | null;
  retryable: boolean;
}

export interface TaskCenterItem {
  task_id: string;
  trace_id?: string;
  task_type: string;
  task_name: string;
  status: ImportTaskStatus;
  progress: number;
  current_step: string;
  attempt: number;
  max_attempts: number;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  result_available: boolean;
  error: TaskCenterError | null;
  input_summary: Record<string, unknown>;
  result_summary: Record<string, unknown> | null;
}

export interface TaskStageEvent {
  event_id: string;
  task_id: string;
  trace_id: string;
  phase: string;
  stage: string;
  event_type: string;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  input_version: number | null;
  retry_count: number;
  warning: string | null;
  error_code: string | null;
  error_message: string | null;
  recommended_action: string | null;
  details: Record<string, unknown>;
}

export interface TaskContextArtifact {
  display_name: string;
  download_url: string;
  type: string;
}

export interface TaskContextAudit {
  audit_id: string;
  action: string;
  created_at: string;
  operator: string;
  confirmed: boolean;
}

export interface TaskContextResponse {
  artifacts: TaskContextArtifact[];
  audits: TaskContextAudit[];
  retry_allowed: boolean;
  retry_reason: string;
}

export interface TaskCenterListResponse {
  items: TaskCenterItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface TaskActionResponse {
  task: TaskCenterItem;
  message: string;
  original_task_id?: string | null;
}

export interface ImportFileInfo {
  id: string;
  name: string;
  size: number;
  type: string;
  extension: string;
}

export interface FileTaskState {
  fileId: string;
  fileName: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  currentStep: 'convert' | 'clean' | 'parse' | 'ai_parse' | 'done';
  convertTask: ImportPipelineTaskResponse | null;
  cleanTask: ImportPipelineTaskResponse | null;
  parseTask: ImportPipelineTaskResponse | null;
  aiParseTask: ImportPipelineTaskResponse | null;
  error: string | null;
  /** 任务来源类型，用于重试时判断是否跳过文件转换步骤 */
  taskSourceType: 'file' | 'direct_text';
}

/** Lightweight reference to a backend pipeline task, stored in localStorage. */
export interface StoredTaskRef {
  task_id: string;
  task_type: string;
  status: ImportTaskStatus;
  error: string | null;
  /** Minimal result snapshot — large text / question arrays are trimmed. */
  resultSummary: Record<string, unknown> | null;
}

/** Serializable snapshot of FileTaskState for localStorage persistence.
 *  Large text payloads are stripped; only IDs and result summaries are kept. */
export interface StoredTaskState {
  fileId: string;
  fileName: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  currentStep: 'convert' | 'clean' | 'parse' | 'ai_parse' | 'done';
  convertTask: StoredTaskRef | null;
  cleanTask: StoredTaskRef | null;
  parseTask: StoredTaskRef | null;
  aiParseTask: StoredTaskRef | null;
  error: string | null;
  taskSourceType: 'file' | 'direct_text';
  /** Timestamp for sorting / staleness. */
  savedAt: string;
}

export interface ImportCleaningOptions {
  strip_headers_footers: boolean;
  normalize_math_delimiters: boolean;
  remove_blank_lines: boolean;
}

// ── Review Workbench Types ──

export type ReviewQuestionStatus = 'pending' | 'modified' | 'discarded' | 'confirmed';

export interface FigureReferenceIssue {
  type: 'missing_figure' | 'unreferenced_figure';
  message: string;
  figUuid?: string;
}

// ── Handout Style Preset Types ──

export type QuestionNumberStyle = 'decimal' | 'circled' | 'bracket';
export type HandoutPageSize = 'A4' | 'A3';
export type HandoutPageOrientation = 'portrait' | 'landscape';
export type HandoutLayoutMode = 'flow' | 'paged-single' | 'paged-double';
export type HandoutFontFamily = 'songti' | 'heiti' | 'kaiti' | 'fangsong' | 'system';
export type HandoutOptionLayout = 'auto' | 'single' | 'double';

export interface HandoutStyleConfig {
  fontFamily: HandoutFontFamily;
  fontSize: number;
  lineHeight: number;
  paragraphSpacing: number;
  questionSpacing: number;
  figureScale: number;
  pageMarginTop: number;
  pageMarginBottom: number;
  pageMarginLeft: number;
  pageMarginRight: number;
  questionNumberStyle: QuestionNumberStyle;
  pageSize: HandoutPageSize;
  pageOrientation: HandoutPageOrientation;
  layoutMode: HandoutLayoutMode;
  optionLayout: HandoutOptionLayout;
  keepQuestionTogether: boolean;
  keepFigureWithStem: boolean;
  startLongQuestionOnNewPage: boolean;
  pageFillPercent: number;
}

export interface HandoutStylePreset {
  id: string;
  name: string;
  config: HandoutStyleConfig;
  category?: 'handout' | 'exam' | 'teacher' | 'large-format';
  description?: string;
  createdAt: string;
  updatedAt: string;
}

// ── Handout Types ──

export interface HandoutConfig {
  title: string;
  subtitle: string;
  showAnswers: boolean;
  showAnalysis: boolean;
  headerFooter: HandoutHeaderFooterConfig;
  styleConfig: HandoutStyleConfig;
}

export interface HandoutKnowledgeItem {
  type: 'knowledge';
  title: string;
  summary: string;
  points: string[];
}

export interface HandoutTextItem {
  type: 'text';
  title: string;
  content: string;
}

export interface HandoutQuestionItem {
  type: 'question';
  question?: Question;
}

export interface HandoutPageBreakItem {
  type: 'page_break';
  title?: string;
}

export interface HandoutItem {
  id?: string;
  type: 'question' | 'page_break' | 'knowledge' | 'text';
  question?: Question;
  title?: string;
  content?: string;
  blockKind?: HandoutTextBlockKind;
  style?: HandoutTextBlockStyle;
  summary?: string;
  points?: string[];
}

export type HeaderFooterAlignment = 'left' | 'center' | 'right';

export interface HandoutHeaderFooterConfig {
  headerEnabled: boolean;
  headerText: string;
  headerAlign: HeaderFooterAlignment;
  footerEnabled: boolean;
  footerText: string;
  footerAlign: HeaderFooterAlignment;
  showPageNumber: boolean;
}

// ── Print Preflight Types ──

export type PreflightRiskSeverity = 'warning' | 'danger';

export interface PreflightRiskItem {
  pageIndex: number;
  pageLabel: string;
  questionIndex?: number;
  questionId?: string;
  severity: PreflightRiskSeverity;
  message: string;
}

// ── Slides Types ──

export type SlidesDisplayMode = 'stem_only' | 'stem_answer' | 'full';

// ── Teaching Slide Types ──
// Re-export from the canonical slides type module.
// Backward-compatible aliases for existing consumers.

export type {
  SlideDeck,
  SlidePage,
  SlidePageType,
  SlideLayout,
  SlideSection,
  SlideSectionType,
  SlideItem,
} from './slides';
export type {
  HandoutArtifact,
  SlideArtifact,
  TeachingArtifactStatus,
  TeachingProject,
  TeachingProjectSummary,
} from './teachingProject';
export type {
  SavedHandoutDocument,
  SavedHandoutListResponse,
  SavedHandoutSummary,
  SavedHandoutVersion,
  SavedHandoutVersionListResponse,
} from './lessonDocument';

import type { SlidePage } from './slides';

/** @deprecated Use SlidePage instead */
export type TeachingSlideData = Pick<
  SlidePage,
  'title' | 'subtitle' | 'badge' | 'sections' | 'footer'
> & { aside?: string };

export interface ReviewQuestionDraft {
  question_id: string;
  question_type: string;
  title: string;
  options: Option[];
  answer: string;
  analysis: string;
  sub_questions: SubQuestion[];
  figures: Figure[];
  difficulty: number | null;
  knowledge_point: string;
  knowledge_points?: KnowledgePoint[];
  topic3_ids?: string[];
  topic1_id?: string;
  topic1_name?: string;
  topic2_id?: string;
  topic2_name?: string;
  topic3_id?: string;
  topic3_name?: string;
  tags: string[];
  source: string;
  year?: number | null;
  import_batch_id?: string;
  source_page?: number | null;
  source_region_id?: string | null;
  source_bbox?: [number, number, number, number] | null;
  raw_text?: string | null;
  status: ReviewQuestionStatus;
  figureIssues: FigureReferenceIssue[];
}

export interface ReviewDraftStatePayload {
  drafts: ReviewQuestionDraft[];
  knowledge_drafts: KnowledgeReviewDraft[];
  task_meta: Record<string, unknown>;
  current_index: number;
  queue: string;
}

export interface ReviewDraftResponse {
  task_id: string;
  version: number;
  state: ReviewDraftStatePayload;
  updated_at: string;
}

export interface ReviewDraftLookupResponse {
  draft: ReviewDraftResponse | null;
}

export interface ReviewDraftVersionListResponse {
  items: ReviewDraftResponse[];
}

export interface SaveReviewDraftRequest {
  base_version: number;
  state: ReviewDraftStatePayload;
}

// ── Review Save API Types ──

export interface ReviewedQuestionPayload {
  question_id: string;
  question_type: string;
  title: string;
  options: Option[];
  answer: string;
  analysis: string;
  sub_questions: SubQuestion[];
  figures: Figure[];
  difficulty: number | null;
  knowledge_point: string;
  knowledge_points?: KnowledgePoint[];
  topic3_ids?: string[];
  topic1_id?: string;
  topic1_name?: string;
  topic2_id?: string;
  topic2_name?: string;
  topic3_id?: string;
  topic3_name?: string;
  tags: string[];
  source: string;
  year?: number | null;
  import_batch_id?: string;
  source_page?: number | null;
  source_region_id?: string | null;
  source_bbox?: [number, number, number, number] | null;
  raw_text?: string | null;
  review_status: string;
}

export interface SaveReviewedQuestionsRequest {
  task_id: string;
  questions: ReviewedQuestionPayload[];
}

export interface SaveResultItem {
  draft_question_id: string;
  saved_question_id: string | null;
  error: string | null;
}

export interface SaveReviewedQuestionsResponse {
  saved_count: number;
  skipped_count: number;
  failed_count: number;
  results: SaveResultItem[];
}

export interface AiGeneratedReviewRequest {
  source_text: string;
  source?: string;
  chat_context?: string | null;
  session_id?: string | null;
}

export interface AiGeneratedReviewResponse {
  task_id: string;
  batch_id: string;
  question_count: number;
  knowledge_count: number;
  warnings: string[];
}

export interface ReviewTaskListItem {
  task_id: string;
  task_type: string;
  status: string;
  batch_id: string;
  title: string;
  question_count: number;
  knowledge_count: number;
  source: string;
  created_at: string;
  updated_at: string;
  warnings: string[];
}

export interface ReviewTaskListResponse {
  items: ReviewTaskListItem[];
}

export interface DeleteReviewTaskResponse {
  task_id: string;
  deleted: boolean;
}

export interface KnowledgeReviewDraft {
  draft_id: string;
  topic3_id: string;
  topic3_name: string;
  topic2_id: string;
  topic2_name: string;
  topic1_id: string;
  topic1_name: string;
  source_chapter: string;
  definition: string;
  formula: string;
  key_summary: string;
  error_prone: string;
  example_analysis: string;
  tags: string[];
  raw_text: string;
  status: 'pending' | 'modified' | 'confirmed' | 'discarded';
}

export interface SaveReviewedKnowledgeRequest {
  task_id: string;
  knowledge_drafts: Array<KnowledgeReviewDraft & { review_status: string }>;
}

export interface SaveReviewedKnowledgeResponse {
  saved_count: number;
  skipped_count: number;
  failed_count: number;
  results: SaveResultItem[];
}

  // ── Assets Manager Types ──

export interface AssetItem {
  filename: string;
  relative_path: string;
  source?: 'question_bank' | 'import_batch' | string;
  batch_id?: string | null;
  size_bytes: number;
  mime_type: string;
  modified_at: string;
  is_referenced: boolean;
  reference_count: number;
  reference_question_ids: string[];
  lifecycle_status: 'referenced' | 'unreferenced' | 'staged' | 'imported' | 'unknown' | string;
}

export interface AssetStats {
  total: number;
  referenced: number;
  unreferenced: number;
  total_size_bytes: number;
}

export interface AssetListResponse {
  assets: AssetItem[];
  stats: AssetStats;
  library_stats: AssetStats;
  batches: AssetBatchSummary[];
  pagination: AssetPagination;
  reference_scan_available: boolean;
}

export interface AssetBatchSummary {
  batch_id: string;
  asset_count: number;
  referenced: number;
  unreferenced: number;
  total_size_bytes: number;
  modified_at: string;
}

export interface AssetPagination {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface CleanupPreviewResponse {
  candidate_count: number;
  reclaimable_bytes: number;
  protected_count: number;
  scope: string;
}

export interface CacheCleanupPreviewResponse {
  batch_id?: string | null;
  batch_count: number;
  candidate_count: number;
  reclaimable_bytes: number;
  protected_count: number;
  active_batches: string[];
}

export interface DuplicateAssetGroup {
  content_hash: string;
  copies: number;
  size_bytes: number;
  reclaimable_bytes: number;
  paths: string[];
}

export interface StorageAnalysisResponse {
  scanned_files: number;
  duplicate_groups: number;
  duplicate_files: number;
  reclaimable_bytes: number;
  tiny_files: string[];
  corrupt_files: string[];
  oversized_files: string[];
  groups: DuplicateAssetGroup[];
}

export interface CleanupResponse {
  deleted_count: number;
  freed_bytes: number;
  errors: string[];
}

export interface DeleteAssetResponse {
  success: boolean;
  message: string;
}

// ── Similar Questions Types ──

export interface SimilarQuestionItem {
  question_id: string;
  question_type: string | null;
  title: string | null;
  difficulty: string | null;
  module: string | null;
  topic2: string | null;
  topic3: string | null;
  similarity_score: number;
  has_media: boolean;
  primary_paper_id: string | null;
}

export interface SimilarQuestionsResponse {
  question_id: string;
  items: SimilarQuestionItem[];
  total_candidates: number;
  limit: number;
}

// ── Batch Analysis Types ──

export interface BatchAnalysisRequest {
  question_ids: string[];
  style: 'classroom_brief' | 'self_study_full' | 'exam_standard';
  include_extension: boolean;
  force_regenerate: boolean;
}

export interface BatchAnalysisItemResult {
  question_id: string;
  status: 'success' | 'skipped' | 'failed';
  message: string;
  saved_to_db: boolean;
}

export interface BatchAnalysisResponse {
  total: number;
  success_count: number;
  skipped_count: number;
  failed_count: number;
  results: BatchAnalysisItemResult[];
}

// ── Collections / Batch Move Types ──

export interface CollectionNode {
  id: string;
  name: string;
  parent_id: string | null;
  type: 'directory' | 'topic' | 'subtopic';
  question_count: number;
  children: CollectionNode[];
  created_at: string;
  updated_at: string;
}

export interface BatchMoveRequest {
  question_ids: string[];
  target_collection_id: string;
}

export interface BatchMoveItemResult {
  question_id: string;
  status: 'success' | 'skipped' | 'failed';
  message: string;
}

export interface BatchMoveResponse {
  total: number;
  success_count: number;
  skipped_count: number;
  failed_count: number;
  results: BatchMoveItemResult[];
}

// ── Favorites / Star Types ──

export interface FavoriteGroupItem {
  id: string;
  name: string;
  question_count: number;
  sort_order: number;
  created_at: string;
}

export interface FavoriteItemView {
  question_id: string;
  group_id: string | null;
  group_name: string | null;
  star_rating: number;
  added_at: string;
}

export interface FavoriteAssignRequest {
  question_ids: string[];
  group_id: string | null;
  star_rating: number | null;
}

export interface BatchFavoriteResponse {
  total: number;
  success_count: number;
  skipped_count: number;
  failed_count: number;
}

// ── Image Management Types ──

export interface QuestionImageDetail {
  link_id: string;
  asset_id: string;
  filename: string;
  file_path: string;
  role: string;
  sort_order: number;
  placeholder_key: string | null;
  is_primary: boolean;
  is_verified: boolean;
  mime_type: string | null;
  width: number | null;
  height: number | null;
  description: string | null;
  display_scale?: number;
}

export interface ImageListResponse {
  question_id: string;
  images: QuestionImageDetail[];
  stem_text: string;
}

export interface PlaceholderIssue {
  type: string;
  message: string;
  fig_uuid: string | null;
}

export interface ValidationResponse {
  valid: boolean;
  issues: PlaceholderIssue[];
}

// ── Restore Package Types ──

export interface RestorePackageResponse {
  success: boolean;
  started_at: string;
  finished_at: string;
  database_file: string | null;
  asset_count: number;
  backup_path: string | null;
  error: string | null;
  warnings: string[];
}

// ── Metadata Batch Types ──

export type MetadataField = 'knowledge_points' | 'tags' | 'source';
export type MetadataMode = 'ai' | 'manual' | 'mixed';

export interface BatchMetadataRequest {
  question_ids: string[];
  fields: MetadataField[];
  mode: MetadataMode;
  manual_values?: {
    knowledge_points?: string;
    tags?: string[];
    source?: string;
  };
  force_overwrite: boolean;
}

export interface BatchMetadataItemResult {
  question_id: string;
  status: 'updated' | 'skipped' | 'failed';
  updated_fields: string[];
  message: string;
}

export interface BatchMetadataResponse {
  total: number;
  updated: number;
  skipped: number;
  failed: number;
  results: BatchMetadataItemResult[];
}

// ── Mistake Types ──

export interface DraftMetadataRequest {
  questions: Record<string, unknown>[];
  fields: MetadataField[];
  force_overwrite: boolean;
}

export interface DraftMetadataResponse {
  batch_id: string;
  status: string;
  updated: number;
  skipped: number;
  failed: number;
  questions: Record<string, unknown>[];
  warnings: string[];
}

export interface MarkMistakeRequest {
  question_id: string;
  is_mistake: boolean;
}

export interface BatchMarkMistakeRequest {
  question_ids: string[];
  is_mistake: boolean;
}

export interface MistakeItemResult {
  question_id: string;
  status: string;
  message: string | null;
}

export interface BatchMarkMistakeResponse {
  total: number;
  success: number;
  skipped: number;
  failed: number;
  items: MistakeItemResult[];
}

export interface MistakeStatsResponse {
  total_questions: number;
  mistake_count: number;
  recent_7d_count: number;
}

// ── Question Annotation Types ──

export type AnnotationType = 'text' | 'highlight' | 'region' | 'lecture_tip' | 'pitfall' | 'board_hint';

export const ANNOTATION_TYPE_LABELS: Record<AnnotationType, string> = {
  text: '文本批注',
  highlight: '高亮标注',
  region: '局部框选',
  lecture_tip: '讲题提示',
  pitfall: '易错提醒',
  board_hint: '板书提示',
};

export const ANNOTATION_COLORS = [
  { value: '#fbbf24', label: '琥珀' },
  { value: '#f87171', label: '红色' },
  { value: '#4ade80', label: '绿色' },
  { value: '#60a5fa', label: '蓝色' },
  { value: '#c084fc', label: '紫色' },
  { value: '#fb923c', label: '橙色' },
];

export interface QuestionAnnotation {
  annotation_id: string;
  question_id: string;
  annotation_type: AnnotationType;
  content: string;
  anchor_start: number | null;
  anchor_end: number | null;
  anchor_text: string | null;
  figure_uuid: string | null;
  color: string;
  author: string;
  visibility: string;
  created_at: string;
  updated_at: string;
}
