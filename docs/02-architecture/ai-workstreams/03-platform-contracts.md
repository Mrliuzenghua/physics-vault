# 代码地图 3：平台装配、API 与类型契约

## 0. 统一代码卡片

| 项目 | 内容 |
| --- | --- |
| 编号 | 3 |
| 负责智能体 | 平台与契约 AI |
| 代码主入口 | `apps/api/src/physics_vault_api/application.py`、Router 装配、`apps/web/src/services/api.ts`、`apps/web/src/types/index.ts` |
| 可写范围 | 应用容器与 Router 装配、前端 API 领域模块、共享类型及其直接相关测试 |
| 禁止越界 | 不改导入、组卷、审核等业务规则；不直接替代代码地图 1 或 2 的领域实现 |
| 当前首要切口 | 固定并验证 `ApplicationContainer` 的装配清单，再按领域拆分前端 API 入口 |
| 验证入口 | 后端 Router/应用测试、前端类型检查与 API 调用回归；详见“测试命令” |

> 统一职责：应用装配、HTTP 路由、前端 API 客户端与共享 TypeScript 类型各自只承担一层职责；所有跨工作流 API/类型变更均由本地图出口处理。

## 1. 开工前约束

1. 先阅读 [00-并行优化协作总则](00-并行优化协作总则.md) 和本文，再查看 `git status --short`。当前工作区已有大量未提交改动，均视为他人或用户资产。
2. 本轮先在任务说明中声明精确文件租约；一个切口只处理一个边界。不要因为文件相邻而格式化或清理其他工作流的改动。
3. 改动 HTTP 路径、请求/响应字段、错误结构、`apps/web/src/types/index.ts` 中共享类型或导出名称前，必须写明：调用方列表、兼容期、迁移顺序和回滚方式。
4. 新接口优先采用 `/api/<domain>`、显式 Pydantic `response_model`、具名请求模型和统一错误载荷。根路径旧接口仅作为兼容层，不得在新页面中继续新增调用。

## 2. 当前职责地图

```text
create_app()                         进程级初始化、基础设施路由、挂载容器路由
    ↓
ApplicationContainer.build()         创建共享 Gateway / Repository / Service 实例
ApplicationContainer.routers()       按领域注册 Router，注入已创建服务
    ↓
Router                               HTTP 参数校验、调用服务、HTTP 错误翻译、响应模型
    ↓
Service / Repository                 领域编排 / 数据存储（不属于 03 的业务实现范围）
    ↓
apiClient.ts                         请求、表单上传、基础错误与 API 基路径
domain API modules                   请求路径、序列化、响应归一化
pages/hooks                          只调用领域模块，不能拼接 HTTP 路径
types/index.ts                       跨领域稳定数据契约的公共出口
```

### 2.1 应用装配

- `apps/api/src/physics_vault_api/app.py`：`create_app()` 初始化数据库、注册 CORS 和进程基础路由（`/health`、受限文件访问、缩略图），随后创建容器并挂载 Router。它不能创建业务 Service 的细节，也不能承载领域端点。
- `apps/api/src/physics_vault_api/application.py`：现有 `ExportWorkerContainer`、`WorkerContainer`、`ApplicationContainer` 负责不同运行角色的依赖组装。`ApplicationContainer` 当前声明约 40 个 repository/service 成员，并在 `build()` 内同时构造依赖、恢复 MCP 配置；`routers()` 顺序注册全部领域路由，是本工作流的主要装配热点。
- 边界目标：保持一个薄的总装配入口，逐步以私有领域工厂（如 `_build_import_domain`、`_build_question_domain`、`_build_lesson_domain`）收纳创建细节；`routers()` 只表达路由清单和注入关系。Worker 容器仍仅装配 Worker 所需依赖，不能反向依赖 Web Router。

### 2.2 Router 层

Router 的允许职责：参数/身份校验、请求 schema 到 service 入参的映射、预期领域异常到 HTTP 状态的映射、响应 schema 序列化、设置 `tags`/`response_model`。

Router 的禁止职责：SQLite 查询、文件读写、MCP 调用编排、跨服务业务决策、访问 service 私有属性、在闭包中保存可变业务状态。

当前需要优先守住的边界：

