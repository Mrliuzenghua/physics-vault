# 工作流 03：平台契约清点表

> 盘点日期：2026-08-10。来源仅为当前工作区的 `application.py`、`routers/`、`apps/web/src/services/api.ts` 和 `apps/web/src/types/index.ts`；它不是接口变更提案，也不改变任何代码所有权。
>
> **使用方式**：新任务先在表中找到所属领域，确认“当前重叠”状态。只有当拟改文件在该领域没有活跃租约、且调用/类型边界不跨到另一行时，才能领取精确文件租约；否则先交给 00 协调或由 03 提供兼容层。

## 统一标记

- **后端入口**：`Router → Service`。未列 Service 表示 Router 暂时直接协调存储或本地模块，属于后续收紧方向，不是授权该领域任务顺手重写的理由。
- **前端入口**：当前经由 `api.ts` 的公开导入名；已经拆出的领域模块仍由 `api.ts` 显式再导出，故旧调用方保持可用。
- **共享类型**：`types/index.ts` 的代表性 DTO/联合类型，不表示该领域所有内部类型。
- **当前重叠**：`是` 指涉及文件当前为已修改或未跟踪状态；不得直接写入。`局部` 指只有表中点名的兼容入口有改动，需先确认行级重叠。`未见` 只代表本次盘点时未见 Git 状态，仍需在开工前复查。

| 领域 | 后端 Router / Service 入口 | 前端调用入口 | 共享类型 | 当前未提交重叠 | 建议的下一个无冲突切口 |
| --- | --- | --- | --- | --- | --- |
| 应用装配与进程基础设施 | `app.py → ApplicationContainer.build()/routers()`；`application.py` 的 `WorkerContainer`、`ExportWorkerContainer`、`AssemblyGroup` | `apiClient.ts`（`request`、`requestForm`、`ApiError`、API 基路径） | `ApiError`；前端 `DatabaseStatus` 目前仍局部定义在 `api.ts` | **是**：`application.py` 已有装配清单和共享导入流水线构造的未提交改动 | 待此文件租约释放后，仅新增 `test_application_composition.py`，断言装配清单成员与注册 Router 的唯一性；不重排既有服务构造。 |
| 系统状态与任务中心 | `system_status.py → QuestionSearchRepository`；`tasks.py → TaskCenterService` | `fetchDatabaseStatus`；`taskApi.ts` 的 `fetchTasks/fetchTask/retryTask/cancelTask/downloadTaskResult` | `TaskCenterError`、`TaskCenterItem`、`TaskCenterListResponse`、`TaskActionResponse` | **局部**：`system_status.py` 已修改；`api.ts`、`types/index.ts` 已修改 | 先为状态响应定义/核对具名 DTO 的只读设计卡；实施须等 system router 和 types 租约释放。 |
| 导入与后台处理 | `import_pipeline.py → ImportPipelineService`、`tasks.py → TaskCenterService`；Worker 复用 `_build_import_pipeline_service` | `uploadImportFile`、`createImportBatch`、`runImportBatch*`、`fetchImportBatchStatus`、`fetchImportTask`、`retrySavedImportBatch` | `ImportBatch*`、`ImportTaskStatus`、`ImportPipelineTaskResponse`、`Convert/Clean/Parse/AiParse*`、`ImportMediaAsset` | **局部**：`application.py`、`api.ts`、`types/index.ts` 已修改；导入 Router 本身本次状态未见改动，但由 01 负责 | 01 可在自己的 service 租约内继续抽纯规则；任何 HTTP 字段或 TypeScript 类型需求以六项契约申请交给 03。 |
| 题库检索、详情与编辑 | `question_search/details/updates/versions/imports/stats.py → Question*Service`；`knowledge_points.py → KnowledgePointService` | `questionApi.ts`（由 `api.ts` 再导出）：`searchQuestions`、`fetchQuestion*`、`updateQuestion`、`deleteQuestions`、知识点与版本函数 | `Question`、`SearchFilters`、`SearchResponse`、`FilterFacets`、`KnowledgePoint*`、`QuestionVersion*` | **是**：`question_search.py`、`api.ts`、`types/index.ts` 已修改；`questionApi.ts` 为新文件 | 保持 URL、响应字段、`normalizeQuestion` 行为不变，仅为已拆出的 `questionApi.ts` 补传输/归一化契约测试；不要同时改页面。 |
| 审核队列与审核草稿 | `question_reviews.py → QuestionReviewService`；`review_queue.py → ReviewQueueRepository`；`review_save.py → ReviewSaveService` | `fetchReviewQueue`、`fetchReviewDraft`、`saveReviewDraft`、`saveReviewedQuestions`、`saveReviewedKnowledge`、`fetchReviewTasks` | `ReviewQuestionDraft`、`ReviewDraft*`、`SaveReviewedQuestions*`、`AiGeneratedReview*`、`ReviewTaskList*` | **局部**：`api.ts`、`types/index.ts` 已修改；Router 当前未见改动，但 02 消费其字段 | 02 先提交实际 UI 字段清单；03 仅在字段明确后，新增不破坏既有 ID/状态/版本语义的 DTO 兼容测试。 |
| 组卷、试卷与教学项目 | `papers.py → PaperService`；`paper_drafts.py → PaperDraftService`；`teaching_projects.py`、`lesson_documents.py`、`lesson_reflections.py` | `list/fetch/savePaperDraft`；`teachingProjectApi.ts`、`lessonDocumentApi.ts`、`lessonReflectionApi.ts`（均经 `api.ts` 再导出） | `PaperDraft*`、`LessonPackage`、`Layout*`、`Template*`、`SavedLessonPackageSummary`、教学项目类型（独立文件） | **是**：`api.ts`、`types/index.ts` 已修改；多个后端 Router 为未跟踪新文件 | 只在 `api.ts` 以外新增领域客户端的契约测试，先确认未跟踪 Router 的来源和字段，不触碰 Compose 页面。 |
| 课件、导出与系统包 | `lesson_exports.py → LessonExportService`；`export_package.py`、`restore_package.py` | `lessonExport.ts`、`lessonServerExport.ts`、`downloadExportPackage`、`restorePackage` | `LessonPackage`、`Handout*`、`RestorePackageResponse`、`ImportPipelineTaskResponse` | **局部**：`api.ts`、`types/index.ts` 已修改；导出 service 由其他改动覆盖 | 可独立清点浏览器下载的输入/输出类型；实际接口迁移等待导出调用方和任务契约共同确认。 |
| MCP、AI 助手与代理 | `mcp.py → McpGatewayService`；`ai_assistant.py → AiAssistantService`；`agents.py → ClaudeCodeAgentService`；`ai_generation.py → AiGenerationService` | `fetchMcp*`、`testMcpConnection`、`sendAiChatTest`、`sendAiAssistantChat`、`fetch/saveAgentConfig`、`runQuestionPickerAgent` | `Mcp*`、`AiChat*`、`AiAssistant*`、`Agent*`、`QuestionPickerAgentResponse` | **是**：`mcp.py`、`api.ts`、`types/index.ts` 已修改 | 不改接口行为；可先将现有 API 函数迁移到新的 `mcpApi.ts` / `agentApi.ts`，`api.ts` 保留显式 re-export，前提是先取得该文件租约。 |
| AI 批处理、标注、元数据与相似题 | `analysis_batch.py → AnalysisBatchService`；`annotations.py`；`metadata_batch.py → MetadataBatchService`；`similar_questions.py → SimilarQuestionsService` | `batchGenerateAnalysis`、`batchUpdateMetadata`、`generateSingleAnalysis`、`generateKnowledge`、`fetchSimilarQuestions`、注释函数 | `BatchAnalysis*`、`BatchMetadata*`、`SimilarQuestions*`、`QuestionAnnotation`、`AnnotationType` | **是**：`api.ts`、`types/index.ts` 已修改；领域 Router 当前未见改动 | 先新建只读接口映射测试或类型断言测试，避免在同一切口混合迁移 API 模块和领域业务。 |
| 资产、图片、收藏、集合与错题 | `assets_manager.py`、`image_management.py`、`image_catalog.py`、`favorites.py`、`collections.py`、`mistake.py` | `fetchAsset*`、清理函数、`fetch/add/updateQuestionImage`、收藏/集合/错题函数 | `Asset*`、`ImageListResponse`、`ValidationResponse`、`Favorite*`、`Collection*`、`Mistake*` | **是**：`assets_manager.py`、`image_management.py`、`api.ts`、`types/index.ts` 已修改；`image_catalog.py` 未跟踪 | 等资产与图片 Router 的活跃改动落定后，优先把 `unknown[]`/`Record<string, unknown>` 返回值替换为具名 DTO；不可修改清理或删除业务逻辑。 |
| 嵌入、检索质量与运行记录 | `embedding_builds.py → EmbeddingBuildService`；`embedding_status.py → EmbeddingStatusService`；`processing_runs.py → ProcessingRunService` | `fetchEmbeddingStatus`、`fetchProcessingRuns` | 当前共享类型缺少稳定的嵌入状态 DTO；运行记录类型待核对 | **局部**：相关 Router 为未跟踪新文件，`api.ts`、`types/index.ts` 已修改 | 单独提一份 DTO 缺口清单；待 Router 稳定后，由 03 增加命名类型并删除前端 `unknown` 返回。 |

