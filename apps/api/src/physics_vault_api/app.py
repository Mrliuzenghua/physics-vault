from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(
        title="Physics Vault API",
        version="0.1.0",
        description="Clean backend workspace for the private high school physics question bank system.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
