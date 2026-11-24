import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Cargar variables del .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("No se encontró DATABASE_URL en el archivo .env")

try:
    # Crear conexión
    engine = create_engine(DATABASE_URL)

    # Ejecutar una consulta de prueba
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT current_database(), version();")
        )

        database, version = result.fetchone()

        print("CONEXIÓN EXITOSA")
        print(f"Base de datos: {database}")
        print(f"PostgreSQL: {version[:60]}")

except Exception as error:
    print("ERROR AL CONECTAR CON SUPABASE")
    print(error)
