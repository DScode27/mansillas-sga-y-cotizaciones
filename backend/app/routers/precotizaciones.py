"""Pre-quotation management endpoints (HU-12, HU-13).

This module owns the survey-consult, pre-quotation create/list/send, and the
public proposal consult. It reuses the existing `Silla`/`Visita`/`Precotizacion`
models, the `SillaOut` schema from the sillas router, the business RBAC in
`app/deps.py`, and the shared consistency rules in
`app/services/precotizacion_rules.py`.

Implemented here: survey consult (`GET /visitas/{id}/levantamiento`),
pre-quotation create and list (`POST`/`GET /precotizaciones`), link send
(`POST /precotizaciones/{id}/enviar`), the public proposal consult
(`GET /propuesta/{token}`), the OTP request and acceptance
(`POST /propuesta/{token}/otp`, `POST /propuesta/{token}/aceptar`, HU-15), and
the quotation-enablement consult (`GET /precotizaciones/{id}/habilitacion-cotizacion`,
HU-16). Business rules and locks live in `app/services/precotizacion_rules.py`;
OTP crypto/abuse-control in `app/services/otp.py`; email in `app/services/email.py`.
"""

import logging
import uuid
from datetime import datetime
from typing import Annotated

import json

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from pydantic import BaseModel, ConfigDict, StrictBool, StrictStr, ValidationError
from sqlalchemy import DateTime, cast, func, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import CurrentUser, require_role
from app.models import (
    AceptacionPrecotizacion,
    CodigoVerificacion,
    Empresa,
    Precotizacion,
    Silla,
    Visita,
)
from app.routers.accesos import registrar_acceso
from app.routers.sillas import SillaOut
from app.services import email as email_service
from app.services import otp as otp_service
from app.services import precotizacion_rules

logger = logging.getLogger(__name__)

router = APIRouter(tags=["precotizaciones"])


class DetalleError(BaseModel):
    """Standard FastAPI error body (`{"detail": "..."}`)."""

    detail: str


# Reusable OpenAPI `responses` fragments documenting the REAL error bodies these
# endpoints return (no invented codes). Attached per endpoint below.
_HDR_NO_STORE = {
    "Cache-Control": {
        "description": "Siempre `no-store` en este endpoint.",
        "schema": {"type": "string"},
    }
}


def _err(descripcion: str, ejemplo: str) -> dict:
    return {
        "model": DetalleError,
        "description": descripcion,
        "content": {"application/json": {"example": {"detail": ejemplo}}},
    }


# Public endpoints always set Cache-Control: no-store (success and errors).
_RESP_PUBLICO_404 = _err("Token inválido, desconocido o propuesta no disponible.", "No encontrado")

