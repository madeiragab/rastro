"""Envio de e-mail.

Dois adaptadores, escolhidos por configuracao:

- **SMTP**, quando `SMTP_HOST` esta definido;
- **log**, quando nao esta -- serve para desenvolvimento e demonstracao, e a
  aplicacao se recusa a subir em producao nesse estado.

Usa `smtplib` da biblioteca padrao. Um cliente de e-mail transacional traria
dependencia, chave de API e um provedor a mais para cair; SMTP funciona com
qualquer provedor, inclusive os gratuitos.

O envio e lento (handshake TLS mais a latencia do provedor), entao roda em
tarefa de fundo -- a rota responde antes. Isso tambem impede que o tempo de
resposta denuncie se a conta existe.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from app.config import settings

log = logging.getLogger("rastro.notificacao")


# ------------------------------------------------------------------ envio
def _enviar_smtp(destino: str, assunto: str, texto: str, html: str) -> None:
    mensagem = EmailMessage()
    mensagem["Subject"] = assunto
    mensagem["From"] = _remetente()
    mensagem["To"] = destino
    # Sinaliza que a caixa nao deve responder nem gerar auto-resposta.
    mensagem["Auto-Submitted"] = "auto-generated"
    mensagem.set_content(texto)
    mensagem.add_alternative(html, subtype="html")

    contexto = ssl.create_default_context()

    if settings.smtp_seguranca == "ssl":
        servidor = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_porta, timeout=settings.smtp_timeout_s,
            context=contexto,
        )
    else:
        servidor = smtplib.SMTP(
            settings.smtp_host, settings.smtp_porta, timeout=settings.smtp_timeout_s
        )

    with servidor:
        if settings.smtp_seguranca == "starttls":
            servidor.starttls(context=contexto)
        if settings.smtp_usuario:
            servidor.login(settings.smtp_usuario, settings.smtp_senha)
        servidor.send_message(mensagem)


def _remetente() -> str:
    nome, endereco = parseaddr(settings.smtp_remetente)
    return formataddr((nome, endereco)) if endereco else settings.smtp_remetente


def enviar(destino: str, assunto: str, texto: str, html: str) -> None:
    """Entrega a mensagem pelo adaptador configurado.

    Nunca levanta: falha de e-mail nao pode derrubar a requisicao que a
    originou, e o chamador ja respondeu ao cliente.
    """
    if not settings.smtp_host:
        log.warning(
            "\n"
            "==========================================================\n"
            " E-MAIL -- entrega simulada (SMTP_HOST nao configurado)\n"
            "----------------------------------------------------------\n"
            " para:    %s\n"
            " assunto: %s\n"
            "\n%s\n"
            "==========================================================",
            destino,
            assunto,
            texto,
        )
        return

    try:
        _enviar_smtp(destino, assunto, texto, html)
        log.info("e-mail enviado para %s: %s", destino, assunto)
    except Exception:  # noqa: BLE001
        # Sem o endereco no log de erro: a trilha costuma sair da maquina.
        log.exception("falha ao enviar e-mail (assunto: %s)", assunto)


# ---------------------------------------------------------------- mensagens
def enviar_link_de_reset(email: str, link: str, validade_min: int) -> None:
    assunto = "Redefinir sua senha do Rastro"

    texto = (
        "Voce pediu para redefinir a senha da sua conta no Rastro.\n\n"
        f"Abra este link para escolher uma senha nova:\n{link}\n\n"
        f"O link vale por {validade_min} minutos e so pode ser usado uma vez.\n\n"
        "Se nao foi voce quem pediu, ignore esta mensagem. Sua senha continua "
        "a mesma, e ninguem consegue troca-la sem este link.\n"
    )

    # HTML simples e sem imagem externa de proposito: cliente de e-mail bloqueia
    # imagem remota por padrao, e o rastreamento de abertura que ela permite nao
    # tem lugar numa mensagem de seguranca.
    html = f"""\
<!doctype html>
<html lang="pt-BR">
  <body style="margin:0;padding:24px;background:#f2f4f5;
               font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
    <div style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:12px;
                padding:28px;border:1px solid #d9e0dc;">
      <div style="font-size:22px;font-weight:700;color:#1f4d3a;margin-bottom:4px;">
        Rastro<span style="color:#2e9e63;">.</span>
      </div>
      <p style="color:#4a5259;font-size:13px;margin:0 0 20px;">
        Rastreamento e geocerca de rebanho
      </p>

      <p style="color:#22282c;font-size:15px;line-height:1.5;">
        Voce pediu para redefinir a senha da sua conta.
      </p>

      <p style="margin:24px 0;">
        <a href="{link}"
           style="display:inline-block;background:#2e9e63;color:#07120c;
                  text-decoration:none;font-weight:700;font-size:15px;
                  padding:13px 22px;border-radius:9px;">
          Escolher senha nova
        </a>
      </p>

      <p style="color:#4a5259;font-size:13px;line-height:1.5;">
        O link vale por {validade_min} minutos e so pode ser usado uma vez.
      </p>

      <p style="color:#4a5259;font-size:13px;line-height:1.5;">
        Se nao foi voce quem pediu, ignore esta mensagem. Sua senha continua a
        mesma, e ninguem consegue troca-la sem este link.
      </p>

      <p style="color:#7b8794;font-size:11px;line-height:1.5;
                border-top:1px solid #e5eae7;padding-top:14px;margin-top:22px;
                word-break:break-all;">
        Se o botao nao funcionar, copie este endereco:<br>{link}
      </p>
    </div>
  </body>
</html>
"""

    enviar(email, assunto, texto, html)
