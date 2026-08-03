from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
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

    physical_manual_included: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default="0"
    )

    physical_manual_missing: Mapped[bool] = mapped_column(
        Boolean(), default=False, server_default="0"
    )

    components: Mapped[list["Component"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
    )

    maintenance_cases: Mapped[list["MaintenanceCase"]] = relationship(
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

    missing_reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    missing_reported_by: Mapped[str | None] = mapped_column(String(80))

    missing_note: Mapped[str | None] = mapped_column(Text())

    missing_ignored_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    missing_ignored_by: Mapped[str | None] = mapped_column(String(80))

    item: Mapped["LenderyItem"] = relationship(
        back_populates="components"
    )


class MaintenanceCase(Base):
    __tablename__ = "lendery_maintenance_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("lendery_items.id", ondelete="CASCADE"), index=True
    )
    component_id: Mapped[int | None] = mapped_column(
        ForeignKey("components.id", ondelete="SET NULL"), index=True
    )
    component_name: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text())
    status: Mapped[str] = mapped_column(
        String(30), default="open", server_default="open", index=True
    )
    opened_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("libtools_users.id"), index=True
    )
    opened_by_name: Mapped[str] = mapped_column(String(80))
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    item: Mapped["LenderyItem"] = relationship(back_populates="maintenance_cases")
    events: Mapped[list["MaintenanceEvent"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="MaintenanceEvent.id",
    )


class MaintenanceEvent(Base):
    __tablename__ = "lendery_maintenance_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(
        ForeignKey("lendery_maintenance_cases.id", ondelete="CASCADE"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text())
    part_name: Mapped[str | None] = mapped_column(String(200))
    quantity: Mapped[int | None] = mapped_column(Integer())
    cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    vendor_url: Mapped[str | None] = mapped_column(String(500))
    order_number: Mapped[str | None] = mapped_column(String(100))
    status_after: Mapped[str | None] = mapped_column(String(30))
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("libtools_users.id"), index=True
    )
    created_by_name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    case: Mapped["MaintenanceCase"] = relationship(back_populates="events")