RESP_LEVANTAMIENTO = {
    401: _err("No autenticado.", "Token de acceso requerido"),
    403: _err("Rol no autorizado.", "Rol no autorizado"),
    404: _err("La visita no existe.", "No encontrado"),
}
RESP_CREAR_PRECOTIZACION = {
    401: _err("No autenticado.", "Token de acceso requerido"),
    403: _err("Rol no autorizado.", "Rol no autorizado"),
    404: _err("La visita no existe.", "No encontrado"),
    409: _err("La visita ya tiene una precotización activa.", "La visita ya tiene una precotización activa"),
    422: _err("Falta confirmar_validacion=true.", "Se requiere confirmar_validacion=true para crear la precotización"),
}
RESP_LISTAR_PRECOTIZACIONES = {
    401: _err("No autenticado.", "Token de acceso requerido"),
    403: _err("Rol no autorizado.", "Rol no autorizado"),
}
RESP_HABILITACION = {
    401: _err("No autenticado.", "Token de acceso requerido"),
    403: _err("Rol no autorizado.", "Rol no autorizado"),
    404: _err("La precotización no existe.", "No encontrado"),
}
RESP_ENVIAR = {
    401: _err("No autenticado.", "Token de acceso requerido"),
    403: _err("Rol no autorizado.", "Rol no autorizado"),
    404: _err("La precotización no existe.", "No encontrado"),
    409: _err("Estado no enviable o cambio de destinatario no permitido.", "La precotización no puede enviarse en su estado actual"),
    422: _err("Correo inválido o falta la confirmación en el primer envío.", "Correo inválido"),
    500: _err("El correo se envió pero no fue posible actualizar el estado.", "El correo se envió pero no fue posible actualizar el estado"),
    502: _err("Fallo del envío SMTP.", "No fue posible enviar el correo"),
    503: _err("Envío de correo no configurado.", "El envío de correo no está configurado"),
}
RESP_PROPUESTA_PUBLICA = {
    200: {"headers": _HDR_NO_STORE, "description": "Propuesta consultable (ENVIADA/ACEPTADA)."},
    404: {**_RESP_PUBLICO_404, "headers": _HDR_NO_STORE},
}
RESP_OTP = {
    202: {"headers": _HDR_NO_STORE, "description": "Solicitud de código aceptada."},
    404: {**_RESP_PUBLICO_404, "headers": _HDR_NO_STORE},
    429: {**_err("Demasiadas solicitudes.", "Demasiadas solicitudes; intente más tarde"), "headers": _HDR_NO_STORE},
    502: {**_err("Fallo del envío SMTP.", "No fue posible enviar el código de verificación"), "headers": _HDR_NO_STORE},
    503: {**_err("Verificación no disponible (OTP/SMTP sin configurar).", "El servicio de verificación no está disponible"), "headers": _HDR_NO_STORE},
    500: {**_err("Fallo inesperado de persistencia.", "No fue posible completar la solicitud"), "headers": _HDR_NO_STORE},
}
RESP_ACEPTAR = {
    200: {"headers": _HDR_NO_STORE, "description": "Aceptación registrada."},
    400: {**_err("OTP inválido, expirado, usado o no disponible.", "Código inválido o expirado"), "headers": _HDR_NO_STORE},
    404: {**_RESP_PUBLICO_404, "headers": _HDR_NO_STORE},
    409: {**_err("Propuesta no disponible o ya aceptada.", "La propuesta ya fue aceptada"), "headers": _HDR_NO_STORE},
    422: {**_err("Datos de aceptación inválidos (no refleja el código enviado).", "Datos de aceptación inválidos"), "headers": _HDR_NO_STORE},
    429: {**_err("Demasiados intentos.", "Demasiados intentos; intente más tarde"), "headers": _HDR_NO_STORE},
    500: {**_err("Inconsistencia interna o fallo de persistencia.", "No fue posible procesar la aceptación"), "headers": _HDR_NO_STORE},
    503: {**_err("Verificación no disponible.", "El servicio de verificación no está disponible"), "headers": _HDR_NO_STORE},
}


class VisitaResumen(BaseModel):
    id_visita: int
    id_empresa: int
    id_sede: int
    id_comercial: int
    id_tecnico: int
    cantidad_estimada: int
    estado: str


class LevantamientoOut(BaseModel):
    """Survey view for commercial review (HU-12 Requirement 1)."""

    visita: VisitaResumen
    sillas: list[SillaOut]
    # Whether an active pre-quotation exists for the visit. This is NOT a
    # standalone validation flag; it does not prove later edits were validated.
    tiene_precotizacion: bool


class PrecotizacionCreate(BaseModel):
    id_visita: int
    # Explicit survey confirmation (HU-12 Requirement 3). StrictBool rejects
    # string/number coercions ("true", "yes", 1, ...): only a real boolean true
    # is accepted.
    confirmar_validacion: StrictBool = False
    observaciones: str | None = None


class PrecotizacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_precotizacion: int
    id_empresa: int
    id_visita: int
    estado: str
    token: uuid.UUID
    correo_cliente: str | None
    fecha_envio: datetime | None
    fecha_creacion: datetime
    observaciones: str | None


class EnvioRequest(BaseModel):
    correo_cliente: str
    # Required on a first send from BORRADOR (re-confirmation of the survey).
    # StrictBool: no coercion. Not required for a resend from ENVIADA.
    confirmar_validacion: StrictBool = False


class SillaPublicaOut(BaseModel):
    """Chair fields exposed in the public proposal (no internal ids/tokens)."""

    codigo_qr: str
    cargo: str
    estado: str


class PropuestaPublicaOut(BaseModel):
    """Explicit public proposal schema (never the internal model)."""

    token: uuid.UUID
    estado: str
    fecha_envio: datetime | None
    empresa_nombre: str
    sillas: list[SillaPublicaOut]


