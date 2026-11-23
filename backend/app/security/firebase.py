"""Integracao com o Firebase (Admin SDK).

Dois usos, independentes:

- **login** (`AUTH_MODO=firebase`): o app entra pelo Firebase Authentication e
  manda o ID token no header `Authorization`. Aqui so validamos assinatura,
  emissor, audiencia, expiracao e revogacao -- quem decide o que a pessoa pode
  fazer continua sendo a tabela `usuarios` (papel e fazenda).
- **push nativo** (FCM): com `FIREBASE_PROJETO_ID` definido, o despachante de
  alertas tambem envia para os aparelhos Android registrados.

A inicializacao e preguicosa: sem Firebase configurado, nada aqui e importado
nem chamado, e a API sobe exatamente como antes.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.config import settings

log = logging.getLogger("rastro.firebase")

_trava = threading.Lock()
_app: Any = None


class TokenFirebaseInvalido(Exception):
    """ID token ausente, malformado, expirado, revogado ou de outro projeto."""


def app_firebase() -> Any:
    """Instancia unica do Admin SDK, criada no primeiro uso."""
    global _app
    if _app is not None:
        return _app

    with _trava:
        if _app is not None:
            return _app

        import firebase_admin
        from firebase_admin import credentials

        if settings.firebase_credenciais:
            credencial = credentials.Certificate(settings.firebase_credenciais)
        else:
            # Credencial padrao do ambiente: no Cloud Run e a conta de servico
            # do servico; na maquina, `gcloud auth application-default login`.
            credencial = credentials.ApplicationDefault()

        _app = firebase_admin.initialize_app(
            credencial, {"projectId": settings.firebase_projeto_id}, name="rastro"
        )
        log.info("Firebase Admin inicializado para o projeto %s", settings.firebase_projeto_id)
        return _app


# ------------------------------------------------------------------ login
def verificar_id_token(token: str) -> dict:
    """Valida o ID token e devolve as claims.

    `check_revoked=True` custa uma consulta ao Firebase, mas e o que faz
    desativar uma pessoa valer na hora, e nao so quando o token expirar.
    """
    from firebase_admin import auth

    try:
        return auth.verify_id_token(token, app=app_firebase(), check_revoked=True)
    except (ValueError, auth.InvalidIdTokenError, auth.ExpiredIdTokenError,
            auth.RevokedIdTokenError, auth.UserDisabledError,
            auth.CertificateFetchError) as erro:
        raise TokenFirebaseInvalido(type(erro).__name__) from None


def garantir_conta(email: str, senha: str, nome: str) -> str:
    """Cria a conta no Firebase Auth (ou reaproveita a existente). Devolve o uid.

    Usado quando o dono cadastra alguem da equipe e na carga inicial. A senha
    sorteada pelo servidor vira a senha do Firebase; a pessoa troca no
    primeiro acesso pelo proprio app.
    """
    from firebase_admin import auth

    app = app_firebase()
    try:
        existente = auth.get_user_by_email(email, app=app)
        return existente.uid
    except auth.UserNotFoundError:
        pass

    # email_verified=True: quem atesta o e-mail aqui e o dono da fazenda que
    # cadastrou a pessoa, nao um link que ela clicou.
    criado = auth.create_user(
        email=email, password=senha, display_name=nome, email_verified=True, app=app
    )
    return criado.uid


def definir_ativo(uid: str, ativo: bool) -> None:
    """Desativa/reativa no Firebase e corta as sessoes abertas."""
    from firebase_admin import auth

    app = app_firebase()
    auth.update_user(uid, disabled=not ativo, app=app)
    if not ativo:
        auth.revoke_refresh_tokens(uid, app=app)


def revogar_sessoes(uid: str) -> None:
    """Forca novo login (ex.: rebaixamento de papel)."""
    from firebase_admin import auth

    auth.revoke_refresh_tokens(uid, app=app_firebase())


# ------------------------------------------------------------------ FCM
class TokenFcmMorto(Exception):
    """O aparelho desinstalou o app ou o token foi trocado: descartar."""


def enviar_fcm(token: str, titulo: str, mensagem: str, dados: dict[str, str]) -> None:
    from firebase_admin import exceptions, messaging

    msg = messaging.Message(
        token=token,
        notification=messaging.Notification(title=titulo, body=mensagem),
        data=dados,
        android=messaging.AndroidConfig(
            # Alerta de rebanho e urgente: prioridade alta acorda o aparelho
            # mesmo em modo de economia (Doze).
            priority="high",
            ttl=3600,
            notification=messaging.AndroidNotification(
                channel_id="alertas", icon="ic_stat_rastro", color="#2E9E63"
            ),
        ),
    )
    try:
        messaging.send(msg, app=app_firebase())
    except (messaging.UnregisteredError, messaging.SenderIdMismatchError) as erro:
        raise TokenFcmMorto(str(erro)) from None
    except exceptions.InvalidArgumentError as erro:
        # Token malformado tambem nao tem conserto.
        raise TokenFcmMorto(str(erro)) from None
