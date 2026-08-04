"""Login, renovacao, logout e troca de senha.

Fluxo de sessao:

    login   -> access token (15 min, corpo)  + refresh (cookie HttpOnly) + csrf
    refresh -> access token novo             + refresh NOVO (rotacao)
    logout  -> revoga a familia inteira e limpa os cookies

O refresh sofre rotacao a cada uso. Se um token ja usado reaparecer, a unica
explicacao e copia -- ou o legitimo ou o ladrao esta com a copia velha. Nao da
para saber qual, entao revogamos a familia toda e forcamos login novo. E a
recomendacao do OAuth 2.0 Security BCP para clientes publicos.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import ip_do_cliente, usuario_atual
from app.config import settings
from app.database import get_db
from app.models import SessaoRefresh, TokenResetSenha, Usuario, agora
from app.schemas import (
    EsqueciSenhaIn,
    LoginIn,
    RedefinirSenhaIn,
    TokenOut,
    TrocarSenhaIn,
    UsuarioOut,
)
from app.security import auditoria, limites, senhas, tokens
from app.services import notificacao

router = APIRouter(prefix="/auth", tags=["autenticacao"])

CABECALHO_CSRF = "X-CSRF-Token"


# --------------------------------------------------------------------- util
def _gravar_cookies(resposta: Response, refresh: str, csrf: str) -> None:
    expira = settings.refresh_token_ttl_dias * 24 * 3600

    # HttpOnly: JavaScript nao le, entao XSS nao exfiltra a sessao longa.
    # SameSite=strict: o navegador nao envia o cookie em navegacao vinda de
    # outro site, o que ja barra a maior parte do CSRF.
    # Path restrito: o cookie so acompanha as rotas que precisam dele.
    resposta.set_cookie(
        settings.cookie_refresh_nome,
        refresh,
        max_age=expira,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_dominio,
        path="/api/auth",
    )

    # O par do double-submit precisa ser legivel pelo JavaScript -- e por isso
    # que ele nao e, sozinho, uma protecao: vale como segunda camada junto do
    # SameSite.
    resposta.set_cookie(
        settings.cookie_csrf_nome,
        csrf,
        max_age=expira,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_dominio,
        path="/",
    )


def _limpar_cookies(resposta: Response) -> None:
    resposta.delete_cookie(settings.cookie_refresh_nome, path="/api/auth", domain=settings.cookie_dominio)
    resposta.delete_cookie(settings.cookie_csrf_nome, path="/", domain=settings.cookie_dominio)


def _abrir_sessao(
    db: Session, usuario: Usuario, request: Request, familia: str | None = None
) -> tuple[str, str]:
    """Cria um refresh token e devolve `(refresh_em_claro, csrf)`."""
    claro, hash_ = tokens.gerar_refresh_token()

    db.add(
        SessaoRefresh(
            usuario_id=usuario.id,
            familia=familia or tokens.nova_familia(),
            token_hash=hash_,
            expira_em=agora() + dt.timedelta(days=settings.refresh_token_ttl_dias),
            ip=ip_do_cliente(request),
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    return claro, tokens.gerar_csrf()


def _resposta_de_token(db: Session, usuario: Usuario) -> TokenOut:
    access, expira_s = tokens.criar_access_token(
        usuario.id, usuario.papel, usuario.fazenda_id, usuario.token_versao
    )
    return TokenOut(
        access_token=access,
        expira_em_s=expira_s,
        usuario=UsuarioOut.model_validate(usuario, from_attributes=True),
    )


# -------------------------------------------------------------------- login
@router.post("/login", response_model=TokenOut)
def login(
    payload: LoginIn,
    request: Request,
    resposta: Response,
    db: Session = Depends(get_db),
) -> TokenOut:
    email = payload.email.lower()
    ip = ip_do_cliente(request)

    restante = limites.bloqueado(db, email, ip)
    if restante:
        auditoria.registrar(db, auditoria.LOGIN_BLOQUEADO, detalhe=email, ip=ip)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"muitas tentativas; tente de novo em {restante // 60 + 1} min",
            headers={"Retry-After": str(restante)},
        )

    usuario = db.execute(select(Usuario).where(Usuario.email == email)).scalar_one_or_none()

    # Mensagem unica para e-mail inexistente, senha errada e conta desativada.
    # Diferenciar entregaria ao atacante uma lista de e-mails validos.
    generico = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="e-mail ou senha incorretos"
    )

    if usuario is None:
        # Gasta o mesmo tempo do caminho valido para nao vazar por temporizacao.
        senhas.consumir_tempo_de_hash()
        limites.registrar(db, email, ip, sucesso=False)
        auditoria.registrar(db, auditoria.LOGIN_FALHA, detalhe=email, ip=ip)
        db.commit()
        raise generico

    confere, novo_hash = senhas.verificar(payload.senha, usuario.senha_hash)
    if not confere or not usuario.ativo:
        limites.registrar(db, email, ip, sucesso=False)
        auditoria.registrar(db, auditoria.LOGIN_FALHA, usuario_id=usuario.id, detalhe=email, ip=ip)
        db.commit()
        raise generico

    # Custo do Argon2 aumentou desde o cadastro: reidrata agora, que e o unico
    # instante em que a senha em claro esta disponivel.
    if novo_hash:
        usuario.senha_hash = novo_hash

    usuario.ultimo_login_em = agora()
    limites.registrar(db, email, ip, sucesso=True)
    limites.limpar(db, email)

    refresh, csrf = _abrir_sessao(db, usuario, request)
    auditoria.registrar(db, auditoria.LOGIN_OK, usuario_id=usuario.id, ip=ip)
    db.commit()

    _gravar_cookies(resposta, refresh, csrf)
    return _resposta_de_token(db, usuario)


# ------------------------------------------------------------------ refresh
@router.post("/refresh", response_model=TokenOut)
def refresh(
    request: Request,
    resposta: Response,
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias=CABECALHO_CSRF),
) -> TokenOut:
    ip = ip_do_cliente(request)
    invalido = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="sessao invalida")

    token_claro = request.cookies.get(settings.cookie_refresh_nome)
    if not token_claro:
        raise invalido

    # Double-submit: o header so pode ser preenchido por JavaScript da mesma
    # origem; um site de terceiros consegue mandar o cookie, mas nao o header.
    csrf_cookie = request.cookies.get(settings.cookie_csrf_nome, "")
    if not tokens.csrf_confere(csrf_cookie, x_csrf_token or ""):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="csrf invalido")

    sessao = db.execute(
        select(SessaoRefresh).where(SessaoRefresh.token_hash == tokens.hash_refresh(token_claro))
    ).scalar_one_or_none()

    if sessao is None:
        raise invalido

    momento = agora()

    # Reuso: este token ja tinha sido trocado. Ou o legitimo esta repetindo, ou
    # alguem copiou. Nao da para distinguir, entao derruba a familia inteira.
    if sessao.usada_em is not None or sessao.revogada_em is not None:
        db.execute(
            update(SessaoRefresh)
            .where(SessaoRefresh.familia == sessao.familia, SessaoRefresh.revogada_em.is_(None))
            .values(revogada_em=momento)
        )
        auditoria.registrar(
            db,
            auditoria.REFRESH_REUSO,
            usuario_id=sessao.usuario_id,
            detalhe=f"familia {sessao.familia} revogada por reuso",
            ip=ip,
        )
        db.commit()
        _limpar_cookies(resposta)
        raise invalido

    if sessao.expira_em <= momento:
        raise invalido

    usuario = db.get(Usuario, sessao.usuario_id)
    if usuario is None or not usuario.ativo:
        raise invalido

    sessao.usada_em = momento
    novo_refresh, csrf = _abrir_sessao(db, usuario, request, familia=sessao.familia)
    auditoria.registrar(db, auditoria.REFRESH_OK, usuario_id=usuario.id, ip=ip)
    db.commit()

    _gravar_cookies(resposta, novo_refresh, csrf)
    return _resposta_de_token(db, usuario)


# ------------------------------------------------------------------- logout
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, resposta: Response, db: Session = Depends(get_db)) -> None:
    """Encerra a sessao.

    Sem autenticacao de propria: logout precisa funcionar mesmo com o access
    token ja expirado, senao o refresh ficaria valido ate o prazo dele.
    """
    token_claro = request.cookies.get(settings.cookie_refresh_nome)

    if token_claro:
        sessao = db.execute(
            select(SessaoRefresh).where(SessaoRefresh.token_hash == tokens.hash_refresh(token_claro))
        ).scalar_one_or_none()

        if sessao is not None:
            db.execute(
                update(SessaoRefresh)
                .where(SessaoRefresh.familia == sessao.familia, SessaoRefresh.revogada_em.is_(None))
                .values(revogada_em=agora())
            )
            auditoria.registrar(
                db, auditoria.LOGOUT, usuario_id=sessao.usuario_id, ip=ip_do_cliente(request)
            )
            db.commit()

    _limpar_cookies(resposta)


# ----------------------------------------------------------------- eu / senha
# ------------------------------------------------------- redefinicao de senha
@router.post("/esqueci", status_code=status.HTTP_202_ACCEPTED)
def esqueci_senha(
    payload: EsqueciSenhaIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Solicita um link de redefinicao.

    Responde **sempre** 202, exista ou nao a conta. Uma resposta diferente para
    e-mail inexistente transformaria este endpoint num verificador de cadastro
    aberto na internet -- e ele nao exige autenticacao nenhuma.
    """
    email = payload.email.lower()
    ip = ip_do_cliente(request)
    resposta_padrao = {"detail": "se houver conta com este e-mail, o link foi enviado"}

    usuario = db.execute(select(Usuario).where(Usuario.email == email)).scalar_one_or_none()
    if usuario is None or not usuario.ativo:
        auditoria.registrar(db, auditoria.SENHA_RESET_SOLICITADO, detalhe=f"{email} (sem conta)", ip=ip)
        db.commit()
        return resposta_padrao

    # Limite por conta: sem isso, o endpoint vira gerador de spam apontado para
    # a caixa de entrada de outra pessoa.
    uma_hora = agora() - dt.timedelta(hours=1)
    recentes = db.execute(
        select(func.count())
        .select_from(TokenResetSenha)
        .where(TokenResetSenha.usuario_id == usuario.id, TokenResetSenha.criado_em >= uma_hora)
    ).scalar_one()

    if recentes >= settings.reset_max_por_hora:
        auditoria.registrar(
            db, auditoria.SENHA_RESET_SOLICITADO, usuario_id=usuario.id,
            detalhe="recusado: limite por hora", ip=ip,
        )
        db.commit()
        return resposta_padrao

    claro, hash_ = tokens.gerar_refresh_token()  # mesma primitiva: 256 bits opacos
    db.add(
        TokenResetSenha(
            usuario_id=usuario.id,
            token_hash=hash_,
            expira_em=agora() + dt.timedelta(minutes=settings.reset_token_ttl_min),
            ip=ip,
        )
    )
    auditoria.registrar(db, auditoria.SENHA_RESET_SOLICITADO, usuario_id=usuario.id, ip=ip)
    db.commit()

    notificacao.enviar_link_de_reset(
        usuario.email,
        f"{settings.app_url}/redefinir?token={claro}",
        settings.reset_token_ttl_min,
    )
    return resposta_padrao


