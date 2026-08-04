# Physics Vault API

本目录是 Physics Vault 后端的唯一运行时包。

## 应用入口

- `app.py` 负责创建 FastAPI 应用、注册中间件和所有路由。
- `main.py` 只保留 ASGI 兼容入口，对外暴露 `app` 和 `create_app`。
- 新功能必须放入独立 router，不得继续向 `legacy_app.py` 添加接口。

## 旧接口兼容

`legacy_app.py` 仅用于迁移尚未模块化的旧接口。`legacy_compat.py` 保存明确的兼容接口清单，启动时会检查遗漏、重复和意外新增的方法。旧接口迁移到独立 router 后，应同时从该清单和 `legacy_app.py` 删除。

## 数据路径

数据库、审核数据库、素材和导出目录统一由 `paths.py` 提供。环境变量中的相对路径以项目根目录为基准；业务模块不得自行拼接旧版外部目录。
