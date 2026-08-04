"""Rastro -- API de rastreamento e geocerca de rebanho bovino."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import api_router
from app.config import settings
from app.database import SessionLocal, engine, init_db
from app.seed import semear
from app.services import simulador

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

    tarefa = None
    if settings.simulator_enabled:
        tarefa = asyncio.create_task(simulador.loop())

    yield

    if tarefa:
        tarefa.cancel()
        try:
            await tarefa
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Rastro API",
    description="Rastreamento em tempo real e geocerca para rebanho bovino.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["infra"])
def health() -> dict[str, str]:
    return {"status": "ok", "servico": "rastro-api"}
