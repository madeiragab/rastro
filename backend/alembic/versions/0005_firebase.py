"""firebase: vinculo de conta e tokens FCM

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("firebase_uid", sa.String(128), nullable=True))
    op.create_unique_constraint("uq_usuarios_firebase_uid", "usuarios", ["firebase_uid"])

    op.create_table(
        "tokens_fcm",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "usuario_id",
            sa.Integer(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("plataforma", sa.String(20), nullable=False, server_default="android"),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ultimo_envio", sa.DateTime(timezone=True), nullable=True),
        sa.Column("falhas", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_tokens_fcm_usuario_id", "tokens_fcm", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_tokens_fcm_usuario_id", table_name="tokens_fcm")
    op.drop_table("tokens_fcm")
    op.drop_constraint("uq_usuarios_firebase_uid", "usuarios", type_="unique")
    op.drop_column("usuarios", "firebase_uid")
