"""Contratos de entrada e saida da API."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field, field_validator


# ------------------------------------------------------------------ fazenda
class FazendaOut(BaseModel):
    id: int
    nome: str
    proprietario: str
    municipio: str
    uf: str


# -------------------------------------------------------------------- pasto
class PastoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    cor: str = "#2E7D53"
    buffer_m: float = 25.0
    # Anel externo do poligono como [[lat, lon], ...]. O fechamento e feito
    # no servidor, entao o cliente nao precisa repetir o primeiro ponto.
    pontos: list[tuple[float, float]]

    @field_validator("pontos")
    @classmethod
    def _minimo_tres_pontos(cls, v: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(v) < 3:
            raise ValueError("um pasto precisa de pelo menos 3 pontos")
        return v


class PastoOut(BaseModel):
    id: int
    nome: str
    cor: str
    buffer_m: float
    pontos: list[tuple[float, float]]
    area_ha: float
    total_animais: int


# ------------------------------------------------------------------- animal
class AnimalOut(BaseModel):
    id: int
    brinco: str
    nome: str
    categoria: str
    status: str
    bateria_pct: int
    lat: float | None
    lon: float | None
    ultimo_contato: dt.datetime | None
    segundos_sem_contato: int | None
    distancia_pasto_m: float
    pasto_id: int | None
    pasto_nome: str | None
    sim_comportamento: str


# ------------------------------------------------------------------ posicao
class PosicaoIn(BaseModel):
    """Payload que o brinco enviaria. Existe para permitir integrar hardware
    real sem tocar no resto da API."""

    brinco: str
    lat: float
    lon: float
    atividade: float = 0.5
    bateria_pct: int = 100
    registrada_em: dt.datetime | None = None


class PosicaoOut(BaseModel):
    lat: float
    lon: float
    registrada_em: dt.datetime
    atividade: float


# ------------------------------------------------------------------- alerta
class AlertaOut(BaseModel):
    id: int
    animal_id: int
    animal_nome: str
    brinco: str
    tipo: str
    severidade: str
    mensagem: str
    lat: float | None
    lon: float | None
    criado_em: dt.datetime
    resolvido_em: dt.datetime | None


# ------------------------------------------------------------------- resumo
class ResumoOut(BaseModel):
    total_animais: int
    em_area: int
    fora_da_area: int
    imoveis: int
    sem_sinal: int
    alertas_abertos: int
    total_pastos: int
    area_total_ha: float


# --------------------------------------------------------------- simulacao
class CenarioIn(BaseModel):
    animal_id: int
    comportamento: str

    @field_validator("comportamento")
    @classmethod
    def _valido(cls, v: str) -> str:
        from app.models import COMPORTAMENTOS

        if v not in COMPORTAMENTOS:
            raise ValueError(f"comportamento deve ser um de {COMPORTAMENTOS}")
        return v
