# scripts

这里仅放可重复执行的正式入口和维护脚本。

1. `dev/`
   本地开发启动、初始化、格式化、检查脚本

2. `maintenance/`
   数据迁移、素材清理、批量校验脚本

3. `physics_vault_mcp_server.py`
   对外提供物理题库 MCP 工具的 stdio 服务入口

根目录不保存绑定固定题号、个人路径或本地端口的一次性排障脚本。可重复的自动检查应写入 `apps/api/tests/`。
