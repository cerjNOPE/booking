# Система бронирования мест в кемпинге

## Запуск

1. Поднять БД в Docker:
```bash
docker compose up -d
```

2. Установить зависимости:
```bash
pip install -r requirements.txt
```

3. Запустить приложение:
```bash
python run.py
```

5. Открыть веб-страницу:
`https://localhost/`

## Настройки БД по умолчанию
- DB: Booking
- user: admin
- password: q-123456   


# API

| Метод | Путь | Ключ | Назначение |
|---|---|---|---|
| `GET` | `/api/places` | не нужен | все места |
| `GET` | `/api/places/{place_id}/availability?check_in=YYYY-MM-DD&check_out=YYYY-MM-DD` | не нужен | доступность места |
| `GET` | `/api/bookings` | нужен | список своих броней |
| `POST` | `/api/bookings` | нужен | создать бронь |
| `GET` | `/api/bookings/{booking_number}` | нужен | статус брони по номеру |
| `POST` | `/api/bookings/{booking_number}/cancel` | нужен | отменить бронь по номеру |


# Скрипты

```bash
python -m scripts.reset_db                  #Пересоздание Базы данных
python -m scripts.seed_places               #Добавление тестовых мест
```

# Тесты
```bash
pytest tests -q
```
```bash
pytest tests --cov=app
```
или
```bash
.\.venv\Scripts\python.exe -m  pytest tests -q
```
```bash
.\.venv\Scripts\python.exe -m  pytest tests --cov=app
```
