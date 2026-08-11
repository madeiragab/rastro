"""Gestão dos brincos-mestre pelo produtor.

O dispositivo se autentica pelas rotas de `/dispositivos`. Aqui é o painel:
vincular uma chave a um animal e a um lote, e ver quem está no comando.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import exige_papel
from app.database import get_db
from app.models import PAPEL_DONO, Animal, ChaveGateway, Mestre, Pasto, Usuario, agora
from app.schemas import MestreIn, MestreOut
from app.services import mestres as servico

router = APIRouter(prefix="/mestres", tags=["mestres"])


def _saida(mestre: Mestre) -> MestreOut:
    silencio = None
    if mestre.ultimo_heartbeat is not None:
        silencio = int((agora() - mestre.ultimo_heartbeat).total_seconds())

    return MestreOut(
        id=mestre.id,
        pasto_id=mestre.pasto_id,
        pasto_nome=mestre.pasto.nome if mestre.pasto else None,
        animal_id=mestre.animal_id,
        animal_nome=mestre.animal.nome if mestre.animal else None,
        prefixo_chave=mestre.chave.prefixo,
        ativo=mestre.ativo,
        bateria_pct=mestre.bateria_pct,
        ultimo_heartbeat=mestre.ultimo_heartbeat,
        segundos_sem_heartbeat=silencio,
        trocas=mestre.trocas,
    )


@router.get("", response_model=list[MestreOut])
def listar(
    usuario: Usuario = Depends(exige_papel(PAPEL_DONO)),
    db: Session = Depends(get_db),
) -> list[MestreOut]:
    registros = (
        db.execute(
            select(Mestre)
            .where(Mestre.fazenda_id == usuario.fazenda_id)
            .order_by(Mestre.pasto_id, Mestre.ativo.desc())
        )
        .scalars()
        .all()
    )
    return [_saida(m) for m in registros]


@router.post("", response_model=MestreOut, status_code=status.HTTP_201_CREATED)
def cadastrar(
    payload: MestreIn,
    usuario: Usuario = Depends(exige_papel(PAPEL_DONO)),
    db: Session = Depends(get_db),
) -> MestreOut:
    """Vincula uma chave de gateway a um animal e a um lote.

    A chave já existe (foi criada em `/api/gateways` e gravada no dispositivo).
    Aqui se diz qual animal a carrega e qual lote ela atende.
    """
    chave = db.get(ChaveGateway, payload.chave_id)
    if chave is None or chave.fazenda_id != usuario.fazenda_id:
        raise HTTPException(status_code=404, detail="chave nao encontrada")

    if db.execute(
        select(Mestre).where(Mestre.chave_gateway_id == chave.id)
    ).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="esta chave ja pertence a um mestre")

    if payload.animal_id is not None:
        animal = db.get(Animal, payload.animal_id)
        if animal is None or animal.fazenda_id != usuario.fazenda_id:
            raise HTTPException(status_code=404, detail="animal nao encontrado")
        if db.execute(
            select(Mestre).where(Mestre.animal_id == payload.animal_id)
        ).scalar_one_or_none():
            raise HTTPException(status_code=409, detail="este animal ja carrega um mestre")

    if payload.pasto_id is not None:
        pasto = db.get(Pasto, payload.pasto_id)
        if pasto is None or pasto.fazenda_id != usuario.fazenda_id:
            raise HTTPException(status_code=404, detail="pasto nao encontrado")

    mestre = Mestre(
        fazenda_id=usuario.fazenda_id,
        pasto_id=payload.pasto_id,
        chave_gateway_id=chave.id,
        animal_id=payload.animal_id,
    )
    db.add(mestre)
    db.commit()
    db.refresh(mestre)
    return _saida(mestre)


@router.post("/{mestre_id}/promover", response_model=MestreOut)
def promover(
    mestre_id: int,
    usuario: Usuario = Depends(exige_papel(PAPEL_DONO)),
    db: Session = Depends(get_db),
) -> MestreOut:
    """Força a troca do mestre em serviço.

    Escotilha de manutenção — trocar bateria, recolher um animal. Fora disso,
    quem decide é a arbitragem automática.
    """
    mestre = db.get(Mestre, mestre_id)
    if mestre is None or mestre.fazenda_id != usuario.fazenda_id:
        raise HTTPException(status_code=404, detail="mestre nao encontrado")

    servico.promover(db, mestre, "troca manual pelo produtor")
    db.commit()
    db.refresh(mestre)
    return _saida(mestre)


@router.delete("/{mestre_id}", status_code=status.HTTP_204_NO_CONTENT)
def remover(
    mestre_id: int,
    usuario: Usuario = Depends(exige_papel(PAPEL_DONO)),
    db: Session = Depends(get_db),
) -> None:
    """Desvincula o mestre. A chave continua existindo e pode ser revogada à parte."""
    mestre = db.get(Mestre, mestre_id)
    if mestre is None or mestre.fazenda_id != usuario.fazenda_id:
        raise HTTPException(status_code=404, detail="mestre nao encontrado")

    db.delete(mestre)
    db.commit()
