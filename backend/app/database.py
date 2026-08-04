"""Engine, sessao e base declarativa do SQLAlchemy."""

from collections.abc import Generator
from pathlib import Path

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
    """Leva o banco ate a ultima migracao.

    Alembic, e nao `create_all`: com `create_all`, uma coluna nova exigia apagar
    o banco inteiro, porque ele so cria tabela que ainda nao existe -- nunca
    altera a que existe. Isso ja derrubou a aplicacao uma vez, com a API subindo
    e toda consulta batendo em coluna inexistente.
    """
    from alembic import command
    from alembic.config import Config

    raiz = Path(__file__).resolve().parent.parent

    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("script_location", str(raiz / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)

    command.upgrade(config, "head")


def criar_schema_direto() -> None:
    """Cria as tabelas por metadata, sem passar pelo Alembic.

    Existe para a suite de testes, que monta e derruba o schema a cada sessao e
    nao ganha nada em reexecutar o historico de migracoes.
    """
    from app import models  # noqa: F401  (registra os modelos no metadata)

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))

    Base.metadata.create_all(bind=engine)
