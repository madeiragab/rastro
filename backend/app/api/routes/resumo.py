from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    STATUS_FORA,
    STATUS_IMOVEL,
    STATUS_OFFLINE,
    STATUS_OK,
    Alerta,
    Animal,
    Fazenda,
    Pasto,
)
from app.schemas import FazendaOut, ResumoOut
from app.services import geofence

router = APIRouter(tags=["resumo"])


@router.get("/fazenda", response_model=FazendaOut)
def fazenda_atual(db: Session = Depends(get_db)) -> FazendaOut:
    """MVP monofazenda: devolve a primeira. Multi-tenant entra depois do piloto."""
    fazenda = db.execute(select(Fazenda).order_by(Fazenda.id).limit(1)).scalar_one()
    return FazendaOut.model_validate(fazenda, from_attributes=True)


@router.get("/resumo", response_model=ResumoOut)
def resumo(db: Session = Depends(get_db)) -> ResumoOut:
    def conta(status: str) -> int:
        return db.execute(
            select(func.count()).select_from(Animal).where(Animal.status == status)
        ).scalar_one()

    pastos = db.execute(select(Pasto).where(Pasto.ativo.is_(True))).scalars().all()
    area = sum(geofence.area_hectares(db, p.id) for p in pastos)

    return ResumoOut(
        total_animais=db.execute(select(func.count()).select_from(Animal)).scalar_one(),
        em_area=conta(STATUS_OK),
        fora_da_area=conta(STATUS_FORA),
        imoveis=conta(STATUS_IMOVEL),
        sem_sinal=conta(STATUS_OFFLINE),
        alertas_abertos=db.execute(
            select(func.count()).select_from(Alerta).where(Alerta.resolvido_em.is_(None))
        ).scalar_one(),
        total_pastos=len(pastos),
        area_total_ha=round(area, 2),
    )