def _normalizar_texto(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpio = valor.strip()
    return limpio or None


@router.get(
    "/visitas/{id_visita}/levantamiento",
    response_model=LevantamientoOut,
    responses=RESP_LEVANTAMIENTO,
)
def consultar_levantamiento(
    id_visita: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("COMERCIAL_MANSILLAS"))],
) -> LevantamientoOut:
    """Return the survey (chairs) of a visit for the Comercial to review.

    Internal commercials may read any visit (existing policy). Chairs are
    returned in a deterministic order (`id_silla`). Component checklist and
    `sugerir_cambio` are out of scope (Esteban's module).
    """
    visita = db.get(Visita, id_visita)
    if visita is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")

    sillas = db.scalars(
        select(Silla).where(Silla.id_visita == id_visita).order_by(Silla.id_silla)
    ).all()

    tiene_precotizacion = (
        precotizacion_rules.precotizacion_activa(db, id_visita) is not None
    )

    return LevantamientoOut(
        visita=VisitaResumen(
            id_visita=visita.id_visita,
            id_empresa=visita.id_empresa,
            id_sede=visita.id_sede,
            id_comercial=visita.id_comercial,
            id_tecnico=visita.id_tecnico,
            cantidad_estimada=visita.cantidad_estimada,
            estado=visita.estado,
        ),
        sillas=[SillaOut.model_validate(s) for s in sillas],
        tiene_precotizacion=tiene_precotizacion,
    )


@router.post(
    "/precotizaciones",
    response_model=PrecotizacionOut,
    status_code=status.HTTP_201_CREATED,
    responses=RESP_CREAR_PRECOTIZACION,
)
def crear_precotizacion(
    payload: PrecotizacionCreate,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("COMERCIAL_MANSILLAS"))],
) -> Precotizacion:
    """Explicitly validate the survey and create the pre-quotation (HU-12/HU-13).

    The explicit `confirmar_validacion: true` is both the validation of the
    current survey and the creation of the `BORRADOR` pre-quotation (combined MVP
    action; no standalone/persistent per-version validation). To avoid concurrent
    duplicates without a UNIQUE constraint, the Visit row is locked first, then
    the active-pre-quotation check and the insert run in the same transaction.
    """
    if payload.confirmar_validacion is not True:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Se requiere confirmar_validacion=true para crear la precotización",
        )

    # Lock the Visit row first (consistent lock order); 404 if it does not exist.
    visita = precotizacion_rules.lock_visita(db, payload.id_visita)
    if visita is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")

    # With the lock held, reject a second active pre-quotation (ANULADA allows a new one).
    if precotizacion_rules.precotizacion_activa(db, payload.id_visita) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La visita ya tiene una precotización activa",
        )

    precotizacion = Precotizacion(
        id_empresa=visita.id_empresa,
        id_visita=visita.id_visita,
        estado="BORRADOR",
        creada_por=user.id,
        observaciones=_normalizar_texto(payload.observaciones),
    )
    db.add(precotizacion)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No fue posible crear la precotización",
        ) from None

    db.refresh(precotizacion)
    return precotizacion


@router.get(
    "/precotizaciones",
    response_model=list[PrecotizacionOut],
    responses=RESP_LISTAR_PRECOTIZACIONES,
)
def listar_precotizaciones(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("COMERCIAL_MANSILLAS"))],
    id_visita: Annotated[int, Query(description="Visit whose pre-quotations are listed")],
) -> list[Precotizacion]:
    """List the pre-quotations of a visit (HU-13, frontend contract).

    `id_visita` is required (matching the frontend's `GET /precotizaciones?id_visita=`
    usage). Internal commercials may query any visit. Returns an empty list when
    none match; results are ordered deterministically by `id_precotizacion`.
    """
    stmt = (
        select(Precotizacion)
        .where(Precotizacion.id_visita == id_visita)
        .order_by(Precotizacion.id_precotizacion)
    )
    return list(db.scalars(stmt).all())


class HabilitacionOut(BaseModel):
    habilitado: bool
    estado: str


@router.get(
    "/precotizaciones/{id_precotizacion}/habilitacion-cotizacion",
    response_model=HabilitacionOut,
    responses=RESP_HABILITACION,
)
def habilitacion_cotizacion(
    id_precotizacion: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("COMERCIAL_MANSILLAS"))],
) -> HabilitacionOut:
    """Report whether quotation is enabled for a pre-quotation (HU-16).

    COMERCIAL only (internal commercials may query any pre-quotation, existing
    policy). Enabled only when the pre-quotation is `ACEPTADA` and an acceptance
    record exists (an `ACEPTADA` without a record → `habilitado=false`). Read
    only: no state change, no insert, no commit, no quotation created.
    """
    estado, habilitado = precotizacion_rules.estado_habilitacion_cotizacion(
        db, id_precotizacion
    )
    if estado is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    return HabilitacionOut(habilitado=habilitado, estado=estado)


