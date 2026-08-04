"""Inscricao do navegador para receber notificacao push."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.database import get_db
from app.models import InscricaoPush, Usuario
from app.schemas import ChavePublicaOut, InscricaoPushIn, InscricaoPushOut
from app.services import push

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/chave-publica", response_model=ChavePublicaOut)
def chave_publica(
    _: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> ChavePublicaOut:
    """Chave usada pelo navegador como `applicationServerKey`.

    E publica por definicao -- vai embutida na inscricao do aparelho.
    """
    return ChavePublicaOut(chave=push.obter_chaves(db).chave_publica_app)


@router.post("/inscricoes", response_model=InscricaoPushOut, status_code=status.HTTP_201_CREATED)
def inscrever(
    payload: InscricaoPushIn,
    request: Request,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> InscricaoPushOut:
    """Registra ou reaproveita a inscricao deste navegador.

    O mesmo endpoint pode reaparecer -- reinstalacao, troca de conta no mesmo
    aparelho. Nesse caso a inscricao passa a pertencer a quem se inscreveu
    agora, em vez de duplicar e mandar aviso para a conta anterior.
    """
    existente = db.execute(
        select(InscricaoPush).where(InscricaoPush.endpoint == payload.endpoint)
    ).scalar_one_or_none()

    if existente is not None:
        existente.usuario_id = usuario.id
        existente.chave_p256dh = payload.chave_p256dh
        existente.chave_auth = payload.chave_auth
        existente.falhas = 0
        db.commit()
        db.refresh(existente)
        return InscricaoPushOut.model_validate(existente, from_attributes=True)

    inscricao = InscricaoPush(
        usuario_id=usuario.id,
        endpoint=payload.endpoint,
        chave_p256dh=payload.chave_p256dh,
        chave_auth=payload.chave_auth,
        user_agent=(request.headers.get("user-agent") or "")[:255],
    )
    db.add(inscricao)
    db.commit()
    db.refresh(inscricao)
    return InscricaoPushOut.model_validate(inscricao, from_attributes=True)


@router.delete("/inscricoes", status_code=status.HTTP_204_NO_CONTENT)
def cancelar(
    payload: InscricaoPushIn,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> None:
    """Cancela a inscricao deste navegador."""
    db.execute(
        delete(InscricaoPush).where(
            InscricaoPush.endpoint == payload.endpoint,
            InscricaoPush.usuario_id == usuario.id,
        )
    )
    db.commit()
