import re
from datetime import datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)

AvailabilityStatus = Literal[
    "available",
    "checked_out",
    "unavailable",
    "not_held",
    "unknown",
]

LifecycleStatus = Literal["active", "broken", "retired", "removed"]

INTERNAL_COMPONENT_IMAGE_PATTERN = re.compile(
    r"/lendery/components/\d+/image"
)


def validate_image_url(value: str | HttpUrl | None) -> str | None:
    if value is None:
        return None
    normalized = str(value)
    if INTERNAL_COMPONENT_IMAGE_PATTERN.fullmatch(normalized):
        return normalized
    parsed = urlsplit(normalized)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return normalized
    raise ValueError("image_url must be an HTTP URL or a Lendery image path")


def validate_library_url(value: HttpUrl | None) -> HttpUrl | None:
    if value is None:
        return None

    parsed = urlsplit(str(value))
    if (
        parsed.scheme != "https"
        or parsed.hostname != "vaughanpl.bibliocommons.com"
    ):
        raise ValueError(
            "library_url must be an HTTPS Vaughan Public Libraries "
            "BiblioCommons record URL"
        )
    if not re.fullmatch(r"/v2/record/S130C\d+/?", parsed.path):
        raise ValueError(
            "library_url must point to a Vaughan BiblioCommons record"
        )
    return value


##Lendery Component Schemas##

class ComponentBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity:int = Field(default=1, ge=1)


    description: str | None = None
    image_url: str | None = None

    optional: bool = False
    check_in_notes: str | None = None

    @field_validator("image_url")
    @classmethod
    def image_url_must_be_safe(cls, value: str | None) -> str | None:
        return validate_image_url(value)


class ComponentCreate(ComponentBase):
    pass


class ComponentUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    quantity: int | None = Field(default=None, ge=1)
    description: str | None = None
    image_url: str | None = None
    optional: bool | None = None
    check_in_notes: str | None = None

    @field_validator("image_url")
    @classmethod
    def image_url_must_be_safe(cls, value: str | None) -> str | None:
        return validate_image_url(value)

    @field_validator("name", "quantity", "optional")
    @classmethod
    def required_values_cannot_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class ComponentResponse(ComponentBase):
    id: int
    missing_reported_at: datetime | None = None
    missing_reported_by: str | None = None
    missing_note: str | None = None
    missing_ignored_at: datetime | None = None
    missing_ignored_by: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ComponentMissingReport(BaseModel):
    note: str | None = Field(default=None, max_length=500)

##Lendery Item Schemas##


class LenderyItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None

    barcode: str = Field(min_length=1, max_length=50)

    notes: str | None = None

    purchase_price: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
    )

    purchase_url: HttpUrl | None = None

    manual_url: HttpUrl | None = None

    image_url: HttpUrl | None = None

    components: list[ComponentCreate] = Field(default_factory=list)

    category: str | None = None

    library_url: HttpUrl | None = None

    physical_manual_included: bool = False

    lifecycle_status: LifecycleStatus = "active"

    lifecycle_note: str | None = Field(default=None, max_length=1000)

    @field_validator("library_url")
    @classmethod
    def library_url_must_be_a_vaughan_record(
        cls,
        value: HttpUrl | None,
    ) -> HttpUrl | None:
        return validate_library_url(value)


class LenderyItemCreate(LenderyItemBase):
    pass


class LenderyItemUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    description: str | None = None
    barcode: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    notes: str | None = None
    purchase_price: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
    )
    purchase_url: HttpUrl | None = None
    manual_url: HttpUrl | None = None
    image_url: HttpUrl | None = None
    category: str | None = None
    library_url: HttpUrl | None = None
    physical_manual_included: bool | None = None
    physical_manual_missing: bool | None = None
    lifecycle_status: LifecycleStatus | None = None
    lifecycle_note: str | None = Field(default=None, max_length=1000)

    @field_validator(
        "name",
        "barcode",
        "physical_manual_included",
        "physical_manual_missing",
        "lifecycle_status",
    )
    @classmethod
    def required_values_cannot_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field cannot be null")
        return value

    @field_validator("library_url")
    @classmethod
    def library_url_must_be_a_vaughan_record(
        cls,
        value: HttpUrl | None,
    ) -> HttpUrl | None:
        return validate_library_url(value)


class LenderyItemResponse(LenderyItemBase):
    id: int
    components: list[ComponentResponse] = Field(default_factory=list)
    availability_status: AvailabilityStatus = "unknown"
    availability_status_version: int = 2
    available_copies: int | None = None
    total_copies_at_branch: int | None = None
    availability_checked_at: datetime | None = None
    availability_error: str | None = None
    physical_manual_missing: bool = False
    lifecycle_changed_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CatalogueItemImportRequest(BaseModel):
    library_url: HttpUrl

    @field_validator("library_url")
    @classmethod
    def library_url_must_be_a_vaughan_record(
        cls, value: HttpUrl
    ) -> HttpUrl:
        return validate_library_url(value)


class CatalogueItemImportResponse(BaseModel):
    name: str | None = None
    description: str | None = None
    image_url: HttpUrl | None = None
    manual_url: HttpUrl | None = None
    library_url: HttpUrl


MaintenanceStatus = Literal[
    "open",
    "waiting_for_part",
    "in_repair",
    "resolved",
    "cancelled",
]
MaintenanceEventType = Literal[
    "issue_update",
    "part_ordered",
    "part_received",
    "part_installed",
    "repair_completed",
]


class MaintenanceCaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    component_id: int | None = Field(default=None, ge=1)
    status: MaintenanceStatus = "open"


class MaintenanceCaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: MaintenanceStatus | None = None

    @field_validator("title", "status")
    @classmethod
    def required_values_cannot_be_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class MaintenanceEventCreate(BaseModel):
    event_type: MaintenanceEventType
    note: str | None = None
    part_name: str | None = Field(default=None, max_length=200)
    quantity: int | None = Field(default=None, ge=1)
    cost: Decimal | None = Field(default=None, ge=0, decimal_places=2)
    vendor_url: HttpUrl | None = None
    order_number: str | None = Field(default=None, max_length=100)
    new_status: MaintenanceStatus | None = None

    @model_validator(mode="after")
    def part_events_have_a_part(self):
        if self.event_type.startswith("part_") and not self.part_name:
            raise ValueError("Part name is required for part updates")
        if self.event_type == "issue_update" and not self.note:
            raise ValueError("Add a note describing the update")
        return self


class MaintenanceEventResponse(BaseModel):
    id: int
    event_type: MaintenanceEventType
    note: str | None = None
    part_name: str | None = None
    quantity: int | None = None
    cost: Decimal | None = None
    vendor_url: str | None = None
    order_number: str | None = None
    status_after: MaintenanceStatus | None = None
    created_by_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MaintenanceCaseResponse(BaseModel):
    id: int
    item_id: int
    component_id: int | None = None
    component_name: str | None = None
    title: str
    description: str | None = None
    status: MaintenanceStatus
    opened_by_name: str
    opened_at: datetime
    resolved_at: datetime | None = None
    events: list[MaintenanceEventResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class MaintenanceQueueEntry(BaseModel):
    id: int
    item_id: int
    item_name: str
    item_barcode: str
    component_id: int | None = None
    component_name: str | None = None
    title: str
    description: str | None = None
    status: MaintenanceStatus
    opened_by_name: str
    opened_at: datetime
