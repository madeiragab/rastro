"""Gestão de equipe.

Sem estas rotas os papéis existiam e não podiam ser atribuídos. Os testes que
mais importam aqui são os dois que impedem o dono de se trancar para fora.
"""

from __future__ import annotations

from app.models import PAPEL_LEITURA, PAPEL_OPERADOR
from tests.conftest import auth, criar_usuario, entrar

NOVO = {"email": "vaqueiro@teste.com.br", "nome": "Marcos", "papel": "operador"}


class TestCriacao:
    def test_dono_cria_e_recebe_a_senha_uma_vez(self, cliente, dono):
        token = entrar(cliente, dono.email)
        resposta = cliente.post("/api/usuarios", headers=auth(token), json=NOVO)
        corpo = resposta.json()

        assert resposta.status_code == 201
        assert corpo["papel"] == "operador"
        assert corpo["ativo"] is True
        assert len(corpo["senha_inicial"]) >= 12

        # A listagem nunca devolve a senha.
        listados = cliente.get("/api/usuarios", headers=auth(token)).json()
        assert all("senha_inicial" not in u for u in listados)
        assert all("senha_hash" not in u for u in listados)

    def test_a_pessoa_criada_consegue_entrar(self, cliente, dono):
        token = entrar(cliente, dono.email)
        senha = cliente.post("/api/usuarios", headers=auth(token), json=NOVO).json()[
            "senha_inicial"
        ]

        resposta = cliente.post(
            "/api/auth/login", json={"email": NOVO["email"], "senha": senha}
        )
        assert resposta.status_code == 200
        assert resposta.json()["usuario"]["papel"] == "operador"

    def test_email_duplicado(self, cliente, dono):
        token = entrar(cliente, dono.email)
        cliente.post("/api/usuarios", headers=auth(token), json=NOVO)

        segunda = cliente.post("/api/usuarios", headers=auth(token), json=NOVO)
        assert segunda.status_code == 409

    def test_papel_invalido(self, cliente, dono):
        token = entrar(cliente, dono.email)
        resposta = cliente.post(
            "/api/usuarios", headers=auth(token), json={**NOVO, "papel": "presidente"}
        )
        assert resposta.status_code == 422

    def test_senha_inicial_e_diferente_a_cada_criacao(self, cliente, dono):
        token = entrar(cliente, dono.email)
        a = cliente.post("/api/usuarios", headers=auth(token), json=NOVO).json()["senha_inicial"]
        b = cliente.post(
            "/api/usuarios",
            headers=auth(token),
            json={**NOVO, "email": "outro@teste.com.br"},
        ).json()["senha_inicial"]

        assert a != b


class TestPermissao:
    def test_operador_nao_gerencia_equipe(self, cliente, db, fazenda):
        criar_usuario(db, fazenda, email="op@teste.com.br", papel=PAPEL_OPERADOR)
        token = entrar(cliente, "op@teste.com.br")

        assert cliente.get("/api/usuarios", headers=auth(token)).status_code == 403
        assert cliente.post("/api/usuarios", headers=auth(token), json=NOVO).status_code == 403

    def test_leitura_nao_gerencia_equipe(self, cliente, db, fazenda):
        criar_usuario(db, fazenda, email="leitor@teste.com.br", papel=PAPEL_LEITURA)
        token = entrar(cliente, "leitor@teste.com.br")

        assert cliente.get("/api/usuarios", headers=auth(token)).status_code == 403


class TestTravasContraAutoBloqueio:
    """O modo mais comum de perder o acesso a um sistema com controle de acesso
    é o próprio administrador se rebaixar ou se desativar."""

    def test_dono_nao_muda_o_proprio_papel(self, cliente, dono):
        token = entrar(cliente, dono.email)
        resposta = cliente.patch(
            f"/api/usuarios/{dono.id}", headers=auth(token), json={"papel": "leitura"}
        )
        assert resposta.status_code == 400

    def test_dono_nao_se_desativa(self, cliente, dono):
        token = entrar(cliente, dono.email)
        resposta = cliente.patch(
            f"/api/usuarios/{dono.id}", headers=auth(token), json={"ativo": False}
        )
        assert resposta.status_code == 400


class TestAlteracao:
    def _criar_operador(self, cliente, token) -> tuple[int, str]:
        corpo = cliente.post("/api/usuarios", headers=auth(token), json=NOVO).json()
        outro = entrar(cliente, NOVO["email"], corpo["senha_inicial"])
        return corpo["id"], outro

    def test_desativar_mata_o_token_na_hora(self, cliente, dono):
        token = entrar(cliente, dono.email)
        alvo_id, token_alvo = self._criar_operador(cliente, token)

        assert cliente.get("/api/animais", headers=auth(token_alvo)).status_code == 200

        cliente.patch(f"/api/usuarios/{alvo_id}", headers=auth(token), json={"ativo": False})

        # Sem invalidar a versão do token, o desligado continuaria dentro até o
        # access token expirar.
        assert cliente.get("/api/animais", headers=auth(token_alvo)).status_code == 401

    def test_rebaixar_papel_invalida_o_token(self, cliente, dono):
        token = entrar(cliente, dono.email)
        alvo_id, token_alvo = self._criar_operador(cliente, token)

        cliente.patch(f"/api/usuarios/{alvo_id}", headers=auth(token), json={"papel": "leitura"})

        # O papel viaja dentro do token: sem invalidar, o rebaixado continuaria
        # com permissão de operador até o token expirar.
        assert cliente.get("/api/animais", headers=auth(token_alvo)).status_code == 401

    def test_reativar(self, cliente, dono):
        token = entrar(cliente, dono.email)
        alvo_id, _ = self._criar_operador(cliente, token)

        cliente.patch(f"/api/usuarios/{alvo_id}", headers=auth(token), json={"ativo": False})
        cliente.patch(f"/api/usuarios/{alvo_id}", headers=auth(token), json={"ativo": True})

        listados = cliente.get("/api/usuarios", headers=auth(token)).json()
        alvo = next(u for u in listados if u["id"] == alvo_id)
        assert alvo["ativo"] is True

    def test_usuario_de_outra_fazenda(self, cliente, db, dono):
        from app.models import Fazenda

        outra = Fazenda(nome="Outra", proprietario="Maria", municipio="Araxá", uf="MG")
        db.add(outra)
        db.flush()
        alheio = criar_usuario(db, outra, email="alheio@teste.com.br")

        token = entrar(cliente, dono.email)
        resposta = cliente.patch(
            f"/api/usuarios/{alheio.id}", headers=auth(token), json={"ativo": False}
        )
        assert resposta.status_code == 404
