# physics_vault_runtime

这个目录保存 Physics Vault FastAPI 的运行时代码入口。

当前结构：

1. `main.py`
   统一运行时入口，后续新的模块化代码从这里装配。

2. `legacy_app.py`
   原有单文件 FastAPI 实现，先保留兼容，避免一次性大改带来风险。

清理原则：

1. 对外统一推荐使用 `physics_vault_runtime.main:app`
2. 旧入口 `physics_vault_api:app` 保留为兼容壳
3. 后续逐步把 `legacy_app.py` 中的搜索、review、embedding、题库写操作拆到独立模块
