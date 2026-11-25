from app.db import normalizar_database_url


def test_anade_driver_psycopg_a_url_sin_driver():
    assert normalizar_database_url(
        "postgresql://user:pass@host:5432/postgres"
    ) == "postgresql+psycopg://user:pass@host:5432/postgres"


def test_respeta_driver_explicito():
    url = "postgresql+psycopg://user:pass@host:5432/postgres"
    assert normalizar_database_url(url) == url


def test_no_toca_otras_urls():
    url = "sqlite+pysqlite:///local.db"
    assert normalizar_database_url(url) == url
