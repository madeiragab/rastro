from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers
from app.api.deps import gateway_atual, ip_do_cliente
from app.database import get_db
from app.models import Animal, ChaveGateway
from app.schemas import AnimalOut, PosicaoIn
from app.security import auditoria
from app.services import telemetria as servico

router = APIRouter(prefix="/telemetria", tags=["telemetria"])


@router.post("", response_model=AnimalOut, status_code=status.HTTP_201_CREATED)
def receber(
    payload: PosicaoIn,
    request: Request,
    gateway: ChaveGateway = Depends(gateway_atual),
    db: Session = Depends(get_db),
) -> AnimalOut:
    """Recebe a leitura de um brinco, repassada pelo gateway.

    Autenticado por chave de API (`X-API-Key`). E o mesmo caminho que o
    simulador usa, entao trocar o simulador por hardware real nao muda nenhuma
    regra de negocio.
    """
    animal = db.execute(select(Animal).where(Animal.brinco == payload.brinco)).scalar_one_or_none()

    # A chave e da fazenda, nao do animal: um gateway so pode reportar posicao
    # dos animais da propria fazenda. Sem essa checagem, uma chave vazada de
    # uma propriedade moveria o gado de outra.
    if animal is None or animal.fazenda_id != gateway.fazenda_id:
        auditoria.registrar(
            db,
            auditoria.TELEMETRIA_NEGADA,
            detalhe=f"gateway {gateway.prefixo} tentou reportar o brinco {payload.brinco}",
            ip=ip_do_cliente(request),
        )
        db.commit()
        # 404 mesmo quando o brinco existe em outra fazenda: responder 403 aqui
        # confirmaria a existencia do brinco para quem esta sondando.
        raise HTTPException(status_code=404, detail="brinco nao encontrado nesta fazenda")

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