| Router / 路径域 | 观察到的职责 | 契约要求 |
| --- | --- | --- |
| `import_pipeline.py`（`/api/import`） | 导入批次、上传、AI 识别、草稿和任务入口 | 01 拥有内部流水线；03 仅在兼容方案已明确时改 HTTP/schema，并保持任务状态和批次 ID 含义不变。 |
| `question_search.py`（根路径搜索 + `/api/questions/*`） | 检索、筛选、批量读删、回退审核 | 根路径 `/search/questions` 与 `/filters/facets` 是兼容契约；迁移必须先新增 `/api/questions/...` 等价入口、切换客户端、再单独评估删除。 |
| `question_reviews.py`、`review_queue.py`、`review_save.py` | 审核动作、审核队列、草稿保存 | 02 依赖其字段；变更必须保留审核 ID、题目 ID、版本和状态语义，不能让导入绕过审核库。 |
| `papers.py`、`paper_drafts.py`、`tasks.py` | 试卷、草稿和跨域任务中心 | 列表接口必须返回一致分页信息；`tasks.py` 不得再通过 `service._...` 私有属性构造队列健康检查，应由服务公开依赖或注入专用健康服务。 |
| `system_status.py` | 诊断性数据库状态 | 诊断响应也要有显式 schema；不能暴露内部绝对路径、原始异常或其他敏感运行信息给普通客户端。 |

### 2.3 前端 API 与类型层

- `apps/web/src/services/apiClient.ts`：唯一的 HTTP 传输层；负责 `API_BASE`、`request`、`requestForm`、`ApiError`，不含领域路径、页面兼容判断或题目归一化。
- `apps/web/src/services/api.ts`：目前约 49 KB、134 个导出异步函数，且同时再导出本地状态、持久化、任务与审计模块；它是历史聚合入口，不能继续扩大。
- `apps/web/src/types/index.ts`：目前约 40 KB；混合题库、导入、审核、组卷、课件、资产、AI、任务等模型。它可保留为**暂时的兼容 barrel**，但新增类型必须落到领域文件后再从这里显式再导出。
- `questionNormalizer.ts`：属于题目 API 的响应适配，不属于页面或通用 HTTP 层。新题目端点若需兼容旧字段，应在该领域适配层统一完成。

### 2.4 当前契约债务与收敛目标

截至 2026-08-10，`api.ts` 仍同时承载题库、导入、组卷、教学项目、课后反思、素材、MCP 与本地状态的出口；现有领域客户端只有 `taskApi.ts`、`auditApi.ts`、`systemPackageApi.ts`。这不是立即重写的理由，但说明新能力不能再继续直接落入 `api.ts`。

本工作流按以下顺序收敛，避免“目录拆了、契约仍然混在一起”：

| 优先级 | 边界 | 当前问题 | 收敛结果 | 兼容策略 |
| --- | --- | --- | --- | --- |
| P0 | `apiClient.ts` | 传输、错误和 JSON/FormData 规则必须唯一 | 只保留 `requestResponse`、`request`、`requestForm`、`ApiError` | 不允许领域模块自行调用 `fetch` |
| P0 | `api.ts` | 历史聚合入口持续增长 | 仅显式 re-export；不再放实现、领域 DTO 或本地状态 | 原有导入路径保留至调用方迁移完成 |
| P1 | 题库与审核 | 旧根路径、`/api/questions` 与字段归一化并存 | `questionApi.ts` / `reviewApi.ts` 拥有 URL、DTO 转换和 `normalizeQuestion` | 先新增领域入口，再保持同名 re-export |
| P1 | 教学项目、课后反思、保存的讲义 | 新接口已进入历史聚合入口，返回值仍出现 `Record<string, unknown>` | 分别落入 `teachingProjectApi.ts`、`lessonReflectionApi.ts`、`lessonDocumentApi.ts`，并定义具名响应 DTO | 不改变路径、限额裁剪和 404 返回 `null` 的语义 |
| P2 | 后端 Router | 部分新 Router 未显式声明 `response_model` | 所有 JSON 端点具名声明请求/响应模型；下载和流式端点显式使用 `response_class` | 先补 schema 与契约测试，后再处理路径迁移 |

