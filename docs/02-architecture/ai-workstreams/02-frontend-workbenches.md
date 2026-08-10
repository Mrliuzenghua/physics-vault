# 代码地图 2：前端组卷与审核工作台

## 0. 统一代码卡片

| 项目 | 内容 |
| --- | --- |
| 编号 | 2 |
| 负责智能体 | 前端工作台 AI |
| 代码主入口 | `apps/web/src/pages/ComposePage.tsx`、`apps/web/src/pages/ReviewWorkbenchPage.tsx` |
| 可写范围 | 上述页面及其专属 `components/`、`hooks/`、`services/`、`stores/`、`utils/` 和直接相关前端测试 |
| 禁止越界 | 不改共享 API、共享 TypeScript 类型、后端实现或 HTTP 协议 |
| 当前首要切口 | 从 `ComposePage.tsx` 提取草稿加载、合并与刷新逻辑到 `useComposeDraftSession` |
| 验证入口 | 前端 lint、类型检查、相关单元测试与组卷/审核手动回归；详见“测试与验收” |

> 函数级补充：[前端工作台函数地图](02-frontend-workbenches-function-map.md)
> 开始前必读：[并行优化协作总则](00-并行优化协作总则.md)。本工作流不负责修改共享 API、共享类型或后端实现。

## 1. 当前边界与问题定位

| 工作台 | 当前入口 | 规模（2026-08-10） | 现有职责混合 |
| --- | --- | ---: | --- |
| 组卷 | `apps/web/src/pages/ComposePage.tsx` | 2,647 行 | 草稿加载/保存、组卷项目历史、设置历史、本地偏好、键盘和拖拽、教学蓝图、题目搜索、版式测量、导出前检查、整页 UI |
| 审核 | `apps/web/src/pages/ReviewWorkbenchPage.tsx` | 2,165 行 | 草稿规范化、localStorage 缓存、质检配置、队列筛选、自动保存与版本冲突、AI 批处理、图片处理、原文定位、整页 UI |

已有、应当保留的较清晰边界：

| 模块 | 单一职责 | 本工作流中的处理方式 |
| --- | --- | --- |
| `stores/useComposeWorkbenchStore.ts` | 组卷条目、选择位置和撤销/重做历史 | 保持为“组卷条目状态机”；不塞入页面 UI 或服务器状态 |
| `services/composeCommands.ts` | 解析并纯函数式应用组卷命令 | 保持无 React 依赖；新增命令先补此处的纯函数测试 |
| `services/composeSettings.ts` | 用户级组卷偏好读写 | 只保存偏好，不保存某份草稿正文 |
| `services/composeDiagnostics.ts` | 从 LessonPackage 计算诊断报告 | 保持纯函数、无 HTTP/DOM/localStorage 副作用 |
| `utils/composeDraft.ts` | 服务端 PaperDraft 与 ComposeItem 的转换 | 保持为转换层；不做网络请求 |
| `utils/reviewQueueNavigation.ts` | 给定谓词后的下一项导航 | 保持为纯函数 |
| `components/compose/*`、`components/review/*` | 可复用展示与局部交互 | 只接收 props/回调，不直接调用页面级 API |

## 2. 本工作流拥有的文件租约

### 可新增、可修改

优先在以下目录新增独立模块；若修改既有文件，必须只改与本次拆分直接相关的调用点。

```text
apps/web/src/pages/ComposePage.tsx
apps/web/src/pages/ReviewWorkbenchPage.tsx
apps/web/src/stores/useComposeWorkbenchStore.ts
apps/web/src/components/compose/**
apps/web/src/components/review/**
apps/web/src/hooks/compose/**              # 可新建
apps/web/src/hooks/review/**               # 可新建
apps/web/src/services/composeCommands.ts
apps/web/src/services/composeSettings.ts
apps/web/src/services/composeDiagnostics.ts
apps/web/src/services/review/**            # 可新建；仅前端领域服务
apps/web/src/utils/composeDraft.ts
apps/web/src/utils/reviewQueueNavigation.ts
apps/web/src/utils/review/**               # 可新建；必须无 React/HTTP 副作用
```

