"""Controle do simulador.

Existe para tornar a demonstracao dirigivel: o apresentador aperta o botao e
o alerta correspondente aparece em segundos. Some quando entrar hardware real.
"""

import math

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import serializers
from app.database import get_db
from app.models import Animal, Pasto
from app.schemas import AnimalOut, CenarioIn

router = APIRouter(prefix="/simulacao", tags=["simulacao"])


@router.post("/cenario", response_model=AnimalOut)
def definir_cenario(payload: CenarioIn, db: Session = Depends(get_db)) -> AnimalOut:
    animal = db.get(Animal, payload.animal_id)
    if animal is None:
        raise HTTPException(status_code=404, detail="animal nao encontrado")

    animal.sim_comportamento = payload.comportamento

    if payload.comportamento == "fugindo" and animal.pasto_id and animal.ultima_geom is not None:
        # Aponta o rumo do centro do pasto para a posicao atual, ou seja,
        # para fora. Assim a fuga sai pela divisa mais proxima.
        centro_lat, centro_lon, lat, lon = db.execute(
            select(
                func.ST_Y(func.ST_Centroid(Pasto.geom)),
                func.ST_X(func.ST_Centroid(Pasto.geom)),
                func.ST_Y(Animal.ultima_geom),
                func.ST_X(Animal.ultima_geom),
            ).where(Pasto.id == animal.pasto_id, Animal.id == animal.id)
        ).one()
        animal.sim_rumo = math.atan2(float(lon) - float(centro_lon), float(lat) - float(centro_lat))

    if payload.comportamento == "normal":
        animal.leituras_fora = 0
        animal.imovel_desde = None

    db.commit()
    db.refresh(animal)
    return serializers.animal_out(db, animal)


@router.post("/reiniciar", response_model=list[AnimalOut])
def reiniciar(db: Session = Depends(get_db)) -> list[AnimalOut]:
    """Devolve todos os animais ao comportamento normal."""
    animais = db.execute(select(Animal)).scalars().all()
    for animal in animais:
        animal.sim_comportamento = "normal"
        animal.leituras_fora = 0
        animal.imovel_desde = None
    db.commit()
    return [serializers.animal_out(db, a) for a in animais]
