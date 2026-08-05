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

LifecycleStatus = Literal["active", "unavailable", "removed"]

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


class PublicComponentResponse(BaseModel):
    """Narrow, hand-picked component fields safe for anonymous visitors.

    Deliberately excludes id and every missing_*/check_in_notes field —
    those are staff workflow state, not patron-facing information.
    """

    name: str
    quantity: int
    description: str | None = None
    image_url: str | None = None
    optional: bool = False

    model_config = ConfigDict(from_attributes=True)

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
    checkin_card_missing: bool | None = None

    @field_validator(
        "name",
        "barcode",
        "physical_manual_included",
        "physical_manual_missing",
        "checkin_card_missing",
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
    checkin_card_missing: bool = False
    lifecycle_status: LifecycleStatus = "active"
    lifecycle_note: str | None = None
    lifecycle_changed_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PublicLenderyItemResponse(BaseModel):
    """Narrow, hand-picked item fields safe for anonymous visitors.

    Deliberately excludes id, notes, purchase_price, purchase_url,
    lifecycle_note, availability_error, and everything catalogue/
    availability-related — those are staff-only or not relevant to a
    visitor who already has the physical item in hand.
    """

    name: str
    description: str | None = None
    barcode: str
    image_url: str | None = None
    category: str | None = None
    manual_url: str | None = None
    physical_manual_included: bool = False
    components: list[PublicComponentResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class LenderyItemRemoval(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_cannot_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("removal reason cannot be blank")
        return value


class LenderyItemUnavailable(LenderyItemRemoval):
    pass


class LenderyItemReturn(BaseModel):
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


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
    barcode: str | None = None


class ItemSuggestionCreate(BaseModel):
    item_name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    category: str | None = Field(default=None, max_length=100)
    product_url: HttpUrl | None = None
    additional_notes: str | None = Field(default=None, max_length=4000)
    submission_key: str = Field(
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )

    @field_validator("item_name", "description")
    @classmethod
    def required_text_cannot_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field cannot be blank")
        return cleaned

    @field_validator("category", "additional_notes")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class ItemSuggestionResponse(BaseModel):
    id: int
    item_name: str
    description: str
    category: str | None = None
    product_url: str | None = None
    additional_notes: str | None = None
    submitted_by_name: str
    submitted_at: datetime

    model_config = ConfigDict(from_attributes=True)


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


ItemActivityType = Literal[
    "item_added",
    "marked_unavailable",
    "returned_to_circulation",
    "removed_from_collection",
    "permanently_deleted",
    "maintenance_opened",
    "maintenance_status_changed",
    "issue_update",
    "part_ordered",
    "part_received",
    "part_installed",
    "repair_completed",
    "component_added",
    "component_removed",
    "component_missing",
    "component_returned",
    "component_report_ignored",
]


class ItemActivityResponse(BaseModel):
    id: int
    original_item_id: int
    item_id: int | None = None
    item_barcode: str
    item_name: str
    item_category: str | None = None
    event_type: ItemActivityType
    from_status: str | None = None
    to_status: str | None = None
    reason: str | None = None
    details: str | None = None
    component_name: str | None = None
    maintenance_case_id: int | None = None
    part_name: str | None = None
    quantity: int | None = None
    cost: Decimal | None = None
    vendor_url: str | None = None
    order_number: str | None = None
    actor_name: str | None = None
    occurred_at: datetime

    model_config = ConfigDict(from_attributes=True)


ExportScope = Literal["all", "category", "item"]

INVENTORY_EXPORT_FIELD_KEYS = {
    "id",
    "barcode",
    "name",
    "category",
    "description",
    "purchase_price",
    "purchase_url",
    "manual_url",
    "image_url",
    "library_url",
    "catalogue_availability",
    "availability_checked_at",
    "circulation_status",
    "status_reason",
    "status_changed_at",
    "component_count",
    "components",
    "open_maintenance_case_count",
    "physical_manual_included",
    "physical_manual_missing",
    "checkin_card_missing",
    "notes",
    "created_at",
    "updated_at",
}

ACTIVITY_EXPORT_FIELD_KEYS = {
    "event_id",
    "occurred_at",
    "event_type",
    "event",
    "item_id",
    "barcode",
    "item_name",
    "category",
    "from_status",
    "to_status",
    "reason",
    "details",
    "component",
    "maintenance_case_id",
    "part_name",
    "quantity",
    "cost",
    "vendor_url",
    "order_number",
    "recorded_by",
}


class ExportRequestBase(BaseModel):
    fields: list[str] = Field(min_length=1, max_length=30)
    scope: ExportScope = "all"
    category: str | None = Field(default=None, max_length=100)
    item_id: int | None = Field(default=None, ge=1)

    @field_validator("fields")
    @classmethod
    def fields_are_unique(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def scope_has_filter(self):
        if self.scope == "category" and not (self.category or "").strip():
            raise ValueError("Choose a category for this export")
        if self.scope == "item" and self.item_id is None:
            raise ValueError("Choose an item for this export")
        if self.category is not None:
            self.category = self.category.strip() or None
        return self


class InventoryExportRequest(ExportRequestBase):
    include_removed: bool = True

    @field_validator("fields")
    @classmethod
    def fields_are_inventory_fields(cls, value: list[str]) -> list[str]:
        unknown = set(value) - INVENTORY_EXPORT_FIELD_KEYS
        if unknown:
            raise ValueError(f"Unknown inventory field: {sorted(unknown)[0]}")
        return value


class ActivityExportRequest(ExportRequestBase):
    @field_validator("fields")
    @classmethod
    def fields_are_activity_fields(cls, value: list[str]) -> list[str]:
        unknown = set(value) - ACTIVITY_EXPORT_FIELD_KEYS
        if unknown:
            raise ValueError(f"Unknown history field: {sorted(unknown)[0]}")
        return value


class ExportFieldDefinition(BaseModel):
    key: str
    label: str
    selected: bool = False


class ExportItemOption(BaseModel):
    id: int
    name: str
    barcode: str
    category: str | None = None
    lifecycle_status: LifecycleStatus


class ExportOptionsResponse(BaseModel):
    inventory_fields: list[ExportFieldDefinition]
    activity_fields: list[ExportFieldDefinition]
    categories: list[str]
    activity_categories: list[str]
    items: list[ExportItemOption]
    activity_items: list[ExportItemOption]
