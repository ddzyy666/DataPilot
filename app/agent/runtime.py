from app.agent.graph import LangGraphTextToSQLService
from app.core.config import settings
from app.services.text_to_sql import TextToSQLService

_langgraph_service: LangGraphTextToSQLService | None = None


def create_text_to_sql_service():
    global _langgraph_service
    if settings.agent_runtime == "langgraph":
        if _langgraph_service is None:
            _langgraph_service = LangGraphTextToSQLService(
                checkpoint_path=settings.checkpoint_database_path
            )
        return _langgraph_service
    return TextToSQLService()


async def close_text_to_sql_runtime() -> None:
    global _langgraph_service
    if _langgraph_service is not None:
        await _langgraph_service.close()
        _langgraph_service = None
