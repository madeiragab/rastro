"""Trilha de auditoria.

Grava quem fez o que, quando e de onde. Append-only por convencao: nenhuma rota
atualiza nem apaga linhas de `eventos_auditoria`.

Regra que nao se quebra: **nada de segredo aqui**. Sem senha, sem token, sem
chave de gateway -- nem em `detalhe`. A trilha e lida por gente e costuma ser
exportada para fora do sistema.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import EventoAuditoria

# Acoes registradas. Constantes em vez de strings soltas para que uma consulta
# por `acao` nao dependa de ninguem lembrar a grafia exata.
LOGIN_OK = "login.sucesso"
LOGIN_FALHA = "login.falha"
LOGIN_BLOQUEADO = "login.bloqueado"
LOGOUT = "logout"
REFRESH_OK = "refresh.rotacionado"
REFRESH_REUSO = "refresh.reuso_detectado"
SENHA_ALTERADA = "senha.alterada"
CHAVE_CRIADA = "gateway.chave_criada"
CHAVE_REVOGADA = "gateway.chave_revogada"
TELEMETRIA_NEGADA = "telemetria.negada"


def registrar(
    db: Session,
    acao: str,
    *,
    usuario_id: int | None = None,
    detalhe: str = "",
    ip: str = "",
) -> None:
    db.add(EventoAuditoria(usuario_id=usuario_id, acao=acao, detalhe=detalhe[:2000], ip=ip or ""))
