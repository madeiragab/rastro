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
    ALERTA_LOTE_MUDO,
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
    # A sessao roda com autoflush desligado, entao um alerta criado nesta mesma
    # transacao ainda nao estaria visivel para o SELECT -- e varias leituras
    # processadas antes do commit gerariam alertas duplicados do mesmo tipo.
    db.flush()

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
def avaliar_posicao(
    db: Session,
    animal: Animal,
    lat: float,
    lon: float,
    atividade: float,
    evento: str | None = None,
) -> None:
    """Roda as regras que dependem de uma leitura recem-chegada.

    `evento` vem preenchido quando o proprio brinco decidiu -- ele carrega o
    poligono e ja aplicou a histerese localmente. Nesse caso o servidor confia e
    abre o alerta na primeira leitura, em vez de esperar a segunda: o
    dispositivo teve acesso a uma serie de posicoes que o servidor nunca viu,
    porque so transmite uma parte delas.
    """
    momento = agora()

    # --- perda de sinal: chegou leitura, entao o enlace voltou.
    _resolver(db, animal.id, ALERTA_SEM_SINAL)

    # --- regra 1: geocerca -------------------------------------------------
    fora_confirmado = False
    if animal.pasto is not None:
        resultado = geofence.avaliar(db, animal.pasto, lat, lon)
        animal.distancia_pasto_m = resultado.distancia_m

        if resultado.dentro and evento != "saiu_da_area":
            animal.leituras_fora = 0
            _resolver(db, animal.id, ALERTA_FORA)
        else:
            animal.leituras_fora += 1
            # Histerese: uma unica leitura fora nao abre alerta -- a menos que o
            # brinco ja tenha confirmado por conta propria.
            if evento == "saiu_da_area":
                animal.leituras_fora = max(
                    animal.leituras_fora, settings.geofence_confirmacoes
                )
            if animal.leituras_fora >= settings.geofence_confirmacoes:
                fora_confirmado = True
                _abrir(
                    db,
                    animal,
                    ALERTA_FORA,
                    f"{animal.nome} saiu de {animal.pasto.nome} "
                    f"({resultado.distancia_m:.0f} m além da divisa).",
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
                f"{animal.nome} sem movimento há {minutos} min. "
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
def _alerta_de_lote_aberto(db: Session, pasto_id: int) -> Alerta | None:
    db.flush()
    return db.execute(
        select(Alerta)
        .where(
            Alerta.pasto_id == pasto_id,
            Alerta.tipo == ALERTA_LOTE_MUDO,
            Alerta.resolvido_em.is_(None),
        )
        .limit(1)
    ).scalar_one_or_none()


def varrer_silencio(db: Session) -> int:
    """Abre alerta para quem passou tempo demais sem reportar.

    O limiar e relativo a periodicidade esperada do proprio dispositivo. Um
    limiar fixo global geraria ruido: a periodicidade varia por animal e por
    terreno.

    **Silencio coletivo e tratado a parte.** Com a topologia de mestre, se o
    brinco que repassa o lote cair, todos os animais daquele lote calam ao mesmo
    tempo. Abrir um alerta por animal produziria vinte notificacoes de
    madrugada dizendo que cada boi foi roubado -- falso, e o suficiente para o
    produtor desinstalar o aplicativo. Vinte animais silenciando juntos e mestre
    caido, nao vinte furtos simultaneos.
    """
    momento = agora()
    limite_s = max(
        settings.intervalo_reporte_s * settings.sinal_fator_silencio,
        settings.sinal_silencio_minimo_s,
    )

    animais = db.execute(select(Animal)).scalars().all()

    # Agrupa por lote para decidir entre alerta individual e alerta de lote.
    por_lote: dict[int | None, list[Animal]] = {}
    calados: dict[int | None, list[Animal]] = {}

    for animal in animais:
        por_lote.setdefault(animal.pasto_id, []).append(animal)

        if animal.ultimo_contato is None:
            continue
        if (momento - animal.ultimo_contato).total_seconds() >= limite_s:
            calados.setdefault(animal.pasto_id, []).append(animal)

    abertos = 0

    for pasto_id, mudos in calados.items():
        total = len(por_lote.get(pasto_id, []))
        fracao = len(mudos) / total if total else 0.0

        coletivo = (
            pasto_id is not None
            and total >= settings.lote_minimo_para_agrupar
            and fracao >= settings.lote_fracao_muda
        )

        for animal in mudos:
            animal.status = STATUS_OFFLINE

        if coletivo:
            # Um alerta para o lote inteiro, e nenhum por animal.
            if _alerta_de_lote_aberto(db, pasto_id) is None:
                nome = mudos[0].pasto.nome if mudos[0].pasto else "lote"
                db.add(
                    Alerta(
                        animal_id=None,
                        pasto_id=pasto_id,
                        tipo=ALERTA_LOTE_MUDO,
                        severidade="alta",
                        mensagem=(
                            f"{len(mudos)} de {total} animais de {nome} sem comunicação. "
                            "Provável falha do brinco que repassa o lote — "
                            "verificar antes de sair procurando gado."
                        ),
                    )
                )
                abertos += 1
            continue

        for animal in mudos:
            silencio_s = (momento - animal.ultimo_contato).total_seconds()
            minutos = int(silencio_s // 60)
            desde = f"{minutos} min" if minutos else f"{int(silencio_s)} s"
            if _abrir(
                db,
                animal,
                ALERTA_SEM_SINAL,
                f"{animal.nome} sem comunicação há {desde}. "
                "Verificar: brinco arrancado, bateria ou área sem propagação.",
                severidade="media",
            ):
                abertos += 1

    # Lote que voltou a falar: fecha o alerta coletivo.
    for pasto_id in list(por_lote):
        if pasto_id is None or pasto_id in calados:
            continue
        aberto = _alerta_de_lote_aberto(db, pasto_id)
        if aberto is not None:
            aberto.resolvido_em = momento

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
