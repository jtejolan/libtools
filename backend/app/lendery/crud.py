import csv
import io
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from lendery import availability, component_images, models, schemas

OPEN_MAINTENANCE_STATUSES = {"open", "waiting_for_part", "in_repair"}


def _model_data(
    value: BaseModel | Mapping[str, Any],
    *,
    exclude_unset: bool = False,
) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(
            mode="json",
            exclude_unset=exclude_unset,
        )
    return dict(value)


def _commit(db: Session, instance: Any) -> Any:
    try:
        db.commit()
        db.refresh(instance)
    except SQLAlchemyError:
        db.rollback()
        raise
    return instance


def get_item(
    db: Session,
    item_id: int,
) -> models.LenderyItem | None:
    return db.get(models.LenderyItem, item_id)


def get_item_by_barcode(
    db: Session,
    barcode: str,
) -> models.LenderyItem | None:
    statement = select(models.LenderyItem).where(
        models.LenderyItem.barcode == barcode
    )
    return db.scalar(statement)


def list_items(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 100,
    availability_status: str | None = None,
) -> list[models.LenderyItem]:
    statement = select(models.LenderyItem)
    if availability_status is not None:
        statement = statement.where(
            models.LenderyItem.availability_status == availability_status
        )
    statement = (
        statement
        .order_by(models.LenderyItem.id)
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


def items_csv(db: Session) -> str:
    statement = (
        select(models.LenderyItem)
        .options(
            selectinload(models.LenderyItem.components),
            selectinload(models.LenderyItem.maintenance_cases),
        )
        .order_by(models.LenderyItem.id)
    )
    items = db.scalars(statement)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "barcode",
            "name",
            "category",
            "description",
            "purchase_price",
            "purchase_url",
            "manual_url",
            "library_url",
            "availability_status",
            "availability_checked_at",
            "component_count",
            "open_maintenance_case_count",
            "physical_manual_included",
            "physical_manual_missing",
            "notes",
        ]
    )
    for item in items:
        open_cases = sum(
            1
            for case in item.maintenance_cases
            if case.status in OPEN_MAINTENANCE_STATUSES
        )
        writer.writerow(
            [
                item.id,
                item.barcode,
                item.name,
                item.category or "",
                item.description or "",
                item.purchase_price if item.purchase_price is not None else "",
                item.purchase_url or "",
                item.manual_url or "",
                item.library_url or "",
                item.availability_status,
                (
                    item.availability_checked_at.isoformat()
                    if item.availability_checked_at
                    else ""
                ),
                len(item.components),
                open_cases,
                item.physical_manual_included,
                item.physical_manual_missing,
                item.notes or "",
            ]
        )
    return buffer.getvalue()


def create_item(
    db: Session,
    item: schemas.LenderyItemCreate,
) -> models.LenderyItem:
    item_data = item.model_dump(
        mode="json",
        exclude={"components"},
    )
    db_item = models.LenderyItem(**item_data)
    db_item.components = [
        models.Component(
            **component.model_dump(mode="json")
        )
        for component in item.components
    ]
    db.add(db_item)
    db_item = _commit(db, db_item)
    if db_item.library_url:
        db_item = refresh_item_availability(db, db_item)
    return db_item


def update_item(
    db: Session,
    item_id: int,
    changes: BaseModel | Mapping[str, Any],
) -> models.LenderyItem | None:
    db_item = get_item(db, item_id)
    if db_item is None:
        return None

    update_data = _model_data(changes, exclude_unset=True)
    update_data.pop("components", None)
    library_url_changed = (
        "library_url" in update_data
        and update_data["library_url"] != db_item.library_url
    )
    for field in (
        "name",
        "description",
        "barcode",
        "notes",
        "purchase_price",
        "purchase_url",
        "manual_url",
        "image_url",
        "category",
        "library_url",
        "physical_manual_included",
        "physical_manual_missing",
    ):
        if field in update_data:
            setattr(db_item, field, update_data[field])

    if library_url_changed:
        db_item.availability_status = "unknown"
        db_item.availability_status_version = (
            availability.AVAILABILITY_STATUS_VERSION
        )
        db_item.available_copies = None
        db_item.total_copies_at_branch = None
        db_item.availability_checked_at = None
        db_item.availability_error = None

    db_item = _commit(db, db_item)
    if library_url_changed and db_item.library_url:
        db_item = refresh_item_availability(db, db_item)
    return db_item


def refresh_item_availability(
    db: Session,
    db_item: models.LenderyItem,
) -> models.LenderyItem:
    if not db_item.library_url:
        return db_item

    checked_at = datetime.now(timezone.utc)
    try:
        result = availability.check_availability(db_item.library_url)
    except availability.AvailabilityCheckError as exc:
        db_item.availability_checked_at = checked_at
        db_item.availability_error = str(exc)
    else:
        db_item.availability_status = result.status
        db_item.availability_status_version = (
            availability.AVAILABILITY_STATUS_VERSION
        )
        db_item.available_copies = result.available_copies
        db_item.total_copies_at_branch = result.total_copies_at_branch
        db_item.availability_checked_at = checked_at
        db_item.availability_error = None
    return _commit(db, db_item)


def delete_item(
    db: Session,
    item_id: int,
) -> bool:
    db_item = get_item(db, item_id)
    if db_item is None:
        return False

    component_ids = [component.id for component in db_item.components]

    try:
        db.delete(db_item)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    for component_id in component_ids:
        component_images.delete_component_image(component_id)
    return True


