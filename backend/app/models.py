"""Modelo de dados do Rastro.

Geometrias em SRID 4326 (lat/lon). Distancias em metros sao calculadas
convertendo para `geography`, o que evita erro de projecao.
"""

from __future__ import annotations

import datetime as dt

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --------------------------------------------------------------------- enums
# Strings simples em vez de Enum do banco: o conjunto ainda vai mudar durante
# o MVP e ALTER TYPE em Postgres e chato.

STATUS_OK = "ok"
STATUS_FORA = "fora_da_area"
STATUS_IMOVEL = "imovel"
STATUS_OFFLINE = "sem_sinal"

ALERTA_FORA = "fora_da_area"
ALERTA_IMOVEL = "imovel"
ALERTA_SEM_SINAL = "sem_sinal"

COMPORTAMENTOS = ("normal", "fugindo", "imovel", "offline")


class Fazenda(Base):
    __tablename__ = "fazendas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    proprietario: Mapped[str] = mapped_column(String(120))
    municipio: Mapped[str] = mapped_column(String(120), default="")
    uf: Mapped[str] = mapped_column(String(2), default="MG")
    criada_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora)

    pastos: Mapped[list[Pasto]] = relationship(back_populates="fazenda", cascade="all, delete-orphan")
    animais: Mapped[list[Animal]] = relationship(back_populates="fazenda", cascade="all, delete-orphan")


class Pasto(Base):
    """Area demarcada pelo produtor no mapa."""

    __tablename__ = "pastos"

    id: Mapped[int] = mapped_column(primary_key=True)
    fazenda_id: Mapped[int] = mapped_column(ForeignKey("fazendas.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    cor: Mapped[str] = mapped_column(String(9), default="#2E7D53")
    geom: Mapped[object] = mapped_column(Geometry("POLYGON", srid=4326))
    buffer_m: Mapped[float] = mapped_column(Float, default=25.0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora)

    fazenda: Mapped[Fazenda] = relationship(back_populates="pastos")
    animais: Mapped[list[Animal]] = relationship(back_populates="pasto")


class Animal(Base):
    __tablename__ = "animais"

    id: Mapped[int] = mapped_column(primary_key=True)
    fazenda_id: Mapped[int] = mapped_column(ForeignKey("fazendas.id", ondelete="CASCADE"), index=True)
    pasto_id: Mapped[int | None] = mapped_column(ForeignKey("pastos.id", ondelete="SET NULL"), index=True)

    # Numeracao no padrao do PNIB: 15 digitos, prefixo 076 (codigo do Brasil).
    brinco: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(80))
    categoria: Mapped[str] = mapped_column(String(40), default="Novilha")

    status: Mapped[str] = mapped_column(String(20), default=STATUS_OK, index=True)
    bateria_pct: Mapped[int] = mapped_column(Integer, default=100)

    # Ultima posicao denormalizada: o mapa precisa dela a cada poll e nao vale
    # varrer a tabela de posicoes toda vez.
    ultima_geom: Mapped[object | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    ultimo_contato: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    distancia_pasto_m: Mapped[float] = mapped_column(Float, default=0.0)

    # Estado do motor de alertas.
    leituras_fora: Mapped[int] = mapped_column(Integer, default=0)
    imovel_desde: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Estado do simulador (nao existiria no produto com hardware real).
    sim_comportamento: Mapped[str] = mapped_column(String(20), default="normal")
    sim_rumo: Mapped[float] = mapped_column(Float, default=0.0)

    fazenda: Mapped[Fazenda] = relationship(back_populates="animais")
    pasto: Mapped[Pasto | None] = relationship(back_populates="animais")


class Posicao(Base):
    __tablename__ = "posicoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animais.id", ondelete="CASCADE"), index=True)
    geom: Mapped[object] = mapped_column(Geometry("POINT", srid=4326))
    registrada_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)

    # Indice de atividade 0..1 vindo do acelerometro do brinco. Sem ele o
    # alerta de imobilidade e inutil: bovino deitado ruminando fica estatico.
    atividade: Mapped[float] = mapped_column(Float, default=0.5)
    bateria_pct: Mapped[int] = mapped_column(Integer, default=100)


class Alerta(Base):
    __tablename__ = "alertas"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animais.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(30), index=True)
    severidade: Mapped[str] = mapped_column(String(10), default="alta")
    mensagem: Mapped[str] = mapped_column(Text)
    geom: Mapped[object | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)
    resolvido_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    animal: Mapped[Animal] = relationship()
