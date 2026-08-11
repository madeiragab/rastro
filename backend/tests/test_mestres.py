"""Topologia de mestre: arbitragem, telemetria em lote e silêncio coletivo.

O teste mais importante deste arquivo é `test_nao_assume_com_mestre_vivo`. Ele
cobre o cenário que quebraria o sistema em campo: o mestre está vivo, o reserva
não o ouve por causa do relevo, e decide assumir. Sem árbitro, passariam a
existir dois mestres que nunca se acertam.

O segundo é `test_lote_mudo_gera_um_alerta_so` — sem ele, uma queda de mestre
vira vinte notificações de madrugada dizendo que cada boi foi roubado.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.models import (
    ALERTA_LOTE_MUDO,
    ALERTA_MESTRE_TROCADO,
    ALERTA_SEM_SINAL,
    Alerta,
    Animal,
    ChaveGateway,
    Mestre,
    Pasto,
    agora,
)
from app.services import alertas as servico_alertas
from app.services import geofence, mestres, telemetria
from tests.conftest import CENTRO, PASTO_TESTE, auth, criar_chave, entrar

# Fora do polígono e além da tolerância.
FORA = (-19.7580, -47.9330)


def chave_header(chave: str) -> dict[str, str]:
    return {"X-API-Key": chave}


@pytest.fixture()
def mestre_ativo(db, fazenda, pasto, animal) -> tuple[Mestre, str]:
    """Um mestre em serviço, com a chave em claro para autenticar."""
    chave = criar_chave(db, fazenda, nome="Mestre A")
    registro = db.execute(select(ChaveGateway).order_by(ChaveGateway.id.desc())).scalars().first()

    m = Mestre(
        fazenda_id=fazenda.id,
        pasto_id=pasto.id,
        chave_gateway_id=registro.id,
        animal_id=animal.id,
        ativo=True,
        bateria_pct=90,
        ultimo_heartbeat=agora(),
        assumiu_em=agora(),
    )
    db.add(m)
    db.commit()
    return m, chave


@pytest.fixture()
def reserva(db, fazenda, pasto) -> tuple[Mestre, str]:
    chave = criar_chave(db, fazenda, nome="Reserva B")
    registro = db.execute(select(ChaveGateway).order_by(ChaveGateway.id.desc())).scalars().first()

    m = Mestre(
        fazenda_id=fazenda.id,
        pasto_id=pasto.id,
        chave_gateway_id=registro.id,
        ativo=False,
        bateria_pct=80,
        ultimo_heartbeat=agora(),
    )
    db.add(m)
    db.commit()
    return m, chave


class TestArbitragem:
    def test_nao_assume_com_mestre_vivo(self, cliente, db, mestre_ativo, reserva):
        """O caso que quebraria tudo: mestre vivo, reserva que não o ouve."""
        _, chave = reserva

        resposta = cliente.post("/api/dispositivos/assumir", headers=chave_header(chave))
        corpo = resposta.json()

        assert resposta.status_code == 200
        assert corpo["assumiu"] is False
        assert "vivo" in corpo["motivo"]
        # Diz quanto esperar, para o reserva não ficar perguntando de segundo em
        # segundo e gastando bateria à toa.
        assert corpo["tente_de_novo_em_s"] > 0

        # E o mestre em serviço continua sendo o mesmo.
        ativos = db.execute(select(Mestre).where(Mestre.ativo.is_(True))).scalars().all()
        assert len(ativos) == 1
        assert ativos[0].id == mestre_ativo[0].id

    def test_assume_com_mestre_calado(self, cliente, db, mestre_ativo, reserva):
        atual, _ = mestre_ativo
        atual.ultimo_heartbeat = agora() - mestres.limite_silencio() - dt.timedelta(seconds=10)
        db.commit()

        _, chave = reserva
        resposta = cliente.post("/api/dispositivos/assumir", headers=chave_header(chave))

        assert resposta.status_code == 200
        assert resposta.json()["assumiu"] is True

        ativos = db.execute(select(Mestre).where(Mestre.ativo.is_(True))).scalars().all()
        assert len(ativos) == 1, "nunca pode haver dois mestres no mesmo lote"
        assert ativos[0].id == reserva[0].id

    def test_troca_gera_alerta_de_lote(self, cliente, db, mestre_ativo, reserva):
        atual, _ = mestre_ativo
        atual.ultimo_heartbeat = agora() - mestres.limite_silencio() - dt.timedelta(seconds=10)
        db.commit()

        cliente.post("/api/dispositivos/assumir", headers=chave_header(reserva[1]))

        alerta = db.execute(
            select(Alerta).where(Alerta.tipo == ALERTA_MESTRE_TROCADO)
        ).scalar_one()
        # Alerta de lote não pertence a nenhum animal.
        assert alerta.animal_id is None
        assert alerta.pasto_id is not None

    def test_desempate_por_bateria(self, cliente, db, fazenda, pasto, mestre_ativo, reserva):
        """Entre dois reservas, assume quem aguenta mais — senão o mais fraco
        assumiria e morreria em seguida."""
        atual, _ = mestre_ativo
        atual.ultimo_heartbeat = agora() - mestres.limite_silencio() - dt.timedelta(seconds=10)

        fraco, chave_fraco = reserva
        fraco.bateria_pct = 20

        chave_forte = criar_chave(db, fazenda, nome="Reserva C")
        registro = db.execute(select(ChaveGateway).order_by(ChaveGateway.id.desc())).scalars().first()
        db.add(
            Mestre(
                fazenda_id=fazenda.id,
                pasto_id=pasto.id,
                chave_gateway_id=registro.id,
                ativo=False,
                bateria_pct=95,
                ultimo_heartbeat=agora(),
            )
        )
        db.commit()

        recusado = cliente.post("/api/dispositivos/assumir", headers=chave_header(chave_fraco))
        assert recusado.json()["assumiu"] is False
        assert "bateria" in recusado.json()["motivo"]

        aceito = cliente.post("/api/dispositivos/assumir", headers=chave_header(chave_forte))
        assert aceito.json()["assumiu"] is True

    def test_heartbeat_informa_se_ainda_manda(self, cliente, db, mestre_ativo, reserva):
        """Mestre que voltou de um apagão descobre aqui que foi substituído."""
        antigo, chave_antigo = mestre_ativo
        antigo.ativo = False
        db.commit()

        resposta = cliente.post(
            "/api/dispositivos/heartbeat",
            headers=chave_header(chave_antigo),
            json={"bateria_pct": 70},
        )

        assert resposta.status_code == 200
        assert resposta.json()["voce_esta_ativo"] is False

    def test_heartbeat_atualiza_bateria(self, cliente, db, mestre_ativo):
        m, chave = mestre_ativo
        cliente.post(
            "/api/dispositivos/heartbeat", headers=chave_header(chave), json={"bateria_pct": 42}
        )
        db.refresh(m)
        assert m.bateria_pct == 42

    def test_chave_sem_mestre_vinculado(self, cliente, db, fazenda):
        avulsa = criar_chave(db, fazenda, nome="Gateway solto")
        resposta = cliente.post("/api/dispositivos/assumir", headers=chave_header(avulsa))
        assert resposta.status_code == 404

    def test_exige_chave(self, cliente):
        assert cliente.post("/api/dispositivos/assumir").status_code == 401
        assert cliente.get("/api/dispositivos/config").status_code == 401


class TestTelemetriaEmLote:
    def test_aceita_varias_leituras(self, cliente, db, fazenda, pasto, animal, mestre_ativo):
        outro = Animal(
            fazenda_id=fazenda.id, pasto_id=pasto.id, brinco="076000000000002", nome="Estrela"
        )
        db.add(outro)
        db.commit()

        _, chave = mestre_ativo
        resposta = cliente.post(
            "/api/dispositivos/telemetria",
            headers=chave_header(chave),
            json={
                "leituras": [
                    {"brinco": animal.brinco, "lat": CENTRO[0], "lon": CENTRO[1], "atividade": 0.6},
                    {"brinco": outro.brinco, "lat": CENTRO[0], "lon": CENTRO[1], "atividade": 0.4},
                ],
                "bateria_mestre_pct": 88,
            },
        )
        corpo = resposta.json()

        assert resposta.status_code == 201
        assert corpo["aceitas"] == 2
        assert corpo["recusadas"] == 0

    def test_brinco_desconhecido_nao_derruba_o_lote(self, cliente, db, animal, mestre_ativo):
        _, chave = mestre_ativo
        corpo = cliente.post(
            "/api/dispositivos/telemetria",
            headers=chave_header(chave),
            json={
                "leituras": [
                    {"brinco": animal.brinco, "lat": CENTRO[0], "lon": CENTRO[1]},
                    {"brinco": "076000000000999", "lat": CENTRO[0], "lon": CENTRO[1]},
                ]
            },
        ).json()

        # A leitura boa entra; a ruim é contada e devolvida para o mestre parar
        # de repassar aquele brinco.
        assert corpo["aceitas"] == 1
        assert corpo["recusadas"] == 1
        assert corpo["desconhecidos"] == ["076000000000999"]

    def test_aproveita_a_viagem_para_o_heartbeat(self, cliente, db, animal, mestre_ativo):
        m, chave = mestre_ativo
        cliente.post(
            "/api/dispositivos/telemetria",
            headers=chave_header(chave),
            json={
                "leituras": [{"brinco": animal.brinco, "lat": CENTRO[0], "lon": CENTRO[1]}],
                "bateria_mestre_pct": 55,
            },
        )
        db.refresh(m)
        assert m.bateria_pct == 55

    def test_evento_do_brinco_dispensa_a_segunda_leitura(self, cliente, db, animal, mestre_ativo):
        """O brinco carrega o polígono e já aplicou a histerese localmente."""
        _, chave = mestre_ativo
        cliente.post(
            "/api/dispositivos/telemetria",
            headers=chave_header(chave),
            json={
                "leituras": [
                    {
                        "brinco": animal.brinco,
                        "lat": FORA[0],
                        "lon": FORA[1],
                        "evento": "saiu_da_area",
                    }
                ]
            },
        )

        abertos = (
            db.execute(
                select(Alerta).where(
                    Alerta.animal_id == animal.id, Alerta.resolvido_em.is_(None)
                )
            )
            .scalars()
            .all()
        )
        # Sem o evento, uma leitura só não abriria alerta.
        assert any(a.tipo == "fora_da_area" for a in abertos)

    def test_evento_invalido(self, cliente, animal, mestre_ativo):
        _, chave = mestre_ativo
        resposta = cliente.post(
            "/api/dispositivos/telemetria",
            headers=chave_header(chave),
            json={
                "leituras": [
                    {"brinco": animal.brinco, "lat": CENTRO[0], "lon": CENTRO[1], "evento": "voou"}
                ]
            },
        )
        assert resposta.status_code == 422


class TestSilencioColetivo:
    def _lote(self, db, fazenda, pasto, quantos: int) -> list[Animal]:
        criados = []
        for i in range(quantos):
            a = Animal(
                fazenda_id=fazenda.id,
                pasto_id=pasto.id,
                brinco=f"07600000000{i + 10:04d}",
                nome=f"Animal {i}",
            )
            db.add(a)
            db.flush()
            telemetria.registrar(db, a, *CENTRO, atividade=0.6)
            criados.append(a)
        db.commit()
        return criados

    def test_lote_mudo_gera_um_alerta_so(self, db, fazenda, pasto):
        """Sem isso, uma queda de mestre vira vinte notificações falsas."""
        rebanho = self._lote(db, fazenda, pasto, 10)
        for a in rebanho:
            a.ultimo_contato = agora() - dt.timedelta(hours=2)
        db.commit()

        servico_alertas.varrer_silencio(db)
        db.commit()

        de_lote = db.execute(
            select(func.count()).select_from(Alerta).where(Alerta.tipo == ALERTA_LOTE_MUDO)
        ).scalar_one()
        individuais = db.execute(
            select(func.count()).select_from(Alerta).where(Alerta.tipo == ALERTA_SEM_SINAL)
        ).scalar_one()

        assert de_lote == 1
        assert individuais == 0, "o lote inteiro calado não é dez roubos simultâneos"

    def test_um_animal_calado_continua_alerta_individual(self, db, fazenda, pasto):
        rebanho = self._lote(db, fazenda, pasto, 10)
        rebanho[0].ultimo_contato = agora() - dt.timedelta(hours=2)
        db.commit()

        servico_alertas.varrer_silencio(db)
        db.commit()

        de_lote = db.execute(
            select(func.count()).select_from(Alerta).where(Alerta.tipo == ALERTA_LOTE_MUDO)
        ).scalar_one()
        individuais = db.execute(
            select(func.count()).select_from(Alerta).where(Alerta.tipo == ALERTA_SEM_SINAL)
        ).scalar_one()

        # Um animal sumindo é exatamente o alerta que o produto existe para dar.
        assert de_lote == 0
        assert individuais == 1

    def test_nao_duplica_o_alerta_de_lote(self, db, fazenda, pasto):
        rebanho = self._lote(db, fazenda, pasto, 10)
        for a in rebanho:
            a.ultimo_contato = agora() - dt.timedelta(hours=2)
        db.commit()

        for _ in range(3):
            servico_alertas.varrer_silencio(db)
            db.commit()

        total = db.execute(
            select(func.count()).select_from(Alerta).where(Alerta.tipo == ALERTA_LOTE_MUDO)
        ).scalar_one()
        assert total == 1

    def test_lote_que_volta_a_falar_resolve(self, db, fazenda, pasto):
        rebanho = self._lote(db, fazenda, pasto, 10)
        for a in rebanho:
            a.ultimo_contato = agora() - dt.timedelta(hours=2)
        db.commit()
        servico_alertas.varrer_silencio(db)
        db.commit()

        for a in rebanho:
            telemetria.registrar(db, a, *CENTRO, atividade=0.6)
        db.commit()
        servico_alertas.varrer_silencio(db)
        db.commit()

        aberto = db.execute(
            select(Alerta).where(
                Alerta.tipo == ALERTA_LOTE_MUDO, Alerta.resolvido_em.is_(None)
            )
        ).scalar_one_or_none()
        assert aberto is None


class TestConfigDosDispositivos:
    def test_entrega_o_poligono(self, cliente, db, pasto, animal, mestre_ativo):
        """É o que permite a geocerca rodar no brinco, sem depender de enlace."""
        _, chave = mestre_ativo
        corpo = cliente.get("/api/dispositivos/config", headers=chave_header(chave)).json()

        assert len(corpo["pastos"]) == 1
        assert len(corpo["pastos"][0]["pontos"]) == len(PASTO_TESTE)
        assert corpo["pastos"][0]["buffer_m"] == pasto.buffer_m
        assert any(a["brinco"] == animal.brinco for a in corpo["animais"])

    def test_versao_muda_quando_o_pasto_muda(self, cliente, db, pasto, animal, mestre_ativo):
        """O mestre só redistribui por rádio quando a versão muda — rádio é o
        recurso escasso aqui."""
        _, chave = mestre_ativo
        antes = cliente.get("/api/dispositivos/config", headers=chave_header(chave)).json()["versao"]

        pasto.buffer_m = 50.0
        db.commit()

        depois = cliente.get("/api/dispositivos/config", headers=chave_header(chave)).json()["versao"]
        assert antes != depois


class TestPainelDoProdutor:
    def test_dono_lista_mestres(self, cliente, dono, mestre_ativo):
        token = entrar(cliente, dono.email)
        corpo = cliente.get("/api/mestres", headers=auth(token)).json()

        assert len(corpo) == 1
        assert corpo[0]["ativo"] is True
        assert corpo[0]["prefixo_chave"]

    def test_operador_nao_gerencia(self, cliente, db, fazenda):
        from app.models import PAPEL_OPERADOR
        from tests.conftest import criar_usuario

        criar_usuario(db, fazenda, email="op@teste.com.br", papel=PAPEL_OPERADOR)
        token = entrar(cliente, "op@teste.com.br")
        assert cliente.get("/api/mestres", headers=auth(token)).status_code == 403
