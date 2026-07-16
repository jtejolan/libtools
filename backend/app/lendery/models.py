from decimal import Decimal
from users import database

from sqlalchemy import (
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from database import Base

class LenderyItem(Base):
    __tablename__ = "lendery_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))

    description: Mapped[str | None] = mapped_column(Text())

    barcode: Mapped[str] = mapped_column(
        String(50),
        unique=True
    )

    notes: Mapped[str | None] = mapped_column(Text())

    purchase_price: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2)
    )

    purchase_url: Mapped[str | None] = mapped_column(
        String(500)
    )

    manual_url: Mapped[str | None] = mapped_column(
        String(500)
    )

    image_url: Mapped[str | None] = mapped_column(
        String(500)
    )

    category: Mapped[str | None] = mapped_column(
        String(100)
    )

class Component(Base):
    __tablename__ = "components"

    id:Mapped[int] = mapped_column(primary_key=True)
    item_id: int

    name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int | 1] = mapped_column(Integer)

    description: Mapped[str | None] = mapped_column(Text())
    image_url: Mapped[str | None] = mapped_column(
        String(500))

    optional: int
    check_in_notes: int

    item: str
    