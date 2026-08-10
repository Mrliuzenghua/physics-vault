# 代码地图 1：导入流水线后端

## 0. 统一代码卡片

| 项目 | 内容 |
| --- | --- |
| 编号 | 1 |
| 负责智能体 | 导入后端 AI |
| 代码主入口 | `apps/api/src/physics_vault_api/services/document_pipeline.py` |
| 可写范围 | `apps/api/src/physics_vault_api/services/import_*`、`document_pipeline.py` 与直接相关导入测试 |
| 禁止越界 | 不改前端、Router/API 协议、正式题库写入、审核工作台、共享类型或 MCP 契约 |
| 当前首要切口 | 已完成：`DocumentCleaningService` 委托 `ImportTextCleaner`；下一步按领域拆分剩余题库治理客户端或导入流程编排 |
| 验证入口 | `apps/api/tests/test_import_*.py`；详见“验证命令” |

> 函数级补充：[导入流水线：函数伪代码与拆分边界](../导入流水线-函数伪代码与拆分边界.md)
> 协作原则：共享工作区可能同时有其他 AI 修改。只提交本工作流允许范围内的文件；发现重叠修改先停下并在交接记录中说明，不能覆盖或回退他人的改动。

## 1. 目标与非目标

目标是在不改变对外 HTTP 接口、导入产物格式和审核边界的前提下，把 `ImportPipelineService` 中混杂的纯规则、外部文档转换、任务编排逐步收敛为可独立测试的组件。每个小步都必须可运行、可回退、可验证。

本工作流不做以下事情：

- 不改前端页面、前端 API 调用、路由 URL 或请求/响应 schema。
- 不改正式题库写入逻辑；导入结果始终先是审核草稿，由审核流程确认后再进入题库。
- 不修改审核工作台、题目检索、组卷、图片管理、数据库迁移及 MCP 协议。
- 不顺带格式化、重命名或清理本工作流目录之外的文件。

## 2. 当前职责边界

```text
上传文件 / 后台任务
        │
        ▼
ImportPipelineService（只编排阶段和公开兼容入口）
  ├─ ImportBatchStorage（批次文件、锁、原子写、content_version）
  ├─ DocumentConverter（Pandoc / MarkItDown 与媒体提取）
  ├─ ImportTextRules（清洗、AI 回包/来源/元数据规范化；纯函数）
  ├─ ImportQuestionParser（Markdown → 审核题目草稿）
  └─ ImportTaskCoordinator（任务状态、幂等键、检查点、重试）
        │
        ▼
审核任务仓储 / 审核中心（只接收草稿，不直接写正式题库）
```

已完成的边界：`ImportBatchStorage` 已拥有批次锁、元数据读写、原子写入、内容版本校验、路径/哈希工具。`document_pipeline.py` 中同名私有兼容方法只能委托给它，不得再次实现文件一致性规则。

## 3. 允许修改范围

### 可以修改

- `apps/api/src/physics_vault_api/services/document_pipeline.py`
- `apps/api/src/physics_vault_api/services/import_batch_storage.py`（仅修复其公开职责或为本工作流提供必要的小接口）
- 新增仅由导入流水线使用的文件：`apps/api/src/physics_vault_api/services/import_*.py`
- 与上述改动一一对应的测试：`apps/api/tests/test_import_*.py`、`test_markitdown_image_binding.py`、`test_ai_generated_review.py`、`test_task_center.py`、`test_task_queue_infrastructure.py`
- 本文档及导入流水线伪代码文档；每完成一个拆分，在伪代码文档标记“已完成/未完成”和新模块归属。

### 禁止修改

- `apps/web/**`
- `apps/api/src/physics_vault_api/routers/**`
- `apps/api/src/physics_vault_api/schemas/**`
- `apps/api/src/physics_vault_api/repositories/**`（包括审核/题库仓储）
- `apps/api/src/physics_vault_api/migrations/**`、`data/**`、`scripts/**`、`packages/**`
- 其他 AI 已经变更的任意文件。即使它与导入有关，若不在“可以修改”清单内，也只能提出建议，不能直接编辑。

