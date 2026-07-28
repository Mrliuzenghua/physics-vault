from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .application import ApplicationContainer
from .db_schema import initialize_database
from .paths import project_root


def create_app() -> FastAPI:
    initialize_database()

    app = FastAPI(
        title="Physics Vault API",
        version="0.1.0",
        description="Clean backend workspace for the private high school physics question bank system.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/files/{file_path:path}")
    def serve_file(file_path: str) -> FileResponse:
        root = project_root().resolve()
        target = (root / file_path).resolve()
        if not target.is_file() or root not in target.parents:
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(target)

    container = ApplicationContainer.build()
    for router in container.routers():
        app.include_router(router)

    return app


app = create_app()
