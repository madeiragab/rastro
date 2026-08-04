"""Engine, sessao e base declarativa do SQLAlchemy."""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Garante a extensao PostGIS e cria as tabelas.

    Para o MVP as tabelas sao criadas por metadata. Quando o schema estabilizar,
    trocar por Alembic -- create_all nao versiona migracao.
    """
    from app import models  # noqa: F401  (registra os modelos no metadata)

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

    Base.metadata.create_all(bind=engine)