@router.post("/redefinir", status_code=status.HTTP_204_NO_CONTENT)
def redefinir_senha(
    payload: RedefinirSenhaIn,
    request: Request,
    resposta: Response,
    db: Session = Depends(get_db),
) -> None:
    """Consome o token e grava a senha nova."""
    ip = ip_do_cliente(request)
    invalido = HTTPException(status_code=400, detail="link invalido ou expirado")

    registro = db.execute(
        select(TokenResetSenha).where(
            TokenResetSenha.token_hash == tokens.hash_refresh(payload.token)
        )
    ).scalar_one_or_none()

    momento = agora()
    if registro is None or registro.usado_em is not None or registro.expira_em <= momento:
        raise invalido

    usuario = db.get(Usuario, registro.usuario_id)
    if usuario is None or not usuario.ativo:
        raise invalido

    try:
        senhas.validar_forca(payload.senha_nova, email=usuario.email, nome=usuario.nome)
    except senhas.SenhaFraca as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro

    registro.usado_em = momento
    usuario.senha_hash = senhas.gerar_hash(payload.senha_nova)
    usuario.senha_alterada_em = momento
    usuario.token_versao += 1

    # Derruba tudo: quem redefine a senha normalmente perdeu o controle da
    # conta, e as sessoes abertas podem ser de quem tomou.
    db.execute(
        update(SessaoRefresh)
        .where(SessaoRefresh.usuario_id == usuario.id, SessaoRefresh.revogada_em.is_(None))
        .values(revogada_em=momento)
    )
    # Invalida os demais links pendentes desta conta.
    db.execute(
        update(TokenResetSenha)
        .where(
            TokenResetSenha.usuario_id == usuario.id,
            TokenResetSenha.usado_em.is_(None),
        )
        .values(usado_em=momento)
    )

    auditoria.registrar(db, auditoria.SENHA_RESET_USADO, usuario_id=usuario.id, ip=ip)
    db.commit()
    _limpar_cookies(resposta)


