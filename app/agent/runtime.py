from app.agent.graph import LangGraphTextToSQLService
from app.core.config import settings
from app.services.text_to_sql import TextToSQLService


def create_text_to_sql_service():
    if settings.agent_runtime == "langgraph":
        return LangGraphTextToSQLService()
    return TextToSQLService()
