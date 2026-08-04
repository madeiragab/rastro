from fastapi import APIRouter

from app.api.routes import alertas, animais, pastos, resumo, simulacao, telemetria

api_router = APIRouter(prefix="/api")
api_router.include_router(resumo.router)
api_router.include_router(pastos.router)
api_router.include_router(animais.router)
api_router.include_router(alertas.router)
api_router.include_router(telemetria.router)
api_router.include_router(simulacao.router)
