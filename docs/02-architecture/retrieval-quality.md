# 题库检索质量基准

题库默认使用“向量召回 + 严格关键词召回 + `gte-rerank-v2` 精排”的混合检索。知识点标签只作为辅助信号，不是硬过滤条件，因此标签错误时仍可依靠题干语义找到题目。

## 在线质量检查

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe scripts\maintenance\evaluate_question_retrieval.py --mode hybrid --check
```

检查覆盖力学、电磁学、光学、热学、近代物理、机械波和解题方法的 19 个自然语言查询，并生成 `data/retrieval-quality/latest.json`。相关性判定同时使用三级知识点 ID 和题干证据，避免把“标签错、内容对”的结果误判为失败。其中“重力配速法”固定要求召回 2008 年江苏卷 Q00000298。

## 解题方法检索

“配速法”等教学术语可能不出现在题干或原解析中。检索层会先识别方法意图，再把方法名展开为可验证的物理结构。例如重力配速法会检查“带电小球、磁场、有效重力、静止释放、运动曲线、曲率半径、`qvB=mg`”等组合；明确写“不计重力”的题不会被判为重力分支。

MCP 的 `search_method_questions`（或带更多过滤条件的 `comprehensive` 模式）会扫描题干、解析、公式、知识点、方法标签和来源。方法查询使用独立概念扩展，不再混入“法拉第、楞次定律”等普通章节扩展词。结果通过 `search_match.matched_locations` 标明每个命中词来自题干、解析、标签还是知识点，并返回三级证据：

- `explicit`：题干、答案或解析原文明确写出方法名；
- `structural`：虽未在正文写方法名，但物理结构满足该方法，或有经维护的方法标签；`match_basis` 会进一步区分 `structure` 与 `method_tag`；
- `related`：只具备部分条件，必须与已确认结果分开。

`search_method_questions` 默认使用 `summary_only=true`、`include_evidence=false`，每题只返回题号、截断标题、来源、题型、难度和方法等级，适合先筛选。需要完整题干和匹配位置时设置 `summary_only=false`；只有需要核验方法证据时再设置 `include_evidence=true`，避免大段解析占满智能体上下文。

默认还会使用 `confirmed_only=true`，只返回 `explicit` 与 `structural`，但仍在统计中保留 `related_candidate_count`；需要查看扩展候选时显式关闭。方法特征已预计算到 `question_method_features`，题干、解析、标签或知识点变化会让对应记录失效，保存后增量重算。结构判定以同一小问/解析段为窗口，避免把综合题不同小问中的“速度分解”和“力平衡”错误拼接。

教师发现误命中或漏检时，使用 `record_method_retrieval_feedback` 记录 `correct`、`incorrect` 或 `missed`。反馈优先级高于自动规则：确认/漏检会维护方法标签、最多三个三级知识点并刷新 embedding 与方法索引；误命中会压制该题在对应方法分支中的结果。`list_method_retrieval_feedback` 可回查审计记录。

方法专项回归：

```powershell
.\.venv\Scripts\python.exe scripts\maintenance\evaluate_method_retrieval.py --check
```

专项门槛包括经典题前 10 召回率、Top 1 稳定性、硬负例、默认 related 泄漏、索引覆盖率和 P95 延迟，报告写入 `data/retrieval-quality/method-latest.json`。

提供年份或地区时，应同时传入 `year`、`region`，不能只把它们拼进查询文本。

质量门槛：

- 向量覆盖率不低于 99%；
- 前 3 命中率不低于 94%；
- 前 10 命中率为 100%；
- 前 5 平均相关率不低于 90%；
- MRR 不低于 94%；
- 单次检索 P95 延迟不高于 8 秒。

脚本返回非零状态即表示回归。修改检索权重、embedding 模型、rerank 模型、知识点结构或批量导入题目后，应运行一次；日常题目编辑产生的向量刷新仍由后台自动完成。