@router.post(
    "/precotizaciones/{id_precotizacion}/enviar",
    response_model=PrecotizacionOut,
    responses=RESP_ENVIAR,
)
def enviar_precotizacion(
    id_precotizacion: int,
    payload: EnvioRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_role("COMERCIAL_MANSILLAS"))],
) -> Precotizacion:
    """Generate the unique link and email it to the client (HU-13).

    First send from `BORRADOR` requires `confirmar_validacion: true`. Resend from
    `ENVIADA` reuses the same token and the stored recipient and does not require
    a new confirmation. Email is sent first; the `ENVIADA` state is persisted
    only after a successful send (no atomicity between SMTP and the DB).
    """
    # Validate the recipient format before contacting SMTP.
    try:
        correo = email_service.validar_destinatario(payload.correo_cliente)
    except email_service.EmailInvalido:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Correo inválido"
        ) from None

    pre = db.get(Precotizacion, id_precotizacion)
    if pre is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")

    # Consistent lock order: lock the Visit row, then refresh the pre-quotation
    # so the state decision is not based on a stale ORM instance. 404 if the
    # visit row no longer exists.
    if precotizacion_rules.lock_visita(db, pre.id_visita) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No encontrado")
    db.refresh(pre)

    if pre.estado in ("ACEPTADA", "ANULADA"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La precotización no puede enviarse en su estado actual",
        )

    primer_envio = pre.estado == "BORRADOR"
    if primer_envio:
        if payload.confirmar_validacion is not True:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Se requiere confirmar_validacion=true para el primer envío",
            )
        destinatario = correo
    else:
        # Resend from ENVIADA: reuse the stored recipient; never silently assign
        # a new one. Reject if there is no valid stored recipient or a change.
        if not pre.correo_cliente:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "La propuesta enviada no tiene un destinatario almacenado",
            )
        if correo != pre.correo_cliente:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "No se puede cambiar el destinatario de una propuesta ya enviada",
            )
        destinatario = pre.correo_cliente

    enlace = f"{settings.frontend_url.rstrip('/')}{settings.proposal_path}/{pre.token}"
    asunto = "Su propuesta de Mansillas SIC"
    cuerpo = (
        "Estimado cliente,\n\n"
        "Mansillas SIC ha preparado una propuesta para usted. Puede "
        "consultarla y aceptarla de forma segura en el siguiente enlace:\n\n"
        f"{enlace}\n\n"
        "Al abrir el enlace podrá revisar el detalle del levantamiento y, si "
        "está de acuerdo, confirmar la propuesta con un código que le "
        "enviaremos por correo.\n\n"
        "Si usted no esperaba este mensaje, puede ignorarlo.\n\n"
        "Gracias por confiar en Mansillas SIC."
    )

    try:
        email_service.enviar_correo(destinatario, asunto, cuerpo)
    except email_service.EmailNoConfigurado:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El envío de correo no está configurado",
        ) from None
    except email_service.EmailInvalido:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Correo inválido"
        ) from None
    except email_service.EmailEnvioError:
        # SMTP failure: do NOT transition to ENVIADA.
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "No fue posible enviar el correo",
        ) from None

    # Email already sent. Persist the state; a DB failure here cannot unsend it.
    pre.correo_cliente = destinatario
    pre.fecha_envio = datetime.now()  # updated on each send (last send)
    pre.estado = "ENVIADA"
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.error(
            "El correo de la precotización %s se envió pero falló la persistencia "
            "del estado ENVIADA; el correo NO se revierte",
            id_precotizacion,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "El correo se envió pero no fue posible actualizar el estado",
        ) from None

    db.refresh(pre)
    return pre