如果为了本工作流确实需要修改禁止范围的文件，先提交最小接口需求：文件、函数/接口、原因、向后兼容方案和预期测试；由协调 AI 分配给对应工作流。

## 4. 不可破坏的接口与数据约束

### 批次一致性

- `content_version` 是防止迟到 Worker 覆盖用户确认/编辑结果的并发栅栏。任何产生持久化输出的阶段，写入前必须校验其输入版本。
- 同一 `(operation, batch_id, input_version, IMPORT_PIPELINE_CONFIG_VERSION)` 必须复用同一幂等任务或有效检查点；不得重复执行外部转换或模型调用。
- 批次元数据必须经 `ImportBatchStorage` 的锁和原子写入更新，不能直接 `write_text` 覆盖状态文件。
- 已完成阶段的缓存只有在结果完整、输入版本一致时才能复用；失败或不完整产物不可伪装为缓存命中。

### 导入与审核边界

- `structure_batch_questions`、`create_ai_generated_review_task`、`confirm_batch_questions` 输出的是审核草稿/审核任务；不得绕过审核写入正式题库。
- 本地解析是保底路径：未配置 MCP/模型时，文本类文件仍需完成本地清洗与切题；视觉类文件应返回可理解的失败或警告，不能丢失既有草稿。
- AI 结果只可补充允许的元数据。题干、选项、答案、解析的实质内容不得被无审计地覆盖；题数不一致时保留本地结果并附警告。
- `warnings` 是降级、媒体未可靠绑定、AI 回包不合格等情况的可见记录，拆分时不得丢失、静默吞掉或改成成功状态。

### 对外兼容

- 保留 `ImportPipelineService`、`PandocAdapter`、`DocumentCleaningService`、`StructuredQuestionParsingService`、`StaleBatchVersionError` 的现有导入路径和公开方法签名，除非协调 AI 明确安排一次兼容迁移。
- 保留批次目录结构、`status.json` 字段含义、任务结果字段、媒体 manifest 以及 `import_task_to_response` 的返回形状。
- `document_pipeline.py` 可以成为薄门面；路由和调用方无需知道新模块存在。

## 5. 建议拆分顺序与每步交付

每一项必须单独提交并验证后再做下一项；不要跨两项做“大搬家”。

1. **纯文本规则：`import_text_rules.py`（首选）**
   - 移动/归并：`_normalize_source_name`、`_difficulty_level`、`normalize_import_question_metadata`、`_normalize_ai_questions`、`_extract_json_payload`、`_safe_json_dict`、题目/知识点草稿提取、元数据补丁解析和合并。
   - 保持这些函数无文件 I/O、无数据库 I/O、无 MCP 调用；使用显式入参和返回值承载警告。
   - 在 `document_pipeline.py` 保留兼容导入或薄委托，避免测试与其他调用方立即断裂。

2. **文档转换：`document_converter.py`**
   - 将完整 `PandocAdapter` 移入新模块，保留 `document_pipeline.PandocAdapter` 的再导出。
   - 仅负责 Pandoc/MarkItDown、DOCX 媒体解包、文本编码兜底；不得接触任务状态、批次元数据或审核库。
   - 保持 Pandoc 不可用时的 MarkItDown 回退以及“图片绑定需人工确认”的警告。

3. **任务协调：`import_task_coordinator.py`**
   - 迁移任务创建、领取、缓存命中、阶段检查点、失败/重试和幂等键逻辑。
   - 对协调器注入任务仓储与一个“执行阶段”的回调；协调器不得知道题目解析细节，解析器也不得直接修改任务状态。
   - 并发同批次、重复派发、版本过期三类测试必须继续通过。

4. **识别流程：`import_recognition_workflow.py`**
   - 已收拢 `recognize_batch` 的文件类型路由和视觉结果整形；文本阶段仍经既有 `_run_text_pipeline` 回调执行，保证 Pandoc、清洗、切题与幂等行为不变。
   - 后续再评估 `retry_batch` 的最小迁移边界；工作流只组合既有能力，不自行处理 JSON 写入、锁或 SQL。