### 禁止修改（由工作流 03 或 01 负责）

```text
apps/web/src/services/api.ts               # HTTP 客户端、端点与请求/响应适配
apps/web/src/services/apiClient.ts
apps/web/src/types/**                      # 共享 TypeScript 契约
apps/api/**                                # 后端、数据库、Router、Service、Repository
```

也禁止：改变路由 URL、localStorage 已发布 key 的含义、正式题库/审核库写入时机、API 负载字段，或将 AI 输出直接写入正式题库。需要任何一项变化时，写明兼容方案和调用点，交给工作流 03。

## 3. 目标职责图

函数级职责、调用路径和拆分边界见：[前端工作台函数地图](02-frontend-workbenches-function-map.md)。

```text
ComposePage / ReviewWorkbenchPage（薄页面容器：路由参数、布局组装）
  ├─ domain hooks（加载、保存、历史、队列、交互编排）
  ├─ pure services / utils（转换、规则、筛选、缓存序列化）
  ├─ state store（仅跨组件的可编辑工作台状态）
  └─ presentational components（props + callback，局部开关可留组件内）
             ↓
       apps/web/src/services/api.ts（既有 HTTP 契约；只消费）
```

页面可以持有路由和“哪个面板打开”这类短生命周期状态；页面不得继续实现领域规则、请求重试/冲突协调、localStorage 编解码，或超过一个完整工作台流程的行内回调。

## 4. 组卷工作台的拆分卡片

### 4.1 草稿会话与持久化：`useComposeDraftSession`

**来源**：`ComposePage.tsx` 中初始化、`hydrateServerDraft`、草稿保存、从 basket/路由状态合并、服务端版本记录。

```text
输入：路由 state、basket、PaperDraft API、ComposeItem store
输出：loading、draftId、saveState、loadDraft/saveDraft/refreshDraft
过程：
  解析“新草稿 / 已有草稿 / 默认草稿”入口
  拉取所需题目快照并转换为 ComposeItem
  合并尚未被草稿包含的 basket 题目
  保存时携带既有乐观锁/更新时间信息
  成功后更新已保存版本与 localStorage 当前草稿 id
副作用：HTTP、localStorage、Zustand store
不得负责：工具栏渲染、版式计算、教学蓝图规则
```

兼容约束：继续使用 `physics-vault.compose.current-draft-id`；保存成功才更新服务器版本标记；加载失败不清空用户正在编辑的内容。

### 4.2 文档设置与历史：`useComposeSettingsHistory`

**来源**：`ComposeSettingsSnapshot`、`settings*Ref`、`updateSettings`、设置撤销/重做和用户偏好保存逻辑。

```text
输入：初始 ComposeUserSettings
输出：settings snapshot、setTitle/setSubtitle/setHeaderFooter/setStyle/setSlideTemplate、undo/redo
过程：在 900ms 同字段窗口内合并历史；最多保留 60 条；每次变更产生可序列化快照
副作用：仅通过 composeSettings 写入用户偏好
不得负责：ComposeItem 的撤销栈、草稿服务器保存
```

关键规则：条目历史仍由 `useComposeWorkbenchStore` 管理；工作台级撤销只在两个历史栈中选择“最后一次真实变更”，不得合并两套数据到一个全局 store。

### 4.3 组卷文档操作：`useComposeItemActions`

**来源**：插入文本/知识卡/分页、复制、删除、多选、拖拽、键盘操作、题目详情更新。

```text
输入：ComposeItem[]、selectedIndex、store command、当前编辑项 id
输出：稳定的 add/update/remove/move/duplicate/select 回调
过程：先生成下一个 immutable items；一次用户操作只调用一次 commitItems 或 transaction
副作用：仅 Zustand store
不得负责：搜索题目、保存服务器草稿、渲染行组件
```

`ComposeAiPanel` 只通过这些明确回调请求变更；AI 面板不得自行访问 store 或构造 PaperDraft。

### 4.4 教学蓝图与补题：`useTeachingBlueprint`

