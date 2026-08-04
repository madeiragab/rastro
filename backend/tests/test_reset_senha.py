"""Redefinição de senha esquecida.

O endpoint `/esqueci` não exige autenticação — por definição, quem esqueceu a
senha não consegue se autenticar. Isso o torna a superfície mais exposta da
aplicação depois do login, e a maior parte destes testes existe para garantir
que ele não vire um verificador de cadastro nem um gerador de spam.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import SessaoRefresh, TokenResetSenha, agora
from app.services import notificacao
from tests.conftest import SENHA_TESTE, auth, entrar

NOVA = "corrego-fundo-da-serra-77"


@pytest.fixture()
def links(monkeypatch) -> list[str]:
    """Captura os links em vez de deixá-los ir para o log."""
    capturados: list[str] = []

    def falso(email: str, link: str, validade_min: int) -> None:
        capturados.append(link)

    monkeypatch.setattr(notificacao, "enviar_link_de_reset", falso)
    # A rota importa o módulo, então basta trocar o atributo nele.
    return capturados


def token_do_link(link: str) -> str:
    return link.split("token=", 1)[1]


class TestSolicitacao:
    def test_resposta_identica_para_conta_inexistente(self, cliente, dono, links):
        existente = cliente.post("/api/auth/esqueci", json={"email": dono.email})
        inexistente = cliente.post(
            "/api/auth/esqueci", json={"email": "ninguem@teste.com.br"}
        )

        assert existente.status_code == inexistente.status_code == 202
        assert existente.json() == inexistente.json()

        # E só uma conta real gera link.
        assert len(links) == 1

    def test_conta_desativada_nao_gera_link(self, cliente, db, dono, links):
        dono.ativo = False
        db.commit()

        resposta = cliente.post("/api/auth/esqueci", json={"email": dono.email})

        assert resposta.status_code == 202
        assert links == []

    def test_limite_por_hora(self, cliente, dono, links):
        for _ in range(settings.reset_max_por_hora + 3):
            cliente.post("/api/auth/esqueci", json={"email": dono.email})

        # Sem o limite, o endpoint viraria gerador de spam apontado para a
        # caixa de entrada de outra pessoa.
        assert len(links) == settings.reset_max_por_hora

    def test_token_e_guardado_como_hash(self, cliente, db, dono, links):
        cliente.post("/api/auth/esqueci", json={"email": dono.email})

        claro = token_do_link(links[0])
        registro = db.execute(select(TokenResetSenha)).scalar_one()

        assert registro.token_hash != claro
        assert len(registro.token_hash) == 64  # SHA-256 em hexadecimal


class TestRedefinicao:
    def _pedir(self, cliente, dono, links) -> str:
        cliente.post("/api/auth/esqueci", json={"email": dono.email})
        return token_do_link(links[-1])

    def test_fluxo_completo(self, cliente, dono, links):
        token = self._pedir(cliente, dono, links)

        resposta = cliente.post(
            "/api/auth/redefinir", json={"token": token, "senha_nova": NOVA}
        )
        assert resposta.status_code == 204

        assert (
            cliente.post(
                "/api/auth/login", json={"email": dono.email, "senha": NOVA}
            ).status_code
            == 200
        )
        # A senha antiga morre.
        assert (
            cliente.post(
                "/api/auth/login", json={"email": dono.email, "senha": SENHA_TESTE}
            ).status_code
            == 401
        )

    def test_token_invalido(self, cliente, dono):
        resposta = cliente.post(
            "/api/auth/redefinir",
            json={"token": "token-que-nunca-existiu", "senha_nova": NOVA},
        )
        assert resposta.status_code == 400

    def test_uso_unico(self, cliente, dono, links):
        token = self._pedir(cliente, dono, links)
        cliente.post("/api/auth/redefinir", json={"token": token, "senha_nova": NOVA})

        segunda = cliente.post(
            "/api/auth/redefinir",
            json={"token": token, "senha_nova": "outra-senha-bem-longa-88"},
        )
        assert segunda.status_code == 400

    def test_token_expirado(self, cliente, db, dono, links):
        token = self._pedir(cliente, dono, links)
        registro = db.execute(select(TokenResetSenha)).scalar_one()
        registro.expira_em = agora() - dt.timedelta(minutes=1)
        db.commit()

        resposta = cliente.post(
            "/api/auth/redefinir", json={"token": token, "senha_nova": NOVA}
        )
        assert resposta.status_code == 400

    def test_senha_fraca(self, cliente, dono, links):
        token = self._pedir(cliente, dono, links)
        resposta = cliente.post(
            "/api/auth/redefinir", json={"token": token, "senha_nova": "123"}
        )
        assert resposta.status_code == 422

    def test_derruba_sessoes_e_tokens_antigos(self, cliente, db, dono, links):
        acesso = entrar(cliente, dono.email)
        token = self._pedir(cliente, dono, links)

        cliente.post("/api/auth/redefinir", json={"token": token, "senha_nova": NOVA})

        # Quem redefine a senha normalmente perdeu o controle da conta; as
        # sessões abertas podem ser de quem tomou.
        abertas = (
            db.execute(select(SessaoRefresh).where(SessaoRefresh.revogada_em.is_(None)))
            .scalars()
            .all()
        )
        assert abertas == []
        assert cliente.get("/api/animais", headers=auth(acesso)).status_code == 401

    def test_invalida_os_demais_links_pendentes(self, cliente, dono, links):
        primeiro = self._pedir(cliente, dono, links)
        segundo = self._pedir(cliente, dono, links)
        assert primeiro != segundo

        cliente.post("/api/auth/redefinir", json={"token": segundo, "senha_nova": NOVA})

        # O link antigo, que pode estar numa caixa de entrada comprometida,
        # para de valer junto.
        resposta = cliente.post(
            "/api/auth/redefinir",
            json={"token": primeiro, "senha_nova": "mais-uma-senha-longa-99"},
        )
        assert resposta.status_code == 400
