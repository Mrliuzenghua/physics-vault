# packages/mcp_contracts

这里放稳定的 MCP 抽象层：

1. 领域契约
2. 输入输出模型
3. 错误码与警告码
4. Mock / Disabled / Real Provider 的统一边界

这层的目标是让业务代码不直接依赖具体模型实现。
