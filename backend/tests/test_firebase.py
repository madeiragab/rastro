"""Login pelo Firebase (AUTH_MODO=firebase) e push nativo por FCM.

O Firebase em si e substituido por dubles: validar assinatura de token do
Google contra a rede nao e teste nosso. O que se testa e a regra do Rastro --
quem o token do Firebase pode virar aqui dentro, e para quem o alerta sai.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import settings
from app.models import Alerta, TokenFcm, agora
from app.security import firebase
from app.services import push
from tests.conftest import EMAIL_DONO, auth, criar_usuario

TOKEN_FCM = "fcm-token-de-teste-" + "x" * 40


@pytest.fixture()
def modo_firebase(monkeypatch):
    """Liga o modo firebase e troca a validacao do token por um dicionario."""
    monkeypatch.setattr(settings, "auth_modo", "firebase")
    monkeypatch.setattr(settings, "firebase_projeto_id", "rastro-teste")

    tokens: dict[str, dict] = {}

    def verificar(token: str) -> dict:
        if token not in tokens:
            raise firebase.TokenFirebaseInvalido("desconhecido")
        return tokens[token]

    monkeypatch.setattr(firebase, "verificar_id_token", verificar)
    return tokens


class TestLoginFirebase:
    def test_token_invalido_e_401(self, cliente, dono, modo_firebase):
        assert cliente.get("/api/auth/eu", headers=auth("lixo")).status_code == 401

    def test_vincula_pelo_email_verificado(self, cliente, db, dono, modo_firebase):
        modo_firebase["t1"] = {"uid": "uid-1", "email": EMAIL_DONO, "email_verified": True}

        resposta = cliente.get("/api/auth/eu", headers=auth("t1"))
        assert resposta.status_code == 200
        db.refresh(dono)
        assert dono.firebase_uid == "uid-1"

    def test_email_nao_verificado_nao_herda_a_conta(self, cliente, db, dono, modo_firebase):
        # Qualquer um cria conta no Firebase com o e-mail do dono. Sem a
        # verificacao, herdaria a fazenda.
        modo_firebase["t1"] = {"uid": "intruso", "email": EMAIL_DONO, "email_verified": False}

        assert cliente.get("/api/auth/eu", headers=auth("t1")).status_code == 401
        db.refresh(dono)
        assert dono.firebase_uid is None

    def test_conta_sem_cadastro_no_rastro_e_401(self, cliente, dono, modo_firebase):
        modo_firebase["t1"] = {"uid": "x", "email": "outro@teste.com.br", "email_verified": True}
        assert cliente.get("/api/auth/eu", headers=auth("t1")).status_code == 401

    def test_uid_ja_vinculado_nao_e_sequestrado_por_email(self, cliente, db, dono, modo_firebase):
        dono.firebase_uid = "uid-legitimo"
        db.commit()
        modo_firebase["t1"] = {"uid": "uid-novo", "email": EMAIL_DONO, "email_verified": True}

        assert cliente.get("/api/auth/eu", headers=auth("t1")).status_code == 401

    def test_desativado_e_401(self, cliente, db, dono, modo_firebase):
        dono.firebase_uid = "uid-1"
        dono.ativo = False
        db.commit()
        modo_firebase["t1"] = {"uid": "uid-1"}

        assert cliente.get("/api/auth/eu", headers=auth("t1")).status_code == 401

    def test_rotas_de_senha_local_somem(self, cliente, dono, modo_firebase):
        for rota in ("/api/auth/login", "/api/auth/refresh", "/api/auth/esqueci"):
            assert cliente.post(rota, json={}).status_code == 404, rota

    def test_modo_e_publico(self, cliente, modo_firebase):
        assert cliente.get("/api/auth/modo").json() == {"modo": "firebase"}

    def test_cadastro_de_equipe_cria_conta_no_firebase(
        self, cliente, db, dono, modo_firebase, monkeypatch
    ):
        dono.firebase_uid = "uid-dono"
        db.commit()
        modo_firebase["t1"] = {"uid": "uid-dono"}
        criadas = []
        monkeypatch.setattr(
            firebase, "garantir_conta", lambda e, s, n: criadas.append(e) or "uid-peao"
        )

        resposta = cliente.post(
            "/api/usuarios",
            json={"email": "peao@teste.com.br", "nome": "Peao", "papel": "leitura"},
            headers=auth("t1"),
        )
        assert resposta.status_code == 201, resposta.text
        assert criadas == ["peao@teste.com.br"]


class TestFcm:
    def test_registrar_e_reaproveitar_token(self, cliente, db, fazenda, modo_firebase):
        a = criar_usuario(db, fazenda, email="a@teste.com.br")
        b = criar_usuario(db, fazenda, email="b@teste.com.br")
        a.firebase_uid, b.firebase_uid = "ua", "ub"
        db.commit()
        modo_firebase.update({"ta": {"uid": "ua"}, "tb": {"uid": "ub"}})

        corpo = {"token": TOKEN_FCM}
        assert cliente.post("/api/push/fcm", json=corpo, headers=auth("ta")).status_code == 204
        assert cliente.post("/api/push/fcm", json=corpo, headers=auth("tb")).status_code == 204

        registros = db.execute(select(TokenFcm)).scalars().all()
        assert len(registros) == 1
        assert registros[0].usuario_id == b.id

    def test_alerta_sai_por_fcm_so_para_a_propria_fazenda(
        self, db, fazenda, animal, monkeypatch
    ):
        monkeypatch.setattr(settings, "firebase_projeto_id", "rastro-teste")
        enviados: list[str] = []
        monkeypatch.setattr(
            firebase, "enviar_fcm", lambda token, titulo, msg, dados: enviados.append(token)
        )

        from app.models import Fazenda

        outra = Fazenda(nome="Outra", proprietario="X", municipio="Y", uf="MG")
        db.add(outra)
        db.flush()
        meu = criar_usuario(db, fazenda, email="meu@teste.com.br")
        alheio = criar_usuario(db, outra, email="alheio@teste.com.br")
        db.add_all([
            TokenFcm(usuario_id=meu.id, token=TOKEN_FCM + "meu"),
            TokenFcm(usuario_id=alheio.id, token=TOKEN_FCM + "alheio"),
        ])
        db.add(Alerta(animal_id=animal.id, tipo="fora_da_area", mensagem="fugiu"))
        db.commit()

        assert push.despachar_pendentes(db) == 1
        assert enviados == [TOKEN_FCM + "meu"]
        assert db.execute(select(Alerta)).scalar_one().notificado_em is not None

    def test_token_morto_e_descartado(self, db, fazenda, animal, monkeypatch):
        monkeypatch.setattr(settings, "firebase_projeto_id", "rastro-teste")

        def morto(*_):
            raise firebase.TokenFcmMorto("unregistered")

        monkeypatch.setattr(firebase, "enviar_fcm", morto)
        u = criar_usuario(db, fazenda)
        db.add(TokenFcm(usuario_id=u.id, token=TOKEN_FCM))
        db.add(Alerta(animal_id=animal.id, tipo="imovel", mensagem="parado", criado_em=agora()))
        db.commit()

        push.despachar_pendentes(db)
        assert db.execute(select(TokenFcm)).scalars().all() == []
