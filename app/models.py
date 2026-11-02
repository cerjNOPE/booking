from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.orm import relationship

from .database import Base


class Place(Base):
    __tablename__ = "places"

    id = Column(Integer, primary_key=True, index=True)
    capacity = Column(Integer, nullable=False)
    address = Column(String, nullable=False)
    isActive = Column(Boolean, default=True)
    # Имя файла в app/static/img, привязанное к месту; NULL — показать заглушку
    image_filename = Column(String(255), nullable=True)

    bookings = relationship("Booking", back_populates="place")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    fullName = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)

    bookingsList = relationship("Booking", back_populates="customer")
    api_keys = relationship("ApiKey", back_populates="customer")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "booking_number",
            name="uq_bookings_customer_number",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    place_id = Column(Integer, ForeignKey("places.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    # Номер брони внутри конкретного клиента: 1, 2, 3...
    booking_number = Column(Integer, nullable=False)
    checkIn = Column(Date, nullable=False)
    checkOut = Column(Date, nullable=False)
    guestsCount = Column(Integer, nullable=False)
    status = Column(String, nullable=False)

    place = relationship("Place", back_populates="bookings")
    customer = relationship("Customer", back_populates="bookingsList")


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        Index(
            "uq_api_keys_active_customer",
            "customer_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    # Первые символы ключа для показа пользователю
    key_prefix = Column(String(16), nullable=False)
    # В БД хранится только SHA-256 хэш полного ключа
    key_hash = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    customer = relationship("Customer", back_populates="api_keys")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class BookingCounter(Base):
    __tablename__ = "booking_counters"

    customer_id = Column(Integer, ForeignKey("customers.id"), primary_key=True)
    last_number = Column(Integer, nullable=False, default=0)
