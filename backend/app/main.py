from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.analyze import router as analyze_router
from app.api.routes.auth import router as auth_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.history import router as history_router
from app.api.routes.profiles import router as profiles_router
from app.core.config import settings
from app.core.db import bootstrap_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap_database()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Recipe Analyzer MVP",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie=settings.session_cookie_name,
        same_site="lax",
        https_only=False,
        max_age=60 * 60 * 24 * 7,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def healthcheck():
        return {"status": "ok"}

    @app.get("/")
    async def root():
        return RedirectResponse(url="/docs")

    app.include_router(auth_router, prefix="/api")
    app.include_router(profiles_router, prefix="/api")
    app.include_router(analyze_router, prefix="/api")
    app.include_router(history_router, prefix="/api")
    app.include_router(dashboard_router, prefix="/api")
    return app


app = create_app()
