# 学案 MCP 与紧凑检索

## 边界

- 题库服务、MCP 服务代码与本机 MCP 配置位于 `Physics Vault`。
- 教学资源库仍是模板与成品的唯一位置；不会复制为题库的依赖、数据库或前后端目录。
- `study_sheet_workflow` 仅通过 `PHYSICS_STUDY_SHEET_ROOT` 定位资源库，并在每次生成前校验模板注册表和 SHA-256。
- 它只允许写入资源库的 `02-知识讲义`、`03-阶段检测`、`04-每日一题`；`01-模板` 与 `.mcp/study-sheet` 始终只读。

## 学案工作流

1. 调用 `list_study_sheet_templates` 选择已登记模板。
2. 从题库 MCP 使用紧凑检索取得候选题号；仅对入选题号调用 `get_questions_by_ids` 取得完整题目。
3. 将结构化 Typst 内容传入 `create_study_sheet`。先使用 `dry_run=true` 预览；确认后再写入允许的成品目录。
4. 使用 `validate_and_compile_study_sheet` 校验生成标记与模板哈希后编译 PDF。

## 紧凑检索

- `search_questions_compact` 复用原 `search_questions` 的本地召回、向量检索与重排，只投影为题号、标题、题型、难度、知识点、来源、年份、分数和媒体标记。
- `search_questions_curated` 同样先完成原有检索，再由服务端从候选集中做均衡精选；不会写入审核工作台。
- 只有在已选定题号后才调用 `get_questions_by_ids` 请求题干、选项、答案、解析与图片信息。

这两个工具优化的是 MCP 往返中的序列化内容与模型上下文占用，不缩小候选检索范围，也不改变原有排序依据。
