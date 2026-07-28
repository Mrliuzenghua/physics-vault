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

- `C:\Users\lzh\OneDrive\Pysics Vault3.0\09-项目工程\physics-vault\config\examples\mcp.env.example`

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

- `C:\Users\lzh\OneDrive\Pysics Vault3.0\09-项目工程\physics-vault\scripts\dev\mock_vl_mcp.py`
- `C:\Users\lzh\OneDrive\Pysics Vault3.0\09-项目工程\physics-vault\scripts\dev\mock_llm_mcp.py`

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
