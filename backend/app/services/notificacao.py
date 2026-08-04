"""Envio de mensagem ao usuario.

**Nao ha SMTP configurado.** O adaptador padrao escreve no log da aplicacao, o
que serve para desenvolvimento e para demonstracao, e nao serve para producao.

A abstracao existe agora, em vez de espalhar chamadas de e-mail pelas rotas,
para que trocar por um provedor real seja substituir uma funcao -- e nao caçar
formatacao de mensagem em cinco arquivos.
"""

from __future__ import annotations

import logging

log = logging.getLogger("rastro.notificacao")


def enviar_link_de_reset(email: str, link: str, validade_min: int) -> None:
    """Entrega o link de redefinicao de senha.

    Em producao isto vira um envio real. Enquanto nao vira, o link aparece no
    log da API -- e isso esta documentado como lacuna, nao como recurso.
    """
    log.warning(
        "\n"
        "==========================================================\n"
        " REDEFINICAO DE SENHA -- entrega simulada (sem SMTP)\n"
        "----------------------------------------------------------\n"
        " para:    %s\n"
        " link:    %s\n"
        " validade: %s minutos, uso unico\n"
        "==========================================================",
        email,
        link,
        validade_min,
    )
