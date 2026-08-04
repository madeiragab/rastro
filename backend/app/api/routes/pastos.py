from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import serializers
from app.database import get_db
from app.models import Animal, Fazenda, Pasto
from app.schemas import PastoIn, PastoOut
from app.services import geofence

router = APIRouter(prefix="/pastos", tags=["pastos"])


@router.get("", response_model=list[PastoOut])
def listar(db: Session = Depends(get_db)) -> list[PastoOut]:
    pastos = db.execute(select(Pasto).where(Pasto.ativo.is_(True)).order_by(Pasto.id)).scalars().all()
    return [serializers.pasto_out(db, p) for p in pastos]


@router.post("", response_model=PastoOut, status_code=status.HTTP_201_CREATED)
def criar(payload: PastoIn, db: Session = Depends(get_db)) -> PastoOut:
    """Cria o pasto desenhado no mapa pelo produtor."""
    fazenda = db.execute(select(Fazenda).order_by(Fazenda.id).limit(1)).scalar_one_or_none()
    if fazenda is None:
        raise HTTPException(status_code=400, detail="nenhuma fazenda cadastrada")

    pasto = Pasto(
        fazenda_id=fazenda.id,
        nome=payload.nome,
        cor=payload.cor,
        buffer_m=payload.buffer_m,
        geom=func.ST_GeomFromText(geofence.wkt_poligono(payload.pontos), 4326),
    )
    db.add(pasto)
    db.commit()
    db.refresh(pasto)
    return serializers.pasto_out(db, pasto)


@router.delete("/{pasto_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(pasto_id: int, db: Session = Depends(get_db)) -> None:
    pasto = db.get(Pasto, pasto_id)
    if pasto is None:
        raise HTTPException(status_code=404, detail="pasto nao encontrado")

    tem_animal = db.execute(
        select(func.count()).select_from(Animal).where(Animal.pasto_id == pasto_id)
    ).scalar_one()
    if tem_animal:
        raise HTTPException(
            status_code=409,
            detail="ha animais vinculados a este pasto; mova-os antes de remover",
        )

    db.delete(pasto)
    db.commit()
