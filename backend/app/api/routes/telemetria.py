from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers
from app.database import get_db
from app.models import Animal
from app.schemas import AnimalOut, PosicaoIn
from app.services import telemetria as servico

router = APIRouter(prefix="/telemetria", tags=["telemetria"])


@router.post("", response_model=AnimalOut, status_code=status.HTTP_201_CREATED)
def receber(payload: PosicaoIn, db: Session = Depends(get_db)) -> AnimalOut:
    """Endpoint que o gateway chamaria ao repassar a leitura de um brinco.

    E o mesmo caminho que o simulador usa. Quando o hardware existir, basta
    apontar o gateway para ca -- nenhuma regra de negocio muda.

    Nota de seguranca: em producao este endpoint precisa de autenticacao por
    dispositivo (chave por gateway ou mTLS). No MVP esta aberto de proposito,
    para permitir teste com curl.
    """
    animal = db.execute(select(Animal).where(Animal.brinco == payload.brinco)).scalar_one_or_none()
    if animal is None:
        raise HTTPException(status_code=404, detail=f"brinco {payload.brinco} nao cadastrado")

    servico.registrar(
        db,
        animal,
        lat=payload.lat,
        lon=payload.lon,
        atividade=payload.atividade,
        bateria_pct=payload.bateria_pct,
        registrada_em=payload.registrada_em,
    )
    db.commit()
    db.refresh(animal)
    return serializers.animal_out(db, animal)
