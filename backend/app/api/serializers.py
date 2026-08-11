"""Conversao de modelo ORM para os schemas de saida.

As geometrias vivem no banco como WKB; a API expoe lat/lon simples porque e o
que o mapa do front consome.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alerta, Animal, Pasto, agora
from app.schemas import AlertaOut, AnimalOut, PastoOut
from app.services import geofence


def _lat_lon(db: Session, modelo, coluna) -> tuple[float | None, float | None]:
    if getattr(modelo, coluna.key) is None:
        return None, None
    lat, lon = db.execute(
        select(func.ST_Y(coluna), func.ST_X(coluna)).where(type(modelo).id == modelo.id)
    ).one()
    return float(lat), float(lon)


def animal_out(db: Session, animal: Animal) -> AnimalOut:
    lat, lon = _lat_lon(db, animal, Animal.ultima_geom)

    silencio = None
    if animal.ultimo_contato is not None:
        silencio = int((agora() - animal.ultimo_contato).total_seconds())

    return AnimalOut(
        id=animal.id,
        brinco=animal.brinco,
        nome=animal.nome,
        categoria=animal.categoria,
        status=animal.status,
        bateria_pct=animal.bateria_pct,
        lat=lat,
        lon=lon,
        ultimo_contato=animal.ultimo_contato,
        segundos_sem_contato=silencio,
        distancia_pasto_m=animal.distancia_pasto_m,
        pasto_id=animal.pasto_id,
        pasto_nome=animal.pasto.nome if animal.pasto else None,
        sim_comportamento=animal.sim_comportamento,
    )


def pasto_out(db: Session, pasto: Pasto) -> PastoOut:
    total = db.execute(
        select(func.count()).select_from(Animal).where(Animal.pasto_id == pasto.id)
    ).scalar_one()

    return PastoOut(
        id=pasto.id,
        nome=pasto.nome,
        cor=pasto.cor,
        buffer_m=pasto.buffer_m,
        pontos=geofence.pontos_do_pasto(db, pasto.id),
        area_ha=geofence.area_hectares(db, pasto.id),
        total_animais=total,
    )


def alerta_out(db: Session, alerta: Alerta) -> AlertaOut:
    lat, lon = _lat_lon(db, alerta, Alerta.geom)
    return AlertaOut(
        id=alerta.id,
        animal_id=alerta.animal_id,
        animal_nome=alerta.animal.nome if alerta.animal else None,
        brinco=alerta.animal.brinco if alerta.animal else None,
        pasto_id=alerta.pasto_id,
        pasto_nome=alerta.pasto.nome if alerta.pasto else None,
        tipo=alerta.tipo,
        severidade=alerta.severidade,
        mensagem=alerta.mensagem,
        lat=lat,
        lon=lon,
        criado_em=alerta.criado_em,
        resolvido_em=alerta.resolvido_em,
    )
