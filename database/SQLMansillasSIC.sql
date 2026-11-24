-- ============================================================
-- MANSILLAS SIC - MODELO DE DATOS MVP AJUSTADO
-- PostgreSQL 14+
-- Mantiene un alcance universitario/MVP, con integridad básica.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE SCHEMA IF NOT EXISTS mansillas;
SET search_path TO mansillas, public;

-- 1. EMPRESAS CLIENTES
CREATE TABLE empresa (
    id_empresa BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    nit VARCHAR(30) NOT NULL UNIQUE,
    correo VARCHAR(150),
    telefono VARCHAR(30),
    -- 1=solo consulta; 2=consulta y tickets;
    -- 3=solo el administrador del cliente crea tickets.
    permiso_qr SMALLINT NOT NULL DEFAULT 1 CHECK (permiso_qr IN (1, 2, 3)),
    activa BOOLEAN NOT NULL DEFAULT TRUE
);

-- 2. SEDES
CREATE TABLE sede (
    id_sede BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_empresa BIGINT NOT NULL REFERENCES empresa(id_empresa),
    nombre VARCHAR(150) NOT NULL,
    direccion VARCHAR(250),
    ciudad VARCHAR(100),
    UNIQUE (id_empresa, nombre),
    UNIQUE (id_empresa, id_sede)
);

-- 3. ÁREAS / DEPARTAMENTOS
CREATE TABLE departamento (
    id_departamento BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_empresa BIGINT NOT NULL REFERENCES empresa(id_empresa),
    id_sede BIGINT NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    UNIQUE (id_empresa, id_sede, nombre),
    UNIQUE (id_empresa, id_departamento),
    FOREIGN KEY (id_empresa, id_sede)
        REFERENCES sede(id_empresa, id_sede)
);

-- 4. USUARIOS Y ROLES
CREATE TABLE usuario (
    id_usuario BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_empresa BIGINT REFERENCES empresa(id_empresa),
    nombre VARCHAR(150) NOT NULL,
    correo VARCHAR(150) NOT NULL UNIQUE,
    password_hash TEXT,
    rol VARCHAR(30) NOT NULL CHECK (rol IN (
        'COMERCIAL_MANSILLAS', 'TECNICO',
        'ADMIN_CLIENTE', 'EMPLEADO_CLIENTE'
    )),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (
        (rol IN ('ADMIN_CLIENTE', 'EMPLEADO_CLIENTE') AND id_empresa IS NOT NULL)
        OR
        (rol IN ('COMERCIAL_MANSILLAS', 'TECNICO') AND id_empresa IS NULL)
    )
);

-- 5. EMPLEADOS DEL CLIENTE
CREATE TABLE empleado (
    id_empleado BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_empresa BIGINT NOT NULL REFERENCES empresa(id_empresa),
    id_sede BIGINT NOT NULL,
    id_departamento BIGINT NOT NULL,
    id_usuario BIGINT UNIQUE REFERENCES usuario(id_usuario),
    nombre VARCHAR(150) NOT NULL,
    documento VARCHAR(30),
    correo VARCHAR(150),
    cargo VARCHAR(100) NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (id_empresa, id_empleado),
    UNIQUE (id_empresa, documento),
    FOREIGN KEY (id_empresa, id_sede)
        REFERENCES sede(id_empresa, id_sede),
    FOREIGN KEY (id_empresa, id_departamento)
        REFERENCES departamento(id_empresa, id_departamento)
);

-- 6. VISITAS
CREATE TABLE visita (
    id_visita BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_empresa BIGINT NOT NULL REFERENCES empresa(id_empresa),
    id_sede BIGINT NOT NULL,
    id_comercial BIGINT NOT NULL REFERENCES usuario(id_usuario),
    id_tecnico BIGINT NOT NULL REFERENCES usuario(id_usuario),
    fecha_programada TIMESTAMP,
    cantidad_estimada INTEGER NOT NULL CHECK (cantidad_estimada >= 0),
    estado VARCHAR(20) NOT NULL DEFAULT 'PROGRAMADA'
        CHECK (estado IN ('PROGRAMADA', 'EN_CURSO', 'FINALIZADA', 'CANCELADA')),
    observaciones TEXT,
    UNIQUE (id_empresa, id_visita),
    FOREIGN KEY (id_empresa, id_sede)
        REFERENCES sede(id_empresa, id_sede)
);
CREATE INDEX idx_visita_tecnico_estado ON visita(id_tecnico, estado);

