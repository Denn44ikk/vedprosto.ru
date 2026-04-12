from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .container import build_container
from .interfaces.ui_api.router import router as ui_api_router
from .security import install_access_gate


def create_app() -> FastAPI:
    container = build_container()
    settings = container.settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if container.db_connection is not None:
            await container.db_connection.create_schema()
        if container.its_service is not None:
            await container.its_service.start()
        await container.sigma_service.start()
        try:
            yield
        finally:
            if container.its_service is not None:
                await container.its_service.close()
            await container.sigma_service.close()
            if container.db_connection is not None:
                await container.db_connection.dispose()

    app = FastAPI(
        title=settings.app_title,
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan,
    )
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_access_gate(app)

    app.include_router(ui_api_router, prefix="/api")
    app.mount("/assets", StaticFiles(directory=settings.frontend_assets_dir), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(settings.frontend_index_file)

    return app
