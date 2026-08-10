# Physics Vault API

本目录是 Physics Vault 后端的唯一运行时包。

## 应用入口

- `app.py` 负责创建 FastAPI 应用、注册中间件和所有路由。
- `main.py` 只保留 ASGI 兼容入口，对外暴露 `app` 和 `create_app`。
- 新功能必须放入独立 router，不得继续向 `legacy_app.py` 添加接口。

## 遗留代码隔离

公开接口已全部由独立 router 装配，应用启动不再加载 `legacy_app.py`。该文件仅作为待审计的历史实现保留；删除前必须确认没有离线脚本或部署入口仍直接引用它。

## 数据路径

数据库、审核数据库、素材和导出目录统一由 `paths.py` 提供。环境变量中的相对路径以项目根目录为基准；业务模块不得自行拼接旧版外部目录。
