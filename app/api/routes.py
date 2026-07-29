from typing import Any

from fastapi import APIRouter

from app.db.base import engine
from app.db.metadata import inspect_schema

router = APIRouter(prefix="/api/v1")


@router.get("/schema", tags=["database"])
async def get_schema() -> dict[str, Any]:
    return inspect_schema(engine)

