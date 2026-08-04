"""Simulador de rebanho.

Substitui o hardware que ainda nao existe. Gera telemetria plausivel para que
o MVP seja demonstravel sem brinco, sem gateway e sem boi.

Cada animal tem um comportamento:

  normal   -- caminhada aleatoria com inercia, dentro do pasto
  fugindo  -- rumo fixo para fora da divisa: dispara a geocerca
  imovel   -- para de andar e zera a atividade: dispara a imobilidade
  offline  -- para de reportar: dispara a perda de sinal

O comportamento e alternavel pela API, o que transforma a apresentacao do MVP
em algo dirigivel: aperta o botao, o alerta aparece.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Animal, Pasto
from app.services import alertas, telemetria

log = logging.getLogger("rastro.simulador")

# Um grau de latitude ~ 111.320 m. Suficiente para converter passo em metros
# na escala de um pasto.
METROS_POR_GRAU_LAT = 111_320.0

PASSO_NORMAL_M = 12.0    # deslocamento tipico entre duas leituras
PASSO_FUGA_M = 55.0      # animal em fuga anda mais e em linha reta


def _metros_para_graus(metros: float, lat: float) -> tuple[float, float]:
    d_lat = metros / METROS_POR_GRAU_LAT
    d_lon = metros / (METROS_POR_GRAU_LAT * max(math.cos(math.radians(lat)), 0.01))
    return d_lat, d_lon


def _posicao_atual(db: Session, animal: Animal) -> tuple[float, float] | None:
    if animal.ultima_geom is None:
        return None
    lat, lon = db.execute(
        select(func.ST_Y(Animal.ultima_geom), func.ST_X(Animal.ultima_geom)).where(
            Animal.id == animal.id
        )
    ).one()
    return float(lat), float(lon)


def _centro_do_pasto(db: Session, pasto_id: int) -> tuple[float, float]:
    lat, lon = db.execute(
        select(func.ST_Y(func.ST_Centroid(Pasto.geom)), func.ST_X(func.ST_Centroid(Pasto.geom))).where(
            Pasto.id == pasto_id
        )
    ).one()
    return float(lat), float(lon)


def _proximo_ponto(db: Session, animal: Animal, lat: float, lon: float) -> tuple[float, float, float]:
    """Devolve (lat, lon, atividade) para o proximo tick."""
    comportamento = animal.sim_comportamento

    if comportamento == "imovel":
        # Fica onde esta e a atividade cai para o ruido de fundo do sensor.
        return lat, lon, round(random.uniform(0.0, 0.03), 3)

    if comportamento == "fugindo":
        # Rumo fixo, apontado do centro do pasto para fora.
        d_lat, d_lon = _metros_para_graus(PASSO_FUGA_M, lat)
        rumo = animal.sim_rumo
        return (
            lat + d_lat * math.cos(rumo),
            lon + d_lon * math.sin(rumo),
            round(random.uniform(0.55, 0.95), 3),
        )

    # normal: caminhada com inercia, puxada de volta se chegar perto da divisa.
    animal.sim_rumo += random.uniform(-0.7, 0.7)
    passo = PASSO_NORMAL_M * random.uniform(0.4, 1.3)
    d_lat, d_lon = _metros_para_graus(passo, lat)

    novo_lat = lat + d_lat * math.cos(animal.sim_rumo)
    novo_lon = lon + d_lon * math.sin(animal.sim_rumo)

    if animal.pasto_id is not None:
        dentro = db.execute(
            select(
                func.ST_Contains(
                    Pasto.geom, func.ST_SetSRID(func.ST_MakePoint(novo_lon, novo_lat), 4326)
                )
            ).where(Pasto.id == animal.pasto_id)
        ).scalar_one()
        if not dentro:
            # Bateu na divisa: inverte o rumo e volta para dentro.
            centro_lat, centro_lon = _centro_do_pasto(db, animal.pasto_id)
            animal.sim_rumo = math.atan2(centro_lon - lon, centro_lat - lat)
            novo_lat = lat + d_lat * math.cos(animal.sim_rumo)
            novo_lon = lon + d_lon * math.sin(animal.sim_rumo)

    return novo_lat, novo_lon, round(random.uniform(0.25, 0.9), 3)


def tick() -> None:
    """Um ciclo do simulador. Sincrono de proposito -- roda em thread separada."""
    db: Session = SessionLocal()
    try:
        animais = db.execute(select(Animal)).scalars().all()

        for animal in animais:
            if animal.sim_comportamento == "offline":
                # Nao reporta. A varredura de silencio cuida do alerta.
                continue

            atual = _posicao_atual(db, animal)
            if atual is None:
                continue

            lat, lon, atividade = _proximo_ponto(db, animal, *atual)

            # Consumo lento de bateria, so para o painel ter um dado vivo.
            if random.random() < 0.05 and animal.bateria_pct > 1:
                animal.bateria_pct -= 1

            telemetria.registrar(db, animal, lat, lon, atividade, animal.bateria_pct)

        alertas.varrer_silencio(db)
        db.commit()
    except Exception:  # pragma: no cover - o loop nao pode morrer
        db.rollback()
        log.exception("falha no tick do simulador")
    finally:
        db.close()


async def loop() -> None:
    log.info("simulador iniciado (tick=%ss)", settings.simulator_tick_s)
    while True:
        await asyncio.sleep(settings.simulator_tick_s)
        await asyncio.to_thread(tick)
