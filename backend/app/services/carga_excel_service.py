"""Lógica de negocio de la carga masiva de empleados por Excel (HU-19, R1-R4).

El router solo traduce HTTP; aquí viven la lectura del `.xlsx`, la validación de
formato, el procesamiento fila por fila y el buscar-o-crear atado a `id_empresa`.

Decisión técnica (ver design.md): la lectura `.xlsx` usa `openpyxl`. El
aislamiento multiempresa es estructural: el service nunca lee `id_empresa` del
archivo; usa siempre el `id_empresa` del `ADMIN_CLIENTE` autenticado.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from openpyxl import load_workbook
from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from ..models import Departamento, Empleado, Sede

# Formato_Carga: columnas que el archivo debe traer (R2.2) y las opcionales.
COLUMNAS_OBLIGATORIAS = ("sede", "departamento", "nombre", "cargo")
COLUMNAS_OPCIONALES = ("documento", "correo")


@dataclass
class ErrorFila:
    """Entrada del Reporte_Resultado: fila rechazada con su motivo (R3.2).

    `fila` es 1-based sobre las filas de datos (la primera fila de datos bajo
    los encabezados es la fila 1), coherente con el schema `ErrorFila` del router.
    """

    fila: int
    motivo: str


@dataclass
class ReporteResultado:
    """Resultado de una carga masiva (Reporte_Resultado, R3.4).

    - `total_procesadas`: número de filas de datos leídas del archivo.
    - `total_aplicadas`: número de filas válidas efectivamente aplicadas.
    - `errores`: lista de `ErrorFila` de las filas rechazadas.

    Invariante: `total_procesadas == total_aplicadas + len(errores)`.
    """

    nombre_archivo: str
    total_procesadas: int = 0
    total_aplicadas: int = 0
    errores: list[ErrorFila] = field(default_factory=list)


class FormatoInvalido(Exception):
    """El contenido no es un `.xlsx` legible (→ 400).

    El router también valida la extensión antes de leer; esta excepción cubre
    el caso de un contenido corrupto o que no es un libro de Excel.
    """


class ColumnasFaltantes(Exception):
    """Faltan columnas obligatorias del Formato_Carga (→ 400).

    Lleva en `columnas` la lista de columnas obligatorias ausentes para que el
    router informe cuáles corregir (R2.2).
    """

    def __init__(self, columnas: list[str]) -> None:
        self.columnas = columnas
        super().__init__(
            "Faltan columnas obligatorias: " + ", ".join(columnas)
        )


class ArchivoVacio(Exception):
    """El archivo no contiene filas de datos (→ 400) (R2.3)."""


def leer_filas(contenido: bytes) -> list[dict[str, str | None]]:
    """Lee un `.xlsx` y devuelve sus filas de datos como dicts por columna.

    Abre el libro con `openpyxl`, toma la primera fila como encabezados, los
    normaliza (minúsculas y sin espacios alrededor) y construye un dict por cada
    fila de datos con una clave por cada columna conocida del Formato_Carga
    (obligatorias y opcionales). Los valores se normalizan a texto recortado o a
    `None` cuando la celda está vacía.

    Raises
    ------
    FormatoInvalido
        Si el contenido no es un libro `.xlsx` legible.
    ColumnasFaltantes
        Si falta alguna columna obligatoria del Formato_Carga.
    ArchivoVacio
        Si no hay ninguna fila de datos bajo los encabezados.
    """
    try:
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl lanza varias excepciones según el daño
        raise FormatoInvalido("El contenido no es un archivo .xlsx válido") from exc

    try:
        hoja = libro.active
        filas = hoja.iter_rows(values_only=True)

        try:
            encabezados_crudos = next(filas)
        except StopIteration:
            # Libro sin ninguna fila: ni siquiera hay encabezados.
            raise ArchivoVacio("El archivo está vacío")

        # Normalizamos los encabezados: índice de columna -> nombre normalizado.
        encabezados: dict[int, str] = {}
        for indice, valor in enumerate(encabezados_crudos):
            nombre = _normalizar(valor)
            if nombre:
                encabezados[indice] = nombre.lower()

        presentes = set(encabezados.values())
        faltantes = [c for c in COLUMNAS_OBLIGATORIAS if c not in presentes]
        if faltantes:
            raise ColumnasFaltantes(faltantes)

        columnas_conocidas = COLUMNAS_OBLIGATORIAS + COLUMNAS_OPCIONALES

        resultado: list[dict[str, str | None]] = []
        for celdas in filas:
            fila: dict[str, str | None] = {columna: None for columna in columnas_conocidas}
            tiene_valor = False
            for indice, valor in enumerate(celdas):
                nombre = encabezados.get(indice)
                if nombre is None or nombre not in columnas_conocidas:
                    continue
                normalizado = _normalizar(valor)
                fila[nombre] = normalizado
                if normalizado is not None:
                    tiene_valor = True
            # Ignoramos las filas completamente vacías (relleno al final del libro).
            if tiene_valor:
                resultado.append(fila)

        if not resultado:
            raise ArchivoVacio("El archivo está vacío")

        return resultado
    finally:
        libro.close()


def _normalizar(valor: object) -> str | None:
    """Convierte una celda a texto recortado o `None` si está vacía.

    `openpyxl` puede devolver números, fechas o `None`; los pasamos a `str` y
    recortamos espacios. Una celda vacía o con solo espacios se trata como
    ausente (`None`) para que la validación por fila la detecte como obligatoria
    no informada.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _resolver_sede(db: Session, id_empresa: int, nombre: str) -> Sede:
    """Busca-o-crea una sede de la empresa por `(id_empresa, nombre)` (R4.1, R4.2).

    Reutiliza la sede existente que coincida con la restricción
    `UNIQUE (id_empresa, nombre)` del esquema; si no existe, crea una nueva
    `Sede` asociada a `id_empresa`. El `id_empresa` es siempre el recibido (el
    del `ADMIN_CLIENTE` autenticado), nunca un valor del archivo.

    La nueva sede se agrega y se vacía (`flush`) para que quede disponible su
    `id_sede` dentro de la misma transacción, sin confirmar todavía: el `commit`
    único lo hace `procesar_carga` al final.
    """
    sede = db.execute(
        select(Sede).where(Sede.id_empresa == id_empresa, Sede.nombre == nombre)
    ).scalar_one_or_none()
    if sede is not None:
        return sede

    sede = Sede(id_empresa=id_empresa, nombre=nombre)
    db.add(sede)
    db.flush()
    return sede