def get_component(
    db: Session,
    component_id: int,
) -> models.Component | None:
    return db.get(models.Component, component_id)


def list_components(
    db: Session,
    *,
    item_id: int | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[models.Component]:
    statement = select(models.Component)
    if item_id is not None:
        statement = statement.where(
            models.Component.item_id == item_id
        )
    statement = (
        statement
        .order_by(models.Component.id)
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


def create_component(
    db: Session,
    item_id: int,
    component: schemas.ComponentCreate,
) -> models.Component | None:
    db_item = get_item(db, item_id)
    if db_item is None:
        return None

    db_component = models.Component(
        item=db_item,
        **component.model_dump(mode="json"),
    )
    db.add(db_component)
    return _commit(db, db_component)


def update_component(
    db: Session,
    component_id: int,
    changes: BaseModel | Mapping[str, Any],
) -> models.Component | None:
    db_component = get_component(db, component_id)
    if db_component is None:
        return None

    update_data = _model_data(changes, exclude_unset=True)
    for field in (
        "name",
        "quantity",
        "description",
        "image_url",
        "optional",
        "check_in_notes",
    ):
        if field in update_data:
            setattr(db_component, field, update_data[field])

    return _commit(db, db_component)


def delete_component(
    db: Session,
    component_id: int,
) -> bool:
    db_component = get_component(db, component_id)
    if db_component is None:
        return False

    try:
        db.delete(db_component)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return True


def list_maintenance_cases(
    db: Session,
    item_id: int,
) -> list[models.MaintenanceCase] | None:
    if get_item(db, item_id) is None:
        return None
    statement = (
        select(models.MaintenanceCase)
        .options(selectinload(models.MaintenanceCase.events))
        .where(models.MaintenanceCase.item_id == item_id)
        .order_by(
            models.MaintenanceCase.resolved_at.is_not(None),
            models.MaintenanceCase.opened_at.desc(),
            models.MaintenanceCase.id.desc(),
        )
    )
    return list(db.scalars(statement))


def get_maintenance_case(
    db: Session,
    case_id: int,
) -> models.MaintenanceCase | None:
    statement = (
        select(models.MaintenanceCase)
        .options(selectinload(models.MaintenanceCase.events))
        .where(models.MaintenanceCase.id == case_id)
    )
    return db.scalar(statement)


def list_open_maintenance_cases(db: Session) -> list[models.MaintenanceCase]:
    statement = (
        select(models.MaintenanceCase)
        .options(joinedload(models.MaintenanceCase.item))
        .where(models.MaintenanceCase.status.in_(OPEN_MAINTENANCE_STATUSES))
        .order_by(models.MaintenanceCase.opened_at)
    )
    return list(db.scalars(statement))


def create_maintenance_case(
    db: Session,
    item_id: int,
    value: schemas.MaintenanceCaseCreate,
    *,
    actor_id: int,
    actor_name: str,
) -> models.MaintenanceCase | None:
    item = get_item(db, item_id)
    if item is None:
        return None
    component_name = None
    if value.component_id is not None:
        component = get_component(db, value.component_id)
        if component is None or component.item_id != item_id:
            raise ValueError("Component does not belong to this item")
        component_name = component.name
    case = models.MaintenanceCase(
        item=item,
        component_id=value.component_id,
        component_name=component_name,
        title=value.title,
        description=value.description,
        status=value.status,
        opened_by_user_id=actor_id,
        opened_by_name=actor_name,
    )
    if value.status in {"resolved", "cancelled"}:
        case.resolved_at = datetime.now(timezone.utc)
    db.add(case)
    _commit(db, case)
    return get_maintenance_case(db, case.id)


def update_maintenance_case(
    db: Session,
    case_id: int,
    value: schemas.MaintenanceCaseUpdate,
) -> models.MaintenanceCase | None:
    case = get_maintenance_case(db, case_id)
    if case is None:
        return None
    update_data = value.model_dump(exclude_unset=True)
    for field in ("title", "description", "status"):
        if field in update_data:
            setattr(case, field, update_data[field])
    if "status" in update_data:
        case.resolved_at = (
            datetime.now(timezone.utc)
            if case.status in {"resolved", "cancelled"}
            else None
        )
    _commit(db, case)
    return get_maintenance_case(db, case.id)


def add_maintenance_event(
    db: Session,
    case_id: int,
    value: schemas.MaintenanceEventCreate,
    *,
    actor_id: int,
    actor_name: str,
) -> models.MaintenanceCase | None:
    case = get_maintenance_case(db, case_id)
    if case is None:
        return None
    automatic_status = {
        "part_ordered": "waiting_for_part",
        "part_received": "in_repair",
        "part_installed": "in_repair",
        "repair_completed": "resolved",
    }.get(value.event_type)
    status_after = value.new_status or automatic_status
    event_data = value.model_dump(mode="json", exclude={"new_status"})
    event = models.MaintenanceEvent(
        case=case,
        **event_data,
        status_after=status_after,
        created_by_user_id=actor_id,
        created_by_name=actor_name,
    )
    if status_after is not None:
        case.status = status_after
        case.resolved_at = (
            datetime.now(timezone.utc)
            if status_after in {"resolved", "cancelled"}
            else None
        )
    db.add(event)
    _commit(db, event)
    return get_maintenance_case(db, case.id)