5. **收尾瘦身（最后才做）**
   - 让 `ImportPipelineService` 留作稳定门面、依赖注入和公开 API 的轻量编排。
   - 审核任务管理相关方法须另行移交给“审核工作流”；本工作流不自行移动它们。

## 6. 实施方式与代码准则

- 先为目标函数补/确认特征测试，再移动实现；移动后先维持行为完全一致，第二个变更再改善命名或数据结构。
- 新模块优先使用类型化的输入/输出或小型 dataclass；不要引入全局单例来隐藏依赖。
- 文件系统副作用只能在 Storage/Converter 边界发生；纯规则模块禁止导入 `Path`、`sqlite3`、`subprocess`、MCP 网关或任务仓储。
- 新异常必须能映射为既有失败状态/警告，不能泄漏为无上下文的 500 错误。
- 将每次变更的文件、测试结果、保留的兼容入口和未完成风险写入本文件末尾的交接记录。

## 7. 验证命令

在仓库根目录执行。PowerShell 示例：

```powershell
$env:PYTHONPATH = "apps/api/src;packages"
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_import_idempotency.py apps/api/tests/test_markitdown_image_binding.py apps/api/tests/test_ai_generated_review.py apps/api/tests/test_import_task_repository.py apps/api/tests/test_task_center.py apps/api/tests/test_task_queue_infrastructure.py -q
```

按改动类型补充验证：

```powershell
# 改动文本清洗、切题或题目元数据时
$env:PYTHONPATH = "apps/api/src;packages"
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_metadata_management.py apps/api/tests/test_review_save.py -q

# 改动批次存储、版本或并发控制时
$env:PYTHONPATH = "apps/api/src;packages"
.\.venv\Scripts\python.exe -m pytest apps/api/tests/test_import_idempotency.py apps/api/tests/test_task_queue_infrastructure.py -q
```

测试前后仅查看与本工作流文件相关的变更；不要用重置、检出或批量格式化来“清理”共享工作区。

## 8. 验收清单

- [ ] 新模块具备单一职责，`document_pipeline.py` 只保留门面/编排和兼容入口。
- [ ] 所有既有导入路径、方法签名、批次文件格式、任务响应字段保持兼容。
- [ ] 同批次并发、重复投递和迟到 Worker 不会破坏元数据，且过期输出被拒绝写入。
- [ ] 文本导入在无 MCP 环境可完成本地处理；模型/转换降级信息保留在 `warnings`。
- [ ] 不会直接写正式题库，审核草稿与审核任务边界不变。
- [ ] 第 7 节中与改动相关的测试通过；新增行为有针对性测试。
- [ ] `git diff -- <本工作流允许范围>` 只包含本工作流文件；未改动禁止范围或其他 AI 的文件。
- [ ] 已更新第 9 节交接记录和函数伪代码文档的拆分状态。

## 9. 与其他工作流的接口约束

| 对接工作流 | 本工作流提供 | 本工作流依赖 | 约束 |
| --- | --- | --- | --- |
| 前端/API | 稳定的既有 HTTP 路由、任务响应、批次状态和媒体字段 | 无 | 本工作流不能改 Router、Schema 或前端；如需字段变更，先由 API 工作流发布兼容契约。 |
| 审核中心 | 规范化的题目/知识点草稿、`warnings`、来源和媒体引用 | 审核任务仓储的既有契约 | 不写正式题库，不迁移审核服务；审核任务的删除/同步逻辑由审核工作流拥有。 |
| 题目与元数据 | `normalize_import_question_metadata` 的稳定结果 | 题型、难度、知识点的现有定义 | 只补齐允许元数据，不覆盖题干、选项、答案、解析的实质内容。 |
| 图片/资产 | `media_assets`（`image_id`、文件名、相对路径、媒体类型） | 既有批次媒体目录格式 | 不改资产库表或图片 API；无法可靠锚定的图片必须显式 warning。 |
| MCP/AI | 明确、最小化的输入和可降级的结果处理 | `McpGatewayService` / `DocumentParser` 现有调用方式 | 不改 MCP 协议；MCP 缺席/失败不能使文本本地导入整体不可用。 |
| 任务基础设施 | 幂等键、阶段检查点与任务状态的稳定语义 | `ImportTask` 和任务仓储接口 | 不改仓储表结构；新增状态或字段先交由任务基础设施工作流评审。 |

