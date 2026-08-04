"""Protecao contra forca bruta no login.

Contagem em banco, e nao em memoria de processo, por dois motivos: sobrevive a
reinicio e continua correta com mais de uma replica da API.

Duas trilhas independentes:

- **por e-mail** -- barra o ataque dirigido a uma conta especifica;
- **por IP** -- barra o password spraying, que testa uma senha comum contra
  muitas contas diferentes e nunca acumula tentativas no mesmo e-mail.

Tentativa bem-sucedida limpa o historico daquele e-mail.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import TentativaLogin, agora

# Limite por IP mais folgado que o por e-mail: varias pessoas podem sair pelo
# mesmo IP (NAT da fazenda, escritorio), e trancar todas seria pior que o ataque.
FATOR_IP = 4


def registrar(db: Session, email: str, ip: str, sucesso: bool) -> None:
    db.add(TentativaLogin(email=(email or "").lower(), ip=ip or "", sucesso=sucesso))


def _falhas_desde(db: Session, desde: dt.datetime, *, email: str = "", ip: str = "") -> int:
    consulta = select(func.count()).select_from(TentativaLogin).where(
        TentativaLogin.sucesso.is_(False), TentativaLogin.criada_em >= desde
    )
    if email:
        consulta = consulta.where(TentativaLogin.email == email.lower())
    if ip:
        consulta = consulta.where(TentativaLogin.ip == ip)
    return int(db.execute(consulta).scalar_one())


def bloqueado(db: Session, email: str, ip: str) -> int:
    """Devolve os segundos restantes de bloqueio, ou 0 se estiver liberado."""
    momento = agora()
    janela = momento - dt.timedelta(minutes=settings.login_janela_min)

    por_email = _falhas_desde(db, janela, email=email) if email else 0
    por_ip = _falhas_desde(db, janela, ip=ip) if ip else 0

    estourou = (
        por_email >= settings.login_max_tentativas
        or por_ip >= settings.login_max_tentativas * FATOR_IP
    )
    if not estourou:
        return 0

    # Conta a partir da ultima falha: cada nova tentativa durante o bloqueio
    # empurra a liberacao para frente.
    ultima = db.execute(
        select(func.max(TentativaLogin.criada_em)).where(
            TentativaLogin.sucesso.is_(False),
            TentativaLogin.criada_em >= janela,
            (TentativaLogin.email == email.lower()) | (TentativaLogin.ip == ip),
        )
    ).scalar_one_or_none()

    if ultima is None:
        return 0

    libera_em = ultima + dt.timedelta(minutes=settings.login_bloqueio_min)
    restante = (libera_em - momento).total_seconds()
    return max(0, int(restante))


def limpar(db: Session, email: str) -> None:
    """Zera o historico de um e-mail apos autenticacao bem-sucedida."""
    db.execute(delete(TentativaLogin).where(TentativaLogin.email == (email or "").lower()))


def podar(db: Session, dias: int = 30) -> int:
    """Descarta tentativas antigas. Chamado pela rotina de manutencao."""
    corte = agora() - dt.timedelta(days=dias)
    resultado = db.execute(delete(TentativaLogin).where(TentativaLogin.criada_em < corte))
    return resultado.rowcount or 0
