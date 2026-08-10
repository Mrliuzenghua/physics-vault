from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


def build_home_router() -> APIRouter:
    router = APIRouter(tags=["system"])

    @router.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home() -> str:
        return """<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>Physics Vault API</title></head><body><h1>Physics Vault API</h1><p>服务正在运行。接口文档请访问 <a href=\"/docs\">/docs</a>，前端应用请通过其独立地址访问。</p></body></html>"""

    return router