-- 7. SILLAS Y QR
CREATE SEQUENCE secuencia_qr START 1;

CREATE TABLE silla (
    id_silla BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_empresa BIGINT NOT NULL REFERENCES empresa(id_empresa),
    id_visita BIGINT NOT NULL,
    id_sede BIGINT NOT NULL,
    id_departamento BIGINT NOT NULL,
    id_empleado BIGINT NOT NULL,
    cargo VARCHAR(100) NOT NULL,
    numero_qr BIGINT NOT NULL DEFAULT nextval('secuencia_qr'),
    codigo_qr VARCHAR(30) NOT NULL UNIQUE,
    token_publico UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    serial_antiguo VARCHAR(100),
    observaciones TEXT,
    estado VARCHAR(25) NOT NULL DEFAULT 'REGISTRADA'
        CHECK (estado IN ('REGISTRADA', 'EN_REVISION', 'CAMBIO_SUGERIDO', 'BAJA')),
    fecha_registro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id_empresa, serial_antiguo),
    FOREIGN KEY (id_empresa, id_visita)
        REFERENCES visita(id_empresa, id_visita),
    FOREIGN KEY (id_empresa, id_sede)
        REFERENCES sede(id_empresa, id_sede),
    FOREIGN KEY (id_empresa, id_departamento)
        REFERENCES departamento(id_empresa, id_departamento),
    FOREIGN KEY (id_empresa, id_empleado)
        REFERENCES empleado(id_empresa, id_empleado)
);

