from pydantic import BaseModel, Field, HttpUrl, ConfigDict
from decimal import Decimal

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

class ComponentResponse(ComponentBase):
    id: int
    components: list[ComponentResponse]
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

    components: list[ComponentCreate] = Field(default_factory=list)

    category: str | None = None

class LenderyItemCreate(LenderyItemBase):
    pass

class LenderyItemResponse(LenderyItemBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)
