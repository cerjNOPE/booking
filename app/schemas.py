from datetime import date

from pydantic import BaseModel, ConfigDict


class PlaceBase(BaseModel):
    capacity: int
    address: str
    isActive: bool = True


class PlaceCreate(PlaceBase):
    pass


class Place(PlaceBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class CustomerCreate(BaseModel):
    """Данные для регистрации. Номер клиента присваивается автоматически."""

    fullName: str
    phone: str
    email: str
    password: str


class Customer(BaseModel):
    id: int
    fullName: str
    phone: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class BookingBase(BaseModel):
    place_id: int
    customer_id: int
    checkIn: date
    checkOut: date
    guestsCount: int
    status: str = "active"


class BookingCreate(BookingBase):
    """Внутренняя схема для crud. customer_id подставляется сервером."""

    pass


class Booking(BookingBase):
    id: int
    booking_number: int

    model_config = ConfigDict(from_attributes=True)


# ---------- Публичный API ----------

class BookingCreateAPI(BaseModel):
    """Создание брони через API. Владелец определяется по API-ключу."""

    place_id: int
    checkIn: date
    checkOut: date
    guestsCount: int


class BookingStatusResponse(BaseModel):
    id: int
    booking_number: int
    place_id: int
    checkIn: date
    checkOut: date
    guestsCount: int
    status: str

    model_config = ConfigDict(from_attributes=True)


class AvailabilityResponse(BaseModel):
    place_id: int
    check_in: date
    check_out: date
    free: bool


class PlacePublic(BaseModel):
    """Публичная информация о месте."""

    id: int
    address: str
    isActive: bool

    model_config = ConfigDict(from_attributes=True)
