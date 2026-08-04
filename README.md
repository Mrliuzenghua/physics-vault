# Physics Vault

Physics Vault 是一个本地高中物理题库、校对与组卷工作台，并通过 MCP 向 AI 助手提供检索、审核、组卷和后台任务工具。

## 主要入口

- 后端 ASGI：`physics_vault_api.main:app`，应用装配位于 `apps/api/src/physics_vault_api/app.py`。
- 前端：`apps/web/src/main.tsx`。
- 物理题库 MCP：`scripts/physics_vault_mcp_server.py`，使用 stdio 传输。
- AI 模型适配层：`packages/mcp_contracts/src`，由后端 `/api/mcp/*` 接口调用。
- 后台 worker：`scripts/dev/start-task-worker.ps1`。

## 数据边界

- 正式题库：`data/app-db/physics_vault.sqlite3`，可通过 `PHYSICS_DB_PATH` 覆盖。
- 校对工作区：`data/mcp/review_workspace.sqlite3`，可通过 `PHYSICS_REVIEW_DB_PATH` 覆盖。
- 素材、导入批次、导出产物和日志都位于 `data/` 下。

相对环境变量路径以项目根目录为基准。正式库缺失时不会自动返回演示题；仅在明确设置 `PHYSICS_ALLOW_DEMO_DATA=true` 时启用内置演示数据。

## 目录

```text
apps/api/       FastAPI、业务服务、仓储、数据模型和测试
apps/web/       React 前端
packages/       MCP 契约等共享包
scripts/        MCP 入口、开发脚本和维护脚本
config/         环境变量示例
docs/           产品、架构和接口文档
data/           本地数据库、素材、缓存、导出和日志
```

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
cd apps/web
npm.cmd test
npm.cmd run lint
npm.cmd run build
```