**这里的“领域 DTO”是 HTTP 返回结构，不等于页面状态。** 例如 `SavedHandoutSummary`、`SavedHandoutDocument`、`SavedHandoutVersion` 应描述服务端返回值；页面的筛选、展开状态与临时编辑字段仍留在页面或 store。禁止用 `Record<string, unknown>`、裸 `dict`、`unknown[]` 作为新增公共 JSON 契约的最终类型。

## 3. 文件租约

### 本工作流可写

- `apps/api/src/physics_vault_api/application.py`
- `apps/api/src/physics_vault_api/app.py`（仅基础设施/挂载边界）
- `apps/api/src/physics_vault_api/routers/*.py`（仅 HTTP 契约、错误映射与 Router 结构；先声明精确文件）
- `apps/api/src/physics_vault_api/schemas/*.py`（仅跨域请求/响应契约）
- `apps/api/tests/test_unified_app_routes.py` 及与所改 Router 对应的契约测试
- `apps/web/src/services/apiClient.ts`
- `apps/web/src/services/api.ts`（过渡 re-export 层）
- `apps/web/src/services/*Api.ts`（领域客户端；新建或本流维护）
- `apps/web/src/types/index.ts`（过渡 barrel）与 `apps/web/src/types/<domain>.ts`
- 本目录下的 `03-*` 文档

### 本工作流默认只读

- `apps/api/src/physics_vault_api/services/import_*`、`services/document_pipeline.py`、导入任务实现及它们的测试：工作流 01。
- `apps/web/src/pages/ComposePage.tsx`、`ReviewWorkbenchPage.tsx` 和各自专属组件/hooks：工作流 02。
- Repository、数据库 schema、迁移、MCP 领域实现：除非 00 已确认这是必要的契约实现，且明确由 03 接手。
- `legacy_app.py`：隔离历史代码，不作为本轮顺手清理对象；任何删除须另立离线审计任务。

## 4. 推荐拆分顺序

### 切口 A：固定并验证装配清单（低风险）

1. 为 `ApplicationContainer.build()` 按领域提取私有工厂或具名局部构造步骤，保持构造顺序、实例共享和环境恢复逻辑不变。
2. 将 Router 注册清单组织为领域分组，保留现有路径和注册顺序；新增 route 仅在已有 Router 内挂载。
3. 补充“无重复 path + method”“无重复 OpenAPI operation ID”“Worker 不加载 Web Router”的测试。

### 切口 B：从 `api.ts` 建立领域入口（低风险）

1. 先创建仅移动实现、不改函数签名的客户端：`questionApi.ts`、`importApi.ts`、`reviewApi.ts`、`paperApi.ts`、`lessonApi.ts`、`systemApi.ts`。
2. `api.ts` 暂时只显式 re-export，保证页面和 02 工作流现有导入不变；禁止通配 `export *`，避免意外扩大公共面。
3. 逐页将新代码导入领域模块；旧页面保持兼容，待调用方为零后再删除对应 re-export。

### 切口 C：拆分共享类型并收紧不安全类型（中风险）

1. 按同一领域创建 `types/question.ts`、`import.ts`、`review.ts`、`paper.ts`、`task.ts`、`lesson.ts`、`system.ts`；`index.ts` 仅显式再导出。
2. 优先替换 API 函数中的 `unknown[]`、`Record<string, unknown>` 和裸 `dict` 响应为具名 DTO；不要用断言掩盖不匹配。
3. 在兼容层完成字段别名、默认值和 `normalizeQuestion` 等旧载荷适配；页面类型只表达稳定 UI 所需字段。

### 切口 D：规范化路由（需跨流确认）

1. 新增 `/api/<domain>` 的等价端点和显式 schema，不立即删除根路径或旧字段。
2. 迁移前端领域客户端，保留旧端点至少跨一个可验证发布周期。
3. 用调用方检索、契约测试、OpenAPI 检查确认无使用后，才由 00 批准移除兼容层，并同步更新 `API-architecture-catalog.md`。

### 切口 E：把契约验证变成默认门禁（低风险）

