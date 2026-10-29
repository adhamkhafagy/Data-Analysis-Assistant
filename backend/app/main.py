from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, data_sources, workspaces
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Configuration is validated on import. Schema changes are applied only by Alembic.
    yield


settings = get_settings()
app = FastAPI(title="AI Business Intelligence Platform API", version="0.1.0",
              docs_url="/docs" if settings.app_env != "production" else None, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_origin], allow_credentials=True,
                   allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
                   allow_headers=["Content-Type", "X-CSRF-Token"])


@app.exception_handler(Exception)
async def unexpected_error(_: Request, __: Exception):
    return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred"})


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(workspaces.router, prefix="/api/v1")
app.include_router(data_sources.router, prefix="/api/v1")
