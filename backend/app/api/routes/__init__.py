"""Montagem do roteador da API.

A autorizacao e declarada **aqui**, no include, e nao rota a rota. Assim, uma
rota nova nasce protegida por omissao: para deixar algo aberto e preciso
adiciona-lo explicitamente ao grupo publico, o que aparece na revisao de codigo.
"""

from fastapi import APIRouter, Depends

from app.api.deps import exige_papel, gateway_atual, usuario_atual
from app.api.routes import (
    alertas,
    animais,
    auth,
    gateways,
    pastos,
    resumo,
    simulacao,
    telemetria,
    usuarios,
)
from app.models import PAPEL_OPERADOR

api_router = APIRouter(prefix="/api")

# --- publico: so o proprio fluxo de autenticacao -------------------------
api_router.include_router(auth.router)

# --- sessao de usuario ---------------------------------------------------
protegido = [Depends(usuario_atual)]
api_router.include_router(resumo.router, dependencies=protegido)
api_router.include_router(animais.router, dependencies=protegido)
api_router.include_router(alertas.router, dependencies=protegido)

# Criar e apagar pasto muda a geocerca de todo o rebanho -- exige operador.
api_router.include_router(pastos.router, dependencies=[Depends(exige_papel(PAPEL_OPERADOR))])

# Chaves de gateway e equipe: a checagem de papel `dono` esta em cada rota,
# porque elas precisam do objeto do usuario para filtrar pela fazenda.
api_router.include_router(gateways.router, dependencies=protegido)
api_router.include_router(usuarios.router, dependencies=protegido)

# --- identidade de dispositivo ------------------------------------------
api_router.include_router(telemetria.router, dependencies=[Depends(gateway_atual)])

# --- demonstracao --------------------------------------------------------
# Desligado em producao pela validacao de configuracao (simulator_enabled).
api_router.include_router(simulacao.router, dependencies=[Depends(exige_papel(PAPEL_OPERADOR))])
