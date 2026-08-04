"""Carga inicial de demonstracao.

Fazenda ficticia no Triangulo Mineiro, dois pastos e um lote de animais.
Roda uma unica vez, no primeiro start, se o banco estiver vazio.
"""

from __future__ import annotations

import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Animal, Fazenda, Pasto
from app.services import geofence, telemetria

# Ponto de referencia: regiao de Uberaba, MG.
PASTO_SEDE = [
    (-19.7508, -47.9358),
    (-19.7512, -47.9294),
    (-19.7462, -47.9286),
    (-19.7448, -47.9316),
    (-19.7458, -47.9354),
]

PASTO_CORREGO = [
    (-19.7446, -47.9312),
    (-19.7458, -47.9268),
    (-19.7408, -47.9256),
    (-19.7396, -47.9302),
]

NOMES = [
    "Mimosa", "Estrela", "Malhada", "Formosa", "Jurema", "Serena", "Chita",
    "Boiadeiro", "Trovao", "Curio", "Pingo", "Guarana", "Fumaca", "Rajada",
]

CATEGORIAS = ["Novilha", "Vaca", "Bezerro", "Boi", "Garrote"]


def _ponto_dentro(db: Session, pasto_id: int) -> tuple[float, float]:
    """Sorteia um ponto dentro do poligono, por rejeicao sobre o envelope."""
    min_lat, max_lat, min_lon, max_lon = db.execute(
        select(
            func.ST_YMin(func.ST_Envelope(Pasto.geom)),
            func.ST_YMax(func.ST_Envelope(Pasto.geom)),
            func.ST_XMin(func.ST_Envelope(Pasto.geom)),
            func.ST_XMax(func.ST_Envelope(Pasto.geom)),
        ).where(Pasto.id == pasto_id)
    ).one()

    for _ in range(200):
        lat = random.uniform(float(min_lat), float(max_lat))
        lon = random.uniform(float(min_lon), float(max_lon))
        dentro = db.execute(
            select(
                func.ST_Contains(Pasto.geom, func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326))
            ).where(Pasto.id == pasto_id)
        ).scalar_one()
        if dentro:
            return lat, lon

    # Fallback: centroide. So chega aqui com poligono degenerado.
    lat, lon = db.execute(
        select(func.ST_Y(func.ST_Centroid(Pasto.geom)), func.ST_X(func.ST_Centroid(Pasto.geom))).where(
            Pasto.id == pasto_id
        )
    ).one()
    return float(lat), float(lon)


def semear(db: Session) -> bool:
    """Cria os dados de demonstracao. Devolve False se ja havia dados."""
    if db.execute(select(func.count()).select_from(Fazenda)).scalar_one():
        return False

    random.seed(42)  # demonstracao reproduzivel

    fazenda = Fazenda(
        nome="Fazenda Boa Vista",
        proprietario="Jose Rodrigues",
        municipio="Uberaba",
        uf="MG",
    )
    db.add(fazenda)
    db.flush()

    sede = Pasto(
        fazenda_id=fazenda.id,
        nome="Pasto da Sede",
        cor="#2E7D53",
        buffer_m=25.0,
        geom=func.ST_GeomFromText(geofence.wkt_poligono(PASTO_SEDE), 4326),
    )
    corrego = Pasto(
        fazenda_id=fazenda.id,
        nome="Pasto do Corrego",
        cor="#3D6EA8",
        buffer_m=25.0,
        geom=func.ST_GeomFromText(geofence.wkt_poligono(PASTO_CORREGO), 4326),
    )
    db.add_all([sede, corrego])
    db.flush()

    for indice, nome in enumerate(NOMES):
        pasto = sede if indice < 9 else corrego
        animal = Animal(
            fazenda_id=fazenda.id,
            pasto_id=pasto.id,
            brinco=f"076{indice + 1:012d}",
            nome=nome,
            categoria=random.choice(CATEGORIAS),
            bateria_pct=random.randint(72, 100),
            sim_rumo=random.uniform(0, 6.28),
        )
        db.add(animal)

    db.flush()

    # Primeira posicao de cada animal, dentro do seu pasto.
    for animal in db.execute(select(Animal)).scalars().all():
        lat, lon = _ponto_dentro(db, animal.pasto_id)
        telemetria.registrar(db, animal, lat, lon, atividade=random.uniform(0.3, 0.8))

    db.commit()
    return True
