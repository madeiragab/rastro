"""Superfície de autorização.

O teste mais importante do arquivo é `test_toda_rota_exige_credencial`: ele
varre a OpenAPI e falha se alguém adicionar uma rota sem proteção. É a rede que
sustenta a decisão de declarar autorização no roteador (ADR-007).
"""

from __future__ import annotations

import pytest

from app.main import app
from app.models import PAPEL_LEITURA, PAPEL_OPERADOR
from tests.conftest import auth, criar_usuario, entrar

EMAIL_LEITOR = "leitor@teste.com.br"
EMAIL_OPERADOR = "operador@teste.com.br"

# Únicas rotas que podem responder sem credencial. Cada entrada aqui é uma
# decisão que precisa ser defendida na revisão — é de propósito que a lista
# fique num único lugar visível.
PUBLICAS = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/refresh"),
    ("POST", "/api/auth/logout"),
    # Recuperação de senha: quem esqueceu a senha, por definição, não consegue
    # se autenticar para pedir a redefinição.
    ("POST", "/api/auth/esqueci"),
    ("POST", "/api/auth/redefinir"),
    ("GET", "/health"),
}


def rotas_da_api() -> list[tuple[str, str]]:
    spec = app.openapi()
    return [
        (metodo.upper(), caminho)
        for caminho, operacoes in spec["paths"].items()
        for metodo in operacoes
    ]


class TestSuperficie:
    @pytest.mark.parametrize("metodo,caminho", rotas_da_api())
    def test_toda_rota_exige_credencial(self, cliente, metodo, caminho):
        if (metodo, caminho) in PUBLICAS:
            pytest.skip("rota pública por decisão explícita")

        # Parâmetros de caminho viram um valor qualquer: o que importa é que a
        # recusa aconteça ANTES de chegar na lógica.
        url = caminho
        for marcador in ("{animal_id}", "{alerta_id}", "{pasto_id}", "{chave_id}", "{id}"):
            url = url.replace(marcador, "1")

        resposta = cliente.request(metodo, url, json={})

        assert resposta.status_code in (401, 403), (
            f"{metodo} {caminho} respondeu {resposta.status_code} sem credencial"
        )

    def test_health_e_publico(self, cliente):
        assert cliente.get("/health").status_code == 200

    def test_token_invalido(self, cliente):
        assert cliente.get("/api/animais", headers=auth("nao-e-um-token")).status_code == 401

    def test_esquema_errado(self, cliente, dono):
        token = entrar(cliente, dono.email)
        resposta = cliente.get("/api/animais", headers={"Authorization": f"Basic {token}"})
        assert resposta.status_code == 401


class TestPapeis:
    def test_leitura_nao_cria_pasto(self, cliente, db, fazenda):
        criar_usuario(db, fazenda, email=EMAIL_LEITOR, papel=PAPEL_LEITURA)
        token = entrar(cliente, EMAIL_LEITOR)

        resposta = cliente.post(
            "/api/pastos",
            headers=auth(token),
            json={
                "nome": "Novo",
                "cor": "#2E7D53",
                "buffer_m": 25,
                "pontos": [[-19.75, -47.93], [-19.75, -47.92], [-19.74, -47.92]],
            },
        )
        assert resposta.status_code == 403

    def test_leitura_ve_animais(self, cliente, db, fazenda, animal):
        criar_usuario(db, fazenda, email=EMAIL_LEITOR, papel=PAPEL_LEITURA)
        token = entrar(cliente, EMAIL_LEITOR)

        assert cliente.get("/api/animais", headers=auth(token)).status_code == 200

    def test_operador_nao_gerencia_chaves(self, cliente, db, fazenda):
        criar_usuario(db, fazenda, email=EMAIL_OPERADOR, papel=PAPEL_OPERADOR)
        token = entrar(cliente, EMAIL_OPERADOR)

        assert cliente.get("/api/gateways", headers=auth(token)).status_code == 403

    def test_operador_cria_pasto(self, cliente, db, fazenda):
        criar_usuario(db, fazenda, email=EMAIL_OPERADOR, papel=PAPEL_OPERADOR)
        token = entrar(cliente, EMAIL_OPERADOR)

        resposta = cliente.post(
            "/api/pastos",
            headers=auth(token),
            json={
                "nome": "Novo",
                "cor": "#2E7D53",
                "buffer_m": 25,
                "pontos": [[-19.752, -47.935], [-19.752, -47.930], [-19.747, -47.930]],
            },
        )
        assert resposta.status_code == 201

    def test_dono_gerencia_chaves(self, cliente, dono):
        token = entrar(cliente, dono.email)

        criada = cliente.post("/api/gateways", headers=auth(token), json={"nome": "Sede"})
        assert criada.status_code == 201
        # A chave completa aparece uma única vez, aqui.
        assert criada.json()["chave"].startswith("rastro_gw_")

        listadas = cliente.get("/api/gateways", headers=auth(token)).json()
        assert len(listadas) == 1
        assert "chave" not in listadas[0], "a listagem nunca devolve o segredo"


class TestCabecalhosDeSeguranca:
    def test_presentes(self, cliente):
        cabecalhos = cliente.get("/health").headers

        assert cabecalhos["X-Content-Type-Options"] == "nosniff"
        assert cabecalhos["X-Frame-Options"] == "DENY"
        assert cabecalhos["Referrer-Policy"] == "no-referrer"
        assert "default-src 'none'" in cabecalhos["Content-Security-Policy"]

    def test_rota_autenticada_nao_entra_em_cache(self, cliente, dono):
        token = entrar(cliente, dono.email)
        resposta = cliente.get("/api/animais", headers=auth(token))
        assert resposta.headers["Cache-Control"] == "no-store"
