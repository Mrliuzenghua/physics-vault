from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from pydantic import BaseModel

from .application import ApplicationContainer
from .db_schema import initialize_database
from .observability import TRACE_ID_HEADER, correlation_context, resolve_trace_id
from .paths import project_root

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".wmf", ".emf"}
OFFICE_METAFILE_EXTENSIONS = {".wmf", ".emf"}


class HealthResponse(BaseModel):
    status: str


def _resolve_project_file(file_path: str) -> Path:
    root = project_root().resolve()
    target = (root / file_path).resolve()
    if not target.is_file() or root not in target.parents:
        raise HTTPException(status_code=404, detail="File not found")
    return target


def _cache_response(response: FileResponse, max_age: int = 86400) -> FileResponse:
    response.headers.setdefault("Cache-Control", f"public, max-age={max_age}")
    return response


def _thumbnail_cache_path(target: Path, width: int) -> Path:
    stat = target.stat()
    key = f"{target}:{stat.st_mtime_ns}:{stat.st_size}:{width}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return project_root() / "data" / ".cache" / "image-thumbs" / f"{digest}.webp"


def _build_thumbnail(target: Path, cache_path: Path, width: int) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(target) as raw_image:
        if target.suffix.lower() in OFFICE_METAFILE_EXTENSIONS:
            base_width = max(int(raw_image.width or 1), 1)
            dpi = min(1200, max(72, round(72 * width / base_width)))
            try:
                raw_image.load(dpi=dpi)
            except TypeError:
                raw_image.load()
            image = raw_image.copy()
        else:
            image = ImageOps.exif_transpose(raw_image)
        image.thumbnail((width, width * 4), Image.Resampling.LANCZOS)
        if image.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")
        image.save(cache_path, "WEBP", quality=82, method=4)


def create_app() -> FastAPI:
    initialize_database()

    app = FastAPI(
        title="Physics Vault API",
        version="0.1.0",
        description="Clean backend workspace for the private high school physics question bank system.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def attach_correlation_id(request, call_next):
        """Preserve a caller trace or create one for every HTTP boundary."""
        trace_id = resolve_trace_id(request.headers.get(TRACE_ID_HEADER))
        with correlation_context(trace_id=trace_id):
            request.state.trace_id = trace_id
            response = await call_next(request)
        response.headers[TRACE_ID_HEADER] = trace_id
        return response

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/files/{file_path:path}", response_class=FileResponse)
    def serve_file(file_path: str) -> FileResponse:
        return _cache_response(FileResponse(_resolve_project_file(file_path)))

    @app.get("/thumbs/{file_path:path}", response_class=FileResponse)
    def serve_thumbnail(file_path: str, w: int = Query(default=720, ge=120, le=1600)) -> FileResponse:
        target = _resolve_project_file(file_path)
        if target.suffix.lower() not in IMAGE_EXTENSIONS:
            return _cache_response(FileResponse(target))

        cache_path = _thumbnail_cache_path(target, w)
        if not cache_path.exists():
            try:
                _build_thumbnail(target, cache_path, w)
            except Exception:
                return _cache_response(FileResponse(target), max_age=3600)
        return _cache_response(FileResponse(cache_path, media_type="image/webp"))

    container = ApplicationContainer.build()
    for router in container.routers():
        app.include_router(router)

    return app


app = create_app()
