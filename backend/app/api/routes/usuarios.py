"""Gestao da equipe da fazenda.

Restrito ao papel `dono`. Sem estas rotas, os papeis `operador` e `leitura`
existiam no codigo e nao havia como atribui-los a ninguem -- a matriz de
permissoes era documentacao sem uso.

Duas travas contra o dono se trancar para fora, que sao o modo mais comum de
transformar um sistema com controle de acesso em um sistema sem acesso:
ninguem rebaixa nem desativa a propria conta.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import segredo_aleatorio
from app.database import get_db
from app.api.deps import exige_papel, ip_do_cliente
from app.models import PAPEL_DONO, Usuario, agora
from app.schemas import UsuarioCriadoOut, UsuarioIn, UsuarioOut, UsuarioPatch
from app.security import auditoria, senhas

router = APIRouter(prefix="/usuarios", tags=["equipe"])


def _saida(usuario: Usuario) -> UsuarioOut:
    return UsuarioOut.model_validate(usuario, from_attributes=True)


@router.get("", response_model=list[UsuarioOut])
def listar(
    atual: Usuario = Depends(exige_papel(PAPEL_DONO)),
    db: Session = Depends(get_db),
) -> list[UsuarioOut]:
    usuarios = (
        db.execute(
            select(Usuario)
            .where(Usuario.fazenda_id == atual.fazenda_id)
            .order_by(Usuario.nome)
        )
        .scalars()
        .all()
    )
    return [_saida(u) for u in usuarios]


@router.post("", response_model=UsuarioCriadoOut, status_code=status.HTTP_201_CREATED)
def criar(
    payload: UsuarioIn,
    request: Request,
    atual: Usuario = Depends(exige_papel(PAPEL_DONO)),
    db: Session = Depends(get_db),
) -> UsuarioCriadoOut:
    """Cria uma conta na mesma fazenda. **A senha inicial e exibida uma vez.**"""
    if atual.fazenda_id is None:
        raise HTTPException(status_code=400, detail="usuario sem fazenda vinculada")

    email = payload.email.lower()
    if db.execute(select(Usuario).where(Usuario.email == email)).scalar_one_or_none():
        # Aqui confirmar a existencia e aceitavel: quem pergunta ja e dono
        # autenticado da fazenda, e precisa da mensagem para agir.
        raise HTTPException(status_code=409, detail="ja existe conta com este e-mail")

    # Senha sorteada, nunca escolhida pelo dono: assim ele nao fica conhecendo
    # a credencial de outra pessoa depois da primeira troca.
    senha = segredo_aleatorio(12)

    usuario = Usuario(
        fazenda_id=atual.fazenda_id,
        email=email,
        nome=payload.nome,
        senha_hash=senhas.gerar_hash(senha),
        papel=payload.papel,
    )
    db.add(usuario)

    auditoria.registrar(
        db,
        auditoria.USUARIO_CRIADO,
        usuario_id=atual.id,
        detalhe=f"{email} como {payload.papel}",  # nunca a senha
        ip=ip_do_cliente(request),
    )
    db.commit()
    db.refresh(usuario)

    return UsuarioCriadoOut(**_saida(usuario).model_dump(), senha_inicial=senha)


@router.patch("/{usuario_id}", response_model=UsuarioOut)
def alterar(
    usuario_id: int,
    payload: UsuarioPatch,
    request: Request,
    atual: Usuario = Depends(exige_papel(PAPEL_DONO)),
    db: Session = Depends(get_db),
) -> UsuarioOut:
    alvo = db.get(Usuario, usuario_id)
    if alvo is None or alvo.fazenda_id != atual.fazenda_id:
        raise HTTPException(status_code=404, detail="usuario nao encontrado")

    if alvo.id == atual.id:
        raise HTTPException(
            status_code=400,
            detail="voce nao pode alterar o proprio papel nem se desativar",
        )

    mudancas = []

    if payload.papel is not None and payload.papel != alvo.papel:
        mudancas.append(f"papel {alvo.papel} -> {payload.papel}")
        alvo.papel = payload.papel
        # O papel viaja dentro do access token. Sem incrementar a versao, um
        # rebaixamento so valeria quando o token atual expirasse.
        alvo.token_versao += 1

    if payload.ativo is not None and payload.ativo != alvo.ativo:
        mudancas.append("ativado" if payload.ativo else "desativado")
        alvo.ativo = payload.ativo
        if not payload.ativo:
            alvo.token_versao += 1
            _revogar_sessoes(db, alvo)

    if mudancas:
        alvo.senha_alterada_em = agora()
        auditoria.registrar(
            db,
            auditoria.USUARIO_ALTERADO,
            usuario_id=atual.id,
            detalhe=f"{alvo.email}: " + "; ".join(mudancas),
            ip=ip_do_cliente(request),
        )
        db.commit()
        db.refresh(alvo)

    return _saida(alvo)


def _revogar_sessoes(db: Session, usuario: Usuario) -> None:
    from sqlalchemy import update

    from app.models import SessaoRefresh

    db.execute(
        update(SessaoRefresh)
        .where(SessaoRefresh.usuario_id == usuario.id, SessaoRefresh.revogada_em.is_(None))
        .values(revogada_em=agora())
    )
