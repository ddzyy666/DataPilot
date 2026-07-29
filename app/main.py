from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        description="A production-oriented Text-to-SQL data analysis agent.",
        version="0.1.0",
        debug=settings.app_debug,
    )

    @application.get("/health", tags=["system"])
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    application.include_router(router)
    return application


app = create_app()
