"""notificacao push

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inscricoes_push",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("chave_p256dh", sa.String(255), nullable=False),
        sa.Column("chave_auth", sa.String(255), nullable=False),
        sa.Column("user_agent", sa.String(255), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ultimo_envio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("falhas", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("endpoint", name="uq_inscricoes_push_endpoint"),
    )
    op.create_index("ix_inscricoes_push_usuario_id", "inscricoes_push", ["usuario_id"])

    op.create_table(
        "configuracao_push",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chave_privada_pem", sa.Text(), nullable=False),
        sa.Column("chave_publica_app", sa.Text(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
    )

    # Alertas ja existentes nascem marcados como notificados: ligar o push nao
    # pode disparar um push retroativo de todo o historico.
    op.add_column("alertas", sa.Column("notificado_em", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE alertas SET notificado_em = criado_em")
    op.create_index("ix_alertas_notificado_em", "alertas", ["notificado_em"])


def downgrade() -> None:
    op.drop_index("ix_alertas_notificado_em", table_name="alertas")
    op.drop_column("alertas", "notificado_em")
    op.drop_table("configuracao_push")
    op.drop_table("inscricoes_push")
