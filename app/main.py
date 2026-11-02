import logging
from datetime import date, datetime
from typing import List

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Security
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import engine, get_db
from .i18n import translate
from .images import place_image
from .security import (
    detect_login_identifier,
    format_phone_display,
    is_valid_email,
    is_valid_password,
    is_valid_phone,
    is_valid_surname,
    md5_hash,
    normalize_phone,
    sha256_hash,
)

models.Base.metadata.create_all(bind=engine)

logger = logging.getLogger("booking")

app = FastAPI(
    title="Booking API",
    description=(
        "API бронирования мест в кемпинге.\n\n"
        "Доступность места и список мест можно смотреть без ключа. "
        "Создание брони, просмотр своих броней, статус и отмена доступны только по "
        "персональному API-ключу в заголовке `X-API-Key`. Ключ выдаётся в настройках "
        "после входа."
    ),
    version="1.0.0",
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["place_image"] = place_image

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

CONTACTS = {
    "email": "camping@example.com",
    "phone": "+7 (900) 000-00-00",
}


# ---------- Помощники ----------

def get_lang(request: Request) -> str:
    lang = request.cookies.get("lang", "ru")
    return lang if lang in ("ru", "en") else "ru"


def tr(request: Request, key: str, **kwargs) -> str:
    return translate(get_lang(request), key, **kwargs)


def render(request: Request, template: str, context: dict | None = None, status_code: int = 200):
    lang = get_lang(request)
    ctx = {
        "t": lambda key, **kwargs: translate(lang, key, **kwargs),
        "lang": lang,
        "contacts": CONTACTS,
    }
    ctx.update(context or {})
    return templates.TemplateResponse(request, template, ctx, status_code=status_code)


def get_current_customer(request: Request, db: Session):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return None
    try:
        customer_id = int(user_id)
    except (TypeError, ValueError):
        return None
    return crud.get_customer(db, customer_id)


def login_context(**values):
    return {
        "identifier": values.get("identifier", ""),
        "password": values.get("password", ""),
        "error": values.get("error"),
        "invalid": values.get("invalid"),
        "not_found": values.get("not_found", False),
        "reset_done": values.get("reset_done", False),
    }


def register_context(**values):
    return {
        "surname": values.get("surname", ""),
        "phone": values.get("phone", ""),
        "email": values.get("email", ""),
        "password": values.get("password", ""),
        "error": values.get("error"),
        "invalid": values.get("invalid"),
        "offer_login": values.get("offer_login", False),
    }


def forgot_context(**values):
    return {
        "identifier": values.get("identifier", ""),
        "new_password": values.get("new_password", ""),
        "confirm": values.get("confirm", ""),
        "error": values.get("error"),
        "invalid": values.get("invalid"),
    }


def login_identifier_display(identifier: str) -> str:
    kind, value = detect_login_identifier(identifier)
    if kind == "phone":
        return format_phone_display(value)
    return identifier


def settings_context(db: Session, customer, **values):
    return {
        "customer": customer,
        "api_keys": crud.get_api_keys_by_customer(db, customer.id),
        "surname": values.get("surname", customer.fullName),
        "phone": values.get("phone", format_phone_display(customer.phone)),
        "email": values.get("email", customer.email),
        "profile_error": values.get("profile_error"),
        "profile_invalid": values.get("profile_invalid"),
        "password_error": values.get("password_error"),
        "password_invalid": values.get("password_invalid"),
        "new_key": values.get("new_key"),
        "key_error": values.get("key_error"),
        "saved": values.get("saved", False),
        "password_changed": values.get("password_changed", False),
    }


def booking_context(db: Session, customer, **values):
    places = crud.get_active_places(db)
    selected = values.get("selected")
    if selected is None:
        selected = places[0] if places else None
    return {
        "places": places,
        "selected": selected,
        "capacity": selected.capacity if selected else 0,
        "check_in": values.get("check_in", ""),
        "check_out": values.get("check_out", ""),
        "guests": values.get("guests", 1),
        "today": date.today().isoformat(),
        "error": values.get("error"),
    }


def get_own_booking_web(db: Session, booking_id: int, customer):
    booking = crud.get_booking(db, booking_id)
    if booking is None or booking.customer_id != customer.id:
        return None
    return booking


def status_label(request: Request, status: str) -> str:
    return tr(request, f"status.{status}")


# ---------- Язык ----------

@app.get("/lang/{lang}", include_in_schema=False)
def set_language(lang: str, request: Request):
    if lang not in ("ru", "en"):
        lang = "ru"
    target = request.headers.get("referer") or "/"
    response = RedirectResponse(url=target, status_code=303)
    response.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax")
    return response


# ---------- Вход / регистрация / восстановление пароля ----------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def read_root(request: Request, db: Session = Depends(get_db)):
    customer = get_current_customer(request, db)
    if customer is None:
        return render(
            request,
            "login.html",
            login_context(
                reset_done=request.query_params.get("reset") == "1",
            ),
        )
    return render(
        request,
        "home.html",
        {
            "customer": customer,
            "places": crud.get_places(db, skip=0, limit=1000),
        },
    )


@app.get("/register", response_class=HTMLResponse, include_in_schema=False)
def register_page(request: Request, db: Session = Depends(get_db)):
    if get_current_customer(request, db) is not None:
        return RedirectResponse(url="/", status_code=303)
    return render(request, "register.html", register_context())


@app.post("/web/register", response_class=HTMLResponse, include_in_schema=False)
def web_register(
    request: Request,
    surname: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    surname = surname.strip()
    phone_input = phone.strip()
    phone_value = normalize_phone(phone_input)
    email_value = email.strip().lower()
    phone_display = format_phone_display(phone_input)

    if not surname:
        return render(
            request,
            "register.html",
            register_context(
                surname=surname,
                phone=phone_display,
                email=email,
                password=password,
                error=tr(request, "error.surname_empty"),
                invalid="surname",
            ),
            status_code=400,
        )
    if not phone_value:
        return render(
            request,
            "register.html",
            register_context(
                surname=surname,
                phone="",
                email=email,
                password=password,
                error=tr(request, "error.phone_empty"),
                invalid="phone",
            ),
            status_code=400,
        )
    if not email_value:
        return render(
            request,
            "register.html",
            register_context(
                surname=surname,
                phone=phone_display,
                email="",
                password=password,
                error=tr(request, "error.email_empty"),
                invalid="email",
            ),
            status_code=400,
        )
    if not password:
        return render(
            request,
            "register.html",
            register_context(
                surname=surname,
                phone=phone_display,
                email=email,
                password="",
                error=tr(request, "error.password_empty"),
                invalid="password",
            ),
            status_code=400,
        )

    if not is_valid_surname(surname):
        return render(
            request,
            "register.html",
            register_context(
                surname=surname,
                phone=phone_display,
                email=email,
                password=password,
                error=tr(request, "error.surname_invalid"),
                invalid="surname",
            ),
            status_code=400,
        )
    if not is_valid_phone(phone_value):
        return render(
            request,
            "register.html",
            register_context(
                surname=surname,
                phone=phone_display,
                email=email,
                password=password,
                error=tr(request, "error.phone_invalid"),
                invalid="phone",
            ),
            status_code=400,
        )
    if not is_valid_email(email_value):
        return render(
            request,
            "register.html",
            register_context(
                surname=surname,
                phone=phone_display,
                email=email,
                password=password,
                error=tr(request, "error.email_invalid"),
                invalid="email",
            ),
            status_code=400,
        )
    if not is_valid_password(password):
        return render(
            request,
            "register.html",
            register_context(
                surname=surname,
                phone=phone_display,
                email=email,
                password=password,
                error=tr(request, "error.password_weak"),
                invalid="password",
            ),
            status_code=400,
        )
    if crud.get_customer_by_phone(db, phone_value) is not None:
        return render(
            request,
            "register.html",
            register_context(
                surname=surname,
                phone=phone_display,
                email=email,
                password=password,
                error=tr(request, "error.phone_taken"),
                invalid="phone",
                offer_login=True,
            ),
            status_code=400,
        )
    if crud.get_customer_by_email(db, email_value) is not None:
        return render(
            request,
            "register.html",
            register_context(
                surname=surname,
                phone=phone_display,
                email=email,
                password=password,
                error=tr(request, "error.email_taken"),
                invalid="email",
                offer_login=True,
            ),
            status_code=400,
        )

    customer = crud.create_customer(
        db,
        schemas.CustomerCreate(
            fullName=surname,
            phone=phone_value,
            email=email_value,
            password=password,
        ),
    )
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("user_id", str(customer.id), httponly=True, samesite="lax")
    return response


@app.get("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
def forgot_password_page(request: Request):
    return render(request, "forgot_password.html", forgot_context())


@app.post("/web/forgot-password", response_class=HTMLResponse, include_in_schema=False)
def forgot_password(
    request: Request,
    identifier: str = Form(""),
    new_password: str = Form(""),
    confirm: str = Form(""),
    db: Session = Depends(get_db),
):
    if not identifier.strip():
        return render(
            request,
            "forgot_password.html",
            forgot_context(
                identifier=identifier,
                error=tr(request, "error.identifier_empty"),
                invalid="identifier",
            ),
            status_code=400,
        )

    kind, value = detect_login_identifier(identifier)
    if kind is None:
        return render(
            request,
            "forgot_password.html",
            forgot_context(
                identifier=identifier,
                error=tr(request, "error.identifier_invalid"),
                invalid="identifier",
            ),
            status_code=400,
        )

    customer = crud.get_customer_by_login(db, value, kind)
    if customer is None:
        return render(
            request,
            "forgot_password.html",
            forgot_context(
                identifier=identifier,
                error=tr(request, "error.user_not_found"),
                invalid="identifier",
            ),
            status_code=404,
        )

    if not new_password:
        return render(
            request,
            "forgot_password.html",
            forgot_context(
                identifier=identifier,
                error=tr(request, "error.password_empty"),
                invalid="new_password",
            ),
            status_code=400,
        )
    if not is_valid_password(new_password):
        return render(
            request,
            "forgot_password.html",
            forgot_context(
                identifier=identifier,
                new_password=new_password,
                confirm=confirm,
                error=tr(request, "error.password_weak"),
                invalid="new_password",
            ),
            status_code=400,
        )
    if new_password != confirm:
        return render(
            request,
            "forgot_password.html",
            forgot_context(
                identifier=identifier,
                new_password=new_password,
                confirm=confirm,
                error=tr(request, "error.password_mismatch"),
                invalid="confirm",
            ),
            status_code=400,
        )

    crud.update_customer_password(db, customer, new_password)
    return RedirectResponse(url="/?reset=1", status_code=303)


@app.post("/web/login", response_class=HTMLResponse, include_in_schema=False)
def web_login(
    request: Request,
    identifier: str = Form(""),
    password: str = Form(""),
    db: Session = Depends(get_db),
):
    if not identifier.strip():
        return render(
            request,
            "login.html",
            login_context(
                identifier="",
                password=password,
                error=tr(request, "error.identifier_empty"),
                invalid="identifier",
            ),
            status_code=400,
        )
    if not password:
        return render(
            request,
            "login.html",
            login_context(
                identifier=login_identifier_display(identifier),
                password="",
                error=tr(request, "error.password_empty"),
                invalid="password",
            ),
            status_code=400,
        )

    kind, value = detect_login_identifier(identifier)
    if kind is None:
        return render(
            request,
            "login.html",
            login_context(
                identifier=identifier,
                password=password,
                error=tr(request, "error.identifier_invalid"),
                invalid="identifier",
            ),
            status_code=400,
        )

    customer = crud.get_customer_by_login(db, value, kind)
    if customer is None:
        return render(
            request,
            "login.html",
            login_context(
                identifier=login_identifier_display(identifier),
                password=password,
                error=tr(request, "error.user_not_found"),
                invalid="identifier",
                not_found=True,
            ),
            status_code=404,
        )

    if customer.password_hash != md5_hash(password):
        return render(
            request,
            "login.html",
            login_context(
                identifier=login_identifier_display(identifier),
                password=password,
                error=tr(request, "error.wrong_password"),
                invalid="password",
            ),
            status_code=400,
        )

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("user_id", str(customer.id), httponly=True, samesite="lax")
    return response


@app.get("/logout", include_in_schema=False)
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_id")
    return response


# ---------- Настройки ----------

@app.get("/settings", response_class=HTMLResponse, include_in_schema=False)
def settings_page(request: Request, db: Session = Depends(get_db)):
    customer = get_current_customer(request, db)
    if customer is None:
        return RedirectResponse(url="/", status_code=303)
    return render(
        request,
        "settings.html",
        settings_context(
            db,
            customer,
            saved=request.query_params.get("saved") == "1",
            password_changed=request.query_params.get("password_changed") == "1",
        ),
    )


@app.post("/web/settings/profile", response_class=HTMLResponse, include_in_schema=False)
def update_profile(
    request: Request,
    surname: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(get_db),
):
    customer = get_current_customer(request, db)
    if customer is None:
        return RedirectResponse(url="/", status_code=303)

    surname = surname.strip()
    phone_input = phone.strip()
    phone_value = normalize_phone(phone_input)
    email_value = email.strip().lower()
    phone_display = format_phone_display(phone_input)

    def fail(key: str, field: str):
        return render(
            request,
            "settings.html",
            settings_context(
                db,
                customer,
                surname=surname,
                phone=phone_display,
                email=email,
                profile_error=tr(request, key),
                profile_invalid=field,
            ),
            status_code=400,
        )

    if not surname:
        return fail("error.surname_empty", "surname")
    if not phone_value:
        return fail("error.phone_empty", "phone")
    if not email_value:
        return fail("error.email_empty", "email")
    if not is_valid_surname(surname):
        return fail("error.surname_invalid", "surname")
    if not is_valid_phone(phone_value):
        return fail("error.phone_invalid", "phone")
    if not is_valid_email(email_value):
        return fail("error.email_invalid", "email")

    phone_owner = crud.get_customer_by_phone(db, phone_value)
    if phone_owner is not None and phone_owner.id != customer.id:
        return fail("error.phone_taken", "phone")
    email_owner = crud.get_customer_by_email(db, email_value)
    if email_owner is not None and email_owner.id != customer.id:
        return fail("error.email_taken", "email")

    crud.update_customer_profile(db, customer, surname, phone_value, email_value)
    return RedirectResponse(url="/settings?saved=1", status_code=303)


@app.post("/web/settings/password", response_class=HTMLResponse, include_in_schema=False)
def change_password(
    request: Request,
    old_password: str = Form(""),
    new_password: str = Form(""),
    confirm: str = Form(""),
    db: Session = Depends(get_db),
):
    customer = get_current_customer(request, db)
    if customer is None:
        return RedirectResponse(url="/", status_code=303)

    def fail(key: str, field: str):
        return render(
            request,
            "settings.html",
            settings_context(
                db,
                customer,
                password_error=tr(request, key),
                password_invalid=field,
            ),
            status_code=400,
        )

    if not old_password:
        return fail("error.old_password_empty", "old_password")
    if customer.password_hash != md5_hash(old_password):
        return fail("error.old_password_wrong", "old_password")
    if not new_password:
        return fail("error.password_empty", "new_password")
    if not is_valid_password(new_password):
        return fail("error.password_weak", "new_password")
    if not confirm:
        return fail("error.confirm_empty", "confirm")
    if new_password != confirm:
        return fail("error.password_mismatch", "confirm")

    crud.update_customer_password(db, customer, new_password)
    return RedirectResponse(url="/settings?password_changed=1", status_code=303)


@app.post("/web/api-keys", response_class=HTMLResponse, include_in_schema=False)
def create_api_key(request: Request, db: Session = Depends(get_db)):
    customer = get_current_customer(request, db)
    if customer is None:
        return RedirectResponse(url="/", status_code=303)

    if crud.get_active_api_key_by_customer(db, customer.id) is not None:
        return render(
            request,
            "settings.html",
            settings_context(
                db,
                customer,
                key_error=tr(request, "settings.key_limit"),
            ),
            status_code=400,
        )

    _, raw_key = crud.create_api_key(db, customer.id)
    if raw_key is None:
        return render(
            request,
            "settings.html",
            settings_context(
                db,
                customer,
                key_error=tr(request, "settings.key_limit"),
            ),
            status_code=400,
        )

    return render(
        request,
        "settings.html",
        settings_context(db, customer, new_key=raw_key),
    )


@app.post("/web/api-keys/{key_id}/revoke", include_in_schema=False)
def revoke_api_key(key_id: int, request: Request, db: Session = Depends(get_db)):
    customer = get_current_customer(request, db)
    if customer is None:
        return RedirectResponse(url="/", status_code=303)

    crud.revoke_api_key(db, key_id, customer.id)
    return RedirectResponse(url="/settings", status_code=303)


# ---------- Бронирование (веб) ----------

@app.get("/book", response_class=HTMLResponse, include_in_schema=False)
def booking_page(request: Request, place_id: int | None = None, db: Session = Depends(get_db)):
    customer = get_current_customer(request, db)
    if customer is None:
        return RedirectResponse(url="/", status_code=303)

    selected = None
    if place_id is not None:
        selected = crud.get_place(db, place_id)
        if selected is not None and not selected.isActive:
            selected = None
    return render(request, "booking.html", booking_context(db, customer, selected=selected))


@app.post("/web/bookings", response_class=HTMLResponse, include_in_schema=False)
def create_booking_web(
    request: Request,
    place_id: str = Form(""),
    check_in: str = Form(""),
    check_out: str = Form(""),
    guests: str = Form(""),
    db: Session = Depends(get_db),
):
    customer = get_current_customer(request, db)
    if customer is None:
        return RedirectResponse(url="/", status_code=303)

    selected = crud.get_place(db, int(place_id)) if place_id.isdigit() else None
    if selected is None:
        return render(
            request,
            "booking.html",
            booking_context(
                db,
                customer,
                check_in=check_in,
                check_out=check_out,
                guests=guests,
                error=tr(request, "booking.error_place_not_found"),
            ),
            status_code=400,
        )
    if not selected.isActive:
        return render(
            request,
            "booking.html",
            booking_context(
                db,
                customer,
                selected=selected,
                check_in=check_in,
                check_out=check_out,
                guests=guests,
                error=tr(request, "booking.error_place_unavailable"),
            ),
            status_code=400,
        )

    try:
        check_in_date = datetime.strptime(check_in, "%Y-%m-%d").date()
        check_out_date = datetime.strptime(check_out, "%Y-%m-%d").date()
        guests_count = int(guests)
    except (TypeError, ValueError):
        return render(
            request,
            "booking.html",
            booking_context(
                db,
                customer,
                selected=selected,
                check_in=check_in,
                check_out=check_out,
                guests=guests,
                error=tr(request, "booking.error_dates"),
            ),
            status_code=400,
        )

    if check_out_date <= check_in_date:
        error = tr(request, "booking.error_dates")
    elif check_in_date < date.today():
        error = tr(request, "booking.error_past_dates")
    elif (check_out_date - check_in_date).days > 7:
        error = tr(request, "booking.error_max_days")
    elif guests_count < 1:
        error = tr(request, "booking.error_guests_min")
    elif guests_count > selected.capacity:
        error = tr(request, "booking.error_guests_capacity", capacity=selected.capacity)
    else:
        error = None

    if error:
        return render(
            request,
            "booking.html",
            booking_context(
                db,
                customer,
                selected=selected,
                check_in=check_in,
                check_out=check_out,
                guests=guests,
                error=error,
            ),
            status_code=400,
        )

    booking = crud.create_booking(
        db,
        schemas.BookingCreate(
            place_id=selected.id,
            customer_id=customer.id,
            checkIn=check_in_date,
            checkOut=check_out_date,
            guestsCount=guests_count,
            status="active",
        ),
    )
    if booking is None:
        return render(
            request,
            "booking.html",
            booking_context(
                db,
                customer,
                selected=selected,
                check_in=check_in,
                check_out=check_out,
                guests=guests,
                error=tr(request, "booking.error_busy"),
            ),
            status_code=409,
        )

    logger.info(
        "Booking %s created for customer %s; customer/admin email notifications are disabled",
        booking.id,
        customer.id,
    )
    return RedirectResponse(url=f"/bookings/{booking.id}?created=1", status_code=303)


@app.get("/bookings", response_class=HTMLResponse, include_in_schema=False)
def my_bookings(request: Request, db: Session = Depends(get_db)):
    customer = get_current_customer(request, db)
    if customer is None:
        return RedirectResponse(url="/", status_code=303)

    message = None
    if request.query_params.get("cancelled") == "1":
        message = tr(request, "bookings.cancelled_msg")
    elif request.query_params.get("not_found") == "1":
        message = tr(request, "bookings.not_found")

    return render(
        request,
        "bookings.html",
        {
            "customer": customer,
            "bookings": crud.get_bookings_by_customer(db, customer.id),
            "message": message,
        },
    )


@app.get("/bookings/{booking_id}", response_class=HTMLResponse, include_in_schema=False)
def booking_detail(request: Request, booking_id: int, db: Session = Depends(get_db)):
    customer = get_current_customer(request, db)
    if customer is None:
        return RedirectResponse(url="/", status_code=303)

    booking = get_own_booking_web(db, booking_id, customer)
    if booking is None:
        return RedirectResponse(url="/bookings?not_found=1", status_code=303)

    message = None
    if request.query_params.get("created") == "1":
        message = tr(request, "booking.success")
    elif request.query_params.get("expired") == "1":
        message = tr(request, "bookings.expired_msg")
    elif request.query_params.get("cannot_cancel") == "1":
        message = tr(request, "bookings.cannot_cancel")

    return render(
        request,
        "booking_detail.html",
        {"customer": customer, "booking": booking, "message": message},
    )


@app.post("/bookings/{booking_id}/cancel", include_in_schema=False)
def cancel_booking_web(request: Request, booking_id: int, db: Session = Depends(get_db)):
    customer = get_current_customer(request, db)
    if customer is None:
        return RedirectResponse(url="/", status_code=303)

    booking = get_own_booking_web(db, booking_id, customer)
    if booking is None:
        return RedirectResponse(url="/bookings?not_found=1", status_code=303)

    if booking.checkIn <= date.today() and booking.status == "active":
        crud.change_booking_status(db, booking.id, "expired")
        return RedirectResponse(url=f"/bookings/{booking.id}?expired=1", status_code=303)

    if booking.status != "active":
        return RedirectResponse(url=f"/bookings/{booking.id}?cannot_cancel=1", status_code=303)

    crud.change_booking_status(db, booking.id, "cancelled")
    logger.info(
        "Booking %s cancelled by customer %s; email notifications are disabled",
        booking.id,
        customer.id,
    )
    return RedirectResponse(url="/bookings?cancelled=1", status_code=303)


# ---------- Публичный API ----------

def api_current_customer(
    api_key: str | None = Security(api_key_header),
    db: Session = Depends(get_db),
):
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Не передан API-ключ. Укажите его в заголовке X-API-Key",
        )
    record = crud.get_api_key_record_by_hash(db, sha256_hash(api_key))
    if record is None or record.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Неверный или отозванный API-ключ")
    return record.customer


def get_own_booking_api(
    db: Session,
    booking_number: int,
    customer: models.Customer,
) -> models.Booking:
    """Бронь ищется по номеру внутри клиента, а не по глобальному id."""
    booking = crud.get_booking_by_number(db, customer.id, booking_number)
    if booking is None:
        raise HTTPException(status_code=404, detail="Бронь не найдена")
    return booking


def validate_booking_dates(check_in: date, check_out: date) -> None:
    if check_out <= check_in:
        raise HTTPException(status_code=400, detail="Дата выезда должна быть позже даты заезда")
    if check_in < date.today():
        raise HTTPException(status_code=400, detail="Нельзя бронировать прошедшие даты")
    if (check_out - check_in).days > 7:
        raise HTTPException(status_code=400, detail="Максимальный срок бронирования — 7 дней")


@app.get(
    "/api/places",
    response_model=List[schemas.PlacePublic],
    tags=["Места"],
    summary="Список всех мест",
)
def api_list_places(db: Session = Depends(get_db)):
    return crud.get_places(db, skip=0, limit=1000)


@app.get(
    "/api/places/{place_id}/availability",
    response_model=schemas.AvailabilityResponse,
    tags=["Доступность"],
    summary="Проверить доступность места на даты",
)
def api_check_availability(
    place_id: int,
    check_in: date,
    check_out: date,
    db: Session = Depends(get_db),
):
    place = crud.get_place(db, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Место не найдено")
    validate_booking_dates(check_in, check_out)
    free = place.isActive and crud.is_place_free(db, place_id, check_in, check_out)
    return schemas.AvailabilityResponse(
        place_id=place_id,
        check_in=check_in,
        check_out=check_out,
        free=free,
    )


@app.get(
    "/api/bookings",
    response_model=List[schemas.BookingStatusResponse],
    tags=["Бронирования"],
    summary="Список своих броней",
)
def api_my_bookings(
    customer: models.Customer = Depends(api_current_customer),
    db: Session = Depends(get_db),
):
    return crud.get_bookings_by_customer(db, customer.id)


@app.post(
    "/api/bookings",
    response_model=schemas.BookingStatusResponse,
    status_code=201,
    tags=["Бронирования"],
    summary="Создать бронь от имени владельца API-ключа",
)
def api_create_booking(
    payload: schemas.BookingCreateAPI,
    customer: models.Customer = Depends(api_current_customer),
    db: Session = Depends(get_db),
):
    place = crud.get_place(db, payload.place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Место не найдено")
    if not place.isActive:
        raise HTTPException(status_code=400, detail="Место недоступно для бронирования")
    validate_booking_dates(payload.checkIn, payload.checkOut)
    if payload.guestsCount < 1:
        raise HTTPException(status_code=400, detail="Количество гостей должно быть больше 0")
    if payload.guestsCount > place.capacity:
        raise HTTPException(status_code=400, detail=f"Вместимость места — {place.capacity} гостей")

    booking = crud.create_booking(
        db,
        schemas.BookingCreate(
            place_id=payload.place_id,
            customer_id=customer.id,
            checkIn=payload.checkIn,
            checkOut=payload.checkOut,
            guestsCount=payload.guestsCount,
            status="active",
        ),
    )
    if booking is None:
        raise HTTPException(status_code=409, detail="Место занято на выбранные даты")
    return booking


@app.get(
    "/api/bookings/{booking_number}",
    response_model=schemas.BookingStatusResponse,
    tags=["Бронирования"],
    summary="Получить статус своей брони по её номеру",
)
def api_booking_status(
    booking_number: int,
    customer: models.Customer = Depends(api_current_customer),
    db: Session = Depends(get_db),
):
    return get_own_booking_api(db, booking_number, customer)


@app.post(
    "/api/bookings/{booking_number}/cancel",
    response_model=schemas.BookingStatusResponse,
    tags=["Бронирования"],
    summary="Отменить свою бронь по её номеру",
)
def api_cancel_booking(
    booking_number: int,
    customer: models.Customer = Depends(api_current_customer),
    db: Session = Depends(get_db),
):
    booking = get_own_booking_api(db, booking_number, customer)
    if booking.status != "active":
        raise HTTPException(status_code=409, detail="Бронь уже отменена или завершена")
    updated = crud.change_booking_status(db, booking.id, "cancelled")
    return updated
