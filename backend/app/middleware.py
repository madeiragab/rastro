"""Cabecalhos de seguranca da resposta.

Camada barata e independente da aplicacao: mesmo que uma rota tenha um bug, o
navegador ja recebe instrucoes que limitam o estrago.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings

# A API so devolve JSON, entao a politica pode ser a mais fechada possivel:
# nada de script, nada de frame, nada de origem externa.
CSP_API = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)

# O Swagger carrega CSS e JS de CDN. Mantido separado e habilitado apenas fora
# de producao -- em producao a documentacao interativa fica desligada.
CSP_DOCS = (
    "default-src 'none'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "img-src 'self' https://fastapi.tiangolo.com data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
)


class CabecalhosDeSeguranca(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resposta = await call_next(request)
        cabecalhos = resposta.headers

        eh_docs = request.url.path in ("/docs", "/redoc", "/openapi.json")
        cabecalhos["Content-Security-Policy"] = CSP_DOCS if eh_docs else CSP_API

        # Impede o navegador de "adivinhar" o tipo do conteudo -- um JSON
        # interpretado como HTML vira vetor de XSS.
        cabecalhos["X-Content-Type-Options"] = "nosniff"
        cabecalhos["X-Frame-Options"] = "DENY"
        cabecalhos["Referrer-Policy"] = "no-referrer"
        cabecalhos["Cross-Origin-Opener-Policy"] = "same-origin"
        cabecalhos["Cross-Origin-Resource-Policy"] = "same-origin"
        cabecalhos["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=(), payment=()"

        # Respostas de rota autenticada nao podem ficar em cache compartilhado.
        if request.url.path.startswith("/api/"):
            cabecalhos["Cache-Control"] = "no-store"

        # HSTS so faz sentido sob HTTPS; anunciado em http:// o navegador ignora,
        # e em desenvolvimento atrapalharia o acesso por localhost.
        if settings.cookie_secure:
            cabecalhos["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Nao entregamos a pilha usada de graca.
        cabecalhos.pop("server", None)

        return resposta
