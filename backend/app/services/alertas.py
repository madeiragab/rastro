"""Motor de alertas.

Tres regras, cada uma com a mitigacao de alarme falso embutida:

1. FORA DA AREA  -- zona de tolerancia + N leituras consecutivas fora.
2. IMOVEL        -- baseado no acelerometro, nao na variacao do GNSS.
3. SEM SINAL     -- limiar relativo a periodicidade do proprio dispositivo.

Um alerta aberto nao e reaberto enquanto nao for resolvido, para nao inundar
o produtor com a mesma ocorrencia a cada leitura.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    ALERTA_FORA,
    ALERTA_IMOVEL,
    ALERTA_SEM_SINAL,
    STATUS_FORA,
    STATUS_IMOVEL,
    STATUS_OFFLINE,
    STATUS_OK,
    Alerta,
    Animal,
    agora,
)
from app.services import geofence


def _alerta_aberto(db: Session, animal_id: int, tipo: str) -> Alerta | None:
    return db.execute(
        select(Alerta)
        .where(Alerta.animal_id == animal_id, Alerta.tipo == tipo, Alerta.resolvido_em.is_(None))
        .limit(1)
    ).scalar_one_or_none()


def _abrir(
    db: Session,
    animal: Animal,
    tipo: str,
    mensagem: str,
    severidade: str = "alta",
    lat: float | None = None,
    lon: float | None = None,
) -> Alerta | None:
    """Abre um alerta se ainda nao houver um aberto do mesmo tipo."""
    if _alerta_aberto(db, animal.id, tipo):
        return None

    alerta = Alerta(
        animal_id=animal.id,
        tipo=tipo,
        severidade=severidade,
        mensagem=mensagem,
        geom=geofence.ponto(lat, lon) if lat is not None and lon is not None else None,
    )
    db.add(alerta)
    return alerta


def _resolver(db: Session, animal_id: int, tipo: str) -> None:
    alerta = _alerta_aberto(db, animal_id, tipo)
    if alerta:
        alerta.resolvido_em = agora()


# --------------------------------------------------------------------------
# Regra 1 e 2: avaliadas quando chega uma posicao nova.
# --------------------------------------------------------------------------
def avaliar_posicao(db: Session, animal: Animal, lat: float, lon: float, atividade: float) -> None:
    """Roda as regras que dependem de uma leitura recem-chegada."""
    momento = agora()

    # --- perda de sinal: chegou leitura, entao o enlace voltou.
    _resolver(db, animal.id, ALERTA_SEM_SINAL)

    # --- regra 1: geocerca -------------------------------------------------
    fora_confirmado = False
    if animal.pasto is not None:
        resultado = geofence.avaliar(db, animal.pasto, lat, lon)
        animal.distancia_pasto_m = resultado.distancia_m

        if resultado.dentro:
            animal.leituras_fora = 0
            _resolver(db, animal.id, ALERTA_FORA)
        else:
            animal.leituras_fora += 1
            # Histerese: uma unica leitura fora nao abre alerta.
            if animal.leituras_fora >= settings.geofence_confirmacoes:
                fora_confirmado = True
                _abrir(
                    db,
                    animal,
                    ALERTA_FORA,
                    f"{animal.nome} saiu de {animal.pasto.nome} "
                    f"({resultado.distancia_m:.0f} m alem da divisa).",
                    severidade="alta",
                    lat=lat,
                    lon=lon,
                )
    else:
        animal.distancia_pasto_m = 0.0
        animal.leituras_fora = 0

    # --- regra 2: imobilidade ---------------------------------------------
    # O acelerometro e quem decide. GNSS parado, sozinho, mente: bovino
    # deitado ruminando fica estatico por horas em condicao normal.
    imovel_confirmado = False
    if atividade <= settings.imobilidade_atividade_max:
        if animal.imovel_desde is None:
            animal.imovel_desde = momento
        parado_s = (momento - animal.imovel_desde).total_seconds()
        if parado_s >= settings.imobilidade_segundos:
            imovel_confirmado = True
            minutos = int(parado_s // 60)
            _abrir(
                db,
                animal,
                ALERTA_IMOVEL,
                f"{animal.nome} sem movimento ha {minutos} min. "
                "Verificar: parto, queda, atolamento ou morte.",
                severidade="critica",
                lat=lat,
                lon=lon,
            )
    else:
        animal.imovel_desde = None
        _resolver(db, animal.id, ALERTA_IMOVEL)

    # --- status consolidado ------------------------------------------------
    if imovel_confirmado:
        animal.status = STATUS_IMOVEL
    elif fora_confirmado:
        animal.status = STATUS_FORA
    else:
        animal.status = STATUS_OK


# --------------------------------------------------------------------------
# Regra 3: avaliada por varredura, porque depende de ausencia de dado.
# --------------------------------------------------------------------------
def varrer_silencio(db: Session) -> int:
    """Abre alerta para todo animal que passou tempo demais sem reportar.

    O limiar e relativo a periodicidade esperada do proprio dispositivo. Um
    limiar fixo global geraria ruido: a periodicidade varia por animal e por
    terreno.
    """
    momento = agora()
    limite_s = max(
        settings.intervalo_reporte_s * settings.sinal_fator_silencio,
        settings.sinal_silencio_minimo_s,
    )

    abertos = 0
    animais = db.execute(select(Animal)).scalars().all()

    for animal in animais:
        if animal.ultimo_contato is None:
            continue

        silencio_s = (momento - animal.ultimo_contato).total_seconds()
        if silencio_s < limite_s:
            continue

        animal.status = STATUS_OFFLINE
        minutos = int(silencio_s // 60)
        desde = f"{minutos} min" if minutos else f"{int(silencio_s)} s"
        if _abrir(
            db,
            animal,
            ALERTA_SEM_SINAL,
            f"{animal.nome} sem comunicacao ha {desde}. "
            "Verificar: brinco arrancado, bateria ou area sem propagacao.",
            severidade="media",
        ):
            abertos += 1

    return abertos


def resolver_todos(db: Session, animal_id: int) -> None:
    """Fecha os alertas abertos de um animal. Usado quando o produtor confirma
    que tratou a ocorrencia."""
    alertas = (
        db.execute(
            select(Alerta).where(Alerta.animal_id == animal_id, Alerta.resolvido_em.is_(None))
        )
        .scalars()
        .all()
    )
    for alerta in alertas:
        alerta.resolvido_em = agora()

    animal = db.get(Animal, animal_id)
    if animal:
        animal.status = STATUS_OK
        animal.leituras_fora = 0
        animal.imovel_desde = None
