"""Arbitragem de qual mestre esta em servico.

O ponto de todo este modulo cabe numa frase: **os brincos nao decidem**.

O cenario comum de campo e o mestre estar vivo e um reserva simplesmente nao
ouvi-lo -- o animal entrou numa grota, choveu, tem mata no meio. Se o reserva
decidisse sozinho, assumiria, e passariam a existir dois mestres transmitindo,
ambos convictos, gastando celular em dobro. Como nao se ouvem, isso nunca se
resolveria.

Com o servidor como unico arbitro, isso e impossivel por construcao: ele sabe
quando recebeu do mestre atual, e essa e a unica verdade que conta.

A garantia nao esta so aqui. Ha indice unico parcial no banco (migracao 0004)
recusando dois ativos no mesmo lote -- inclusive numa corrida entre dois
pedidos simultaneos.
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import ALERTA_MESTRE_TROCADO, Alerta, Mestre, agora

log = logging.getLogger("rastro.mestres")


def limite_silencio() -> dt.timedelta:
    """Quanto tempo sem heartbeat antes de o mestre ser considerado calado."""
    return dt.timedelta(seconds=settings.mestre_heartbeat_s * settings.mestre_fator_silencio)


def ativo_do_lote(db: Session, pasto_id: int | None) -> Mestre | None:
    return db.execute(
        select(Mestre).where(Mestre.pasto_id == pasto_id, Mestre.ativo.is_(True)).limit(1)
    ).scalar_one_or_none()


def registrar_heartbeat(db: Session, mestre: Mestre, bateria_pct: int) -> Mestre:
    mestre.ultimo_heartbeat = agora()
    mestre.bateria_pct = bateria_pct
    return mestre


def pode_assumir(db: Session, candidato: Mestre) -> tuple[bool, str, int | None]:
    """Decide se o candidato assume. Devolve `(assumiu, motivo, esperar_s)`."""
    momento = agora()
    atual = ativo_do_lote(db, candidato.pasto_id)

    # Ninguem no comando: assume sem discussao. E o caso da primeira subida.
    if atual is None:
        return True, "sem mestre em servico", None

    if atual.id == candidato.id:
        return True, "voce ja e o mestre", None

    # O mestre atual nunca deu sinal desde que foi promovido: trata como calado.
    ultimo = atual.ultimo_heartbeat or atual.assumiu_em or atual.criado_em
    silencio = momento - ultimo
    limite = limite_silencio()

    if silencio < limite:
        # Aqui esta o valor do arbitro: o mestre esta VIVO, quem nao esta
        # ouvindo e o candidato. Negar impede o cerebro dividido.
        faltam = int((limite - silencio).total_seconds()) + 1
        return False, "o mestre em servico esta vivo", faltam

    # Desempate por bateria: entre dois candidatos, assume quem aguenta mais.
    # Sem isso, o mais fraco poderia assumir e morrer em seguida.
    melhor = db.execute(
        select(Mestre)
        .where(
            Mestre.pasto_id == candidato.pasto_id,
            Mestre.ativo.is_(False),
            Mestre.id != atual.id,
            Mestre.bateria_pct > candidato.bateria_pct,
            Mestre.ultimo_heartbeat.is_not(None),
            Mestre.ultimo_heartbeat >= momento - limite,
        )
        .limit(1)
    ).scalar_one_or_none()

    if melhor is not None:
        return False, "outro reserva tem mais bateria", int(limite.total_seconds())

    return True, "mestre em servico calado", None


def promover(db: Session, candidato: Mestre, motivo: str) -> None:
    """Troca o mestre em servico e registra o alerta."""
    momento = agora()
    anterior = ativo_do_lote(db, candidato.pasto_id)

    if anterior is not None and anterior.id != candidato.id:
        anterior.ativo = False

    # Precisa ir ao banco antes de marcar o novo: o indice unico parcial recusa
    # dois ativos no mesmo lote, e o anterior ainda conta como ativo ate aqui.
    db.flush()

    candidato.ativo = True
    candidato.assumiu_em = momento
    candidato.trocas += 1
    candidato.ultimo_heartbeat = momento

    nome_lote = candidato.pasto.nome if candidato.pasto else "sem lote"
    db.add(
        Alerta(
            # Alerta de lote: nao pertence a nenhum animal.
            animal_id=None,
            pasto_id=candidato.pasto_id,
            tipo=ALERTA_MESTRE_TROCADO,
            severidade="media",
            mensagem=(
                f"O brinco que repassa {nome_lote} mudou ({motivo}). "
                "O rebanho segue sendo monitorado."
            ),
        )
    )

    log.info("mestre do lote %s trocado para %s (%s)", candidato.pasto_id, candidato.id, motivo)