**来源**：知识点分组、蓝图规则、补题候选搜索、预览、应用补题。

```text
输入：当前题目、TeachingBlueprintRules、searchQuestions API
输出：preview、candidate list、loading/error、generate/apply 操作
过程：从当前 ComposeItem 推导蓝图；请求候选题；仅在用户确认后将选中题转换为 ComposeItem
副作用：HTTP、store
不得负责：弹窗布局或最终导出
```

### 4.5 版式测量与预检：`useComposePreview` + `ComposePreflightPanel`

**来源**：页面尺寸、缩放、分页测量报告、`buildComposeDiagnostics`、预览页数限制。

纯计算保留在 `services/composeDiagnostics.ts` 或 `utils/compose/*`；Hook 只协调 DOM 测量和 React 状态。`HandoutDocument` 仍是文档渲染的唯一所有者，不复制其分页规则。

### 4.6 建议的 UI 落点

从 `ComposePage.tsx` 移出纯展示组件时，优先形成：

```text
components/compose/ComposeToolbar.tsx
components/compose/ComposeOutline.tsx
components/compose/ComposeCanvas.tsx
components/compose/ComposeInspector.tsx
components/compose/ComposePreflightPanel.tsx
components/compose/TeachingBlueprintDialog.tsx
components/compose/SupplementCandidatesDialog.tsx
```

这些组件可保留自身的折叠/hover/输入草稿状态，但不得发起 `fetch*` 或保存草稿。

## 5. 审核工作台的拆分卡片

### 5.1 审核草稿转换：`utils/review/reviewDraft.ts`

将 `normalizeDraft`、`normalizeKnowledgeDraft`、`normalizeOptions`、`normalizeSourceBBox`、`cloneDraft`、`applyAiPatch`、`getChangedReviewFields`、展示值格式化移出页面。

```text
输入：未知 API 数据或 AI 文本
输出：合法的 ReviewQuestionDraft / KnowledgeReviewDraft / 安全 patch
过程：校验数组和枚举；规范化数学文本；保留未知/缺失字段的安全默认值；计算图片引用问题
副作用：无
```

所有输入容错和“AI 文本不是 JSON 时视为解析文本”的兼容语义必须保留，并补单元测试；不改变 `ReviewQuestionDraft` 的共享字段定义。

### 5.2 缓存与质检偏好：`services/review/reviewCache.ts`

将 `reviewCacheKey/read/write/clear`、`read/writeQualityConfig`、媒体资源合并和任务元数据合并移出页面。

```text
输入：taskId、可序列化审核状态、质检配置
输出：缓存状态或 null、合并后的 ReviewTaskMeta
过程：检查版本与 taskId；JSON 解析失败时安全降级；按 relative_path/image_id/filename 去重资源
副作用：localStorage
```

兼容约束：保持 `physics_vault_review_cache.`、缓存版本 `1` 和 `physics_vault_review_quality_config.v1`；存储异常必须吞掉并让页面继续可用。

### 5.3 队列和质量规则：`useReviewQueue`

**输入**：草稿、当前队列、当前索引、质检配置。
**输出**：筛选后的索引、计数、当前题、前后跳转、队列切换、搜索过滤。
**规则**：质量规则仍使用 `services/questionQuality.ts`；`findNextMatchingIndex` 是唯一的下一项索引选择器；筛选不修改草稿状态。

### 5.4 服务端同步和冲突：`useReviewDraftPersistence`

**来源**：初始化加载、`serverVersionRef`、待保存队列、自动保存、冲突恢复、版本历史、确认提交与删除。

```text
输入：taskId、当前 drafts/knowledgeDrafts/taskMeta、既有 review API
输出：load、saveState、autosave、restoreVersion、commit、delete、conflict 状态
过程：
  加载远端草稿及任务元数据，必要时与本地缓存合并
  本地变更序列化后去重，串行发送，保留最后一个待保存状态
  遇到 ReviewDraftConflictError 时停止覆盖、显示可恢复状态并重新加载远端版本
  仅明确确认操作调用正式“保存审核结果”端点
副作用：HTTP、localStorage
不得负责：编辑器 JSX、质量展示、图片面板 UI
```

