from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError

from dependencies import DatabaseSession, get_db
from accounts.auth import require_lendery_manage, require_lendery_view
from bookclub.catalogue import CatalogueImportError
from lendery import catalogue, component_images, crud, schemas


router = APIRouter(
    prefix="/lendery",
    tags=["lendery"],
    dependencies=[Depends(require_lendery_view)],
)

Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]
AvailabilityFilter = Literal[
    "in",
    "out",
    "available",
    "checked_out",
    "unavailable",
]


@router.post(
    "/items",
    response_model=schemas.LenderyItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_item(
    item: schemas.LenderyItemCreate,
    db: DatabaseSession,
    _manager=Depends(require_lendery_manage),
):
    try:
        return crud.create_item(db, item)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An item with this barcode already exists",
        ) from exc


@router.post(
    "/items/import",
    response_model=schemas.CatalogueItemImportResponse,
)
def import_item(
    value: schemas.CatalogueItemImportRequest,
    _manager=Depends(require_lendery_manage),
):
    try:
        return catalogue.fetch_catalogue_item(str(value.library_url))
    except CatalogueImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
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
    "/items/export.csv",
    include_in_schema=False,
)
def export_items_csv(
    db: DatabaseSession,
    _manager=Depends(require_lendery_manage),
) -> Response:
    return Response(
        content=crud.items_csv(db),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="lendery-inventory.csv"',
        },
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
    _manager=Depends(require_lendery_manage),
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
    _manager=Depends(require_lendery_manage),
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
    _manager=Depends(require_lendery_manage),
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
    _manager=Depends(require_lendery_manage),
):
    component = crud.update_component(db, component_id, changes)
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found",
        )
    return component


@router.get(
    "/components/{component_id}/image",
    include_in_schema=False,
)
def get_component_image(
    component_id: int,
    db: DatabaseSession,
):
    component = crud.get_component(db, component_id)
    path = component_images.component_image_path(component_id)
    if component is None or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component photo not found",
        )
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "private, no-store"},
    )


@router.post(
    "/components/{component_id}/image",
    response_model=schemas.ComponentResponse,
)
async def upload_component_image(
    component_id: int,
    db: DatabaseSession,
    image: UploadFile = File(...),
    _manager=Depends(require_lendery_manage),
):
    component = crud.get_component(db, component_id)
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found",
        )
    try:
        await component_images.save_component_image(component_id, image)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return crud.update_component(
        db,
        component_id,
        {"image_url": component_images.component_image_url(component_id)},
    )


@router.delete(
    "/components/{component_id}/image",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_component_image(
    component_id: int,
    db: DatabaseSession,
    _manager=Depends(require_lendery_manage),
) -> Response:
    component = crud.get_component(db, component_id)
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found",
        )
    crud.update_component(db, component_id, {"image_url": None})
    component_images.delete_component_image(component_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/components/{component_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_component(
    component_id: int,
    db: DatabaseSession,
    _manager=Depends(require_lendery_manage),
) -> Response:
    if not crud.delete_component(db, component_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found",
        )
    component_images.delete_component_image(component_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/components/{component_id}/missing-report",
    response_model=schemas.ComponentResponse,
)
def report_component_missing(
    component_id: int,
    value: schemas.ComponentMissingReport,
    db: DatabaseSession,
    viewer=Depends(require_lendery_view),
):
    component = crud.report_component_missing(
        db,
        component_id,
        note=value.note,
        reported_by=viewer.username,
    )
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found",
        )
    return component


@router.delete(
    "/components/{component_id}/missing-report",
    response_model=schemas.ComponentResponse,
)
def resolve_component_missing(
    component_id: int,
    db: DatabaseSession,
    manager=Depends(require_lendery_manage),
    resolution: Literal["resolved", "ignored"] = "resolved",
):
    component = crud.resolve_component_missing(
        db,
        component_id,
        resolution=resolution,
        resolved_by=manager.username,
    )
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Component not found",
        )
    return component


@router.get(
    "/maintenance",
    response_model=list[schemas.MaintenanceQueueEntry],
)
def list_maintenance_queue(
    db: DatabaseSession,
    _editor=Depends(require_lendery_manage),
):
    return [
        schemas.MaintenanceQueueEntry(
            id=case.id,
            item_id=case.item_id,
            item_name=case.item.name,
            item_barcode=case.item.barcode,
            component_id=case.component_id,
            component_name=case.component_name,
            title=case.title,
            description=case.description,
            status=case.status,
            opened_by_name=case.opened_by_name,
            opened_at=case.opened_at,
        )
        for case in crud.list_open_maintenance_cases(db)
    ]


@router.get(
    "/items/{item_id}/maintenance",
    response_model=list[schemas.MaintenanceCaseResponse],
)
def list_maintenance_cases(
    item_id: int,
    db: DatabaseSession,
    _editor=Depends(require_lendery_manage),
):
    cases = crud.list_maintenance_cases(db, item_id)
    if cases is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return cases


@router.post(
    "/items/{item_id}/maintenance",
    response_model=schemas.MaintenanceCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_maintenance_case(
    item_id: int,
    value: schemas.MaintenanceCaseCreate,
    db: DatabaseSession,
    editor=Depends(require_lendery_manage),
):
    try:
        case = crud.create_maintenance_case(
            db,
            item_id,
            value,
            actor_id=editor.id,
            actor_name=editor.username,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found",
        )
    return case


@router.patch(
    "/maintenance/{case_id}",
    response_model=schemas.MaintenanceCaseResponse,
)
def update_maintenance_case(
    case_id: int,
    value: schemas.MaintenanceCaseUpdate,
    db: DatabaseSession,
    _editor=Depends(require_lendery_manage),
):
    case = crud.update_maintenance_case(db, case_id, value)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance case not found",
        )
    return case


@router.post(
    "/maintenance/{case_id}/events",
    response_model=schemas.MaintenanceCaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_maintenance_event(
    case_id: int,
    value: schemas.MaintenanceEventCreate,
    db: DatabaseSession,
    editor=Depends(require_lendery_manage),
):
    case = crud.add_maintenance_event(
        db,
        case_id,
        value,
        actor_id=editor.id,
        actor_name=editor.username,
    )
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance case not found",
        )
    return case
