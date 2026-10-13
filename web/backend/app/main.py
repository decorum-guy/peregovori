from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .config import WEB_DIR, Settings
from .models import MessageRequest, SessionOptions
from .providers import MockProvider, OpenRouterProvider
from .service import DemoService, ServiceError
from .storage import SessionStore


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def create_app(
    settings: Optional[Settings] = None,
    provider=None,
    database_path: Optional[str] = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    active_settings.validate()
    store = SessionStore(database_path or active_settings.database_path)
    active_provider = provider or (MockProvider() if active_settings.llm_mode == "mock" else OpenRouterProvider(active_settings))
    service = DemoService(active_settings, store, active_provider)
    app = FastAPI(title="Линия решения", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.demo_service = service
    app.state.session_store = store
    app.state.provider = active_provider

    @app.exception_handler(ServiceError)
    async def service_error_handler(_request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc), "code": exc.code})

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for error in exc.errors()[:10]:
            errors.append({
                "field": ".".join(str(part) for part in error.get("loc", ())[1:]),
                "message": error.get("msg", "Некорректное значение."),
            })
        return JSONResponse(status_code=422, content={"detail": "Проверьте введённые данные.", "errors": errors})

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "database": "ready", "provider_mode": active_settings.provider_mode}

    @app.get("/api/config")
    async def config(refresh: bool = False):
        return await service.config(force=refresh)

    @app.post("/api/sessions")
    async def create_session(options: SessionOptions):
        return await service.create_session(options)

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str):
        return service.snapshot(store.get(session_id))

    @app.post("/api/sessions/{session_id}/message")
    async def send_message(session_id: str, message: MessageRequest):
        return await service.message(session_id, message.request_id, message.text)

    @app.post("/api/sessions/{session_id}/finish")
    async def finish_session(session_id: str):
        return service.finish(session_id)

    @app.post("/api/sessions/{session_id}/skip-debrief")
    async def skip_debrief(session_id: str):
        return service.skip_debrief(session_id)

    @app.post("/api/sessions/{session_id}/debrief")
    async def debrief_session(session_id: str):
        return await service.debrief(session_id)

    dist = WEB_DIR / "frontend" / "dist"
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    catalog = WEB_DIR / "catalog"
    if (catalog / "assets").is_dir():
        app.mount("/catalog-assets", StaticFiles(directory=catalog / "assets"), name="catalog-assets")

    @app.get("/games", include_in_schema=False)
    @app.get("/games/", include_in_schema=False)
    async def games():
        return FileResponse(catalog / "index.html")

    @app.get("/", include_in_schema=False)
    @app.get("/games/line-decision", include_in_schema=False)
    @app.get("/games/line-decision/", include_in_schema=False)
    async def root():
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return PlainTextResponse("Frontend не собран. Для разработки запустите Vite в web/frontend.")

    @app.get("/{frontend_path:path}", include_in_schema=False)
    async def frontend_fallback(frontend_path: str):
        if frontend_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        index = dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    return app


app = create_app()