@router.get("/eu", response_model=UsuarioOut)
def eu(usuario: Usuario = Depends(usuario_atual)) -> UsuarioOut:
    return UsuarioOut.model_validate(usuario, from_attributes=True)


@router.post("/senha", status_code=status.HTTP_204_NO_CONTENT)
def trocar_senha(
    payload: TrocarSenhaIn,
    request: Request,
    resposta: Response,
    usuario: Usuario = Depends(usuario_atual),
    db: Session = Depends(get_db),
) -> None:
    confere, _ = senhas.verificar(payload.senha_atual, usuario.senha_hash)
    if not confere:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="senha atual incorreta")

    try:
        senhas.validar_forca(payload.senha_nova, email=usuario.email, nome=usuario.nome)
    except senhas.SenhaFraca as erro:
        # Literal em vez da constante: o Starlette renomeou
        # HTTP_422_UNPROCESSABLE_ENTITY para ..._CONTENT, e usar qualquer um dos
        # nomes prende o codigo a uma faixa de versao.
        raise HTTPException(status_code=422, detail=str(erro)) from erro

    usuario.senha_hash = senhas.gerar_hash(payload.senha_nova)
    # Invalida todo access token ja emitido (ver deps.py) e derruba todas as
    # sessoes: se a troca foi motivada por suspeita de invasao, o invasor perde
    # o acesso agora, nao daqui a 14 dias.
    usuario.senha_alterada_em = agora()
    usuario.token_versao += 1
    db.execute(
        update(SessaoRefresh)
        .where(SessaoRefresh.usuario_id == usuario.id, SessaoRefresh.revogada_em.is_(None))
        .values(revogada_em=agora())
    )

    auditoria.registrar(
        db, auditoria.SENHA_ALTERADA, usuario_id=usuario.id, ip=ip_do_cliente(request)
    )
    db.commit()
    _limpar_cookies(resposta)
