function togglePassword(inputId, button) {
    const input = document.getElementById(inputId);
    if (!input) return;
    const willShow = input.type === "password";
    input.type = willShow ? "text" : "password";
    button.setAttribute("aria-label", willShow ? "hide password" : "show password");
    button.classList.toggle("is-visible", willShow);
}

function checkPassword(value) {
    const checks = {
        length: value.length >= 8,
        letter: /[A-Za-zА-Яа-яЁё]/.test(value),
        digit: /\d/.test(value),
        special: /[^A-Za-zА-Яа-яЁё0-9\s]/.test(value),
    };
    document.querySelectorAll("[data-req]").forEach((item) => {
        item.classList.toggle("met", Boolean(checks[item.dataset.req]));
    });
}

function formatRuPhone(digits) {
    let out = "8";
    if (digits.length > 1) out += " (" + digits.slice(1, 4);
    if (digits.length >= 5) out += ") " + digits.slice(4, 7);
    if (digits.length >= 8) out += "-" + digits.slice(7, 9);
    if (digits.length >= 10) out += "-" + digits.slice(9, 11);
    return out;
}

function toRuDigits(value) {
    let digits = value.replace(/\D/g, "");
    if (!digits) return "";
    if (digits.startsWith("7")) digits = "8" + digits.slice(1);
    else if (!digits.startsWith("8")) digits = "8" + digits;
    return digits.slice(0, 11);
}

function applyPhoneMask(input) {
    if (input.value.trim()) {
        const initial = toRuDigits(input.value);
        if (initial.length >= 10) input.value = formatRuPhone(initial);
    }

    const startWithEight = () => {
        if (!input.value.trim()) input.value = "8 ";
    };
    input.addEventListener("focus", startWithEight);
    input.addEventListener("click", startWithEight);

    input.addEventListener("input", () => {
        const digits = toRuDigits(input.value);
        input.value = digits ? formatRuPhone(digits) : "";
    });

    input.addEventListener("blur", () => {
        if (input.value.trim() === "8") input.value = "";
    });
}

function looksLikeEmail(value) {
    return value.includes("@") || /[A-Za-zА-Яа-я]/.test(value);
}

function applyLoginIdentifier(input) {
    let mode = null;

    const formatPhone = () => {
        if (mode !== "phone") return;
        let digits = input.value.replace(/\D/g, "");
        if (!digits) {
            input.value = "";
            return;
        }
        if (digits.startsWith("7")) digits = "8" + digits.slice(1);
        else if (!digits.startsWith("8")) digits = "8" + digits;
        digits = digits.slice(0, 11);
        input.value = formatRuPhone(digits);
    };

    if (input.value.trim()) {
        if (looksLikeEmail(input.value)) {
            mode = "email";
        } else if (input.value.replace(/\D/g, "").length >= 10) {
            mode = "phone";
            formatPhone();
        }
    }

    input.addEventListener("input", () => {
        if (!input.value) {
            mode = null;
            return;
        }
        if (!mode) {
            mode = looksLikeEmail(input.value) ? "email" : "phone";
        } else if (mode === "phone" && looksLikeEmail(input.value)) {
            mode = "email";
            return;
        }
        formatPhone();
    });

    input.addEventListener("blur", () => {
        if (mode === "phone" && input.value.trim() === "8") {
            input.value = "";
            mode = null;
        }
    });
}

function applyBookingForm() {
    const select = document.getElementById("place-select");
    const capacity = document.getElementById("capacity-output");
    const guests = document.getElementById("guests");

    if (select && capacity) {
        const sync = () => {
            const option = select.options[select.selectedIndex];
            const value = option ? option.dataset.capacity || "" : "";
            capacity.value = value;
            if (guests && value) guests.max = value;
        };
        select.addEventListener("change", sync);
        sync();
    }

    const checkIn = document.getElementById("check-in");
    const checkOut = document.getElementById("check-out");
    const bookingForm = document.querySelector(".booking-form");

    const localToday = () => {
        const now = new Date();
        return new Date(now.getTime() - now.getTimezoneOffset() * 60000)
            .toISOString()
            .slice(0, 10);
    };

    const addDays = (value, days) => {
        const date = new Date(value + "T12:00:00");
        date.setDate(date.getDate() + days);
        const pad = (number) => String(number).padStart(2, "0");
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
    };

    const syncDates = () => {
        if (!checkIn || !checkOut) return;
        const today = localToday();
        checkIn.min = today;
        checkOut.min = today;
        checkOut.removeAttribute("max");
        if (checkIn.value) {
            checkOut.min = checkIn.value > today ? checkIn.value : today;
            checkOut.max = addDays(checkIn.value, 7);
        }
    };

    if (checkIn && checkOut) {
        ["focus", "click", "change"].forEach((eventName) => {
            checkIn.addEventListener(eventName, syncDates);
            checkOut.addEventListener(eventName, syncDates);
        });
        syncDates();
    }

    if (bookingForm && checkIn && checkOut) {
        bookingForm.addEventListener("submit", (event) => {
            syncDates();
            const today = localToday();
            if (checkIn.value && checkIn.value < today) {
                event.preventDefault();
                alert(
                    bookingForm.dataset.pastDateError ||
                        "Нельзя бронировать прошедшие даты"
                );
                return;
            }
            if (checkIn.value && checkOut.value && checkOut.value < checkIn.value) {
                event.preventDefault();
                alert(
                    bookingForm.dataset.datesError ||
                        "Дата выезда должна быть позже даты заезда"
                );
                return;
            }
            if (checkIn.value && checkOut.value) {
                const start = new Date(checkIn.value + "T00:00:00");
                const end = new Date(checkOut.value + "T00:00:00");
                const days = Math.round((end - start) / 86400000);
                if (days > 7) {
                    event.preventDefault();
                    alert(
                        bookingForm.dataset.maxDaysError ||
                            "Максимальный срок бронирования — 7 дней"
                    );
                }
            }
        });
    }
}

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-password-check]").forEach((input) => {
        checkPassword(input.value);
        input.addEventListener("input", () => checkPassword(input.value));
    });

    document.querySelectorAll("[data-phone-mask]").forEach((input) => {
        applyPhoneMask(input);
    });

    const identifier = document.getElementById("identifier");
    if (identifier) {
        applyLoginIdentifier(identifier);
    }

    applyBookingForm();
});
