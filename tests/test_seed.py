from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.models import Customer, Order, Product, Region
from app.db.seed import seed_database


def test_seed_database_is_repeatable() -> None:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    seed_database(test_engine)
    seed_database(test_engine)

    with Session(test_engine) as session:
        assert session.scalar(select(func.count()).select_from(Region)) == 5
        assert session.scalar(select(func.count()).select_from(Product)) == 8
        assert session.scalar(select(func.count()).select_from(Customer)) == 50
        assert session.scalar(select(func.count()).select_from(Order)) == 400

