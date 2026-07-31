from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
)

##Lendery Component Schemas##

class ComponentBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity:int = Field(default=1, ge=1)


    description: str | None = None
    image_url: HttpUrl | None = None

    optional: bool = False
    check_in_notes: str | None = None


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
    image_url: HttpUrl | None = None
    optional: bool | None = None
    check_in_notes: str | None = None

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

    @field_validator("name", "barcode")
    @classmethod
    def required_values_cannot_be_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("field cannot be null")
        return value


class LenderyItemResponse(LenderyItemBase):
    id: int
    components: list[ComponentResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
