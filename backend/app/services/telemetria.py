"""Ingestao de posicao.

Ponto unico de entrada de telemetria: o simulador e o endpoint publico
`POST /api/telemetria` passam os dois por aqui, entao trocar o simulador por
hardware real nao muda nenhuma regra de negocio.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.models import Animal, Posicao, agora
from app.services import alertas, geofence


def registrar(
    db: Session,
    animal: Animal,
    lat: float,
    lon: float,
    atividade: float = 0.5,
    bateria_pct: int | None = None,
    registrada_em: dt.datetime | None = None,
    evento: str | None = None,
) -> Posicao:
    momento = registrada_em or agora()

    posicao = Posicao(
        animal_id=animal.id,
        geom=geofence.ponto(lat, lon),
        registrada_em=momento,
        atividade=atividade,
        bateria_pct=bateria_pct if bateria_pct is not None else animal.bateria_pct,
    )
    db.add(posicao)

    animal.ultima_geom = geofence.ponto(lat, lon)
    animal.ultimo_contato = momento
    if bateria_pct is not None:
        animal.bateria_pct = bateria_pct

    alertas.avaliar_posicao(db, animal, lat, lon, atividade, evento)
    return posicao
