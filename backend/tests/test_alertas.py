"""As três regras de alerta.

Este é o arquivo que protege a tese do produto: **alarme falso é o que mata a
adoção**. Cada regra tem um teste do caso positivo e, mais importante, um teste
do caso que NÃO pode disparar.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.config import settings
from app.models import (
    ALERTA_FORA,
    ALERTA_IMOVEL,
    ALERTA_SEM_SINAL,
    STATUS_FORA,
    STATUS_IMOVEL,
    STATUS_OK,
    Alerta,
    agora,
)
from app.services import alertas as servico
from app.services import geofence, telemetria
from tests.conftest import CENTRO

# Bem dentro do polígono.
DENTRO = CENTRO
# ~700 m ao sul da divisa: fora do polígono e além dos 25 m de tolerância.
FORA = (-19.7580, -47.9330)
# ~10 m além da divisa: fora do polígono, mas DENTRO da tolerância.
NA_BORDA = (-19.75109, -47.9330)


def alertas_de(db, animal, tipo) -> list[Alerta]:
    return list(
        db.execute(
            select(Alerta).where(
                Alerta.animal_id == animal.id,
                Alerta.tipo == tipo,
                Alerta.resolvido_em.is_(None),
            )
        ).scalars()
    )


class TestGeocerca:
    def test_dentro_nao_alerta(self, db, animal):
        telemetria.registrar(db, animal, *DENTRO, atividade=0.6)
        db.commit()

        assert alertas_de(db, animal, ALERTA_FORA) == []
        assert animal.status == STATUS_OK

    def test_uma_leitura_fora_nao_alerta(self, db, animal):
        """Histerese: é o teste que representa o requisito central do produto.

        Uma leitura isolada fora é ruído de GNSS, não fuga.
        """
        telemetria.registrar(db, animal, *FORA, atividade=0.6)
        db.commit()

        assert alertas_de(db, animal, ALERTA_FORA) == []
        assert animal.leituras_fora == 1

    def test_duas_leituras_consecutivas_alertam(self, db, animal):
        for _ in range(settings.geofence_confirmacoes):
            telemetria.registrar(db, animal, *FORA, atividade=0.6)
        db.commit()

        abertos = alertas_de(db, animal, ALERTA_FORA)
        assert len(abertos) == 1
        assert animal.status == STATUS_FORA

    def test_borda_dentro_da_tolerancia_nao_alerta(self, db, animal):
        """Animal pastando junto à cerca não pode gerar alerta."""
        for _ in range(4):
            telemetria.registrar(db, animal, *NA_BORDA, atividade=0.6)
        db.commit()

        assert alertas_de(db, animal, ALERTA_FORA) == []

    def test_voltar_zera_o_contador(self, db, animal):
        telemetria.registrar(db, animal, *FORA, atividade=0.6)
        assert animal.leituras_fora == 1

        telemetria.registrar(db, animal, *DENTRO, atividade=0.6)
        db.commit()

        assert animal.leituras_fora == 0

    def test_voltar_resolve_o_alerta(self, db, animal):
        for _ in range(settings.geofence_confirmacoes):
            telemetria.registrar(db, animal, *FORA, atividade=0.6)
        db.commit()
        assert len(alertas_de(db, animal, ALERTA_FORA)) == 1

        telemetria.registrar(db, animal, *DENTRO, atividade=0.6)
        db.commit()

        assert alertas_de(db, animal, ALERTA_FORA) == []

    def test_nao_duplica_enquanto_aberto(self, db, animal):
        """Uma ocorrência gera uma notificação, não uma por leitura."""
        for _ in range(8):
            telemetria.registrar(db, animal, *FORA, atividade=0.6)
        db.commit()

        assert len(alertas_de(db, animal, ALERTA_FORA)) == 1

    def test_distancia_em_metros(self, db, animal, pasto):
        """A distância sai de `geography`, então é metro de verdade."""
        resultado = geofence.avaliar(db, pasto, *FORA)

        assert resultado.dentro is False
        assert 500 < resultado.distancia_m < 1000


class TestImobilidade:
    def test_atividade_normal_nao_alerta(self, db, animal):
        telemetria.registrar(db, animal, *DENTRO, atividade=0.6)
        db.commit()

        assert alertas_de(db, animal, ALERTA_IMOVEL) == []
        assert animal.imovel_desde is None

    def test_gnss_parado_com_atividade_nao_alerta(self, db, animal):
        """O caso que a regra existe para não errar.

        Bovino deitado ruminando fica no mesmo ponto por horas. Se a regra
        olhasse a variação do GNSS, alertaria todo fim de tarde.
        """
        for _ in range(10):
            telemetria.registrar(db, animal, *DENTRO, atividade=0.5)
        db.commit()

        assert alertas_de(db, animal, ALERTA_IMOVEL) == []

    def test_atividade_baixa_por_pouco_tempo_nao_alerta(self, db, animal):
        telemetria.registrar(db, animal, *DENTRO, atividade=0.0)
        db.commit()

        assert alertas_de(db, animal, ALERTA_IMOVEL) == []
        assert animal.imovel_desde is not None

    def test_atividade_baixa_prolongada_alerta(self, db, animal):
        telemetria.registrar(db, animal, *DENTRO, atividade=0.0)
        # Recua o marcador para simular a passagem do tempo, em vez de dormir.
        animal.imovel_desde = agora() - dt.timedelta(
            seconds=settings.imobilidade_segundos + 10
        )

        telemetria.registrar(db, animal, *DENTRO, atividade=0.0)
        db.commit()

        assert len(alertas_de(db, animal, ALERTA_IMOVEL)) == 1
        assert animal.status == STATUS_IMOVEL

    def test_voltar_a_se_mover_resolve(self, db, animal):
        telemetria.registrar(db, animal, *DENTRO, atividade=0.0)
        animal.imovel_desde = agora() - dt.timedelta(
            seconds=settings.imobilidade_segundos + 10
        )
        telemetria.registrar(db, animal, *DENTRO, atividade=0.0)
        db.commit()
        assert len(alertas_de(db, animal, ALERTA_IMOVEL)) == 1

        telemetria.registrar(db, animal, *DENTRO, atividade=0.7)
        db.commit()

        assert alertas_de(db, animal, ALERTA_IMOVEL) == []
        assert animal.imovel_desde is None


class TestPerdaDeSinal:
    def test_contato_recente_nao_alerta(self, db, animal):
        telemetria.registrar(db, animal, *DENTRO, atividade=0.6)
        db.commit()

        servico.varrer_silencio(db)
        db.commit()

        assert alertas_de(db, animal, ALERTA_SEM_SINAL) == []

    def test_silencio_prolongado_alerta(self, db, animal):
        animal.ultimo_contato = agora() - dt.timedelta(hours=2)
        db.commit()

        servico.varrer_silencio(db)
        db.commit()

        assert len(alertas_de(db, animal, ALERTA_SEM_SINAL)) == 1

    def test_nao_duplica(self, db, animal):
        animal.ultimo_contato = agora() - dt.timedelta(hours=2)
        db.commit()

        for _ in range(3):
            servico.varrer_silencio(db)
            db.commit()

        assert len(alertas_de(db, animal, ALERTA_SEM_SINAL)) == 1

    def test_voltar_a_reportar_resolve(self, db, animal):
        animal.ultimo_contato = agora() - dt.timedelta(hours=2)
        db.commit()
        servico.varrer_silencio(db)
        db.commit()
        assert len(alertas_de(db, animal, ALERTA_SEM_SINAL)) == 1

        telemetria.registrar(db, animal, *DENTRO, atividade=0.6)
        db.commit()

        assert alertas_de(db, animal, ALERTA_SEM_SINAL) == []

    def test_animal_sem_contato_algum_e_ignorado(self, db, fazenda, pasto):
        """Animal recém-cadastrado que nunca reportou não é 'perda de sinal'."""
        from app.models import Animal

        novo = Animal(
            fazenda_id=fazenda.id,
            pasto_id=pasto.id,
            brinco="076000000000002",
            nome="Novato",
        )
        db.add(novo)
        db.commit()

        servico.varrer_silencio(db)
        db.commit()

        assert alertas_de(db, novo, ALERTA_SEM_SINAL) == []


class TestResolucaoManual:
    def test_resolver_todos_do_animal(self, db, animal):
        for _ in range(settings.geofence_confirmacoes):
            telemetria.registrar(db, animal, *FORA, atividade=0.6)
        db.commit()
        assert len(alertas_de(db, animal, ALERTA_FORA)) == 1

        servico.resolver_todos(db, animal.id)
        db.commit()

        assert alertas_de(db, animal, ALERTA_FORA) == []
        assert animal.status == STATUS_OK
        assert animal.leituras_fora == 0

    def test_reabre_se_a_causa_persistir(self, db, animal):
        """Marcar como resolvido não conserta o mundo real."""
        for _ in range(settings.geofence_confirmacoes):
            telemetria.registrar(db, animal, *FORA, atividade=0.6)
        db.commit()

        servico.resolver_todos(db, animal.id)
        db.commit()

        for _ in range(settings.geofence_confirmacoes):
            telemetria.registrar(db, animal, *FORA, atividade=0.6)
        db.commit()

        assert len(alertas_de(db, animal, ALERTA_FORA)) == 1
