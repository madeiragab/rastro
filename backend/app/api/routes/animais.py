from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import serializers
from app.database import get_db
from app.models import Animal, Posicao
from app.schemas import AnimalOut, PosicaoOut

router = APIRouter(prefix="/animais", tags=["animais"])


@router.get("", response_model=list[AnimalOut])
def listar(
    status_filtro: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[AnimalOut]:
    consulta = select(Animal).order_by(Animal.nome)
    if status_filtro:
        consulta = consulta.where(Animal.status == status_filtro)

    animais = db.execute(consulta).scalars().all()
    return [serializers.animal_out(db, a) for a in animais]


@router.get("/{animal_id}", response_model=AnimalOut)
def detalhe(animal_id: int, db: Session = Depends(get_db)) -> AnimalOut:
    animal = db.get(Animal, animal_id)
    if animal is None:
        raise HTTPException(status_code=404, detail="animal nao encontrado")
    return serializers.animal_out(db, animal)


@router.get("/{animal_id}/trilha", response_model=list[PosicaoOut])
def trilha(
    animal_id: int,
    limite: int = Query(default=60, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PosicaoOut]:
    """Ultimas posicoes do animal, da mais antiga para a mais recente."""
    if db.get(Animal, animal_id) is None:
        raise HTTPException(status_code=404, detail="animal nao encontrado")

    linhas = db.execute(
        select(
            func.ST_Y(Posicao.geom),
            func.ST_X(Posicao.geom),
            Posicao.registrada_em,
            Posicao.atividade,
        )
        .where(Posicao.animal_id == animal_id)
        .order_by(Posicao.registrada_em.desc())
        .limit(limite)
    ).all()

    return [
        PosicaoOut(lat=float(lat), lon=float(lon), registrada_em=momento, atividade=atividade)
        for lat, lon, momento, atividade in reversed(linhas)
    ]