CREATE OR REPLACE FUNCTION generar_codigo_qr()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.codigo_qr IS NULL OR NEW.codigo_qr = '' THEN
        NEW.codigo_qr := 'SIC-' || LPAD(NEW.numero_qr::TEXT, 8, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_generar_codigo_qr
BEFORE INSERT ON silla
FOR EACH ROW EXECUTE FUNCTION generar_codigo_qr();

CREATE INDEX idx_silla_visita ON silla(id_visita);
CREATE INDEX idx_silla_empresa ON silla(id_empresa);

-- 8. CATÁLOGO DE COMPONENTES
CREATE TABLE componente (
    id_componente BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE
);

INSERT INTO componente(nombre) VALUES
('Cilindros'), ('Ruedas'), ('Bases'),
('Asiento / Espaldar'), ('Malla');

-- 9. ESTADO DE COMPONENTES POR SILLA
CREATE TABLE silla_componente (
    id_silla_componente BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_silla BIGINT NOT NULL REFERENCES silla(id_silla),
    id_componente BIGINT NOT NULL REFERENCES componente(id_componente),
    estado VARCHAR(20) NOT NULL
        CHECK (estado IN ('BUENO', 'MANTENIMIENTO', 'DANADO', 'NO_APLICA')),
    observacion TEXT,
    UNIQUE (id_silla, id_componente)
);

CREATE VIEW vista_estado_mantenimiento AS
SELECT
    s.id_silla,
    s.codigo_qr,
    COUNT(sc.id_componente) FILTER (WHERE sc.estado <> 'NO_APLICA') AS total_componentes,
    COUNT(sc.id_componente) FILTER (WHERE sc.estado = 'DANADO') AS componentes_danados,
    CASE
        WHEN COUNT(sc.id_componente) FILTER (WHERE sc.estado <> 'NO_APLICA') = 0
            THEN FALSE
        ELSE
            COUNT(sc.id_componente) FILTER (WHERE sc.estado = 'DANADO')::DECIMAL
            / COUNT(sc.id_componente) FILTER (WHERE sc.estado <> 'NO_APLICA') > 0.70
    END AS sugerir_cambio
FROM silla s
LEFT JOIN silla_componente sc ON sc.id_silla = s.id_silla
GROUP BY s.id_silla, s.codigo_qr;

-- 10. FOTOGRAFÍAS
CREATE TABLE fotografia (
    id_fotografia BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_silla BIGINT NOT NULL REFERENCES silla(id_silla),
    ruta_archivo TEXT NOT NULL,
    fecha_subida TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 11. PRECOTIZACIÓN
CREATE TABLE precotizacion (
    id_precotizacion BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_empresa BIGINT NOT NULL REFERENCES empresa(id_empresa),
    id_visita BIGINT NOT NULL,
    token UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    estado VARCHAR(20) NOT NULL DEFAULT 'BORRADOR'
        CHECK (estado IN ('BORRADOR', 'ENVIADA', 'ACEPTADA', 'ANULADA')),
    correo_cliente VARCHAR(150),
    fecha_envio TIMESTAMP,
    fecha_aceptacion TIMESTAMP,
    creada_por BIGINT NOT NULL REFERENCES usuario(id_usuario),
    observaciones TEXT,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id_empresa, id_precotizacion),
    FOREIGN KEY (id_empresa, id_visita)
        REFERENCES visita(id_empresa, id_visita)
);

-- Impide modificar la precotización una vez aceptada.
CREATE OR REPLACE FUNCTION impedir_edicion_precotizacion_aceptada()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.estado = 'ACEPTADA' THEN
        RAISE EXCEPTION 'La precotización aceptada no puede modificarse ni eliminarse';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bloquear_precotizacion_aceptada
BEFORE UPDATE OR DELETE ON precotizacion
FOR EACH ROW EXECUTE FUNCTION impedir_edicion_precotizacion_aceptada();

-- 12. ACCESOS AL ENLACE PÚBLICO DE PRECOTIZACIÓN
CREATE TABLE acceso_precotizacion (
    id_acceso BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_precotizacion BIGINT NOT NULL REFERENCES precotizacion(id_precotizacion),
    fecha_acceso TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ip VARCHAR(45),
    navegador VARCHAR(150),
    sistema_operativo VARCHAR(150)
);

-- 13. CÓDIGOS DE VERIFICACIÓN
-- Se usan tanto para aceptar precotizaciones como para identificar empleados
-- cuando acceden a funciones del QR que requieren identificación.
CREATE TABLE codigo_verificacion (
    id_codigo BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_precotizacion BIGINT REFERENCES precotizacion(id_precotizacion),
    id_empleado BIGINT REFERENCES empleado(id_empleado),
    correo_destino VARCHAR(150) NOT NULL,
    codigo_hash TEXT NOT NULL,
    fecha_expiracion TIMESTAMP NOT NULL,
    utilizado BOOLEAN NOT NULL DEFAULT FALSE,
    CHECK (
        (id_precotizacion IS NOT NULL AND id_empleado IS NULL)
        OR
        (id_precotizacion IS NULL AND id_empleado IS NOT NULL)
    )
);

-- 14. ACEPTACIÓN DE PRECOTIZACIÓN
CREATE TABLE aceptacion_precotizacion (
    id_aceptacion BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_precotizacion BIGINT NOT NULL UNIQUE REFERENCES precotizacion(id_precotizacion),
    id_codigo BIGINT NOT NULL UNIQUE REFERENCES codigo_verificacion(id_codigo),
    nombre_aceptante VARCHAR(150) NOT NULL,
    cargo_aceptante VARCHAR(100) NOT NULL,
    correo_aceptante VARCHAR(150) NOT NULL,
    fecha_aceptacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Al registrar aceptación, se marca la precotización como aceptada.
-- El backend debe validar hash, vencimiento y correo antes de insertar.
CREATE OR REPLACE FUNCTION registrar_aceptacion_precotizacion()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM codigo_verificacion cv
        WHERE cv.id_codigo = NEW.id_codigo
          AND cv.id_precotizacion = NEW.id_precotizacion
          AND cv.utilizado = TRUE
          AND cv.fecha_expiracion >= CURRENT_TIMESTAMP
    ) THEN
        RAISE EXCEPTION 'El código de verificación no es válido para esta precotización';
    END IF;

    UPDATE precotizacion
       SET estado = 'ACEPTADA',
           fecha_aceptacion = NEW.fecha_aceptacion
     WHERE id_precotizacion = NEW.id_precotizacion
       AND estado = 'ENVIADA';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'La precotización no está disponible para aceptación';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_registrar_aceptacion
BEFORE INSERT ON aceptacion_precotizacion
FOR EACH ROW EXECUTE FUNCTION registrar_aceptacion_precotizacion();

-- 15. COTIZACIÓN: solo se crea después de la aceptación.
CREATE TABLE cotizacion (
    id_cotizacion BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_precotizacion BIGINT NOT NULL UNIQUE
        REFERENCES precotizacion(id_precotizacion),
    numero VARCHAR(50) UNIQUE,
    valor_total NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (valor_total >= 0),
    detalle TEXT,
    estado VARCHAR(20) NOT NULL DEFAULT 'BORRADOR'
        CHECK (estado IN ('BORRADOR', 'ENVIADA', 'APROBADA', 'RECHAZADA')),
    creada_por BIGINT NOT NULL REFERENCES usuario(id_usuario),
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION validar_cotizacion_tras_aceptacion()
RETURNS TRIGGER AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM precotizacion p
        WHERE p.id_precotizacion = NEW.id_precotizacion
          AND p.estado = 'ACEPTADA'
    ) THEN
        RAISE EXCEPTION 'Solo se puede cotizar después de aceptar la precotización';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cotizacion_tras_aceptacion
BEFORE INSERT OR UPDATE OF id_precotizacion ON cotizacion
FOR EACH ROW EXECUTE FUNCTION validar_cotizacion_tras_aceptacion();

-- 16. TICKETS Y COMENTARIOS
CREATE TABLE ticket (
    id_ticket BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_silla BIGINT NOT NULL REFERENCES silla(id_silla),
    id_usuario BIGINT REFERENCES usuario(id_usuario),
    asunto VARCHAR(150) NOT NULL,
    descripcion TEXT NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'ABIERTO'
        CHECK (estado IN ('ABIERTO', 'EN_GESTION', 'RESUELTO', 'CERRADO')),
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE comentario_ticket (
    id_comentario BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_ticket BIGINT NOT NULL REFERENCES ticket(id_ticket),
    id_usuario BIGINT REFERENCES usuario(id_usuario),
    comentario TEXT NOT NULL,
    fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 17. SESIONES DE USUARIOS INTERNOS Y ADMINISTRADORES
-- El servidor guarda solo el hash del token de sesión.
CREATE TABLE sesion_usuario (
    id_sesion BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_usuario BIGINT NOT NULL REFERENCES usuario(id_usuario),
    token_hash TEXT NOT NULL UNIQUE,
    fecha_inicio TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ultima_actividad TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_expiracion TIMESTAMP NOT NULL,
    fecha_cierre TIMESTAMP,
    CHECK (fecha_expiracion > fecha_inicio)
);
CREATE INDEX idx_sesion_usuario_activa
    ON sesion_usuario(id_usuario, fecha_expiracion)
    WHERE fecha_cierre IS NULL;

-- 18. REGISTRO BÁSICO DE CARGAS EXCEL
CREATE TABLE carga_excel (
    id_carga BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_empresa BIGINT NOT NULL REFERENCES empresa(id_empresa),
    id_usuario BIGINT NOT NULL REFERENCES usuario(id_usuario),
    nombre_archivo VARCHAR(255) NOT NULL,
    fecha_carga TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    registros_procesados INTEGER NOT NULL DEFAULT 0 CHECK (registros_procesados >= 0),
    registros_con_error INTEGER NOT NULL DEFAULT 0 CHECK (registros_con_error >= 0),
    observaciones TEXT
);

-- ============================================================
-- REGLAS QUE DEBE APLICAR EL BACKEND
-- ============================================================
-- 1. Las sillas no se limitan por cantidad_estimada; contar las registradas.
-- 2. Para crear una silla, enviar codigo_qr='' o NULL para generar SIC-00000001...
-- 3. El QR contiene token_publico/URL, nunca datos personales.
-- 4. En QR público mostrar solo información básica. Para tickets/comentarios,
--    identificar al empleado por correo/documento y OTP enviado a su correo.
-- 5. Aplicar empresa.permiso_qr: 1 consulta; 2 consulta y tickets;
--    3 tickets únicamente por ADMIN_CLIENTE.
-- 6. Validar roles en cada endpoint y que el usuario pertenezca a la empresa
--    del recurso. Las FK compuestas evitan cruces empresa-visita/sede/empleado.
-- 7. COMERCIAL_MANSILLAS, TECNICO y ADMIN_CLIENTE deben iniciar sesión.
--    EMPLEADO_CLIENTE puede identificarse en el flujo QR mediante OTP.
-- 8. Guardar hash del token de sesión; actualizar ultima_actividad y cerrar
--    (fecha_cierre) al salir o al vencer el tiempo de inactividad.
-- 9. Al aceptar precotización, validar el OTP (hash, correo y expiración),
--    marcar codigo_verificacion.utilizado=TRUE e insertar aceptación en una
--    misma transacción. La BD cambia el estado a ACEPTADA y bloquea su edición.
-- 10. Exportar QR/CSV/XLSX, enviar correos y procesar el Excel son funciones
--     del backend; las tablas almacenan los datos, no generan esos archivos.
-- 11. Las fotografías se guardan en almacenamiento de archivos; ruta_archivo
--     conserva su ubicación.
-- 12. La vista vista_estado_mantenimiento calcula la sugerencia >70%.
-- ============================================================
