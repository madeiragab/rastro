"""Notificação push.

O envio em si é substituído por um dublê: exercitar a criptografia do Web Push
contra um serviço real de terceiro não é teste, é dependência de rede. O que se
testa aqui é o que é nosso — chaves, inscrição, escopo por fazenda e a marcação
que impede aviso repetido.
"""

from __future__ import annotations

import base64

import pytest
from sqlalchemy import select

from app.models import Alerta, ConfiguracaoPush, InscricaoPush, agora
from app.services import push
from tests.conftest import auth, criar_usuario, entrar

INSCRICAO = {
    "endpoint": "https://fcm.googleapis.com/fcm/send/exemplo-de-teste",
    "chave_p256dh": "BFakeP256dhKeyParaTesteApenas0000000000000000",
    "chave_auth": "FakeAuthKey0",
}


@pytest.fixture()
def enviados(monkeypatch) -> list[tuple[str, dict]]:
    """Substitui o envio real; guarda para quem foi e o quê."""
    registro: list[tuple[str, dict]] = []

    def falso(config, inscricao, carga):
        registro.append((inscricao.endpoint, carga))
        return True

    monkeypatch.setattr(push, "_enviar", falso)
    return registro


class TestChaves:
    def test_gera_uma_vez_e_reaproveita(self, db):
        primeira = push.obter_chaves(db)
        segunda = push.obter_chaves(db)

        assert primeira.id == segunda.id
        assert db.execute(select(ConfiguracaoPush)).scalars().all().__len__() == 1

    def test_formato_da_chave_publica(self, db):
        chave = push.obter_chaves(db).chave_publica_app
        bruta = base64.urlsafe_b64decode(chave + "=" * ((4 - len(chave) % 4) % 4))

        # Ponto não comprimido de curva P-256: 1 byte de prefixo + 32 + 32.
        assert len(bruta) == 65
        assert bruta[0] == 4

    def test_exige_autenticacao(self, cliente):
        assert cliente.get("/api/push/chave-publica").status_code == 401


class TestInscricao:
    def test_cria(self, cliente, db, dono):
        token = entrar(cliente, dono.email)
        resposta = cliente.post("/api/push/inscricoes", headers=auth(token), json=INSCRICAO)

        assert resposta.status_code == 201
        assert db.execute(select(InscricaoPush)).scalars().all().__len__() == 1

    def test_mesmo_endpoint_nao_duplica(self, cliente, db, dono):
        token = entrar(cliente, dono.email)
        cliente.post("/api/push/inscricoes", headers=auth(token), json=INSCRICAO)
        cliente.post("/api/push/inscricoes", headers=auth(token), json=INSCRICAO)

        # Um aparelho, uma inscrição. Duplicar mandaria o mesmo aviso duas vezes.
        assert db.execute(select(InscricaoPush)).scalars().all().__len__() == 1

    def test_endpoint_muda_de_dono(self, cliente, db, fazenda, dono):
        """Mesmo aparelho, outra conta: a inscrição passa para quem entrou."""
        token = entrar(cliente, dono.email)
        cliente.post("/api/push/inscricoes", headers=auth(token), json=INSCRICAO)

        outro = criar_usuario(db, fazenda, email="outro@teste.com.br")
        token_outro = entrar(cliente, outro.email)
        cliente.post("/api/push/inscricoes", headers=auth(token_outro), json=INSCRICAO)

        inscricoes = db.execute(select(InscricaoPush)).scalars().all()
        assert len(inscricoes) == 1
        assert inscricoes[0].usuario_id == outro.id

    def test_cancelar(self, cliente, db, dono):
        token = entrar(cliente, dono.email)
        cliente.post("/api/push/inscricoes", headers=auth(token), json=INSCRICAO)

        resposta = cliente.request(
            "DELETE", "/api/push/inscricoes", headers=auth(token), json=INSCRICAO
        )

        assert resposta.status_code == 204
        assert db.execute(select(InscricaoPush)).scalars().all() == []


class TestDespacho:
    def _alerta(self, db, animal) -> Alerta:
        alerta = Alerta(
            animal_id=animal.id,
            tipo="fora_da_area",
            severidade="alta",
            mensagem="Mimosa saiu de Pasto de Teste (90 m além da divisa).",
        )
        db.add(alerta)
        db.commit()
        return alerta

    def test_envia_e_marca(self, cliente, db, dono, animal, enviados):
        token = entrar(cliente, dono.email)
        cliente.post("/api/push/inscricoes", headers=auth(token), json=INSCRICAO)
        alerta = self._alerta(db, animal)

        push.despachar_pendentes(db)

        assert len(enviados) == 1
        assert "além da divisa" in enviados[0][1]["mensagem"]
        assert enviados[0][1]["titulo"] == "Animal fora da area"

        db.refresh(alerta)
        assert alerta.notificado_em is not None

    def test_nao_repete(self, cliente, db, dono, animal, enviados):
        token = entrar(cliente, dono.email)
        cliente.post("/api/push/inscricoes", headers=auth(token), json=INSCRICAO)
        self._alerta(db, animal)

        push.despachar_pendentes(db)
        push.despachar_pendentes(db)

        # Um alerta, um aviso. Sem a marcação, o laço reenviaria a cada ciclo.
        assert len(enviados) == 1

    def test_sem_inscricao_marca_assim_mesmo(self, db, animal, enviados):
        alerta = self._alerta(db, animal)

        push.despachar_pendentes(db)

        # Senão os alertas ficariam represados e cairiam todos de uma vez na
        # primeira pessoa que ativasse as notificações.
        db.refresh(alerta)
        assert alerta.notificado_em is not None
        assert enviados == []

    def test_nao_vaza_para_outra_fazenda(self, cliente, db, fazenda, dono, animal, enviados):
        from app.models import Fazenda

        outra = Fazenda(nome="Outra", proprietario="Maria", municipio="Araxá", uf="MG")
        db.add(outra)
        db.flush()
        alheio = criar_usuario(db, outra, email="alheio@teste.com.br")

        token = entrar(cliente, alheio.email)
        cliente.post("/api/push/inscricoes", headers=auth(token), json=INSCRICAO)

        self._alerta(db, animal)
        push.despachar_pendentes(db)

        # O animal é da fazenda do `dono`; quem é de outra propriedade não pode
        # receber aviso sobre ele.
        assert enviados == []

    def test_alerta_resolvido_nao_notifica(self, cliente, db, dono, animal, enviados):
        token = entrar(cliente, dono.email)
        cliente.post("/api/push/inscricoes", headers=auth(token), json=INSCRICAO)

        alerta = self._alerta(db, animal)
        alerta.resolvido_em = agora()
        db.commit()

        push.despachar_pendentes(db)
        assert enviados == []

    def test_inscricao_morta_e_descartada(self, cliente, db, dono, animal, monkeypatch):
        token = entrar(cliente, dono.email)
        cliente.post("/api/push/inscricoes", headers=auth(token), json=INSCRICAO)

        monkeypatch.setattr(push, "_enviar", lambda *a, **k: False)

        for _ in range(push.MAX_FALHAS):
            self._alerta(db, animal)
            push.despachar_pendentes(db)

        # Endpoint expira quando a pessoa desinstala o app; insistir para sempre
        # só gera tráfego e ruído.
        assert db.execute(select(InscricaoPush)).scalars().all() == []
