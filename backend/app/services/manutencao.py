"""Rotina periodica de limpeza.

Sessoes expiradas e tentativas de login antigas nao servem para nada e crescem
para sempre. Guardar dado alem do necessario e, alem de desperdicio, aumento de
superficie: o que nao esta no banco nao vaza.

Os eventos de auditoria **nao** sao apagados aqui. Trilha de auditoria tem
politica de retencao propria, decidida por quem opera, nao pela aplicacao.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import SessaoRefresh, agora
from app.security import limites

log = logging.getLogger("rastro.manutencao")

INTERVALO_S = 3600

# Sessao revogada ou expirada ainda serve por um tempo para investigar reuso de
# token; depois disso, vira lixo.
RETENCAO_SESSAO_DIAS = 30
RETENCAO_TENTATIVAS_DIAS = 30


def limpar() -> tuple[int, int]:
    db: Session = SessionLocal()
    try:
        corte = agora() - dt.timedelta(days=RETENCAO_SESSAO_DIAS)
        sessoes = db.execute(delete(SessaoRefresh).where(SessaoRefresh.expira_em < corte)).rowcount or 0
        tentativas = limites.podar(db, dias=RETENCAO_TENTATIVAS_DIAS)
        db.commit()
        return sessoes, tentativas
    except Exception:  # pragma: no cover
        db.rollback()
        log.exception("falha na limpeza periodica")
        return 0, 0
    finally:
        db.close()


async def loop() -> None:
    while True:
        await asyncio.sleep(INTERVALO_S)
        sessoes, tentativas = await asyncio.to_thread(limpar)
        if sessoes or tentativas:
            log.info("limpeza: %s sessoes, %s tentativas de login", sessoes, tentativas)
