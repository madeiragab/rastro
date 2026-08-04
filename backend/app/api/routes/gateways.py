"""Gestao das chaves de gateway.

Restrito ao papel `dono`: quem cria uma chave passa a poder injetar posicao de
qualquer animal da fazenda.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import exige_papel, ip_do_cliente
from app.database import get_db
from app.models import PAPEL_DONO, ChaveGateway, Usuario, agora
from app.schemas import ChaveGatewayCriadaOut, ChaveGatewayIn, ChaveGatewayOut
from app.security import auditoria, chaves

router = APIRouter(prefix="/gateways", tags=["gateways"])


def _saida(registro: ChaveGateway) -> ChaveGatewayOut:
    return ChaveGatewayOut.model_validate(registro, from_attributes=True)


@router.get("", response_model=list[ChaveGatewayOut])
def listar(
    usuario: Usuario = Depends(exige_papel(PAPEL_DONO)),
    db: Session = Depends(get_db),
) -> list[ChaveGatewayOut]:
    registros = (
        db.execute(
            select(ChaveGateway)
            .where(ChaveGateway.fazenda_id == usuario.fazenda_id)
            .order_by(ChaveGateway.criada_em.desc())
        )
        .scalars()
        .all()
    )
    return [_saida(r) for r in registros]


@router.post("", response_model=ChaveGatewayCriadaOut, status_code=status.HTTP_201_CREATED)
def criar(
    payload: ChaveGatewayIn,
    request: Request,
    usuario: Usuario = Depends(exige_papel(PAPEL_DONO)),
    db: Session = Depends(get_db),
) -> ChaveGatewayCriadaOut:
    """Cria uma chave. **A chave completa e devolvida uma unica vez.**"""
    if usuario.fazenda_id is None:
        raise HTTPException(status_code=400, detail="usuario sem fazenda vinculada")

    chave, prefixo, hash_ = chaves.gerar()

    registro = ChaveGateway(
        fazenda_id=usuario.fazenda_id,
        nome=payload.nome,
        prefixo=prefixo,
        chave_hash=hash_,
        expira_em=(
            agora() + dt.timedelta(days=payload.dias_validade) if payload.dias_validade else None
        ),
    )
    db.add(registro)

    auditoria.registrar(
        db,
        auditoria.CHAVE_CRIADA,
        usuario_id=usuario.id,
        detalhe=f"prefixo {prefixo} ({payload.nome})",  # nunca o segredo
        ip=ip_do_cliente(request),
    )
    db.commit()
    db.refresh(registro)

    return ChaveGatewayCriadaOut(**_saida(registro).model_dump(), chave=chave)


@router.delete("/{chave_id}", status_code=status.HTTP_204_NO_CONTENT)
def revogar(
    chave_id: int,
    request: Request,
    usuario: Usuario = Depends(exige_papel(PAPEL_DONO)),
    db: Session = Depends(get_db),
) -> None:
    """Revoga a chave. O registro fica, para a auditoria continuar legivel."""
    registro = db.get(ChaveGateway, chave_id)
    if registro is None or registro.fazenda_id != usuario.fazenda_id:
        raise HTTPException(status_code=404, detail="chave nao encontrada")

    if registro.revogada_em is None:
        registro.revogada_em = agora()
        registro.ativa = False
        auditoria.registrar(
            db,
            auditoria.CHAVE_REVOGADA,
            usuario_id=usuario.id,
            detalhe=f"prefixo {registro.prefixo}",
            ip=ip_do_cliente(request),
        )
        db.commit()
