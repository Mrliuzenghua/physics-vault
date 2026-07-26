# Physics Vault

这是 `Pysics Vault3.0` 的干净工程工作区。

这个目录的目标是：

1. 和现有历史脚本、临时文件、试验代码隔离
2. 作为后续正式开发、Git 管理、GitHub 协作的唯一工程目录
3. 让前端、后端、MCP、文档、配置、数据目录分层清晰

## 目录原则

1. 运行时代码只放在 `apps/` 和 `packages/`
2. 文档只放在 `docs/`
3. 配置模板只放在 `config/`
4. 脚本只放在 `scripts/`
5. 本地数据库、素材、缓存、日志只放在 `data/`
6. 不要把一次性调试脚本重新放回根目录

## 顶层结构

```text
physics-vault/
  apps/
  packages/
  docs/
  config/
  scripts/
  data/
  tests/
  .gitignore
```

## 建议开发入口

1. 后端：`apps/api`
2. 前端：`apps/web`
3. MCP 契约与适配：`packages/mcp_contracts`
4. 共享类型与工具：`packages/shared`

## 当前状态

这是一个新的、干净的工程骨架。

历史内容仍保留在仓库原有目录中，例如：

1. `08-前端API/`
2. `07-资料/`
3. `02-数据库/`

后续应以本目录为正式开发主线，逐步把可复用内容迁移进来，而不是继续在旧目录上堆积。