1. 在 `test_unified_app_routes.py` 中继续保留“无重复 path + method / operation ID”，并新增基于 FastAPI 路由元数据的检查：除 `/docs`、`/openapi.json`、HTML、下载与流式端点外，每个 JSON 端点必须有 `response_model` 或明确的例外说明。
2. 为每个新领域客户端添加轻量测试，至少覆盖 URL 编码、方法、请求体、分页/限额裁剪、404 → `null`（如有）和 `ApiError` 透传。测试应 mock `fetch`，不依赖运行中的 API 服务。
3. 每次 HTTP 变更生成并审阅 OpenAPI diff：新增端点、删除端点、请求模型、响应模型、状态码和 operation ID 任一变化都要进入交接说明。不要用“测试通过”替代兼容性审阅。

### 4.1 契约命名与兼容规则

| 场景 | 规则 | 示例 |
| --- | --- | --- |
| 列表响应 | 使用 `XxxListResponse`，稳定包含 `items`；有分页时包含 `limit`、`offset` 与 `total` | `PaperDraftListResponse` |
| 资源详情 | 使用 `XxxResponse` 或领域名；找不到资源由端点返回 404，客户端决定是否映射为 `null` | `TeachingProject` |
| 写入请求 | 使用 `CreateXxxRequest`、`UpdateXxxRequest` 或动作名请求体，不复用 UI 对象 | `RenameSavedHandoutRequest` |
| 动作响应 | 返回具名 `XxxActionResponse`，至少表达可供调用方判断的结果 | `RollbackQuestionVersionResponse` |
| 错误 | 后端统一为 FastAPI `detail` 负载；前端仅经 `ApiError` 与 `extractErrorMessage` 消费 | `{ "detail": { "message": "…" } }` |

兼容字段只能出现在领域适配层，并且要满足三个条件：有删除日期或删除前提、调用方可检索、测试覆盖新旧载荷。不得把兼容判断散落在页面；不得为了兼容把后端 schema 放宽成无类型字典。

## 5. 与其他工作流的接口约束

| 对接方 | 03 提供 | 对接方必须提供 | 禁止事项 |
| --- | --- | --- | --- |
| 01 导入后端 | 导入 API 的 schema、客户端类型、兼容迁移层 | 字段变更申请：旧/新字段、状态机影响、调用方、回滚方案 | 01 不直接改 `api.ts`、共享类型或 HTTP 公开字段；03 不改导入服务算法。 |
| 02 前端工作台 | 领域 API 函数、稳定 DTO、迁移日期 | 页面实际需要的读写字段、交互兼容要求、旧函数调用点 | 02 不在页面拼 URL、不在页面修补后端字段，也不直接改 `types/index.ts`。 |
| 00 集成协调 | 兼容矩阵、切换清单、跨流契约测试结果 | 有冲突的文件租约裁决、删除旧接口的最终批准 | 未经 00，任何流不得删除兼容端点/共享导出或改变审核、导入状态语义。 |

统一交换格式：提出方在任务消息中包含 `领域 / 现状 / 目标字段或路径 / 调用方 / 向后兼容策略 / 验收测试` 六项。没有这六项的跨域变更先停在设计阶段。

## 6. 测试命令

按本次切口选最小充分集；涉及路径、装配或响应模型时必须跑后端路由检查。

```powershell
python -m pytest apps/api/tests/test_unified_app_routes.py
python -m pytest apps/api/tests/test_question_search.py apps/api/tests/test_question_reviews.py apps/api/tests/test_papers.py apps/api/tests/test_task_center.py
Set-Location apps/web; npm run lint
Set-Location apps/web; npm run build
Set-Location apps/web; npm test
git diff --check
```

若改动导入、审核、组卷契约，还需分别由 01 或 02 运行其领域回归，并在交接中标明命令和结果。`npm test` 是项目当前定义的服务层测试集合；新增领域客户端须把相应测试加入该脚本或明确列入独立命令。

契约测试应优先读取实际路由对象与 OpenAPI 结果，不要通过扫描源文件文本来判断 `response_model`；装饰器换行、别名导入和 `response_class` 都会使文本规则误报。

## 7. 验收清单