def _resolver_departamento(
    db: Session, id_empresa: int, id_sede: int, nombre: str
) -> Departamento:
    """Busca-o-crea un departamento por `(id_empresa, id_sede, nombre)` (R4.3, R4.4).

    Reutiliza el departamento existente que coincida con la restricción
    `UNIQUE (id_empresa, id_sede, nombre)` del esquema; si no existe, crea uno
    nuevo asociado a la empresa y la sede resueltas. El `id_empresa` es siempre
    el recibido, nunca un valor del archivo.

    Igual que `_resolver_sede`, hace `flush` para disponer del `id_departamento`
    dentro de la transacción sin confirmar (el `commit` lo hace `procesar_carga`).
    """
    departamento = db.execute(
        select(Departamento).where(
            Departamento.id_empresa == id_empresa,
            Departamento.id_sede == id_sede,
            Departamento.nombre == nombre,
        )
    ).scalar_one_or_none()
    if departamento is not None:
        return departamento

    departamento = Departamento(
        id_empresa=id_empresa, id_sede=id_sede, nombre=nombre
    )
    db.add(departamento)
    db.flush()
    return departamento


def _upsert_empleado(
    db: Session,
    id_empresa: int,
    id_sede: int,
    id_departamento: int,
    fila: dict[str, str | None],
) -> Empleado:
    """Crea o actualiza un empleado de la empresa según su identidad (R4.5, R4.6).

    Identifica al empleado por `documento` o por `correo` cuando están
    informados en la fila, acotando siempre a `id_empresa` recibido (nunca del
    archivo). Si existe, actualiza `id_sede`, `id_departamento`, `nombre`,
    `cargo` y los opcionales presentes en la fila. Si no, crea un `Empleado`
    nuevo con `activo=True`.

    La identidad se evalúa dentro de `id_empresa` (coherente con
    `UNIQUE (id_empresa, documento)`), de modo que un mismo documento/correo en
    otra empresa no se confunde con este.

    Devuelve el empleado creado o actualizado. No confirma la transacción: el
    `commit` único lo hace `procesar_carga` tras procesar todas las filas.
    """
    documento = fila.get("documento")
    correo = fila.get("correo")

    empleado: Empleado | None = None
    condiciones = []
    if documento is not None:
        condiciones.append(Empleado.documento == documento)
    if correo is not None:
        condiciones.append(Empleado.correo == correo)
    if condiciones:
        empleado = db.execute(
            select(Empleado).where(
                Empleado.id_empresa == id_empresa, or_(*condiciones)
            )
        ).scalars().first()

    if empleado is not None:
        empleado.id_sede = id_sede
        empleado.id_departamento = id_departamento
        empleado.nombre = fila["nombre"]
        empleado.cargo = fila["cargo"]
        if documento is not None:
            empleado.documento = documento
        if correo is not None:
            empleado.correo = correo
        db.flush()
        return empleado

    empleado = Empleado(
        id_empresa=id_empresa,
        id_sede=id_sede,
        id_departamento=id_departamento,
        nombre=fila["nombre"],
        cargo=fila["cargo"],
        documento=documento,
        correo=correo,
        activo=True,
    )
    db.add(empleado)
    db.flush()
    return empleado


