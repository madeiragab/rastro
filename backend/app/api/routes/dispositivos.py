"""Rotas chamadas pelos brincos, através do mestre.

Todas autenticam por chave de gateway (`X-API-Key`), não por sessão de usuário:
quem fala aqui é equipamento em campo, não gente.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import serializers
from app.api.deps import gateway_atual, ip_do_cliente
from app.config import settings
from app.database import get_db
from app.models import Animal, ChaveGateway, Mestre, Pasto
from app.schemas import (
    AnimalConfigOut,
    AssumirOut,
    ConfigDispositivosOut,
    HeartbeatIn,
    HeartbeatOut,
    LoteTelemetriaIn,
    LoteTelemetriaOut,
    PastoConfigOut,
)
from app.security import auditoria
from app.services import geofence, mestres, telemetria

router = APIRouter(prefix="/dispositivos", tags=["dispositivos"])


def _mestre_da_chave(db: Session, chave: ChaveGateway) -> Mestre:
    mestre = db.execute(
        select(Mestre).where(Mestre.chave_gateway_id == chave.id)
    ).scalar_one_or_none()
    if mestre is None:
        raise HTTPException(status_code=404, detail="esta chave nao esta vinculada a um mestre")
    return mestre


# --------------------------------------------------------------- configuracao
@router.get("/config", response_model=ConfigDispositivosOut)
def config(
    gateway: ChaveGateway = Depends(gateway_atual),
    db: Session = Depends(get_db),
) -> ConfigDispositivosOut:
    """Configuração que o mestre baixa e distribui por rádio para o lote.

    É o que permite a geocerca rodar **no dispositivo**: o polígono viaja uma
    vez, e depois cada brinco decide sozinho se saiu, sem depender de enlace.
    Essa é a diferença entre um alerta que chega e um alerta que depende de o
    animal estar ao alcance na hora exata em que fugiu.

    A `versao` é um resumo do conteúdo. O mestre guarda a última e só
    redistribui por rádio quando muda — rádio é o recurso escasso aqui.
    """
    pastos = (
        db.execute(select(Pasto).where(Pasto.fazenda_id == gateway.fazenda_id, Pasto.ativo.is_(True)))
        .scalars()
        .all()
    )
    animais = (
        db.execute(select(Animal).where(Animal.fazenda_id == gateway.fazenda_id))
        .scalars()
        .all()
    )

    pastos_out = [
        PastoConfigOut(
            id=p.id,
            pontos=geofence.pontos_do_pasto(db, p.id),
            buffer_m=p.buffer_m,
        )
        for p in pastos
    ]
    animais_out = [AnimalConfigOut(brinco=a.brinco, pasto_id=a.pasto_id) for a in animais]

    corpo = {
        "intervalo": settings.intervalo_reporte_s,
        "imobilidade": settings.imobilidade_segundos,
        "atividade": settings.imobilidade_atividade_max,
        "pastos": [p.model_dump() for p in pastos_out],
        "animais": [a.model_dump() for a in animais_out],
    }
    versao = hashlib.sha256(
        json.dumps(corpo, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]

    return ConfigDispositivosOut(
        versao=versao,
        intervalo_reporte_s=settings.intervalo_reporte_s,
        imobilidade_segundos=settings.imobilidade_segundos,
        imobilidade_atividade_max=settings.imobilidade_atividade_max,
        heartbeat_mestre_s=settings.mestre_heartbeat_s,
        pastos=pastos_out,
        animais=animais_out,
    )


# ----------------------------------------------------------------- telemetria
@router.post("/telemetria", response_model=LoteTelemetriaOut, status_code=status.HTTP_201_CREATED)
def telemetria_em_lote(
    payload: LoteTelemetriaIn,
    request: Request,
    gateway: ChaveGateway = Depends(gateway_atual),
    db: Session = Depends(get_db),
) -> LoteTelemetriaOut:
    """Recebe várias leituras de uma vez, como o mestre as acumula.

    O mestre guarda o que ouviu por rádio e sobe tudo numa conexão só: ligar o
    modem celular é o que mais gasta bateria dele, e ligar uma vez para vinte
    leituras custa quase o mesmo que ligar para uma.

    Uma leitura ruim não derruba o lote — as boas entram, e as recusadas são
    contadas na resposta.
    """
    aceitas = 0
    desconhecidos: list[str] = []

    for leitura in payload.leituras:
        animal = db.execute(
            select(Animal).where(Animal.brinco == leitura.brinco)
        ).scalar_one_or_none()

        # A chave é da fazenda: um mestre não reporta gado de outra propriedade.
        if animal is None or animal.fazenda_id != gateway.fazenda_id:
            desconhecidos.append(leitura.brinco)
            continue

        telemetria.registrar(
            db,
            animal,
            lat=leitura.lat,
            lon=leitura.lon,
            atividade=leitura.atividade,
            bateria_pct=leitura.bateria_pct,
            registrada_em=leitura.registrada_em,
            evento=leitura.evento,
        )
        aceitas += 1

    if payload.bateria_mestre_pct is not None:
        mestre = db.execute(
            select(Mestre).where(Mestre.chave_gateway_id == gateway.id)
        ).scalar_one_or_none()
        if mestre is not None:
            mestres.registrar_heartbeat(db, mestre, payload.bateria_mestre_pct)

    if desconhecidos:
        auditoria.registrar(
            db,
            auditoria.TELEMETRIA_NEGADA,
            detalhe=f"gateway {gateway.prefixo}: {len(desconhecidos)} brincos desconhecidos",
            ip=ip_do_cliente(request),
        )

    db.commit()
    return LoteTelemetriaOut(
        aceitas=aceitas, recusadas=len(desconhecidos), desconhecidos=desconhecidos[:20]
    )


# -------------------------------------------------------------------- mestre
@router.post("/heartbeat", response_model=HeartbeatOut)
def heartbeat(
    payload: HeartbeatIn,
    gateway: ChaveGateway = Depends(gateway_atual),
    db: Session = Depends(get_db),
) -> HeartbeatOut:
    """O mestre diz que está vivo e recebe de volta se ainda está no comando.

    `voce_esta_ativo` é ordem, não informação. Um mestre que ficou incomunicável
    e voltou descobre aqui que foi substituído, e deve desligar o modem — senão
    passaria a transmitir em paralelo com quem assumiu no lugar dele.
    """
    mestre = _mestre_da_chave(db, gateway)
    mestres.registrar_heartbeat(db, mestre, payload.bateria_pct)
    db.commit()

    return HeartbeatOut(
        voce_esta_ativo=mestre.ativo,
        proximo_heartbeat_s=settings.mestre_heartbeat_s,
    )


@router.post("/assumir", response_model=AssumirOut)
def assumir(
    gateway: ChaveGateway = Depends(gateway_atual),
    db: Session = Depends(get_db),
) -> AssumirOut:
    """Um reserva pede para assumir. **O servidor decide, não ele.**

    O cenário comum de campo é o mestre estar vivo e o reserva simplesmente não
    ouvi-lo — grota, mata, chuva. Se o reserva decidisse sozinho, passariam a
    existir dois mestres transmitindo, ambos convictos, e como não se ouvem isso
    nunca se resolveria.
    """
    mestre = _mestre_da_chave(db, gateway)

    pode, motivo, esperar = mestres.pode_assumir(db, mestre)
    if not pode:
        db.commit()
        return AssumirOut(assumiu=False, motivo=motivo, tente_de_novo_em_s=esperar)

    mestres.promover(db, mestre, motivo)
    db.commit()
    return AssumirOut(assumiu=True, motivo=motivo)
