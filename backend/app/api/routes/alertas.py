from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers
from app.database import get_db
from app.models import Alerta, Animal, agora
from app.schemas import AlertaOut
from app.services import alertas as servico_alertas

router = APIRouter(prefix="/alertas", tags=["alertas"])


@router.get("", response_model=list[AlertaOut])
def listar(
    abertos: bool = Query(default=True, description="somente alertas nao resolvidos"),
    limite: int = Query(default=50, ge=1, le=300),
    db: Session = Depends(get_db),
) -> list[AlertaOut]:
    consulta = select(Alerta).order_by(Alerta.criado_em.desc()).limit(limite)
    if abertos:
        consulta = consulta.where(Alerta.resolvido_em.is_(None))

    return [serializers.alerta_out(db, a) for a in db.execute(consulta).scalars().all()]


@router.post("/{alerta_id}/resolver", response_model=AlertaOut)
def resolver(alerta_id: int, db: Session = Depends(get_db)) -> AlertaOut:
    alerta = db.get(Alerta, alerta_id)
    if alerta is None:
        raise HTTPException(status_code=404, detail="alerta nao encontrado")

    if alerta.resolvido_em is None:
        alerta.resolvido_em = agora()
        db.commit()
        db.refresh(alerta)

    return serializers.alerta_out(db, alerta)


@router.post("/animal/{animal_id}/resolver", status_code=204)
def resolver_do_animal(animal_id: int, db: Session = Depends(get_db)) -> None:
    """Fecha todos os alertas abertos de um animal.

    Nao altera o comportamento do simulador de proposito: se a causa ainda
    existe, o alerta reabre no proximo ciclo. E o comportamento correto.
    """
    if db.get(Animal, animal_id) is None:
        raise HTTPException(status_code=404, detail="animal nao encontrado")

    servico_alertas.resolver_todos(db, animal_id)
    db.commit()


@router.post("/lote/{pasto_id}/resolver", status_code=204)
def resolver_do_lote(pasto_id: int, db: Session = Depends(get_db)) -> None:
    """Fecha os alertas de lote (mestre caido, lote mudo) de um pasto.

    Se a causa persistir, o alerta reabre no proximo ciclo -- marcar como
    resolvido nao conserta o mundo real.
    """
    from app.models import Pasto

    if db.get(Pasto, pasto_id) is None:
        raise HTTPException(status_code=404, detail="pasto nao encontrado")

    abertos = (
        db.execute(
            select(Alerta).where(
                Alerta.pasto_id == pasto_id,
                Alerta.animal_id.is_(None),
                Alerta.resolvido_em.is_(None),
            )
        )
        .scalars()
        .all()
    )
    for alerta in abertos:
        alerta.resolvido_em = agora()
    db.commit()