绝对禁止删掉现有乐观锁、请求串行化、冲突停写或草稿优先恢复逻辑来“简化”代码。

### 5.5 审核 UI 组件

页面最终仅组装以下区域；可从现有行内组件迁移，但不改交互语义：

```text
components/review/ReviewQueueSidebar.tsx
components/review/ReviewEditorWorkspace.tsx
components/review/ReviewSourcePreview.tsx
components/review/ReviewQualityPanel.tsx
components/review/ReviewBatchActions.tsx
components/review/ReviewImageCache.tsx
components/review/ReviewChangePanel.tsx
components/review/KnowledgeReviewWorkspace.tsx
```

原文页图定位（bbox 归一化、缩放、翻页）属于 `ReviewSourcePreview`；图片上传、剪贴板写入属于 `ReviewImageCache`，但网络动作仍由 Hook 注入回调。`QuestionEditor`、`QuestionList`、`QuestionMeta` 是已有子组件，应优先复用，不另建功能重叠的编辑器。

## 6. 推荐实施顺序（只做一个切口后再集成）

1. **纯函数先行**：为 `composeCommands`、`composeDraft`、`reviewDraft`、`reviewCache` 添加/补齐测试；不改任何页面行为。
2. **审核数据层**：迁出审核规范化、缓存和队列计算，再以 Hook 承接保存/冲突编排；页面仍保留原 JSX。
3. **组卷数据层**：迁出设置历史、草稿会话、条目操作；保持 `useComposeWorkbenchStore` API 向后兼容。
4. **展示层迁移**：一次迁一个视觉区域，先通过 props 串回原页面；不得在“拆组件”时调整样式和产品交互。
5. **收尾**：页面只保留路由、顶层布局和 Hook 装配；删掉已迁移的重复 helper，并更新本文件的“已完成项”。

每个 PR/提交最多覆盖上面一个编号；若同时碰到组卷和审核，只能共享纯函数测试或通用 UI，不能顺手重写两个工作台。

## 7. 与其他工作流的接口约束

| 对方 | 本工作流可以做 | 必须交接的事项 |
| --- | --- | --- |
| 01 导入后端 | 消费既有 review/import API 和 `ImportMediaAsset` 数据 | 新增任务状态、页图、媒体或草稿字段时，给出字段语义、空值规则、示例响应；由 03 管理共享契约 |
| 03 平台与契约 | 只调用 `services/api.ts` 已有导出、只消费 `types/**` | 需要新端点、修改 API 参数/响应、拆分 `api.ts`、移动共享类型时，提交调用点清单和向后兼容建议 |
| 00 集成协调 | 提供小切口、测试和风险说明 | 文件租约冲突、跨两个工作流的交互变化、缓存 key 迁移、路由调整必须先报 00 决策 |

禁止反向依赖：组件不得 import 后端实现；纯工具不得 import React、store 或 `services/api.ts`；领域 Hook 不得从 UI 组件反向 import。

## 8. 测试与验收

在 `apps/web` 目录运行：

```powershell
npm run lint
npm run build
npm test
node --experimental-strip-types --test src/utils/composeDraft.test.ts src/utils/reviewQueueNavigation.test.ts
```

新增 `utils/review/*.test.ts` 或 `services/review/*.test.ts` 后，把相应文件追加到最后一条命令；若工作流 03 未更新统一 `npm test` 脚本，也必须在交接说明中列出显式测试命令。

人工回归最小清单：

- 组卷：加载旧草稿、从 basket 合并、插入/拖拽/删除、条目和设置的撤销重做、自动保存、刷新后恢复、教学蓝图补题、学生/教师输出切换。
- 审核：加载远端或本地缓存草稿、各风险队列筛选与下一题导航、编辑后自动保存、网络冲突提示与恢复、版本恢复、原文页图定位、图片插入、AI 批量动作、确认提交。
- 兼容：缓存不可用或 JSON 损坏不会使页面白屏；API 失败不会静默丢失本地编辑；既有键盘、拖拽和预览功能保持可用。

