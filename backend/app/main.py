from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import accesos, auth, qr, sillas, visitas

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
app.include_router(visitas.router)
app.include_router(sillas.router)
app.include_router(qr.router)
app.include_router(accesos.router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
