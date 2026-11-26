"""Aplicación FastAPI de MansillasSIC.

Monta CORS para el frontend Vite y registra todos los routers del backend:
seguridad (auth HU-21/25, usuarios HU-20) y los recursos de negocio (visitas,
sillas, QR, accesos).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import accesos, auth, fotos, precotizaciones, qr, sillas, usuarios, visitas

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API for the Mansillas SGA and quotes system.",
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(visitas.router)
app.include_router(sillas.router)
app.include_router(fotos.router)
app.include_router(precotizaciones.router)
app.include_router(qr.router)
app.include_router(accesos.router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
