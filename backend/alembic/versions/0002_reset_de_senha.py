"""tokens de redefinicao de senha

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tokens_reset_senha",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_tokens_reset_senha_usuario_id", "tokens_reset_senha", ["usuario_id"])
    op.create_index(
        "ix_tokens_reset_senha_token_hash", "tokens_reset_senha", ["token_hash"], unique=True
    )
    op.create_index("ix_tokens_reset_senha_criado_em", "tokens_reset_senha", ["criado_em"])


def downgrade() -> None:
    op.drop_table("tokens_reset_senha")