@router.get(
    "/propuesta/{token}",
    response_model=PropuestaPublicaOut,
    responses=RESP_PROPUESTA_PUBLICA,
)
def consultar_propuesta_publica(
    token: str,
    respuesta: Response,
    db: Annotated[Session, Depends(get_db)],
    user_agent: Annotated[str | None, Header()] = None,
) -> PropuestaPublicaOut:
    """Public, unauthenticated consult of a proposal by its link token (HU-13).

    Only `ENVIADA`/`ACEPTADA` proposals are returned. An invalid/unknown token,
    or one in `BORRADOR`/`ANULADA`, gives an indistinguishable 404. The access
    is logged via Davidson's `registrar_acceso` only after the proposal is
    confirmed consultable.
    """
    respuesta.headers["Cache-Control"] = "no-store"
    # Error responses must also carry no-store (HTTPException builds its own
    # response, so the header is set on the exception explicitly).
    no_store = {"Cache-Control": "no-store"}

    # Malformed token → 404 (indistinguishable from unknown).
    try:
        token_uuid = uuid.UUID(token)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No encontrado", headers=no_store
        ) from None

    pre = db.scalar(select(Precotizacion).where(Precotizacion.token == token_uuid))
    if pre is None or pre.estado not in ("ENVIADA", "ACEPTADA"):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No encontrado", headers=no_store
        )

    empresa = db.get(Empresa, pre.id_empresa)
    sillas = db.scalars(
        select(Silla)
        .where(Silla.id_empresa == pre.id_empresa, Silla.id_visita == pre.id_visita)
        .order_by(Silla.id_silla)
    ).all()

    # Log the access only after confirming the proposal is consultable. If the
    # log fails, do not claim it was recorded; the consult still succeeds.
    try:
        registrar_acceso(db, pre.id_precotizacion, user_agent)
    except Exception:
        db.rollback()
        logger.warning(
            "No se pudo registrar el acceso a la precotización %s",
            pre.id_precotizacion,
        )

    return PropuestaPublicaOut(
        token=pre.token,
        estado=pre.estado,
        fecha_envio=pre.fecha_envio,
        empresa_nombre=empresa.nombre if empresa else "",
        sillas=[
            SillaPublicaOut(codigo_qr=s.codigo_qr, cargo=s.cargo, estado=s.estado)
            for s in sillas
        ],
    )


class OtpResponse(BaseModel):
    mensaje: str


_NO_STORE = {"Cache-Control": "no-store"}


@router.post(
    "/propuesta/{token}/otp",
    response_model=OtpResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=RESP_OTP,
)
def solicitar_otp(
    token: str,
    respuesta: Response,
    db: Annotated[Session, Depends(get_db)],
) -> OtpResponse:
    """Public: request a one-time code for an `ENVIADA` proposal (HU-15).

    No authentication; the recipient is ONLY the pre-quotation's stored
    `correo_cliente` (never from the request). An invalid/unknown token or a
    non-`ENVIADA` proposal returns an indistinguishable 404. The response never
    contains the code, hash, nonce, email, or internal ids. All responses carry
    `Cache-Control: no-store`.
    """
    respuesta.headers["Cache-Control"] = "no-store"

    # Resolve the token and check the allowed state FIRST, so an invalid/unknown
    # token or a non-ENVIADA proposal is an indistinguishable 404 regardless of
    # OTP configuration (no information leak).
    try:
        token_uuid = uuid.UUID(token)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No encontrado", headers=_NO_STORE
        ) from None

    pre = db.scalar(select(Precotizacion).where(Precotizacion.token == token_uuid))
    if pre is None or pre.estado != "ENVIADA":
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No encontrado", headers=_NO_STORE
        )

    # Lock the Visit row first (consistent order), then re-read the state/email.
    if precotizacion_rules.lock_visita(db, pre.id_visita) is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No encontrado", headers=_NO_STORE
        )
    db.refresh(pre)
    if pre.estado != "ENVIADA":
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No encontrado", headers=_NO_STORE
        )

    # Only now surface a controlled 503 if OTP is not securely configured.
    if not otp_service.otp_configurado():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El servicio de verificación no está disponible",
            headers=_NO_STORE,
        )

    # Recipient comes only from the stored correo_cliente; validate it.
    try:
        destino = email_service.validar_destinatario(pre.correo_cliente or "")
    except email_service.EmailInvalido:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El servicio de verificación no está disponible",
            headers=_NO_STORE,
        ) from None

    # Request throttle / cumulative limit. Counted here (before SMTP) so a
    # provider failure cannot enable unlimited requests (provisional policy).
    try:
        otp_service.control_abuso.registrar_solicitud(pre.id_precotizacion)
    except otp_service.OtpLimiteError:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiadas solicitudes; intente más tarde",
            headers=_NO_STORE,
        ) from None

    # Generate the OTP and its hash.
    try:
        codigo = otp_service.generar_otp()
        codigo_hash = otp_service.hash_otp(pre.id_precotizacion, codigo)
    except otp_service.OtpConfigError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El servicio de verificación no está disponible",
            headers=_NO_STORE,
        ) from None

    # Expire this pre-quotation's previous, unused, still-valid codes. Use the
    # real clock (`clock_timestamp()`, which advances within the transaction,
    # unlike `now()` = transaction start) and set the expiry strictly in the
    # PAST (minus 1 s) so an invalidated code is never considered valid by any
    # later `>=`/`<` comparison nor by the acceptance trigger. Invalidation is
    # NOT consumption: `utilizado` is left FALSE. Only this pre-quotation's own
    # non-employee codes are touched.
    db.query(CodigoVerificacion).filter(
        CodigoVerificacion.id_precotizacion == pre.id_precotizacion,
        CodigoVerificacion.id_empleado.is_(None),
        CodigoVerificacion.utilizado.is_(False),
        CodigoVerificacion.fecha_expiracion >= func.clock_timestamp(),
    ).update(
        {
            CodigoVerificacion.fecha_expiracion: func.clock_timestamp()
            - func.make_interval(0, 0, 0, 0, 0, 0, 1)
        },
        synchronize_session=False,
    )

    # Insert the new code; fecha_expiracion = clock_timestamp() + 10 min on the
    # real DB clock (consistent with the acceptance re-check and the trigger).
    nuevo = CodigoVerificacion(
        id_precotizacion=pre.id_precotizacion,
        id_empleado=None,
        correo_destino=destino,
        codigo_hash=codigo_hash,
        fecha_expiracion=func.clock_timestamp()
        + func.make_interval(0, 0, 0, 0, 0, otp_service.OTP_TTL_MINUTES),
        utilizado=False,
    )
    db.add(nuevo)
    db.flush()

    cuerpo = (
        "Mansillas SIC\n\n"
        "Para confirmar su propuesta, use este código de verificación:\n\n"
        f"    {codigo}\n\n"
        "El código vence en 10 minutos. No lo comparta con nadie.\n"
        "Si usted no solicitó este código, ignore este mensaje."
    )
    try:
        email_service.enviar_correo(
            destino, "Código de verificación de su propuesta", cuerpo, exigir_tls=True
        )
    except email_service.EmailNoConfigurado:
        db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El servicio de verificación no está disponible",
            headers=_NO_STORE,
        ) from None
    except email_service.EmailInvalido:
        db.rollback()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El servicio de verificación no está disponible",
            headers=_NO_STORE,
        ) from None
    except email_service.EmailEnvioError:
        # SMTP failure → full rollback: the new code is not persisted and the
        # previously expired codes recover their state (same transaction).
        db.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "No fue posible enviar el código de verificación",
            headers=_NO_STORE,
        ) from None

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.error(
            "El código de la precotización %s se envió pero falló la persistencia; "
            "no se afirma reversión del correo",
            pre.id_precotizacion,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible completar la solicitud",
            headers=_NO_STORE,
        ) from None

    return OtpResponse(mensaje="Se ha solicitado el código de verificación.")


