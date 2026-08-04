"""Ingestão de telemetria: autenticação de dispositivo e validação de entrada.

É a superfície mais exposta do sistema — o que está do outro lado é um
equipamento em campo, que pode estar com firmware velho, com defeito, ou sob
controle de terceiros.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select

from app.models import Animal, Fazenda, Pasto, Posicao
from app.services import geofence
from tests.conftest import CENTRO, PASTO_TESTE, criar_chave


def payload(**extra):
    base = {
        "brinco": "076000000000001",
        "lat": CENTRO[0],
        "lon": CENTRO[1],
        "atividade": 0.6,
        "bateria_pct": 88,
    }
    base.update(extra)
    return base


class TestAutenticacaoDoGateway:
    def test_sem_chave(self, cliente, animal):
        assert cliente.post("/api/telemetria", json=payload()).status_code == 401

    @pytest.mark.parametrize(
        "chave", ["lixo", "rastro_gw_soprefixo", "rastro_gw_aaaa_segredo-errado", ""]
    )
    def test_chave_invalida(self, cliente, animal, chave):
        resposta = cliente.post(
            "/api/telemetria", json=payload(), headers={"X-API-Key": chave}
        )
        assert resposta.status_code == 401

    def test_chave_valida(self, cliente, animal, chave_gateway):
        resposta = cliente.post(
            "/api/telemetria", json=payload(), headers={"X-API-Key": chave_gateway}
        )
        assert resposta.status_code == 201
        assert resposta.json()["brinco"] == "076000000000001"

    def test_chave_revogada(self, cliente, db, animal, chave_gateway):
        from app.models import ChaveGateway, agora

        registro = db.execute(select(ChaveGateway)).scalar_one()
        registro.ativa = False
        registro.revogada_em = agora()
        db.commit()

        resposta = cliente.post(
            "/api/telemetria", json=payload(), headers={"X-API-Key": chave_gateway}
        )
        assert resposta.status_code == 401

    def test_chave_expirada(self, cliente, db, animal, chave_gateway):
        from app.models import ChaveGateway, agora

        registro = db.execute(select(ChaveGateway)).scalar_one()
        registro.expira_em = agora() - dt.timedelta(days=1)
        db.commit()

        resposta = cliente.post(
            "/api/telemetria", json=payload(), headers={"X-API-Key": chave_gateway}
        )
        assert resposta.status_code == 401

    def test_registra_a_ultima_utilizacao(self, cliente, db, animal, chave_gateway):
        from app.models import ChaveGateway

        cliente.post("/api/telemetria", json=payload(), headers={"X-API-Key": chave_gateway})

        registro = db.execute(select(ChaveGateway)).scalar_one()
        db.refresh(registro)
        assert registro.ultima_utilizacao is not None


class TestEscopoDaChave:
    def test_nao_reporta_animal_de_outra_fazenda(self, cliente, db, animal, chave_gateway):
        """Chave vazada de uma propriedade não move o gado da outra."""
        outra = Fazenda(nome="Outra", proprietario="Maria", municipio="Araxá", uf="MG")
        db.add(outra)
        db.flush()

        pasto = Pasto(
            fazenda_id=outra.id,
            nome="Pasto da outra",
            buffer_m=25.0,
            geom=func.ST_GeomFromText(geofence.wkt_poligono(PASTO_TESTE), 4326),
        )
        db.add(pasto)
        db.flush()
        db.add(
            Animal(
                fazenda_id=outra.id,
                pasto_id=pasto.id,
                brinco="076000000000999",
                nome="Estrela",
            )
        )
        db.commit()

        chave_da_outra = criar_chave(db, outra, nome="Gateway da outra")

        # A chave da outra fazenda não alcança o animal desta.
        resposta = cliente.post(
            "/api/telemetria",
            json=payload(brinco="076000000000001"),
            headers={"X-API-Key": chave_da_outra},
        )
        # 404, não 403: 403 confirmaria que o brinco existe.
        assert resposta.status_code == 404

    def test_brinco_inexistente(self, cliente, animal, chave_gateway):
        resposta = cliente.post(
            "/api/telemetria",
            json=payload(brinco="076000000000777"),
            headers={"X-API-Key": chave_gateway},
        )
        assert resposta.status_code == 404


class TestValidacaoDeEntrada:
    @pytest.mark.parametrize(
        "campo,valor",
        [
            ("lat", 91.0),
            ("lat", -91.0),
            ("lon", 181.0),
            ("lon", -181.0),
            ("atividade", 1.5),
            ("atividade", -0.1),
            ("bateria_pct", 101),
            ("bateria_pct", -1),
            ("brinco", "abc"),
            ("brinco", "0" * 16),
        ],
    )
    def test_fora_da_faixa(self, cliente, animal, chave_gateway, campo, valor):
        resposta = cliente.post(
            "/api/telemetria",
            json=payload(**{campo: valor}),
            headers={"X-API-Key": chave_gateway},
        )
        assert resposta.status_code == 422

    def test_recusa_carimbo_no_futuro(self, cliente, animal, chave_gateway):
        """Sem isso, um gateway comprometido silenciaria o alerta de perda de
        sinal para sempre."""
        futuro = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
        resposta = cliente.post(
            "/api/telemetria",
            json=payload(registrada_em=futuro.isoformat()),
            headers={"X-API-Key": chave_gateway},
        )
        assert resposta.status_code == 422

    def test_recusa_carimbo_antigo_demais(self, cliente, animal, chave_gateway):
        antigo = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
        resposta = cliente.post(
            "/api/telemetria",
            json=payload(registrada_em=antigo.isoformat()),
            headers={"X-API-Key": chave_gateway},
        )
        assert resposta.status_code == 422

    def test_aceita_atraso_plausivel(self, cliente, animal, chave_gateway):
        """O gateway pode ter ficado offline e estar descarregando um lote."""
        atrasado = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)
        resposta = cliente.post(
            "/api/telemetria",
            json=payload(registrada_em=atrasado.isoformat()),
            headers={"X-API-Key": chave_gateway},
        )
        assert resposta.status_code == 201


class TestPersistencia:
    def test_grava_posicao_e_atualiza_o_animal(self, cliente, db, animal, chave_gateway):
        antes = db.execute(
            select(func.count()).select_from(Posicao).where(Posicao.animal_id == animal.id)
        ).scalar_one()

        cliente.post("/api/telemetria", json=payload(), headers={"X-API-Key": chave_gateway})

        depois = db.execute(
            select(func.count()).select_from(Posicao).where(Posicao.animal_id == animal.id)
        ).scalar_one()

        assert depois == antes + 1

        db.refresh(animal)
        assert animal.ultimo_contato is not None
        assert animal.bateria_pct == 88