def _validar_fila(fila: dict[str, str | None], id_empresa: int) -> str | None:
    """Valida una fila de forma independiente; devuelve el motivo de rechazo o None.

    Dos razones de rechazo (R3.2, R1.4):

    - Alguna columna obligatoria del Formato_Carga está vacía (`None`).
    - La fila referencia una empresa distinta de la Empresa_Propia. El
      Formato_Carga no trae columna de empresa, así que estructuralmente una
      fila no puede apuntar a otra empresa; esta comprobación es defensiva para
      el caso de que en el futuro llegue una columna `id_empresa`/`empresa` con
      un valor distinto al del admin autenticado.

    Devolver `None` significa que la fila es válida.
    """
    faltantes = [c for c in COLUMNAS_OBLIGATORIAS if not fila.get(c)]
    if faltantes:
        return "Faltan columnas obligatorias: " + ", ".join(faltantes)

    empresa_fila = fila.get("id_empresa")
    if empresa_fila is not None and str(empresa_fila) != str(id_empresa):
        return "La fila referencia una empresa distinta de la propia"

    return None


def procesar_carga(
    db: Session,
    *,
    id_empresa: int,
    id_usuario: int,
    nombre_archivo: str,
    contenido: bytes,
) -> ReporteResultado:
    """Procesa el `.xlsx` fila por fila, aplica las válidas y devuelve el reporte.

    Flujo (ver design.md / R3):

    1. `leer_filas` valida el formato completo (extensión/columnas/vacío) y
       puede lanzar `FormatoInvalido`/`ColumnasFaltantes`/`ArchivoVacio`. Estas
       validaciones abortan toda la carga antes de tocar la base.
    2. Cada fila se valida de forma independiente (`_validar_fila`): las
       inválidas registran un `ErrorFila` (número 1-based + motivo) y no se
       aplican; las válidas se aplican con buscar-o-crear sede → departamento →
       upsert empleado (R3.1, R3.2, R3.3).
    3. El aislamiento multiempresa es estructural: se usa siempre `id_empresa`
       (el del `ADMIN_CLIENTE` autenticado), nunca un valor del archivo (R1.3).
    4. Tras procesar todas las filas se registra el resumen en `carga_excel` por
       SQL `text()` y se confirma todo con un único `commit`, en la misma
       transacción que las filas válidas (R3.5). Las filas inválidas no aportan
       cambios.

    Devuelve un `ReporteResultado` con el total procesado, el total aplicado y
    la lista de `ErrorFila` (R3.4).
    """
    filas = leer_filas(contenido)

    reporte = ReporteResultado(nombre_archivo=nombre_archivo)
    reporte.total_procesadas = len(filas)

    for numero, fila in enumerate(filas, start=1):
        motivo = _validar_fila(fila, id_empresa)
        if motivo is not None:
            reporte.errores.append(ErrorFila(fila=numero, motivo=motivo))
            continue

        sede = _resolver_sede(db, id_empresa, fila["sede"])
        departamento = _resolver_departamento(
            db, id_empresa, sede.id_sede, fila["departamento"]
        )
        _upsert_empleado(
            db, id_empresa, sede.id_sede, departamento.id_departamento, fila
        )
        reporte.total_aplicadas += 1

    _registrar_carga(
        db,
        id_empresa=id_empresa,
        id_usuario=id_usuario,
        nombre_archivo=nombre_archivo,
        registros_procesados=reporte.total_procesadas,
        registros_con_error=len(reporte.errores),
    )

    # `get_db` entrega una Session ORM que revierte al cerrar la petición: las
    # filas válidas y el registro en carga_excel deben confirmarse con un único
    # commit al final de todo el procesamiento.
    db.commit()

    return reporte


def _registrar_carga(
    db: Session,
    *,
    id_empresa: int,
    id_usuario: int,
    nombre_archivo: str,
    registros_procesados: int,
    registros_con_error: int,
) -> None:
    """Inserta el resumen de la carga en `carga_excel` por SQL `text()` (R3.5).

    Sigue el patrón de `auth_service`/`usuarios_service` (sin modelo ORM para
    esta tabla). No confirma la transacción: el `commit` lo hace `procesar_carga`
    para que el registro quede en la misma transacción que las filas aplicadas.
    """
    db.execute(
        text(
            """
            INSERT INTO carga_excel
                (id_empresa, id_usuario, nombre_archivo,
                 registros_procesados, registros_con_error)
            VALUES
                (:id_empresa, :id_usuario, :nombre_archivo,
                 :registros_procesados, :registros_con_error)
            """
        ),
        {
            "id_empresa": id_empresa,
            "id_usuario": id_usuario,
            "nombre_archivo": nombre_archivo,
            "registros_procesados": registros_procesados,
            "registros_con_error": registros_con_error,
        },
    )
