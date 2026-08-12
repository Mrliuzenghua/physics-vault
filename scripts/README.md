# scripts

## Windows 本地启动

`启动题库.cmd` 是桌面快捷方式使用的一键启动入口。它会调用同目录的
`启动题库.ps1`，检查并启动本机 `127.0.0.1:8000` 后端和
`127.0.0.1:5173` 前端；缺失的依赖只会安装在项目自己的 `.venv` 或
`apps/web/node_modules` 中。服务日志统一写入项目根目录 `.server-logs/`，
重复执行不会重复创建服务进程。

这里仅放可重复执行的正式入口和维护脚本。

1. `dev/`
   本地开发启动、初始化、格式化、检查脚本

2. `maintenance/`
   数据迁移、素材清理、批量校验脚本

3. `physics_vault_mcp_server.py`
   对外提供物理题库 MCP 工具的 stdio 服务入口

4. `study_sheet_mcp_server.mjs`
   对外提供教学资源工作流 MCP：受控生成 Typst 学案，以及 HTML 网页、Typst PDF 两种高中物理课堂课件。Typst 课件使用原生数学排版并可完全离线编译，能力包含 `get_typst_presentation_template`、`create_typst_presentation`、`validate_typst_presentation` 与 `audit_typst_presentation_template`。

常用维护命令：

```powershell
# 非破坏性补齐标准知识树和标签目录，可重复执行
.\.venv\Scripts\python.exe scripts\maintenance\seed_metadata_catalog.py
```

根目录不保存绑定固定题号、个人路径或本地端口的一次性排障脚本。可重复的自动检查应写入 `apps/api/tests/`。
