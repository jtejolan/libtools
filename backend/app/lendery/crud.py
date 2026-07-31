from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from lendery import models, schemas


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
) -> list[models.LenderyItem]:
    statement = (
        select(models.LenderyItem)
        .order_by(models.LenderyItem.id)
        .offset(offset)
        .limit(limit)
    )
    return list(db.scalars(statement))


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
    return _commit(db, db_item)


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
    ):
        if field in update_data:
            setattr(db_item, field, update_data[field])

    return _commit(db, db_item)


def delete_item(
    db: Session,
    item_id: int,
) -> bool:
    db_item = get_item(db, item_id)
    if db_item is None:
        return False

    try:
        db.delete(db_item)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
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