_MAX_BODY_ACEPTAR = 4096  # bytes; the acceptance body is tiny


async def _leer_cuerpo_acotado(peticion: Request) -> bytes:
    """Read the request body bounded by `_MAX_BODY_ACEPTAR`, streaming.

    Reading is done in this async dependency so the acceptance handler can be a
    plain `def` (run by FastAPI in a worker thread with its own Session), which
    avoids blocking the event loop with synchronous SQLAlchemy calls. Aborts
    early with a sanitized 422 instead of buffering an arbitrarily large body.
    """
    trozos: list[bytes] = []
    total = 0
    async for trozo in peticion.stream():
        total += len(trozo)
        if total > _MAX_BODY_ACEPTAR:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Solicitud inválida",
                headers=_NO_STORE,
            )
        trozos.append(trozo)
    return b"".join(trozos)


class AceptarRequest(BaseModel):
    """Acceptance input (documented in OpenAPI; validated manually too).

    `codigo` is a strict string (preserves leading zeros); numbers/null/lists/
    objects are rejected. Extra fields are forbidden.
    """

    model_config = ConfigDict(extra="forbid")

    nombre_aceptante: StrictStr
    cargo_aceptante: StrictStr
    codigo: StrictStr


class AceptacionOut(BaseModel):
    estado: str
    fecha_aceptacion: datetime


