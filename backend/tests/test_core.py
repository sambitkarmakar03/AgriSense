from app.core.config import normalize_database_url


def test_postgresql_urls_use_psycopg_3_driver():
    assert normalize_database_url("postgres://db.example/agrisense") == "postgresql+psycopg://db.example/agrisense"
    assert normalize_database_url("postgresql://db.example/agrisense") == "postgresql+psycopg://db.example/agrisense"
    assert normalize_database_url("sqlite:///./agrisense.db") == "sqlite:///./agrisense.db"


def test_cors_rejects_wildcard_origin():
    import pytest
    from pydantic import ValidationError
    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(cors_origins="*")
