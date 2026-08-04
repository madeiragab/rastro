"""Infraestrutura dos testes.

Os testes rodam contra **PostGIS de verdade**, não contra um banco em memória.
A regra de geocerca é `ST_Contains` mais distância em `geography`: testar isso
com um dublê seria testar o dublê. O banco de teste é separado do de
desenvolvimento e recriado a cada sessão.

O `lifespan` da aplicação não é acionado de propósito — ele semeia dados de
demonstração e liga o simulador, e um simulador escrevendo no meio do teste
torna o resultado não reprodutível.
"""

from __future__ import annotations

import os

# Precisa vir antes de importar app.config: as configurações são lidas uma vez,
# na importação do módulo.
os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://rastro:rastro@localhost:5432/rastro_test",
    ),
)
os.environ.setdefault("SIMULATOR_ENABLED", "false")
os.environ.setdefault("AMBIENTE", "desenvolvimento")

# Argon2 barato SÓ nos testes. Em produção o custo alto é a proteção; aqui ele
# dominava o relógio (a suíte inteira gasta mais tempo derivando hash do que
# exercitando regra). O que se testa é o comportamento, não a dureza do KDF.
os.environ.setdefault("ARGON2_MEMORIA_KIB", "8192")
os.environ.setdefault("ARGON2_ITERACOES", "1")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, func, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, criar_schema_direto, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    PAPEL_DONO,
    Animal,
    ChaveGateway,
    Fazenda,
    Pasto,
    Usuario,
)
from app.security import chaves, senhas  # noqa: E402
from app.services import geofence, telemetria  # noqa: E402

SENHA_TESTE = "pasto-do-corrego-2026"

# Domínio real de propósito: `.local` é reservado (RFC 6762) e o validador de
# e-mail o recusa — foi exatamente o bug que impedia login na conta semeada.
EMAIL_DONO = "dono@teste.com.br"

# Retângulo de ~600 m x 600 m na região de Uberaba/MG.
PASTO_TESTE = [
    (-19.7510, -47.9360),
    (-19.7510, -47.9300),
    (-19.7460, -47.9300),
    (-19.7460, -47.9360),
]
CENTRO = (-19.7485, -47.9330)


def _criar_banco_de_teste() -> None:
    """Cria o banco de teste se ainda não existir."""
    url_admin = settings.database_url.rsplit("/", 1)[0] + "/postgres"
    nome = settings.database_url.rsplit("/", 1)[1]

    admin = create_engine(url_admin, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        existe = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": nome}
        ).scalar()
        if not existe:
            conn.execute(text(f'CREATE DATABASE "{nome}"'))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def schema():
    _criar_banco_de_teste()
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.drop_all(bind=engine)
    criar_schema_direto()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db(schema) -> Session:
    """Sessão limpa. Truncate é mais rápido que recriar o schema por teste."""
    sessao = SessionLocal()
    tabelas = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    sessao.execute(text(f"TRUNCATE {tabelas} RESTART IDENTITY CASCADE"))
    sessao.commit()
    try:
        yield sessao
    finally:
        sessao.close()


@pytest.fixture()
def cliente(db) -> TestClient:
    """Cliente HTTP compartilhando a sessão do teste.

    Sem o override, a rota abriria uma sessão própria e não enxergaria o que o
    teste preparou dentro da transação.
    """

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    # Sem `with`: usado como gerenciador de contexto, o TestClient dispara o
    # lifespan — que semeia dados e liga o simulador. Aqui não queremos nenhum
    # dos dois.
    cliente = TestClient(app, base_url="http://testserver")
    yield cliente
    app.dependency_overrides.clear()


# --------------------------------------------------------------- fábricas
@pytest.fixture()
def fazenda(db) -> Fazenda:
    f = Fazenda(nome="Fazenda de Teste", proprietario="José", municipio="Uberaba", uf="MG")
    db.add(f)
    db.flush()
    return f


@pytest.fixture()
def pasto(db, fazenda) -> Pasto:
    p = Pasto(
        fazenda_id=fazenda.id,
        nome="Pasto de Teste",
        buffer_m=25.0,
        geom=func.ST_GeomFromText(geofence.wkt_poligono(PASTO_TESTE), 4326),
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def animal(db, fazenda, pasto) -> Animal:
    a = Animal(
        fazenda_id=fazenda.id,
        pasto_id=pasto.id,
        brinco="076000000000001",
        nome="Mimosa",
        categoria="Vaca",
    )
    db.add(a)
    db.flush()
    telemetria.registrar(db, a, CENTRO[0], CENTRO[1], atividade=0.6)
    db.commit()
    return a


def criar_usuario(db, fazenda, email=EMAIL_DONO, papel=PAPEL_DONO) -> Usuario:
    u = Usuario(
        fazenda_id=fazenda.id,
        email=email,
        nome="José Teste",
        senha_hash=senhas.gerar_hash(SENHA_TESTE),
        papel=papel,
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture()
def dono(db, fazenda) -> Usuario:
    return criar_usuario(db, fazenda)


def criar_chave(db, fazenda, nome="Gateway de Teste") -> str:
    """Devolve a chave em claro."""
    chave, prefixo, hash_ = chaves.gerar()
    db.add(ChaveGateway(fazenda_id=fazenda.id, nome=nome, prefixo=prefixo, chave_hash=hash_))
    db.commit()
    return chave


@pytest.fixture()
def chave_gateway(db, fazenda) -> str:
    return criar_chave(db, fazenda)


def entrar(cliente: TestClient, email=EMAIL_DONO, senha=SENHA_TESTE) -> str:
    """Faz login e devolve o access token. Os cookies ficam no jar do cliente."""
    resposta = cliente.post("/api/auth/login", json={"email": email, "senha": senha})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
