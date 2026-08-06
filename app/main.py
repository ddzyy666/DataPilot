from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.runtime import close_text_to_sql_runtime
from app.api.docs import get_chinese_swagger_ui
from app.api.routes import router
from app.core.config import settings


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await close_text_to_sql_runtime()

    application = FastAPI(
        title=f"{settings.app_name} 智能数据分析助手",
        description=(
            "面向企业数据库的 Text-to-SQL 数据分析 Agent，"
            "支持数据库结构识别、安全 SQL 生成、查询执行与结果分析。"
        ),
        version="0.1.0",
        debug=settings.app_debug,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
        openapi_tags=[
            {
                "name": "系统",
                "description": "服务状态与运行环境检查。",
            },
            {
                "name": "数据库",
                "description": "查看数据表、字段、主键和外键等数据库元数据。",
            },
            {
                "name": "审计",
                "description": "根据请求追踪ID查询Text-to-SQL审计记录。",
            },
        ],
    )

    @application.get(
        "/health",
        tags=["系统"],
        summary="检查服务状态",
        description="确认 DataPilot 后端服务是否正常运行。",
        response_description="服务运行正常",
    )
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    application.include_router(router)

    @application.get("/docs", include_in_schema=False)
    async def chinese_swagger_ui():
        return get_chinese_swagger_ui(
            openapi_url=application.openapi_url,
            title=f"{settings.app_name} API 文档",
        )

    return application


app = create_app()
