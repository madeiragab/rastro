"""Emissao e validacao de tokens.

Dois tipos, de proposito diferente:

**Access token** -- JWT assinado, curto (15 min), enviado no header
`Authorization: Bearer`. E autocontido: a API valida a assinatura sem consultar
o banco. O preco disso e nao poder revogar antes de expirar; por isso a vida
util e curta.

**Refresh token** -- string opaca de 256 bits, sem significado proprio, guardada
no banco apenas como SHA-256 e enviada em cookie HttpOnly. E revogavel a
qualquer momento e sofre rotacao a cada uso.

Por que SHA-256 no refresh e Argon2 na senha: Argon2 e caro de proposito para
proteger segredos de baixa entropia, que humanos escolhem e atacantes adivinham.
Um token de 256 bits aleatorios nao tem dicionario a percorrer, entao basta um
hash rapido para que um vazamento do banco nao vire sessao valida.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets

import jwt

from app.config import settings

TIPO_ACESSO = "access"


class TokenInvalido(Exception):
    """Assinatura, formato, emissor, audiencia ou validade incorretos."""


def _agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --------------------------------------------------------------- access token
def criar_access_token(usuario_id: int, papel: str, fazenda_id: int | None) -> tuple[str, int]:
    """Devolve `(token, segundos_ate_expirar)`."""
    emitido = _agora()
    expira = emitido + dt.timedelta(minutes=settings.access_token_ttl_min)

    payload = {
        "sub": str(usuario_id),
        "papel": papel,
        "fazenda": fazenda_id,
        "tipo": TIPO_ACESSO,
        "iss": settings.jwt_emissor,
        "aud": settings.jwt_audiencia,
        "iat": int(emitido.timestamp()),
        "nbf": int(emitido.timestamp()),
        "exp": int(expira.timestamp()),
        # jti unico permite auditar e, se um dia for preciso, manter uma lista
        # de revogacao pontual sem invalidar todas as sessoes.
        "jti": secrets.token_urlsafe(16),
    }

    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algoritmo)
    return token, settings.access_token_ttl_min * 60


def ler_access_token(token: str) -> dict:
    """Valida e devolve as claims. Levanta `TokenInvalido` em qualquer falha."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            # Lista fixa de algoritmos: aceitar o `alg` do proprio token e a
            # falha classica que permite o ataque com alg=none.
            algorithms=[settings.jwt_algoritmo],
            audience=settings.jwt_audiencia,
            issuer=settings.jwt_emissor,
            options={"require": ["exp", "iat", "nbf", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as erro:
        raise TokenInvalido(str(erro)) from erro

    if payload.get("tipo") != TIPO_ACESSO:
        raise TokenInvalido("tipo de token incorreto")

    return payload


# -------------------------------------------------------------- refresh token
def gerar_refresh_token() -> tuple[str, str]:
    """Devolve `(token_em_claro, hash)`. O claro so existe nesta chamada."""
    token = secrets.token_urlsafe(32)  # 256 bits
    return token, hash_refresh(token)


def hash_refresh(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def nova_familia() -> str:
    """Identificador da cadeia de rotacoes de um mesmo login."""
    return secrets.token_urlsafe(24)


# ------------------------------------------------------------------ csrf
def gerar_csrf() -> str:
    return secrets.token_urlsafe(32)


def csrf_confere(a: str, b: str) -> bool:
    """Comparacao em tempo constante, para nao vazar o token byte a byte."""
    return hmac.compare_digest(a or "", b or "")
