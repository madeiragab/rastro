"""esquema inicial

Revision ID: 0001
Revises:
Create Date: 2026-08-04

Captura o schema que ate aqui era criado por `Base.metadata.create_all`. A
partir desta revisao, mudanca de modelo vira migracao -- e nao mais um
`docker compose down -v`.
"""

from __future__ import annotations

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A extensao precisa existir antes de qualquer coluna `geometry`.
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "fazendas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("proprietario", sa.String(120), nullable=False),
        sa.Column("municipio", sa.String(120), nullable=False),
        sa.Column("uf", sa.String(2), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "pastos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fazenda_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("cor", sa.String(9), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POLYGON", srid=4326),
            nullable=False,
        ),
        sa.Column("buffer_m", sa.Float(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["fazenda_id"], ["fazendas.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_pastos_fazenda_id", "pastos", ["fazenda_id"])

    op.create_table(
        "animais",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fazenda_id", sa.Integer(), nullable=False),
        sa.Column("pasto_id", sa.Integer(), nullable=True),
        sa.Column("brinco", sa.String(15), nullable=False),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column("categoria", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("bateria_pct", sa.Integer(), nullable=False),
        sa.Column(
            "ultima_geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("ultimo_contato", sa.DateTime(timezone=True), nullable=True),
        sa.Column("distancia_pasto_m", sa.Float(), nullable=False),
        sa.Column("leituras_fora", sa.Integer(), nullable=False),
        sa.Column("imovel_desde", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sim_comportamento", sa.String(20), nullable=False),
        sa.Column("sim_rumo", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["fazenda_id"], ["fazendas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["pasto_id"], ["pastos.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_animais_fazenda_id", "animais", ["fazenda_id"])
    op.create_index("ix_animais_pasto_id", "animais", ["pasto_id"])
    op.create_index("ix_animais_brinco", "animais", ["brinco"], unique=True)
    op.create_index("ix_animais_status", "animais", ["status"])

    op.create_table(
        "posicoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("animal_id", sa.Integer(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326),
            nullable=False,
        ),
        sa.Column("registrada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atividade", sa.Float(), nullable=False),
        sa.Column("bateria_pct", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["animal_id"], ["animais.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_posicoes_animal_id", "posicoes", ["animal_id"])
    op.create_index("ix_posicoes_registrada_em", "posicoes", ["registrada_em"])

    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fazenda_id", sa.Integer(), nullable=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("senha_hash", sa.String(255), nullable=False),
        sa.Column("papel", sa.String(20), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("senha_alterada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ultimo_login_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_versao", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["fazenda_id"], ["fazendas.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_usuarios_fazenda_id", "usuarios", ["fazenda_id"])
    op.create_index("ix_usuarios_email", "usuarios", ["email"], unique=True)

    op.create_table(
        "alertas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("animal_id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("severidade", sa.String(10), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column(
            "geom",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolvido_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["animal_id"], ["animais.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_alertas_animal_id", "alertas", ["animal_id"])
    op.create_index("ix_alertas_tipo", "alertas", ["tipo"])
    op.create_index("ix_alertas_criado_em", "alertas", ["criado_em"])

    op.create_table(
        "sessoes_refresh",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("familia", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("user_agent", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sessoes_refresh_usuario_id", "sessoes_refresh", ["usuario_id"])
    op.create_index("ix_sessoes_refresh_familia", "sessoes_refresh", ["familia"])
    op.create_index(
        "ix_sessoes_refresh_token_hash", "sessoes_refresh", ["token_hash"], unique=True
    )
    op.create_index("ix_sessoes_refresh_expira_em", "sessoes_refresh", ["expira_em"])

    op.create_table(
        "chaves_gateway",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fazenda_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("prefixo", sa.String(16), nullable=False),
        sa.Column("chave_hash", sa.String(255), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultima_utilizacao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["fazenda_id"], ["fazendas.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chaves_gateway_fazenda_id", "chaves_gateway", ["fazenda_id"])
    op.create_index("ix_chaves_gateway_prefixo", "chaves_gateway", ["prefixo"], unique=True)

    op.create_table(
        "tentativas_login",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("sucesso", sa.Boolean(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tentativas_email_data", "tentativas_login", ["email", "criada_em"])
    op.create_index("ix_tentativas_ip_data", "tentativas_login", ["ip", "criada_em"])

    op.create_table(
        "eventos_auditoria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("acao", sa.String(60), nullable=False),
        sa.Column("detalhe", sa.Text(), nullable=False),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_eventos_auditoria_usuario_id", "eventos_auditoria", ["usuario_id"])
    op.create_index("ix_eventos_auditoria_acao", "eventos_auditoria", ["acao"])
    op.create_index("ix_eventos_auditoria_criado_em", "eventos_auditoria", ["criado_em"])


def downgrade() -> None:
    for tabela in (
        "eventos_auditoria",
        "tentativas_login",
        "chaves_gateway",
        "sessoes_refresh",
        "alertas",
        "usuarios",
        "posicoes",
        "animais",
        "pastos",
        "fazendas",
    ):
        op.drop_table(tabela)
