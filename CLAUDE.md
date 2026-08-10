# Physics Vault：Claude Code 数据库操作规范

本项目只允许通过 `physics_vault` MCP 访问业务数据；不得使用原始 SQLite、文件系统或其他 MCP 绕过数据库边界。

## 数据库边界

- **标准库（Canonical DB）**：正式题库。默认只读；批量修改必须使用受控工具，并在执行前说明影响范围。
- **审核库（Review DB）**：校对中心、草稿、送审任务。可读写，可进行批量清洗和统一规范。

## 路由规则

若用户说“送审、校对中心、待校对、审核任务、草稿、回炉、LaTeX 清洗/结构化”，只能先调用以下审核库工具：

- `list_review_tasks` / `list_review_queue`
- `import_word_folder_to_review`（先 `dry_run=true` 查看文件夹清单，用户确认后再执行）
- `get_review_task` / `get_review_task_full`
- `clean_review_task_latex` / `update_review_task_draft`

不得用 `search_questions`、`get_questions_by_ids` 或 `database_health_report` 来定位上述审核库数据。

若用户未明确数据范围，先调用 `database_boundary_report`，再选择工具。

## 写入规则

- 标准库的标签、年份、知识点等检索元数据使用 `batch_update_question_metadata` 直接维护；知识点修改会自动保留可回滚变更批次。
- 每道正式题采用“1 个主三级知识点 + 最多 2 个辅助三级知识点”。只在题干或解析存在明确证据时补充辅助知识点，不得为了凑满三个而添加弱相关节点。
- 检索结果的题干/解析与现有知识点明显冲突、知识点缺失或绑定不完整时，调用 `maintain_question_knowledge_points`。允许自动应用高置信度修复；`needs_review` 项不得强行修改。
- 需要撤销时先调用 `get_change_batch`，再调用 `rollback_change_batch`。
- 将正式题退回审核只能使用 `return_question_to_review`。
- 审核库内的 LaTeX 规范化优先使用 `clean_review_task_latex`；先 dry run，确认后再执行。
- 当用户要求“导入某文件夹的 Word、逐个上传/清洗后送审”时，使用 `import_word_folder_to_review`，而不是搜索文件或直接写 SQLite。
- 当用户要求“组卷、加入组卷工作台、插入试卷标题/分节标题/教学说明、调整工作台顺序”时，优先使用一次性工具 `apply_composition_workbench_plan`，在一次调用中批量添加题目、知识点、教学对象并完成排序；只在小范围临时修改时使用单项工具。它们仅写入组卷草稿（`paper_drafts`），不会修改正式题库题目或标准知识点；这是自由编排区，老师明确提出操作时可直接执行，只有老师主动要求预览时才设 `dry_run=true`。
- 当用户说“检索所有某主题题目、精选 N 道加入工作台/组卷”时，优先使用 `curate_questions_to_composition_workbench`。它一次完成正式题库检索、排除已在工作台中的题目、按题型/难度/来源均衡精选和组卷草稿预览；先 `dry_run=true`，确认后再写入。

回答中说明本次操作的数据范围（标准库或审核库）、是否写入，以及可撤销方式。