## 跨领域公共面

| 公共面 | 当前事实 | 文件租约规则 |
| --- | --- | --- |
| HTTP 传输 | `apiClient.ts` 已集中请求、表单、API 基路径和 `ApiError` | 仅 03 可修改。领域工作流只能提出路径/字段需求，不能在页面或领域 Service 中复刻请求逻辑。 |
| 兼容入口 | `api.ts` 仍是旧调用方入口，同时显式再导出 `questionApi.ts`、任务、教学项目、课件等模块 | 任何新领域模块必须先从此处显式再导出，再逐步迁移调用方；不可直接删除旧导出。当前文件有重叠，暂不领取。 |
| 类型出口 | `types/index.ts` 同时含跨域 DTO 和历史聚合类型 | 新类型应先进入领域类型文件，再由 `index.ts` 显式导出；HTTP 字段变更必须先列兼容期与调用方。当前文件有重叠，暂不领取。 |
| 后端装配 | `ApplicationContainer.ASSEMBLY_MANIFEST` 已开始表达成员分组；`routers()` 决定全部公开 HTTP 面 | 改动 `application.py` 必须同时运行路由唯一性/OpenAPI 测试。当前文件有重叠，暂不领取。 |

## 释放租约的最小流程

1. 00 在集成前对照本表，确认某一行的已修改/未跟踪文件已归属、测试通过或已提交。
2. 03 把该行的“下一个无冲突切口”转为精确租约：文件列表、不可变行为、测试命令和归还条件。
3. 领域 AI 只在自己的 Service/页面范围工作；若出现 HTTP 或共享类型需求，按 `领域 / 现状 / 目标字段或路径 / 调用方 / 向后兼容策略 / 验收测试` 交回 03。
4. 03 实施兼容层并通过路由、类型、客户端测试后，00 才允许调用方切换；旧导出或端点必须在调用方归零后单独删除。

这张表的目的不是扩大 03 的修改范围，而是让每次并行改动都能先定位到一个领域行、一个公共面和一组可验证的文件租约。
