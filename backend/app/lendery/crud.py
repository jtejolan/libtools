import csv
import io
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from lendery import availability, component_images, models, schemas

OPEN_MAINTENANCE_STATUSES = {"open", "waiting_for_part", "in_repair"}

INVENTORY_EXPORT_FIELDS = {
    "id": "Item ID",
    "barcode": "Barcode",
    "name": "Item name",
    "category": "Category",
    "description": "Description",
    "purchase_price": "Purchase price",
    "purchase_url": "Purchase URL",
    "manual_url": "Manual URL",
    "image_url": "Image URL",
    "library_url": "Catalogue URL",
    "catalogue_availability": "Catalogue availability",
    "availability_checked_at": "Availability checked at",
    "circulation_status": "Collection status",
    "status_reason": "Status reason",
    "status_changed_at": "Status changed at",
    "component_count": "Component count",
    "components": "Components",
    "open_maintenance_case_count": "Open maintenance cases",
    "physical_manual_included": "Physical manual included",
    "physical_manual_missing": "Physical manual missing",
    "checkin_card_missing": "Check-in card missing",
    "notes": "Staff notes",
    "created_at": "Created at",
    "updated_at": "Updated at",
}
INVENTORY_DEFAULT_FIELDS = {
    "barcode",
    "name",
    "category",
    "description",
    "purchase_price",
    "circulation_status",
    "status_reason",
    "component_count",
    "open_maintenance_case_count",
}

ACTIVITY_EXPORT_FIELDS = {
    "event_id": "Event ID",
    "occurred_at": "Date and time",
    "event_type": "Event type",
    "event": "Event",
    "item_id": "Item ID",
    "barcode": "Barcode",
    "item_name": "Item name",
    "category": "Category",
    "from_status": "Previous status",
    "to_status": "New status",
    "reason": "Reason",
    "details": "Details",
    "component": "Component",
    "maintenance_case_id": "Maintenance case ID",
    "part_name": "Part or piece",
    "quantity": "Quantity",
    "cost": "Cost",
    "vendor_url": "Vendor URL",
    "order_number": "Order number",
    "recorded_by": "Recorded by",
}
ACTIVITY_DEFAULT_FIELDS = {
    "occurred_at",
    "event",
    "barcode",
    "item_name",
    "category",
    "reason",
    "details",
    "component",
    "part_name",
    "quantity",
    "cost",
    "recorded_by",
}

ACTIVITY_EVENT_LABELS = {
    "item_added": "Added to inventory",
    "marked_unavailable": "Marked unavailable",
    "returned_to_circulation": "Returned to circulation",
    "removed_from_collection": "Removed from collection",
    "permanently_deleted": "Record permanently deleted",
    "maintenance_opened": "Maintenance issue reported",
    "maintenance_status_changed": "Maintenance status changed",
    "issue_update": "Maintenance update",
    "part_ordered": "Part ordered",
    "part_received": "Part received",
    "part_installed": "Part installed",
    "repair_completed": "Repair completed",
    "component_added": "Component added",
    "component_removed": "Component removed",
    "component_missing": "Component reported missing",
    "component_returned": "Component returned",
    "component_report_ignored": "Missing-component report dismissed",
}


def get_suggestion(
    db: Session, suggestion_id: int
) -> models.ItemSuggestion | None:
    return db.get(models.ItemSuggestion, suggestion_id)


def list_suggestions(db: Session) -> list[models.ItemSuggestion]:
    statement = select(models.ItemSuggestion).order_by(
        models.ItemSuggestion.submitted_at.desc(),
        models.ItemSuggestion.id.desc(),
    )
    return list(db.scalars(statement))


def create_suggestion(
    db: Session,
    value: schemas.ItemSuggestionCreate,
    *,
    actor_id: int,
    actor_name: str,
) -> models.ItemSuggestion:
    existing = db.scalar(
        select(models.ItemSuggestion).where(
            models.ItemSuggestion.submitted_by_user_id == actor_id,
            models.ItemSuggestion.submission_key == value.submission_key,
        )
    )
    if existing is not None:
        return existing
    suggestion = models.ItemSuggestion(
        **value.model_dump(mode="json"),
        submitted_by_user_id=actor_id,
        submitted_by_name=actor_name,
    )
    db.add(suggestion)
    try:
        db.commit()
        db.refresh(suggestion)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(models.ItemSuggestion).where(
                models.ItemSuggestion.submitted_by_user_id == actor_id,
                models.ItemSuggestion.submission_key == value.submission_key,
            )
        )
        if existing is None:
            raise
        return existing
    return suggestion


