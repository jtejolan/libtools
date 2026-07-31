from collections.abc import Generator
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal
from lendery import crud, schemas


router = APIRouter(
    prefix="/lendery",
    tags=["lendery"],
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DatabaseSession = Annotated[Session, Depends(get_db)]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]
AvailabilityFilter = Literal[
    "in",
    "out",
    "available",
    "checked_out",
    "unavailable",
    "not_held",
    "unknown",
]


@router.post(
    "/items",
    response_model=schemas.LenderyItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_item(
    item: schemas.LenderyItemCreate,
    db: DatabaseSession,
):
    try:
        return crud.create_item(db, item)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An item with this barcode already exists",
        ) from exc


@router.get(
    "/items",
    response_model=list[schemas.LenderyItemResponse],
)
def list_items(
    db: DatabaseSession,
    offset: Offset = 0,
    limit: Limit = 100,
    availability: AvailabilityFilter | None = None,
):
    status_filter = {
        "in": "available",
        "out": "checked_out",
    }.get(availability, availability)
    return crud.list_items(
        db,
        offset=offset,
        limit=limit,
        availability_status=status_filter,
    )


@router.get(
    "/items/barcode/{barcode}",
    response_model=schemas.LenderyItemResponse,
)
def get_item_by_barcode(
    barcode: str,
    db: DatabaseSession,
):
    item = crud.get_item_by_barcode(db, barcode)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return crud.refresh_item_availability(db, item)


@router.get(
    "/items/{item_id}",
    response_model=schemas.LenderyItemResponse,
)
def get_item(
    item_id: int,
    db: DatabaseSession,
):
    item = crud.get_item(db, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return crud.refresh_item_availability(db, item)


@router.post(
    "/items/{item_id}/availability/refresh",
    response_model=schemas.LenderyItemResponse,
)
def refresh_item_availability(
    item_id: int,
    db: DatabaseSession,
):
    item = crud.get_item(db, item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return crud.refresh_item_availability(db, item)


@router.patch(
    "/items/{item_id}",
    response_model=schemas.LenderyItemResponse,
)
def update_item(
    item_id: int,
    changes: schemas.LenderyItemUpdate,
    db: DatabaseSession,
):
    try:
        item = crud.update_item(db, item_id, changes)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An item with this barcode already exists",
        ) from exc
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return item


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_item(
    item_id: int,
    db: DatabaseSession,
) -> Response:
    if not crud.delete_item(db, item_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/items/{item_id}/components",
    response_model=schemas.ComponentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_component(
    item_id: int,
    component: schemas.ComponentCreate,
    db: DatabaseSession,
):
    db_component = crud.create_component(db, item_id, component)
    if db_component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return db_component


@router.get(
    "/items/{item_id}/components",
    response_model=list[schemas.ComponentResponse],
)
def list_item_components(
    item_id: int,
    db: DatabaseSession,
    offset: Offset = 0,
    limit: Limit = 100,
):
    if crud.get_item(db, item_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return crud.list_components(
        db,
        item_id=item_id,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/components",
    response_model=list[schemas.ComponentResponse],
)
def list_components(
    db: DatabaseSession,
    offset: Offset = 0,
    limit: Limit = 100,
):
    return crud.list_components(db, offset=offset, limit=limit)


@router.get(
    "/components/{component_id}",
    response_model=schemas.ComponentResponse,
)
def get_component(
    component_id: int,
    db: DatabaseSession,
):
    component = crud.get_component(db, component_id)
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found",
        )
    return component


@router.patch(
    "/components/{component_id}",
    response_model=schemas.ComponentResponse,
)
def update_component(
    component_id: int,
    changes: schemas.ComponentUpdate,
    db: DatabaseSession,
):
    component = crud.update_component(db, component_id, changes)
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found",
        )
    return component


@router.delete(
    "/components/{component_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_component(
    component_id: int,
    db: DatabaseSession,
) -> Response:
    if not crud.delete_component(db, component_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
