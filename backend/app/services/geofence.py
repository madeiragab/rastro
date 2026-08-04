"""Avaliacao de geocerca.

O teste ponto-em-poligono roda no PostGIS, nao em Python: o banco ja tem
indice espacial e a conta de distancia em metros sai correta via `geography`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.models import Pasto


@dataclass(frozen=True)
class ResultadoGeocerca:
    dentro: bool
    """True se o ponto esta dentro do poligono OU dentro da zona de tolerancia."""

    dentro_estrito: bool
    """True apenas se o ponto esta dentro do poligono, ignorando a tolerancia."""

    distancia_m: float
    """Distancia ate a borda do pasto. Zero quando o ponto esta dentro."""


def ponto(lat: float, lon: float):
    """Constroi um POINT em SRID 4326. Atencao a ordem: ST_MakePoint(x=lon, y=lat)."""
    return func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)


def avaliar(db: Session, pasto: Pasto, lat: float, lon: float) -> ResultadoGeocerca:
    """Compara uma posicao com o pasto do animal."""
    pt = ponto(lat, lon)

    dentro_estrito, distancia = db.execute(
        select(
            func.ST_Contains(Pasto.geom, pt),
            func.ST_Distance(cast(Pasto.geom, Geography), cast(pt, Geography)),
        ).where(Pasto.id == pasto.id)
    ).one()

    distancia = float(distancia or 0.0)
    # A tolerancia absorve o erro do GNSS: o animal so conta como fora quando
    # ultrapassa a cerca E se afasta mais que buffer_m dela.
    dentro = bool(dentro_estrito) or distancia <= (pasto.buffer_m or 0.0)

    return ResultadoGeocerca(
        dentro=dentro,
        dentro_estrito=bool(dentro_estrito),
        distancia_m=round(distancia, 1),
    )


def area_hectares(db: Session, pasto_id: int) -> float:
    valor = db.execute(
        select(func.ST_Area(cast(Pasto.geom, Geography)) / 10000.0).where(Pasto.id == pasto_id)
    ).scalar_one_or_none()
    return round(float(valor or 0.0), 2)


def pontos_do_pasto(db: Session, pasto_id: int) -> list[tuple[float, float]]:
    """Devolve o anel externo como [[lat, lon], ...], sem repetir o ponto final."""
    geojson = db.execute(
        select(func.ST_AsGeoJSON(Pasto.geom)).where(Pasto.id == pasto_id)
    ).scalar_one_or_none()
    if not geojson:
        return []

    anel = json.loads(geojson)["coordinates"][0]
    pontos = [(float(lat), float(lon)) for lon, lat in anel]
    if len(pontos) > 1 and pontos[0] == pontos[-1]:
        pontos.pop()
    return pontos


def wkt_poligono(pontos: list[tuple[float, float]]) -> str:
    """Monta o WKT de um POLYGON a partir de [[lat, lon], ...], fechando o anel."""
    anel = list(pontos)
    if anel[0] != anel[-1]:
        anel.append(anel[0])
    coords = ", ".join(f"{lon} {lat}" for lat, lon in anel)
    return f"POLYGON(({coords}))"
