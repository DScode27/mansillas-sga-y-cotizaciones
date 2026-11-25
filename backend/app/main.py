from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import accesos, qr, sillas, visitas

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API for the Mansillas SGA and quotes system.",
)

origenes = {
    settings.frontend_url.rstrip("/"),
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted(origenes),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(visitas.router)
app.include_router(sillas.router)
app.include_router(qr.router)
app.include_router(accesos.router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "healthy"}
