"""Notificacao push (Web Push com VAPID).

E a promessa central do produto: sem push, o alerta so existe enquanto o
aplicativo esta aberto -- ou seja, o produtor precisaria vigiar a tela para
descobrir que nao precisa vigiar o pasto.

Desenho do envio: um laco de fundo varre alertas com `notificado_em` nulo e
manda. Nao e feito no caminho da requisicao de telemetria de proposito -- push
sai por HTTP para um servico de terceiro, que pode estar lento, e o gateway nao
pode ficar esperando isso para confirmar uma posicao.

Contexto seguro: navegador so registra Service Worker em HTTPS **ou** em
localhost. Para abrir no celular pela rede local e preciso TLS -- ver o perfil
`tls` do docker compose.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Alerta, Animal, ConfiguracaoPush, InscricaoPush, Usuario, agora

log = logging.getLogger("rastro.push")

INTERVALO_S = 5.0

# Depois disso, a inscricao e considerada morta e descartada. Endpoint de push
# expira quando a pessoa desinstala o app ou limpa os dados do navegador, e
# insistir para sempre so gera trafego e ruido no log.
MAX_FALHAS = 5

TITULOS = {
    "fora_da_area": "Animal fora da area",
    "imovel": "Animal sem movimento",
    "sem_sinal": "Brinco sem sinal",
}


# ------------------------------------------------------------------ chaves
def obter_chaves(db: Session) -> ConfiguracaoPush:
    """Devolve o par VAPID, gerando na primeira vez.

    Guardado no banco para sobreviver a reinicializacao: trocar a chave
    invalidaria todas as inscricoes, e os aparelhos so perceberiam deixando de
    receber aviso.
    """
    config = db.execute(select(ConfiguracaoPush).limit(1)).scalar_one_or_none()
    if config is not None:
        return config

    vapid = Vapid01()
    vapid.generate_keys()

    privada = vapid.private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    # O navegador espera a chave publica como ponto nao comprimido em base64url
    # sem preenchimento -- e o formato do `applicationServerKey`.
    bruta = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    publica = base64.urlsafe_b64encode(bruta).rstrip(b"=").decode()

    config = ConfiguracaoPush(chave_privada_pem=privada, chave_publica_app=publica)
    db.add(config)
    db.commit()
    db.refresh(config)

    log.info("par de chaves VAPID gerado e guardado")
    return config


# ------------------------------------------------------------------ envio
def _enviar(config: ConfiguracaoPush, inscricao: InscricaoPush, carga: dict) -> bool:
    try:
        webpush(
            subscription_info={
                "endpoint": inscricao.endpoint,
                "keys": {"p256dh": inscricao.chave_p256dh, "auth": inscricao.chave_auth},
            },
            data=json.dumps(carga),
            vapid_private_key=config.chave_privada_pem,
            # O `sub` identifica quem opera o servico, para o fabricante do
            # navegador ter a quem recorrer em caso de abuso.
            vapid_claims={"sub": "mailto:suporte@rastro.com.br"},
            ttl=3600,
        )
        return True
    except WebPushException as erro:
        codigo = getattr(erro.response, "status_code", None)
        # 404 e 410 significam inscricao morta: o navegador foi desinstalado ou
        # os dados foram limpos. Nao adianta insistir.
        if codigo in (404, 410):
            log.info("inscricao %s expirada no servico de push", inscricao.id)
            return False
        log.warning("falha ao enviar push para a inscricao %s: %s", inscricao.id, erro)
        return False
    except Exception:  # noqa: BLE001 - o laco nao pode morrer por um envio
        log.exception("erro inesperado no envio de push")
        return False


def _carga_do_alerta(db: Session, alerta: Alerta) -> dict:
    animal = db.get(Animal, alerta.animal_id)
    return {
        "titulo": TITULOS.get(alerta.tipo, "Alerta no rebanho"),
        "mensagem": alerta.mensagem,
        "tipo": alerta.tipo,
        "animal_id": alerta.animal_id,
        "fazenda_id": animal.fazenda_id if animal else None,
    }


def despachar_pendentes(db: Session) -> int:
    """Envia os alertas ainda nao notificados. Devolve quantos foram enviados."""
    pendentes = (
        db.execute(
            select(Alerta)
            .where(Alerta.notificado_em.is_(None), Alerta.resolvido_em.is_(None))
            .order_by(Alerta.criado_em)
            .limit(20)
        )
        .scalars()
        .all()
    )
    if not pendentes:
        return 0

    inscricoes = db.execute(select(InscricaoPush)).scalars().all()

    # Marca antes de ter destinatario: sem inscricao nenhuma, o alerta nao pode
    # ficar pendente para sempre e ser despejado em massa quando alguem ativar
    # as notificacoes.
    if not inscricoes:
        for alerta in pendentes:
            alerta.notificado_em = agora()
        db.commit()
        return 0

    config = obter_chaves(db)
    enviados = 0

    for alerta in pendentes:
        carga = _carga_do_alerta(db, alerta)

        for inscricao in inscricoes:
            # Cada pessoa so recebe alerta da propria fazenda.
            usuario = db.get(Usuario, inscricao.usuario_id)
            if usuario is None or not usuario.ativo:
                continue
            if carga["fazenda_id"] is not None and usuario.fazenda_id != carga["fazenda_id"]:
                continue

            if _enviar(config, inscricao, carga):
                inscricao.ultimo_envio = agora()
                inscricao.falhas = 0
                enviados += 1
            else:
                inscricao.falhas += 1
                if inscricao.falhas >= MAX_FALHAS:
                    db.delete(inscricao)

        alerta.notificado_em = agora()

    db.commit()
    return enviados


async def loop() -> None:
    log.info("despachante de push iniciado (intervalo=%ss)", INTERVALO_S)
    while True:
        await asyncio.sleep(INTERVALO_S)
        try:
            await asyncio.to_thread(_ciclo)
        except Exception:  # pragma: no cover
            log.exception("falha no ciclo de push")


def _ciclo() -> None:
    db = SessionLocal()
    try:
        despachar_pendentes(db)
    finally:
        db.close()