## 10. 交接记录

### 初始基线（2026-08-10）

- `ImportBatchStorage` 已从导入主服务中抽出，负责锁、原子写、元数据读写、版本校验、路径与哈希工具。
- 下一优先项：建立 `import_text_rules.py`，先抽纯函数并用兼容再导出保持现有调用方稳定。
- 已知风险：`document_pipeline.py` 仍是高聚合模块；不要与审核任务/路由/仓储工作流同时修改同一段代码。

### 本次变更

- 已新增 `services/import_text_rules.py`，迁移来源/难度、题目元数据、文件类型与 AI 题目草稿的纯规则；`document_pipeline.py` 通过兼容导入保留原有公开路径。
- 已继续迁移 AI JSON/知识点草稿提取、审核内容识别、元数据补丁载荷/解析/合并；题目块切分暂留在 `document_pipeline.py`，等待与专用题目解析器一并迁移。
- 新增并扩展 `tests/test_import_text_rules.py`，直接验证新规则模块；未改动 Router、Schema、Repository、前端或 MCP 契约。
- 验证：导入规则、元数据、AI 审核、幂等、任务仓储、任务中心与队列相关测试共 52 项通过。
- 已新增 `services/document_converter.py` 并迁移完整 `PandocAdapter`：Pandoc/MarkItDown 回退、DOCX 媒体解包、图片引用改写和编码兜底均不再归属业务编排层；`document_pipeline.PandocAdapter` 保持兼容导入。
- 新增 `tests/test_document_converter.py` 验证兼容导入，且 MarkItDown 图片绑定、导入任务和队列相关测试共 42 项通过。
- 已新增 `services/import_question_parser.py` 并迁移 Markdown 切题、AI 对话题目块解析和单题降级构造；`document_pipeline.StructuredQuestionParsingService` 保持兼容导入。
- 新增 `tests/test_import_question_parser.py`，API、AI 审核、幂等、任务仓储与任务队列相关测试共 47 项通过。
- 已新增 `services/import_task_coordinator.py`，迁移幂等键、结果有效性、阶段检查点、缓存复用与后台任务派发判定；具体阶段运行、领取和重试/失败状态仍由 `ImportPipelineService` 编排。
- 新增 `tests/test_import_task_coordinator.py`，协调器、导入幂等、任务仓储、任务中心、队列与 API 测试共 41 项通过。
- 已迁移背景任务的领取、运行/完成状态、重试和失败状态更新；协调器通过阶段执行回调保持与 Pandoc、AI 和题目解析细节解耦。
- 回归：协调器、导入幂等、任务仓储、任务中心、队列与 API 测试共 41 项通过。
- 已新增 `services/import_text_cleaner.py`：`ImportTextCleaner` 独占纯文本/Markdown 清洗规则，`DocumentCleaningService` 仅保留兼容门面并委托该组件；不涉及文件、任务、数据库或 MCP。
- `tests/test_import_text_cleaner.py` 现同时锁定清洗规则和兼容门面委托，确保既有 `DocumentCleaningService` 导入路径与清洗产物不变。
- 已新增 `services/import_recognition_workflow.py`：统一文本与视觉文件类型路由，并保持视觉成功、失败、零题警告和不支持格式的既有响应形状；`ImportPipelineService.recognize_batch` 仅作为兼容入口，通过回调复用已有文本流水线与 AI 解析任务。
- 新增 `tests/test_import_recognition_workflow.py`，覆盖文本回调、视觉失败、零题警告和不支持格式；连同清洗、导入流水线与幂等测试共 21 项通过。
- 下一切口：评估 `retry_batch` 是否能以同样的薄委托方式接入识别工作流；不改 Router、审核边界或任务协议。
