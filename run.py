"""Запуск приложения по HTTPS на порту 443."""

import os
from pathlib import Path

import uvicorn

BASE_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "443")),
        ssl_keyfile=str(BASE_DIR / "certs" / "key.pem"),
        ssl_certfile=str(BASE_DIR / "certs" / "cert.pem"),
    )
