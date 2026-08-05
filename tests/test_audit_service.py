from sqlalchemy import create_engine

from app.audit.service import QueryAuditService


def test_audit_service_returns_none_for_unknown_request() -> None:
    service = QueryAuditService(create_engine("sqlite://"))

    assert service.get_by_request_id("missing") is None