def delete_suggestion(db: Session, suggestion_id: int) -> bool:
    suggestion = get_suggestion(db, suggestion_id)
    if suggestion is None:
        return False
    try:
        db.delete(suggestion)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return True


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


def _touch_item(item: models.LenderyItem) -> None:
    item.updated_at = datetime.now(timezone.utc)


def _record_activity(
    db: Session,
    item: models.LenderyItem,
    event_type: str,
    *,
    actor_id: int | None = None,
    actor_name: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str | None = None,
    details: str | None = None,
    component_name: str | None = None,
    maintenance_case_id: int | None = None,
    part_name: str | None = None,
    quantity: int | None = None,
    cost: Any = None,
    vendor_url: str | None = None,
    order_number: str | None = None,
    source_type: str | None = None,
    source_id: int | None = None,
) -> models.ItemActivity:
    activity = models.ItemActivity(
        original_item_id=item.id,
        item_id=item.id,
        item_barcode=item.barcode,
        item_name=item.name,
        item_category=item.category,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        details=details,
        component_name=component_name,
        maintenance_case_id=maintenance_case_id,
        part_name=part_name,
        quantity=quantity,
        cost=cost,
        vendor_url=vendor_url,
        order_number=order_number,
        actor_user_id=actor_id,
        actor_name=actor_name,
        source_type=source_type,
        source_id=source_id,
    )
    db.add(activity)
    return activity


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
        models.LenderyItem.barcode == barcode,
        models.LenderyItem.lifecycle_status != "removed",
    )
    return db.scalar(statement)


def get_all_barcodes(db: Session) -> set[str]:
    return set(db.scalars(select(models.LenderyItem.barcode)))


