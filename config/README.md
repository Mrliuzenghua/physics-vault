# config

这里放配置模板，不放真实密钥。

建议：

1. 真实配置放本地 `.env`
2. 模板放 `examples/`
3. MCP 命令、数据库路径、素材路径都应通过配置注入
4. MCP 客户端一致性检查默认读取本地 `mcp_client_baseline.json`；该文件已被忽略，可从 `examples/mcp_client_baseline.example.json` 复制后填写本机资源库路径
5. 未创建本地基线时，检查脚本使用可提交示例，并从已配置客户端推断学案资源库路径，避免把用户名和绝对路径提交到仓库