@router.post(
    "/propuesta/{token}/aceptar",
    response_model=AceptacionOut,
    responses=RESP_ACEPTAR,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": AceptarRequest.model_json_schema()}
            },
        }
    },
)
def aceptar_propuesta(
    token: str,
    respuesta: Response,
    db: Annotated[Session, Depends(get_db)],
    raw: Annotated[bytes, Depends(_leer_cuerpo_acotado)],
) -> AceptacionOut:
    """Public: accept a proposal with the OTP (HU-15).

    The body (read bounded by an async dependency) is parsed and validated
    locally so a Pydantic 422 never echoes the submitted code. This handler is
    synchronous: FastAPI runs it in a worker thread with its own Session, so the
    blocking SQLAlchemy calls do not block the event loop and no Session is
    shared across threads. The whole acceptance (consume code → insert record →
    trigger transition) runs in one transaction under the Visit-row lock.
    """
    respuesta.headers["Cache-Control"] = "no-store"

    # --- Local, non-echoing body validation (sanitizes pre-handler 422s) ---
    try:
        datos = AceptarRequest.model_validate_json(raw)
    except ValidationError:
        # Never reflect the received body/code.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Datos de aceptación inválidos",
            headers=_NO_STORE,
        ) from None
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Cuerpo JSON inválido", headers=_NO_STORE
        ) from None

    nombre = (datos.nombre_aceptante or "").strip()
    cargo = (datos.cargo_aceptante or "").strip()
    codigo = datos.codigo
    if not nombre or len(nombre) > 150 or not cargo or len(cargo) > 100:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Datos de aceptación inválidos",
            headers=_NO_STORE,
        )
    if not otp_service.es_otp_valido(codigo):
        # Wrong shape of the code → generic 422, no echo.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Datos de aceptación inválidos",
            headers=_NO_STORE,
        )

    # --- Resolve + lock (shared order: Visit first) ---
    try:
        token_uuid = uuid.UUID(token)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No encontrado", headers=_NO_STORE
        ) from None

    pre = db.scalar(select(Precotizacion).where(Precotizacion.token == token_uuid))
    if pre is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No encontrado", headers=_NO_STORE
        )

    if precotizacion_rules.lock_visita(db, pre.id_visita) is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No encontrado", headers=_NO_STORE
        )
    db.refresh(pre)

    if pre.estado != "ENVIADA":
        # Already ACEPTADA, or BORRADOR/ANULADA → not acceptable.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "La propuesta no está disponible para aceptación",
            headers=_NO_STORE,
        )

    if not otp_service.otp_configurado():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El servicio de verificación no está disponible",
            headers=_NO_STORE,
        )

    # An existing acceptance (UNIQUE) means it was already accepted.
    ya = db.scalar(
        select(AceptacionPrecotizacion.id_aceptacion).where(
            AceptacionPrecotizacion.id_precotizacion == pre.id_precotizacion
        )
    )
    if ya is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "La propuesta ya fue aceptada", headers=_NO_STORE
        )

    # --- Select the MOST RECENT issuance for THIS pre-quotation and lock it ---
    # Pick strictly the newest code (highest id_codigo); an earlier issuance must
    # never become acceptable if the newest is used/expired/inconsistent. Lock it
    # FOR UPDATE, then re-check used/expired on the actual wall clock AFTER the
    # lock (clock_timestamp, not the transaction-start now()).
    codigo_row = db.scalar(
        select(CodigoVerificacion)
        .where(
            CodigoVerificacion.id_precotizacion == pre.id_precotizacion,
            CodigoVerificacion.id_empleado.is_(None),
        )
        .order_by(CodigoVerificacion.id_codigo.desc())
        .limit(1)
        .with_for_update()
    )
    if codigo_row is None:
        # No code was ever requested for this pre-quotation.
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Código inválido o expirado", headers=_NO_STORE
        )
    # Re-check validity after acquiring the row lock.
    # Read the server clock as TIMESTAMP WITHOUT TIME ZONE (naive) to match the
    # schema's `fecha_expiracion` column; `clock_timestamp()` is a timestamptz,
    # so without the cast the comparison would mix naive and aware datetimes.
    ahora = db.scalar(select(cast(func.clock_timestamp(), DateTime)))
    if codigo_row.utilizado or codigo_row.fecha_expiracion < ahora:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Código inválido o expirado", headers=_NO_STORE
        )

    # Recipient must match the stored, authorized email.
    try:
        correo_autorizado = email_service.validar_destinatario(pre.correo_cliente or "")
    except email_service.EmailInvalido:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "El servicio de verificación no está disponible",
            headers=_NO_STORE,
        ) from None
    if codigo_row.correo_destino != correo_autorizado:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Código inválido o expirado", headers=_NO_STORE
        )

    # Parse the issuance nonce; a malformed stored hash is an internal
    # inconsistency (500), NOT a client crypto failure (not counted as attempt).
    try:
        nonce = otp_service.extraer_nonce(codigo_row.codigo_hash)
    except otp_service.OtpFormatoError:
        logger.error(
            "codigo_hash malformado para la precotización %s", pre.id_precotizacion
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible procesar la aceptación",
            headers=_NO_STORE,
        ) from None

    # Enforce attempt limits BEFORE verifying.
    try:
        otp_service.control_abuso.verificar_intentos(pre.id_precotizacion, nonce)
    except otp_service.OtpLimiteError:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiados intentos; intente más tarde",
            headers=_NO_STORE,
        ) from None

    # Verify the OTP (HMAC compare_digest). A format error here would be our own
    # inconsistency; the client code shape was already validated.
    try:
        correcto = otp_service.verificar_otp(codigo_row.codigo_hash, pre.id_precotizacion, codigo)
    except otp_service.OtpFormatoError:
        logger.error(
            "codigo_hash malformado para la precotización %s", pre.id_precotizacion
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible procesar la aceptación",
            headers=_NO_STORE,
        ) from None

    if not correcto:
        # Record the failed attempt (in memory, survives the rollback); do not
        # consume the code, insert, or change state. Reaching abuse-control
        # capacity also surfaces as a controlled 429.
        try:
            otp_service.control_abuso.registrar_fallo(pre.id_precotizacion, nonce)
        except otp_service.OtpLimiteError:
            db.rollback()
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Demasiados intentos; intente más tarde",
                headers=_NO_STORE,
            ) from None
        db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Código inválido o expirado", headers=_NO_STORE
        )

    # --- Acceptance transaction: everything below is one protected unit, from
    # consuming the code through the single commit. No intermediate commit. ---
    try:
        codigo_row.utilizado = True
        db.flush()  # ensure the trigger sees utilizado = TRUE

        aceptacion = AceptacionPrecotizacion(
            id_precotizacion=pre.id_precotizacion,
            id_codigo=codigo_row.id_codigo,
            nombre_aceptante=nombre,
            cargo_aceptante=cargo,
            correo_aceptante=correo_autorizado,
        )
        db.add(aceptacion)
        db.flush()  # fires registrar_aceptacion_precotizacion → ENVIADA->ACEPTADA
        db.refresh(aceptacion)
        db.refresh(pre)

        # Verify the trigger actually produced the expected transition before
        # committing; capture the minimal response data now.
        if pre.estado != "ACEPTADA" or aceptacion.fecha_aceptacion is None:
            raise RuntimeError("estado de aceptación inconsistente tras el trigger")
        estado = pre.estado
        fecha = aceptacion.fecha_aceptacion
    except IntegrityError as error:
        db.rollback()
        # Only the two known UNIQUE constraints mean "already accepted" (409);
        # any other integrity error is an internal fault (500).
        restriccion = getattr(getattr(error, "orig", None), "diag", None)
        nombre_restriccion = getattr(restriccion, "constraint_name", "") or ""
        detalle = f"{nombre_restriccion} {error}".lower()
        if (
            "id_precotizacion" in detalle
            or "id_codigo" in detalle
            or "aceptacion_precotizacion" in detalle
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT, "La propuesta ya fue aceptada",
                headers=_NO_STORE,
            ) from None
        logger.error(
            "Error de integridad inesperado al aceptar la precotización %s",
            pre.id_precotizacion,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible registrar la aceptación",
            headers=_NO_STORE,
        ) from None
    except Exception:
        db.rollback()
        logger.error(
            "Fallo al registrar la aceptación de la precotización %s", pre.id_precotizacion
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible registrar la aceptación",
            headers=_NO_STORE,
        ) from None

    # Commit; distinguish a confirmed failure from an uncertain outcome.
    try:
        db.commit()
    except DBAPIError as error:
        try:
            db.rollback()
        except Exception:
            pass
        if getattr(error, "connection_invalidated", False):
            logger.error(
                "Resultado de commit INCIERTO al aceptar la precotización %s "
                "(conexión invalidada); no se afirma que no ocurrió",
                pre.id_precotizacion,
            )
        else:
            logger.error(
                "Fallo de commit confirmado al aceptar la precotización %s",
                pre.id_precotizacion,
            )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible completar la aceptación",
            headers=_NO_STORE,
        ) from None
    except Exception:
        db.rollback()
        logger.error(
            "Fallo de commit al aceptar la precotización %s", pre.id_precotizacion
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No fue posible completar la aceptación",
            headers=_NO_STORE,
        ) from None

    return AceptacionOut(estado=estado, fecha_aceptacion=fecha)
