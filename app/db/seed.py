from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from random import Random

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base, engine
from app.db.models import Category, Customer, Order, OrderItem, Product, Region


def seed_database(target_engine: Engine = engine) -> None:
    Path("data").mkdir(exist_ok=True)
    Base.metadata.create_all(target_engine)

    with Session(target_engine) as session:
        existing_regions = session.scalar(select(func.count()).select_from(Region))
        if existing_regions:
            return

        regions = [Region(name=name) for name in ["华东", "华南", "华北", "西南", "东北"]]
        categories = [
            Category(name=name) for name in ["数码产品", "办公用品", "家居生活", "运动户外"]
        ]
        session.add_all([*regions, *categories])
        session.flush()

        products = [
            Product(name="无线耳机", category=categories[0], price=Decimal("299.00")),
            Product(name="机械键盘", category=categories[0], price=Decimal("459.00")),
            Product(name="笔记本支架", category=categories[1], price=Decimal("129.00")),
            Product(name="人体工学椅", category=categories[1], price=Decimal("1299.00")),
            Product(name="智能台灯", category=categories[2], price=Decimal("239.00")),
            Product(name="保温杯", category=categories[2], price=Decimal("99.00")),
            Product(name="瑜伽垫", category=categories[3], price=Decimal("159.00")),
            Product(name="露营帐篷", category=categories[3], price=Decimal("899.00")),
        ]
        session.add_all(products)

        rng = Random(20260729)
        start = datetime(2024, 1, 1, 9, 0)
        customers = [
            Customer(
                name=f"客户{i:03d}",
                region=regions[(i - 1) % len(regions)],
                created_at=start + timedelta(days=i),
            )
            for i in range(1, 51)
        ]
        session.add_all(customers)
        session.flush()

        for order_number in range(1, 401):
            created_at = start + timedelta(days=rng.randrange(0, 730), hours=rng.randrange(0, 12))
            status = rng.choices(
                ["paid", "cancelled", "pending"],
                weights=[82, 10, 8],
                k=1,
            )[0]
            order = Order(
                customer=rng.choice(customers),
                status=status,
                created_at=created_at,
                paid_at=created_at + timedelta(hours=rng.randrange(1, 48))
                if status == "paid"
                else None,
            )
            for product in rng.sample(products, k=rng.randint(1, 3)):
                order.items.append(
                    OrderItem(
                        product=product,
                        quantity=rng.randint(1, 4),
                        unit_price=product.price,
                    )
                )
            session.add(order)

        session.commit()


def main() -> None:
    seed_database()
    print("DataPilot demo database initialized: data/datapilot.db")


if __name__ == "__main__":
    main()

