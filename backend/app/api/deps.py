"""Dependencias de autenticacao e autorizacao.

Tres identidades circulam na API:

- **usuario** -- pessoa, autenticada por access token JWT no header Authorization;
- **gateway** -- dispositivo, autenticado por chave de API no header X-API-Key;
- **anonimo** -- so `/health` e o login.

Nenhuma rota fica aberta por omissao: quem escrever uma rota nova sem declarar
uma destas dependencias devolve 401, porque `usuario_atual` e exigida no router.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NIVEL_PAPEL, ChaveGateway, Usuario, agora
from app.security import chaves, tokens

# auto_error=False para controlarmos a resposta: o default do FastAPI vaza a
# diferenca entre "sem header" e "header invalido".
_bearer = HTTPBearer(auto_error=False)

CABECALHO_CHAVE = "X-API-Key"


def ip_do_cliente(request: Request) -> str:
    """IP de origem.

    Atras de proxy reverso, `request.client.host` e o IP do proxy. Lemos
    `X-Forwarded-For` **apenas** quando a aplicacao esta explicitamente atras de
    um proxy confiavel -- caso contrario qualquer cliente falsifica o header e
    escapa do bloqueio por IP. No MVP, sem proxy declarado, usamos o socket.
    """
    return request.client.host if request.client else ""


def _nao_autorizado(detalhe: str = "credencial ausente ou invalida") -> HTTPException:
    # Mensagem deliberadamente generica: nao dizemos se o token expirou, se a
    # assinatura falhou ou se o usuario foi desativado.
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalhe,
        headers={"WWW-Authenticate": "Bearer"},
    )


def usuario_atual(
    credencial: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> Usuario:
    if credencial is None or credencial.scheme.lower() != "bearer":
        raise _nao_autorizado()

    try:
        claims = tokens.ler_access_token(credencial.credentials)
    except tokens.TokenInvalido:
        raise _nao_autorizado() from None

    usuario = db.get(Usuario, int(claims["sub"]))
    if usuario is None or not usuario.ativo:
        raise _nao_autorizado()

    # Trocar a senha invalida os access tokens emitidos antes. Sem esta
    # checagem, um token roubado continuaria valendo ate expirar mesmo depois
    # de a vitima trocar a senha -- que e justamente a acao de quem suspeita
    # de invasao.
    if int(claims.get("ver", -1)) != usuario.token_versao:
        raise _nao_autorizado()

    return usuario


def exige_papel(minimo: str):
    """Fabrica de dependencia por nivel de papel: leitura < operador < dono."""

    def verificar(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
        if NIVEL_PAPEL.get(usuario.papel, -1) < NIVEL_PAPEL[minimo]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="seu papel nao permite esta operacao",
            )
        return usuario

    return verificar


def gateway_atual(
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias=CABECALHO_CHAVE),
) -> ChaveGateway:
    """Autentica o dispositivo que envia telemetria."""
    if not x_api_key:
        raise _nao_autorizado("chave de gateway ausente")

    partes = chaves.separar(x_api_key)
    if partes is None:
        raise _nao_autorizado("chave de gateway invalida")

    prefixo, segredo = partes
    registro = db.execute(
        select(ChaveGateway).where(ChaveGateway.prefixo == prefixo)
    ).scalar_one_or_none()

    # Verificamos o hash mesmo sem registro para que o tempo de resposta nao
    # revele quais prefixos existem.
    if registro is None:
        chaves.consumir_tempo()
        raise _nao_autorizado("chave de gateway invalida")

    momento = agora()
    if not registro.ativa or registro.revogada_em is not None:
        raise _nao_autorizado("chave de gateway revogada")
    if registro.expira_em is not None and registro.expira_em <= momento:
        raise _nao_autorizado("chave de gateway expirada")

    if not chaves.confere(segredo, registro.chave_hash):
        raise _nao_autorizado("chave de gateway invalida")

    registro.ultima_utilizacao = momento
    db.commit()
    return registro
