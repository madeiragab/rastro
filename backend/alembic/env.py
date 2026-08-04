"""Ambiente do Alembic.

A URL do banco vem de `app.config`, nunca do alembic.ini: um unico lugar
dizendo onde o banco esta.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.database import Base
from app import models  # noqa: F401  (registra os modelos no metadata)

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

# Tabelas e indices que o PostGIS cria e mantem sozinho. Sem esta exclusao, o
# autogenerate propoe apagar `spatial_ref_sys` a cada migracao nova.
IGNORAR_TABELAS = {"spatial_ref_sys"}


def incluir_objeto(objeto, nome, tipo, reflexivo, comparar_com):
    if tipo == "table" and nome in IGNORAR_TABELAS:
        return False
    # O GeoAlchemy2 cria os indices espaciais por conta propria, junto da
    # coluna. Deixar o Alembic gerencia-los produz DDL duplicada.
    if tipo == "index" and nome and nome.startswith("idx_") and nome.endswith("_geom"):
        return False
    return True


def migrar_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=incluir_objeto,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def migrar_online() -> None:
    conectavel = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with conectavel.connect() as conexao:
        context.configure(
            connection=conexao,
            target_metadata=target_metadata,
            include_object=incluir_objeto,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    migrar_offline()
else:
    migrar_online()
