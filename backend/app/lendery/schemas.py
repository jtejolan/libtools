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
)

AvailabilityStatus = Literal[
    "available",
    "checked_out",
    "unavailable",
    "not_held",
    "unknown",
]

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

    @field_validator("name", "barcode")
    @classmethod
    def required_values_cannot_be_null(cls, value: str | None) -> str:
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

    model_config = ConfigDict(from_attributes=True)