完成定义：构建、静态检查及相关单测通过；页面大小实质下降；每个新 Hook/服务有单一职责和明确副作用；没有修改 `api.ts`、`types/**` 或后端；`git diff --check` 通过。

## 9. 交接模板

每次交给 00 的结果必须按以下格式：

```text
工作切口：
文件：新增 / 修改（只列本切口）
保留的行为：
职责变化：迁出了什么；页面现在只保留什么
测试：命令 + 结果
未验证风险：
需 01 / 03 / 00 决策的事项：无 / 具体说明
```

## 10. 已完成项

### 10.1 审核草稿纯函数抽离（2026-08-10）

- 新增 `apps/web/src/utils/review/reviewDraft.ts`：承接审核题目与知识点草稿规范化、选项与原文 bbox 校验、图片引用检查、AI patch 解析、深拷贝、字段差异与展示值格式化。
- `ReviewWorkbenchPage.tsx` 只保留页面组装、领域编排和 UI 标签；不再内联上述转换规则。
- 新增 `apps/web/src/utils/review/reviewDraft.test.ts`，覆盖不完整草稿的安全默认值、实验题识别、无效 bbox、知识点草稿回退、非 JSON AI 输出与字段差异。
- 保留既有 HTTP、缓存 key、共享类型、保存/冲突处理和审核交互语义。

### 10.2 审核缓存与元数据服务抽离（2026-08-10）

- 新增 `apps/web/src/services/review/reviewCache.ts`：承接审核草稿缓存读写、质检偏好读写、媒体资源去重及任务元数据合并。
- `ReviewWorkbenchPage.tsx` 保留缓存触发时机、服务端保存和 UI 状态，不再内联 localStorage 编解码或媒体合并规则。
- 新增 `apps/web/src/services/review/reviewCache.test.ts`，覆盖缓存损坏、任务 id 隔离、存储不可用和媒体去重。
- 保持 `physics_vault_review_cache.`、缓存版本 `1` 与 `physics_vault_review_quality_config.v1` 的语义不变。

### 10.3 审核队列 Hook 抽离（2026-08-10）

- 新增 `apps/web/src/hooks/review/useReviewQueue.ts`：管理当前题、队列类型、搜索词、风险计数、筛选结果和前后/下一风险题导航。
- 新增 `apps/web/src/utils/review/reviewQueue.ts`：承接纯队列规则、质检报告、风险计数、筛选与统一的环形风险导航选择器。
- `ReviewWorkbenchPage.tsx` 保留确认提交时的业务提示与状态更新，不再实现队列计算或手工扫描“下一风险题”。
- 新增 `apps/web/src/utils/review/reviewQueue.test.ts`，覆盖计数、失败页/文本筛选和风险队列环绕导航。

### 10.4 审核队列侧栏组件抽离（2026-08-10）

- 新增 `apps/web/src/components/review/ReviewQueueSidebar.tsx`：承接队列选择、文本搜索和题目列表展示。
- 组件只接收队列状态、筛选结果、风险查询、展示标签与选择回调；不访问 API、缓存、store 或页面状态。
- `ReviewWorkbenchPage.tsx` 仅装配组件并注入回调，保持原有筛选、状态标签和风险提示语义。

### 10.5 组卷草稿会话 Hook 抽离（2026-08-10）

- 新增 `apps/web/src/hooks/compose/useComposeDraftSession.ts`：承接已记忆草稿、路由素材包、最新草稿和题篮四类加载入口。
- Hook 负责服务端草稿 hydrate、题篮增量合并、服务端空闲刷新，以及草稿 id/版本标记和已发布 localStorage key 的维护。
- `ComposePage.tsx` 只注入条目 store、路由状态与标题回调；自动保存仍在页面，继续使用 Hook 返回的草稿版本和冲突刷新入口。
- 保留“加载失败不清空编辑内容”“保存成功才更新服务端版本标记”和 `physics-vault.compose.current-draft-id` 的兼容语义。
