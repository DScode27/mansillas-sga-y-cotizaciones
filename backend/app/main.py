"""Aplicación FastAPI de MansillasSIC (parte de seguridad de Nicolás).

Monta CORS para el frontend Vite y registra los routers de seguridad:
autenticación (HU-21/25) y gestión de usuarios (HU-20). Las siguientes HU añaden
sus propios routers.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import auth, usuarios

settings = get_settings()

app = FastAPI(title=settings.app_name, debug=settings.debug)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(usuarios.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Sonda simple para verificar que la app responde."""
    return {"status": "ok"}