def list_items(
    db: Session,
    *,
    offset: int = 0,
    limit: int = 100,
    availability_status: str | None = None,
    lifecycle_status: str | None = "inventory",
) -> list[models.LenderyItem]:
    statement = select(models.LenderyItem)
    if availability_status is not None:
        statement = statement.where(
            models.LenderyItem.availability_status == availability_status
        )
    if lifecycle_status == "inventory":
        statement = statement.where(models.LenderyItem.lifecycle_status != "removed")
    elif lifecycle_status not in (None, "all"):
        statement = statement.where(
            models.LenderyItem.lifecycle_status == lifecycle_status
        )
    statement = (
        statement
        .order_by(models.LenderyItem.id)
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


def _write_csv(fields: list[str], rows: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(fields)
    for row in rows:
        writer.writerow([_csv_cell(row.get(field)) for field in fields])
    return buffer.getvalue()


def _inventory_export_row(item: models.LenderyItem) -> dict[str, Any]:
    open_cases = sum(
        1
        for case in item.maintenance_cases
        if case.status in OPEN_MAINTENANCE_STATUSES
    )
    components = "; ".join(
        f"{component.name} (x{component.quantity})"
        for component in item.components
    )
    return {
        "id": item.id,
        "barcode": item.barcode,
        "name": item.name,
        "category": item.category,
        "description": item.description,
        "purchase_price": item.purchase_price,
        "purchase_url": item.purchase_url,
        "manual_url": item.manual_url,
        "image_url": item.image_url,
        "library_url": item.library_url,
        "catalogue_availability": item.availability_status,
        "availability_status": item.availability_status,
        "availability_checked_at": item.availability_checked_at,
        "circulation_status": item.lifecycle_status,
        "lifecycle_status": item.lifecycle_status,
        "status_reason": item.lifecycle_note,
        "lifecycle_note": item.lifecycle_note,
        "status_changed_at": item.lifecycle_changed_at,
        "lifecycle_changed_at": item.lifecycle_changed_at,
        "component_count": len(item.components),
        "components": components,
        "open_maintenance_case_count": open_cases,
        "physical_manual_included": item.physical_manual_included,
        "physical_manual_missing": item.physical_manual_missing,
        "checkin_card_missing": item.checkin_card_missing,
        "notes": item.notes,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def inventory_csv(
    db: Session,
    request: schemas.InventoryExportRequest,
) -> str:
    statement = select(models.LenderyItem).options(
        selectinload(models.LenderyItem.components),
        selectinload(models.LenderyItem.maintenance_cases),
    )
    if request.scope == "category":
        statement = statement.where(
            models.LenderyItem.category == request.category
        )
    elif request.scope == "item":
        statement = statement.where(models.LenderyItem.id == request.item_id)
    if not request.include_removed:
        statement = statement.where(
            models.LenderyItem.lifecycle_status != "removed"
        )
    items = list(db.scalars(statement.order_by(models.LenderyItem.id)))
    return _write_csv(
        request.fields,
        [_inventory_export_row(item) for item in items],
    )


def items_csv(db: Session) -> str:
    """Legacy default export retained for existing bookmarks and integrations."""
    statement = select(models.LenderyItem).options(
        selectinload(models.LenderyItem.components),
        selectinload(models.LenderyItem.maintenance_cases),
    )
    items = list(db.scalars(statement.order_by(models.LenderyItem.id)))
    fields = [
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
        "lifecycle_status",
        "lifecycle_note",
        "lifecycle_changed_at",
        "component_count",
        "open_maintenance_case_count",
        "physical_manual_included",
        "physical_manual_missing",
        "checkin_card_missing",
        "notes",
    ]
    return _write_csv(
        fields,
        [_inventory_export_row(item) for item in items],
    )


def list_item_activity(
    db: Session,
    *,
    item_id: int | None = None,
    category: str | None = None,
    offset: int = 0,
    limit: int = 500,
) -> list[models.ItemActivity]:
    statement = select(models.ItemActivity)
    if item_id is not None:
        statement = statement.where(
            models.ItemActivity.original_item_id == item_id
        )
    if category is not None:
        statement = statement.where(
            models.ItemActivity.item_category == category
        )
    statement = (
        statement.order_by(
            models.ItemActivity.occurred_at.desc(),
            models.ItemActivity.id.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


def _activity_export_row(activity: models.ItemActivity) -> dict[str, Any]:
    return {
        "event_id": activity.id,
        "occurred_at": activity.occurred_at,
        "event_type": activity.event_type,
        "event": ACTIVITY_EVENT_LABELS.get(
            activity.event_type, activity.event_type.replace("_", " ").title()
        ),
        "item_id": activity.original_item_id,
        "barcode": activity.item_barcode,
        "item_name": activity.item_name,
        "category": activity.item_category,
        "from_status": activity.from_status,
        "to_status": activity.to_status,
        "reason": activity.reason,
        "details": activity.details,
        "component": activity.component_name,
        "maintenance_case_id": activity.maintenance_case_id,
        "part_name": activity.part_name,
        "quantity": activity.quantity,
        "cost": activity.cost,
        "vendor_url": activity.vendor_url,
        "order_number": activity.order_number,
        "recorded_by": activity.actor_name,
    }


def activity_csv(
    db: Session,
    request: schemas.ActivityExportRequest,
) -> str:
    activities = list_item_activity(
        db,
        item_id=request.item_id if request.scope == "item" else None,
        category=request.category if request.scope == "category" else None,
        limit=100_000,
    )
    return _write_csv(
        request.fields,
        [_activity_export_row(activity) for activity in activities],
    )


def export_options(db: Session) -> schemas.ExportOptionsResponse:
    items = list(
        db.scalars(
            select(models.LenderyItem).order_by(
                models.LenderyItem.name,
                models.LenderyItem.barcode,
            )
        )
    )
    item_options = [
        schemas.ExportItemOption.model_validate(item, from_attributes=True)
        for item in items
    ]
    activity_options_by_id = {item.id: item for item in item_options}
    activities = list(
        db.scalars(
            select(models.ItemActivity).order_by(
                models.ItemActivity.occurred_at.desc(),
                models.ItemActivity.id.desc(),
            )
        )
    )
    for activity in activities:
        if activity.original_item_id in activity_options_by_id:
            continue
        activity_options_by_id[activity.original_item_id] = schemas.ExportItemOption(
            id=activity.original_item_id,
            name=activity.item_name,
            barcode=activity.item_barcode,
            category=activity.item_category,
            lifecycle_status="removed",
        )
    categories = sorted(
        {item.category for item in items if item.category},
        key=str.casefold,
    )
    activity_categories = sorted(
        {
            *(item.category for item in items if item.category),
            *(
                activity.item_category
                for activity in activities
                if activity.item_category
            ),
        },
        key=str.casefold,
    )
    return schemas.ExportOptionsResponse(
        inventory_fields=[
            schemas.ExportFieldDefinition(
                key=key,
                label=label,
                selected=key in INVENTORY_DEFAULT_FIELDS,
            )
            for key, label in INVENTORY_EXPORT_FIELDS.items()
        ],
        activity_fields=[
            schemas.ExportFieldDefinition(
                key=key,
                label=label,
                selected=key in ACTIVITY_DEFAULT_FIELDS,
            )
            for key, label in ACTIVITY_EXPORT_FIELDS.items()
        ],
        categories=categories,
        activity_categories=activity_categories,
        items=item_options,
        activity_items=sorted(
            activity_options_by_id.values(),
            key=lambda item: (item.name.casefold(), item.barcode.casefold()),
        ),
    )


def create_item(
    db: Session,
    item: schemas.LenderyItemCreate,
    *,
    actor_id: int,
    actor_name: str,
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
    db.flush()
    _record_activity(
        db,
        db_item,
        "item_added",
        actor_id=actor_id,
        actor_name=actor_name,
        to_status="active",
    )
    db_item = _commit(db, db_item)
    if db_item.library_url:
        db_item = refresh_item_availability(db, db_item)
    return db_item


def update_item(
    db: Session,
    item_id: int,
    changes: BaseModel | Mapping[str, Any],
    *,
    actor_id: int | None = None,
    actor_name: str | None = None,
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
    manual_was_missing = db_item.physical_manual_missing
    checkin_card_was_missing = db_item.checkin_card_missing
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
        "checkin_card_missing",
    ):
        if field in update_data:
            setattr(db_item, field, update_data[field])

    db_item.updated_at = datetime.now(timezone.utc)

    if library_url_changed:
        db_item.availability_status = "unknown"
        db_item.availability_status_version = (
            availability.AVAILABILITY_STATUS_VERSION
        )
        db_item.available_copies = None
        db_item.total_copies_at_branch = None
        db_item.availability_checked_at = None
        db_item.availability_error = None

    if (
        "physical_manual_missing" in update_data
        and db_item.physical_manual_missing != manual_was_missing
    ):
        _record_activity(
            db,
            db_item,
            "component_missing" if db_item.physical_manual_missing else "component_returned",
            actor_id=actor_id,
            actor_name=actor_name,
            reason="Physical manual was reported missing"
            if db_item.physical_manual_missing
            else "Physical manual was found",
            component_name="Physical manual",
        )

    if (
        "checkin_card_missing" in update_data
        and db_item.checkin_card_missing != checkin_card_was_missing
    ):
        _record_activity(
            db,
            db_item,
            "component_missing" if db_item.checkin_card_missing else "component_returned",
            actor_id=actor_id,
            actor_name=actor_name,
            reason="Check-in card was reported missing"
            if db_item.checkin_card_missing
            else "Check-in card was found",
            component_name="Check-in card",
        )

    db_item = _commit(db, db_item)
    if library_url_changed and db_item.library_url:
        db_item = refresh_item_availability(db, db_item)
    return db_item


def refresh_item_availability(
    db: Session,
    db_item: models.LenderyItem,
) -> models.LenderyItem:
    if not db_item.library_url or db_item.lifecycle_status != "active":
        return db_item

    checked_at = datetime.now(timezone.utc)
    try:
        result = availability.check_availability(
            db_item.library_url, db_item.barcode
        )
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
    reason: str,
    *,
    actor_id: int,
    actor_name: str,
) -> bool:
    db_item = get_item(db, item_id)
    if db_item is None:
        return False

    if db_item.lifecycle_status == "removed":
        return True
    previous_status = db_item.lifecycle_status
    db_item.lifecycle_status = "removed"
    db_item.lifecycle_changed_at = datetime.now(timezone.utc)
    db_item.lifecycle_note = reason
    _touch_item(db_item)
    _record_activity(
        db,
        db_item,
        "removed_from_collection",
        actor_id=actor_id,
        actor_name=actor_name,
        from_status=previous_status,
        to_status="removed",
        reason=reason,
    )
    _commit(db, db_item)
    return True


def mark_item_unavailable(
    db: Session,
    item_id: int,
    reason: str,
    *,
    actor_id: int,
    actor_name: str,
) -> models.LenderyItem | None:
    db_item = get_item(db, item_id)
    if db_item is None:
        return None
    if db_item.lifecycle_status == "removed":
        raise ValueError("Restore the item before marking it unavailable")
    if db_item.lifecycle_status == "unavailable":
        raise ValueError("Item is already marked unavailable")
    db_item.lifecycle_status = "unavailable"
    db_item.lifecycle_note = reason
    db_item.lifecycle_changed_at = datetime.now(timezone.utc)
    _touch_item(db_item)
    _record_activity(
        db,
        db_item,
        "marked_unavailable",
        actor_id=actor_id,
        actor_name=actor_name,
        from_status="active",
        to_status="unavailable",
        reason=reason,
    )
    return _commit(db, db_item)


def restore_item(
    db: Session,
    item_id: int,
    *,
    actor_id: int,
    actor_name: str,
    note: str | None = None,
) -> models.LenderyItem | None:
    db_item = get_item(db, item_id)
    if db_item is None:
        return None
    if db_item.lifecycle_status == "active":
        return db_item
    previous_status = db_item.lifecycle_status
    db_item.lifecycle_status = "active"
    db_item.lifecycle_changed_at = datetime.now(timezone.utc)
    db_item.lifecycle_note = None
    _touch_item(db_item)
    _record_activity(
        db,
        db_item,
        "returned_to_circulation",
        actor_id=actor_id,
        actor_name=actor_name,
        from_status=previous_status,
        to_status="active",
        reason=note,
    )
    return _commit(db, db_item)


def permanently_delete_item(
    db: Session,
    item_id: int,
    *,
    actor_id: int,
    actor_name: str,
) -> bool | None:
    db_item = get_item(db, item_id)
    if db_item is None:
        return None
    if db_item.lifecycle_status != "removed":
        return False

    component_ids = [component.id for component in db_item.components]
    try:
        _record_activity(
            db,
            db_item,
            "permanently_deleted",
            actor_id=actor_id,
            actor_name=actor_name,
            from_status="removed",
            reason="Inventory record permanently deleted; activity history retained",
        )
        db.flush()
        db.execute(
            update(models.ItemActivity)
            .where(models.ItemActivity.item_id == item_id)
            .values(item_id=None)
        )
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
    *,
    actor_id: int,
    actor_name: str,
) -> models.Component | None:
    db_item = get_item(db, item_id)
    if db_item is None:
        return None

    db_component = models.Component(
        item=db_item,
        **component.model_dump(mode="json"),
    )
    _touch_item(db_item)
    db.add(db_component)
    _record_activity(
        db,
        db_item,
        "component_added",
        actor_id=actor_id,
        actor_name=actor_name,
        component_name=db_component.name,
        quantity=db_component.quantity,
    )
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

    _touch_item(db_component.item)
    return _commit(db, db_component)


def report_component_missing(
    db: Session,
    component_id: int,
    *,
    note: str | None,
    actor_id: int,
    actor_name: str,
) -> models.Component | None:
    db_component = get_component(db, component_id)
    if db_component is None:
        return None

    db_component.missing_reported_at = datetime.now(timezone.utc)
    db_component.missing_reported_by = actor_name
    db_component.missing_note = note
    db_component.missing_ignored_at = None
    db_component.missing_ignored_by = None
    _touch_item(db_component.item)
    _record_activity(
        db,
        db_component.item,
        "component_missing",
        actor_id=actor_id,
        actor_name=actor_name,
        reason=note,
        component_name=db_component.name,
        quantity=db_component.quantity,
    )
    return _commit(db, db_component)


def resolve_component_missing(
    db: Session,
    component_id: int,
    *,
    resolution: str,
    actor_id: int,
    actor_name: str,
) -> models.Component | None:
    db_component = get_component(db, component_id)
    if db_component is None:
        return None

    db_component.missing_reported_at = None
    db_component.missing_reported_by = None

    if resolution == "ignored":
        db_component.missing_ignored_at = datetime.now(timezone.utc)
        db_component.missing_ignored_by = actor_name
    else:
        db_component.missing_note = None
        db_component.missing_ignored_at = None
        db_component.missing_ignored_by = None

    _touch_item(db_component.item)
    _record_activity(
        db,
        db_component.item,
        "component_report_ignored" if resolution == "ignored" else "component_returned",
        actor_id=actor_id,
        actor_name=actor_name,
        reason=db_component.missing_note if resolution == "ignored" else None,
        component_name=db_component.name,
        quantity=db_component.quantity,
    )
    return _commit(db, db_component)


def delete_component(
    db: Session,
    component_id: int,
    *,
    actor_id: int,
    actor_name: str,
) -> bool:
    db_component = get_component(db, component_id)
    if db_component is None:
        return False

    _touch_item(db_component.item)
    try:
        _record_activity(
            db,
            db_component.item,
            "component_removed",
            actor_id=actor_id,
            actor_name=actor_name,
            component_name=db_component.name,
            quantity=db_component.quantity,
        )
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
        .join(models.MaintenanceCase.item)
        .where(models.MaintenanceCase.status.in_(OPEN_MAINTENANCE_STATUSES))
        .where(models.LenderyItem.lifecycle_status != "removed")
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
    _touch_item(item)
    db.add(case)
    db.flush()
    _record_activity(
        db,
        item,
        "maintenance_opened",
        actor_id=actor_id,
        actor_name=actor_name,
        to_status=case.status,
        reason=case.title,
        details=case.description,
        component_name=case.component_name,
        maintenance_case_id=case.id,
        source_type="maintenance_case",
        source_id=case.id,
    )
    _commit(db, case)
    return get_maintenance_case(db, case.id)


def update_maintenance_case(
    db: Session,
    case_id: int,
    value: schemas.MaintenanceCaseUpdate,
    *,
    actor_id: int,
    actor_name: str,
) -> models.MaintenanceCase | None:
    case = get_maintenance_case(db, case_id)
    if case is None:
        return None
    update_data = value.model_dump(exclude_unset=True)
    previous_status = case.status
    for field in ("title", "description", "status"):
        if field in update_data:
            setattr(case, field, update_data[field])
    if "status" in update_data:
        case.resolved_at = (
            datetime.now(timezone.utc)
            if case.status in {"resolved", "cancelled"}
            else None
        )
    _touch_item(case.item)
    if "status" in update_data and case.status != previous_status:
        _record_activity(
            db,
            case.item,
            "maintenance_status_changed",
            actor_id=actor_id,
            actor_name=actor_name,
            from_status=previous_status,
            to_status=case.status,
            reason=case.title,
            component_name=case.component_name,
            maintenance_case_id=case.id,
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
    previous_status = case.status
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
    _touch_item(case.item)
    db.add(event)
    db.flush()
    _record_activity(
        db,
        case.item,
        event.event_type,
        actor_id=actor_id,
        actor_name=actor_name,
        from_status=previous_status if status_after != previous_status else None,
        to_status=status_after,
        reason=case.title,
        details=event.note,
        component_name=case.component_name,
        maintenance_case_id=case.id,
        part_name=event.part_name,
        quantity=event.quantity,
        cost=event.cost,
        vendor_url=event.vendor_url,
        order_number=event.order_number,
        source_type="maintenance_event",
        source_id=event.id,
    )
    _commit(db, event)
    return get_maintenance_case(db, case.id)