- 每个改动的函数、模块都有单一职责，且没有把业务流程搬进 Router、`app.py` 或 `apiClient.ts`。
- `ApplicationContainer` 的外部构造结果、共享实例关系、Router 路径和顺序保持兼容；Worker 容器不引入 Web 依赖。
- 每个受影响端点具备显式请求/响应模型和可预期错误结构；不新增裸 `dict`/`unknown` 作为公共协议。
- 新的前端领域客户端可被独立导入；`api.ts` 与 `types/index.ts` 只作为有意维护的兼容出口，不新增领域实现。
- 旧端点、旧导出、字段别名在调用方迁移前仍可用；没有未公告的删除或语义变化。
- 相关后端与前端测试通过，`git diff --check` 无问题；交接中写明修改文件、保留行为、测试结果、风险和下一步。

## 8. 首个可执行任务卡

**目标：** 只拆分 `apps/web/src/services/api.ts` 的“问题题库 API”到 `questionApi.ts`，并由 `api.ts` 显式 re-export；不改 URL、请求体、响应类型、页面调用或 `types/index.ts`。该卡只处理现有题库调用，不吸收 MCP 题目润色、导入、审核草稿或教学项目 API。

**伪代码：**

```text
identify question-related exports in api.ts and record their current importers
move buildSearchParams + search/detail/batch/update/version/knowledge/image request functions
    and normalizeQuestion adaptation to questionApi.ts
preserve imports from apiClient and types
replace moved implementations in api.ts with named re-exports
add request-level tests for encoded IDs, batch payloads and normalization
run TypeScript build and API-client/domain-client tests
verify every public function has identical import path through api.ts
```

**完成标准：** Diff 只包含 `api.ts`、`questionApi.ts`、相关测试（如新增）与本文件；`api.ts` 行数下降，调用方零改动，构建与测试通过。交接中要列出保留的根路径与 `normalizeQuestion` 兼容规则。此任务与 01/02 的文件租约无重叠，适合作为多个 AI 并行前的第一个平台切口。

## 9. 交接记录

### 2026-08-10：教学生产领域客户端拆分

- **变更文件：** `apps/web/src/services/teachingProjectApi.ts`、`lessonReflectionApi.ts`、`lessonDocumentApi.ts`、`questionApi.ts`、`platformContracts.test.ts`；`api.ts` 改为四个领域的具名兼容 re-export；`questionNormalizer.ts` 使用可在 Node 测试中解析的本地运行时导入；`types/teachingProject.ts` 与 `types/lessonDocument.ts` 增加 DTO；`types/index.ts` 显式再导出；`package.json` 将契约测试纳入默认脚本。后端的 `schemas/teaching_projects.py`、`schemas/lesson_reflections.py`、`schemas/lesson_documents.py` 与对应 Router 已增加具名响应模型；`test_platform_contract_schemas.py` 锁定该约束。
- **保留行为：** 所有既有 `services/api` 导入仍可用；列表限额、ID URL 编码、教学项目/讲义 404 → `null`、课后复盘上传时剥离本地同步字段的行为均不变。
- **兼容债务：** `SavedHandoutVersion` 暂时保留索引签名，以兼容 `HandoutPage` 现有的 `Record<string, unknown>[]` 本地状态。由 02 在页面状态完成类型化后移除，03 不直接修改该页面。
- **响应模型兼容：** 教学项目、课后复盘和已保存讲义的顶层 JSON 现在有 OpenAPI 可见模型；响应模型允许已持久化的扩展字段，且讲义包与历史版本快照仍作为下一轮独立类型化的嵌套载荷保留。
- **题库客户端：** `questionApi.ts` 现拥有搜索、详情、批量获取/删除、回退审核、更新、版本、知识点与题目资产调用；保留 `api.ts` 的同名导出，搜索载荷归一化和更新时剥离媒体字段的语义不变。ID 路径统一 URL 编码。
- **验证：** `npm.cmd run build`、`npm.cmd test`（27 passed）、后端领域与契约测试（13 passed）、统一路由检查（4 passed）与 `git diff --check` 通过；Vite 仍报告既有的大型 chunk 警告，未在本切口处理。
- **下一步：** 将图片、收藏、集合、错题、批注、元数据等题库治理能力按各自领域拆分；并针对其余 JSON Router 建立基于 FastAPI 路由元数据与 OpenAPI 的 `response_model` 门禁。
