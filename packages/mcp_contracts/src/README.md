# physics_mcp

这是给 Physics Vault 当前 FastAPI 后端准备的 MCP 模块骨架，目标是把 AI 能力从业务逻辑中拆出来，便于：

1. 先用 Mock 跑通页面和服务
2. 再接真实 stdio MCP 服务
3. 在离线模式下切换到 Disabled Provider
4. 让不同开发者并行开发

## 目录说明

- `contracts.py`：稳定领域契约
- `models.py`：输入输出 DTO
- `errors.py`：统一错误码和警告结构
- `schemas.py`：基础 Schema 模型
- `client.py`：MCP 客户端抽象与 stdio 客户端
- `providers.py`：真实 / Mock / Disabled Provider
- `container.py`：服务装配入口
- `runtime/`：MCP 入口共用的数据库连接、服务工厂、参数/错误载荷与审计上下文；不承载业务工具或数据库表结构

## 快速使用

```python
from physics_mcp import build_container

container = build_container(mode="mock")

result = await container.metadata_generator.generate_metadata(...)
```

## 环境变量

如果使用真实 stdio 模式，需要配置：

- `PHYSICS_MCP_VL_COMMAND`
- `PHYSICS_MCP_LLM_COMMAND`

例如：

```powershell
$env:PHYSICS_MCP_VL_COMMAND="python .\\mcp_vl_server.py"
$env:PHYSICS_MCP_LLM_COMMAND="python .\\mcp_llm_server.py"
```
