# MCP后端接入说明

## 1. 目标

本模块为题库系统提供统一 AI 入口，当前已经落地为一套可替换、可扩展的三层结构：

1. `packages/mcp_contracts/src`
   负责 MCP 合同、数据模型、错误模型、mock / stdio provider。
2. `apps/api/src/physics_vault_api/services/mcp_gateway.py`
   负责后端业务层装配，屏蔽底层 MCP 调用细节。
3. `apps/api/src/physics_vault_api/routers/mcp.py`
   负责对外暴露统一 HTTP 接口，供前端与后续任务编排调用。

## 2. 当前已支持能力

- 文档解析 `parse-document`
- 题块检测 `detect-question-regions`
- 单题区域解析 `parse-question-region`
- 试题解析生成 `generate-analysis`
- 专题知识点生成 `generate-knowledge`
- 批量元信息补全 `generate-metadata`
- 运行状态检查 `status`

## 3. 环境配置

参考文件：

- `config/examples/mcp.env.example`

关键变量：

- `PHYSICS_AI_ENABLED`
- `PHYSICS_MCP_MODE`
- `PHYSICS_MCP_WORKDIR`
- `PHYSICS_MCP_VL_COMMAND`
- `PHYSICS_MCP_LLM_COMMAND`

模式说明：

- `mock`：本地演示模式，默认可直接跑通
- `stdio`：接真实 MCP 子进程
- `disabled`：关闭所有 AI 调用

## 4. 本地演示

当前项目已提供两个本地 mock 服务脚本：

- `scripts/dev/mock_vl_mcp.py`
- `scripts/dev/mock_llm_mcp.py`

它们遵循 stdin 输入、stdout 输出 JSON 的约定，后续替换成真实视觉模型或文本模型时，只要保持相同输入输出结构即可。

## 5. HTTP 接口清单

- `GET /api/mcp/status`
- `POST /api/mcp/parse-document`
- `POST /api/mcp/detect-question-regions`
- `POST /api/mcp/parse-question-region`
- `POST /api/mcp/generate-analysis`
- `POST /api/mcp/generate-knowledge`
- `POST /api/mcp/generate-metadata`

返回统一格式：

```json
{
  "ok": true,
  "data": {}
}
```

异常时返回：

```json
{
  "detail": {
    "code": "MCP_TIMEOUT",
    "message": "MCP call timed out",
    "retryable": true
  }
}
```

## 6. 真实模型替换约定

别人接手时只需要替换两部分：

1. 修改环境变量中的命令路径，把 mock 命令换成真实 MCP 服务启动命令。
2. 保持返回字段结构与 `packages/mcp_contracts/src/schemas.py` 中 `BaseResponseModel` 一致。

不需要改前端接口，不需要改路由路径，不需要改业务层调用方式。

## 7. 下一步建议

- 将当前内存态调用日志与任务记录写入 SQLite
- 增加请求限流、超时重试次数配置化
- 给 `generate-metadata` 增加 JSON 修复与字段级容错
- 将 mock provider 换成真实 OCR / VL / LLM 服务

## 8. 题库 MCP 写入边界

题库 MCP 将数据分为两类，避免“所有修改都要审批”和“智能体可以改正文”两个极端：

- **可直接更新的检索元数据**：标签、知识点绑定、难度、题型、规范化来源、年份、地区和考试类型。使用 `batch_update_question_metadata`，无需预演或审核。
- **可直接维护的目录数据**：使用 `create_knowledge_points` 创建知识点；重复调用会返回已有记录，不会重复创建。
- **仅供建议的知识点匹配**：使用 `suggest_knowledge_points_for_task`。它只返回已有知识树中的候选，不会虚构知识点编号。
- **必须人工确认的正式内容**：题干、选项、答案、解析、图片和正式发布状态仍通过导入校对中心处理，智能体不能绕过校对直接覆盖。
- **原始来源永久保留**：来源规范化只更新检索字段，导入时的原始来源文本保留在 `question_text_index.source_text`。

批量导入支持 `file_filter` 和 `skip_if_duplicate`。重复任务可先通过 `find_duplicate_review_tasks` 查看，再调用 `delete_review_tasks`；真正删除时必须显式传入 `confirmed=true`。

初始化知识点与标签目录：

```powershell
.\.venv\Scripts\python.exe scripts\maintenance\seed_metadata_catalog.py
```

脚本可重复执行，只补缺失目录，不修改已有题目内容或自动给题目打标签。
