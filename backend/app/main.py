"""Rastro -- API de rastreamento e geocerca de rebanho bovino."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.deps import CABECALHO_CHAVE
from app.api.routes import api_router
from app.api.routes.auth import CABECALHO_CSRF
from app.config import settings
from app.database import SessionLocal, engine, init_db
from app.middleware import CabecalhosDeSeguranca
from app.seed import semear
from app.services import manutencao, simulador

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("rastro")


def _esperar_banco(tentativas: int = 30, intervalo: float = 2.0) -> None:
    """O container da API sobe junto com o do banco; o healthcheck do compose
    cobre o caso normal, mas fora do Docker vale a pena esperar."""
    import time

    for tentativa in range(1, tentativas + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as erro:  # noqa: BLE001
            log.warning("banco indisponivel (%s/%s): %s", tentativa, tentativas, erro)
            time.sleep(intervalo)

    raise RuntimeError("banco de dados nao respondeu a tempo")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _esperar_banco()
    init_db()

    db = SessionLocal()
    try:
        if semear(db):
            log.info("dados de demonstracao criados")
    finally:
        db.close()

    tarefas = [asyncio.create_task(manutencao.loop())]
    if settings.simulator_enabled:
        tarefas.append(asyncio.create_task(simulador.loop()))

    yield

    for tarefa in tarefas:
        tarefa.cancel()
    for tarefa in tarefas:
        try:
            await tarefa
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Rastro API",
    description="Rastreamento em tempo real e geocerca para rebanho bovino.",
    version="0.2.0",
    lifespan=lifespan,
    # Documentacao interativa desligada em producao: o esquema completo da API
    # e um mapa pronto para quem estiver sondando.
    docs_url=None if settings.em_producao else "/docs",
    redoc_url=None if settings.em_producao else "/redoc",
    openapi_url=None if settings.em_producao else "/openapi.json",
)

app.add_middleware(CabecalhosDeSeguranca)

app.add_middleware(
    CORSMiddleware,
    # Lista explicita de origens. `allow_credentials` com origem "*" e recusado
    # pelo navegador, e com regex frouxa vira roubo de sessao.
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", CABECALHO_CSRF, CABECALHO_CHAVE],
    max_age=600,
)

app.include_router(api_router)


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    """Sonda de disponibilidade. Nao revela versao nem estado interno."""
    return {"status": "ok"}
