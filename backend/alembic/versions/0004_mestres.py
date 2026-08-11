"""mestres de lote

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alerta passa a poder ser sobre o LOTE, e nao sobre um animal: "lote sem
    # comunicacao" e "mestre trocado" nao pertencem a nenhum bicho especifico.
    op.alter_column("alertas", "animal_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("alertas", sa.Column("pasto_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_alertas_pasto", "alertas", "pastos", ["pasto_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_alertas_pasto_id", "alertas", ["pasto_id"])

    op.create_table(
        "mestres",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fazenda_id", sa.Integer(), nullable=False),
        sa.Column("pasto_id", sa.Integer(), nullable=True),
        sa.Column("chave_gateway_id", sa.Integer(), nullable=False),
        sa.Column("animal_id", sa.Integer(), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("bateria_pct", sa.Integer(), nullable=False),
        sa.Column("ultimo_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assumiu_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trocas", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fazenda_id"], ["fazendas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pasto_id"], ["pastos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chave_gateway_id"], ["chaves_gateway.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["animal_id"], ["animais.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("chave_gateway_id", name="uq_mestres_chave"),
        sa.UniqueConstraint("animal_id", name="uq_mestres_animal"),
    )
    op.create_index("ix_mestres_fazenda_id", "mestres", ["fazenda_id"])
    op.create_index("ix_mestres_pasto_id", "mestres", ["pasto_id"])
    op.create_index("ix_mestres_ativo", "mestres", ["ativo"])
    op.create_index("ix_mestres_ultimo_heartbeat", "mestres", ["ultimo_heartbeat"])

    # A trava contra cerebro dividido fica NO BANCO, nao so no codigo: um lote
    # nao pode ter dois mestres ativos, nem por corrida entre duas requisicoes
    # simultaneas de "assumo?". Indice unico parcial faz o Postgres recusar.
    op.execute(
        "CREATE UNIQUE INDEX uq_mestre_ativo_por_pasto "
        "ON mestres (pasto_id) WHERE ativo AND pasto_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_mestre_ativo_por_pasto")
    op.drop_table("mestres")

    # Alertas de lote nao cabem no schema antigo; some com eles antes de voltar
    # a coluna para NOT NULL.
    op.execute("DELETE FROM alertas WHERE animal_id IS NULL")
    op.drop_index("ix_alertas_pasto_id", table_name="alertas")
    op.drop_constraint("fk_alertas_pasto", "alertas", type_="foreignkey")
    op.drop_column("alertas", "pasto_id")
    op.alter_column("alertas", "animal_id", existing_type=sa.Integer(), nullable=False)
