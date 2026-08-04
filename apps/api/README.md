# apps/api

## 服务端 Word / PPTX 后台导出

- `POST /api/exports/word` 与 `POST /api/exports/pptx` 接收组卷页面的完整快照。
- 快照和产物保存在 `data/exports/{task_id}/`；生成过程使用同目录临时文件，完成后原子替换。
- `GET /api/tasks/{task_id}` 查询状态，`GET /api/tasks/{task_id}/download` 下载结果。
- 未配置 Redis 时导出在 API 进程内同步执行；配置 Redis 后由 Dramatiq worker 继续处理，关闭页面不会中断任务。
- worker 启动脚本同时加载导入和导出 actor：`scripts/dev/start-task-worker.ps1`。
- `PHYSICS_EXPORT_DIR`、`PHYSICS_EXPORT_RETENTION_DAYS` 和 `PHYSICS_EXPORT_MAX_SNAPSHOT_BYTES` 分别控制存储目录、孤儿目录保留期和快照大小上限。
- 清理只移除超过保留期且数据库中没有对应任务记录的孤儿目录，不删除仍被任务引用的产物。

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
