from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
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

    library_url: Mapped[str | None] = mapped_column(
        String(500)
    )

    availability_status: Mapped[str] = mapped_column(
        String(20),
        default="unknown",
        server_default="unknown",
    )

    availability_status_version: Mapped[int] = mapped_column(
        Integer(),
        default=2,
        server_default="2",
    )

    available_copies: Mapped[int | None] = mapped_column(Integer())

    total_copies_at_branch: Mapped[int | None] = mapped_column(Integer())

    availability_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    availability_error: Mapped[str | None] = mapped_column(Text())

    components: Mapped[list["Component"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )


class Component(Base):
    __tablename__ = "components"

    id: Mapped[int] = mapped_column(primary_key=True)

    item_id: Mapped[int] = mapped_column(
        ForeignKey("lendery_items.id")
    )

    name: Mapped[str] = mapped_column(String(200))

    quantity: Mapped[int] = mapped_column(default=1)

    description: Mapped[str | None] = mapped_column(Text())

    image_url: Mapped[str | None] = mapped_column(String(500))

    optional: Mapped[bool] = mapped_column(default=False)

    check_in_notes: Mapped[str | None] = mapped_column(Text())

    item: Mapped["LenderyItem"] = relationship(
        back_populates="components"
    )
