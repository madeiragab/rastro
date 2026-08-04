"""Configuracao central da aplicacao.

Todos os limiares do motor de alertas e todos os parametros de seguranca ficam
aqui, e nao espalhados pelo codigo, porque sao os pontos de calibragem quando o
produto vai a campo.

Os valores default dos alertas estao COMPRIMIDOS para demonstracao: um alerta
que na operacao real levaria horas dispara em segundos, para que o MVP seja
apresentavel em poucos minutos. As constantes `*_producao` documentam o valor
que faz sentido no campo.
"""

from __future__ import annotations

import logging
import secrets

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("rastro.config")

# Marcador do segredo de desenvolvimento. A aplicacao se recusa a subir em
# producao com este valor -- e a diferenca entre "esqueci de configurar" e
# "qualquer um forja um token de administrador".
#
# Tem mais de 32 bytes de proposito: a RFC 7518 exige chave de pelo menos o
# tamanho do digest para HMAC-SHA256, e um default curto faria a biblioteca
# alertar a cada token emitido -- ruido que ensina a ignorar aviso.
SEGREDO_DEV = "dev-inseguro-nao-usar-fora-da-sua-maquina"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---------------------------------------------------------------- infra
    ambiente: str = "desenvolvimento"  # "desenvolvimento" | "producao"
    database_url: str = "postgresql+psycopg://rastro:rastro@localhost:5432/rastro"

    # Lista explicita. Nunca use "*" com credenciais: o navegador rejeita, e se
    # aceitasse seria um convite a roubo de sessao a partir de qualquer site.
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # ---------------------------------------------------------- autenticacao
    secret_key: str = SEGREDO_DEV
    jwt_algoritmo: str = "HS256"
    jwt_emissor: str = "rastro"
    jwt_audiencia: str = "rastro-app"

    # Access token curto: se vazar, a janela de abuso e pequena. A renovacao
    # silenciosa pelo refresh token evita que o usuario perceba.
    access_token_ttl_min: int = 15
    refresh_token_ttl_dias: int = 14

    # Argon2id -- parametros acima do minimo do OWASP (19 MiB / t=2).
    argon2_memoria_kib: int = 65536  # 64 MiB
    argon2_iteracoes: int = 3
    argon2_paralelismo: int = 2

    senha_tamanho_minimo: int = 12

    # ---------------------------------------------- protecao contra forca bruta
    login_max_tentativas: int = 5
    login_janela_min: int = 15
    login_bloqueio_min: int = 15

    # ------------------------------------------------------------- cookies
    # O refresh token vive num cookie HttpOnly: JavaScript nao le, entao um XSS
    # nao consegue exfiltrar a sessao de longa duracao.
    cookie_refresh_nome: str = "rastro_refresh"
    cookie_csrf_nome: str = "rastro_csrf"
    cookie_secure: bool = False  # True obrigatorio em producao (ver validador)
    cookie_samesite: str = "strict"
    cookie_dominio: str | None = None

    # ------------------------------------------------------------ geocerca
    # Zona de tolerancia. O animal so e considerado fora quando ultrapassa o
    # poligono E esta buffer_m alem dele. Sem isso, o erro do GNSS gera alarme
    # falso continuo com o animal pastando junto a cerca.
    geofence_buffer_m: float = 25.0
    geofence_confirmacoes: int = 2

    # ----------------------------------------------------------- imobilidade
    imobilidade_atividade_max: float = 0.08
    imobilidade_segundos: int = 90
    imobilidade_segundos_producao: int = 4 * 3600

    # --------------------------------------------------------- perda de sinal
    sinal_fator_silencio: float = 4.0
    sinal_silencio_minimo_s: int = 60

    # ------------------------------------------------------------- simulador
    simulator_enabled: bool = True
    simulator_tick_s: float = 4.0

    intervalo_reporte_s: int = 8
    intervalo_reporte_s_producao: int = 1800

    # ----------------------------------------------------- conta inicial
    # Usada apenas na carga de demonstracao. Em producao, criar a conta por
    # fora e nunca versionar a senha.
    # Domínio real de propósito: `.local` é reservado (RFC 6762) e validadores
    # de e-mail o recusam, o que tornaria a conta semeada impossível de usar.
    admin_email: str = "produtor@rastro.com.br"
    admin_senha: str = Field(default="", repr=False)

    # ------------------------------------------------------------ validacao
    @model_validator(mode="after")
    def _travas_de_producao(self) -> "Settings":
        producao = self.ambiente.lower().startswith("prod")

        if producao:
            if self.secret_key == SEGREDO_DEV or len(self.secret_key) < 32:
                raise RuntimeError(
                    "SECRET_KEY ausente ou fraca. Em producao defina um valor "
                    "aleatorio de 32+ bytes: python -c \"import secrets; "
                    "print(secrets.token_urlsafe(48))\""
                )
            if not self.cookie_secure:
                raise RuntimeError("COOKIE_SECURE precisa ser true em producao (cookies so por HTTPS).")
            if any(o.startswith("http://") and "localhost" not in o for o in self.cors_origins):
                raise RuntimeError("CORS_ORIGINS contem origem http:// nao-local em producao.")
            if self.simulator_enabled:
                raise RuntimeError("SIMULATOR_ENABLED precisa ser false em producao.")
        elif self.secret_key == SEGREDO_DEV:
            log.warning(
                "usando SECRET_KEY de desenvolvimento -- tokens sao forjaveis. "
                "Nunca use este valor fora da sua maquina."
            )

        return self

    @property
    def em_producao(self) -> bool:
        return self.ambiente.lower().startswith("prod")


settings = Settings()


def segredo_aleatorio(bytes_: int = 32) -> str:
    """Gerador unico de segredo, para nao haver `random` espalhado pelo codigo."""
    return secrets.token_urlsafe(bytes_)
