# apps/api

这里是新的正式后端目录。

目标：

1. 不再直接在旧的 `08-前端API/01-api` 上继续堆逻辑
2. 按 `routers / services / repositories / schemas` 做模块化
3. 通过 `packages/mcp_contracts` 接 MCP 能力

建议后续迁移顺序：

1. 先迁移健康检查和基础配置
2. 再迁移题目检索接口
3. 再迁移考点编辑与 review 接口
4. 最后迁移 embedding 和批量 AI 标注接口
