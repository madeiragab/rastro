"""Contratos de entrada e saida da API."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, EmailStr, Field, field_validator


# ------------------------------------------------------------------ fazenda
class FazendaOut(BaseModel):
    id: int
    nome: str
    proprietario: str
    municipio: str
    uf: str


# -------------------------------------------------------------------- pasto
class PastoIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    cor: str = "#2E7D53"
    buffer_m: float = 25.0
    # Anel externo do poligono como [[lat, lon], ...]. O fechamento e feito
    # no servidor, entao o cliente nao precisa repetir o primeiro ponto.
    pontos: list[tuple[float, float]]

    @field_validator("pontos")
    @classmethod
    def _minimo_tres_pontos(cls, v: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if len(v) < 3:
            raise ValueError("um pasto precisa de pelo menos 3 pontos")
        return v


class PastoOut(BaseModel):
    id: int
    nome: str
    cor: str
    buffer_m: float
    pontos: list[tuple[float, float]]
    area_ha: float
    total_animais: int


# ------------------------------------------------------------------- animal
class AnimalOut(BaseModel):
    id: int
    brinco: str
    nome: str
    categoria: str
    status: str
    bateria_pct: int
    lat: float | None
    lon: float | None
    ultimo_contato: dt.datetime | None
    segundos_sem_contato: int | None
    distancia_pasto_m: float
    pasto_id: int | None
    pasto_nome: str | None
    sim_comportamento: str


# ------------------------------------------------------------------ posicao
class PosicaoIn(BaseModel):
    """Payload que o brinco enviaria, repassado pelo gateway.

    Toda faixa e validada aqui, e nao no banco: e entrada de rede vinda de um
    dispositivo em campo, que pode estar com firmware velho, com defeito ou
    sob controle de terceiros.
    """

    brinco: str = Field(min_length=1, max_length=15, pattern=r"^\d{1,15}$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    atividade: float = Field(default=0.5, ge=0, le=1)
    bateria_pct: int = Field(default=100, ge=0, le=100)
    registrada_em: dt.datetime | None = None

    @field_validator("registrada_em")
    @classmethod
    def _horario_plausivel(cls, v: dt.datetime | None) -> dt.datetime | None:
        """Recusa carimbo de tempo absurdo.

        Sem isso, um gateway comprometido poderia inserir posicao no futuro e
        silenciar o alerta de perda de sinal para sempre, ou reescrever a
        trilha do passado.
        """
        if v is None:
            return None

        momento = v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
        agora = dt.datetime.now(dt.timezone.utc)

        # Alguma folga no futuro absorve relogio dessincronizado do dispositivo.
        if momento > agora + dt.timedelta(minutes=5):
            raise ValueError("registrada_em no futuro")
        # Aceita ate 7 dias de atraso: o gateway pode ter ficado offline e estar
        # descarregando um lote acumulado.
        if momento < agora - dt.timedelta(days=7):
            raise ValueError("registrada_em antiga demais")

        return momento


class PosicaoOut(BaseModel):
    lat: float
    lon: float
    registrada_em: dt.datetime
    atividade: float


# ------------------------------------------------------------------- alerta
class AlertaOut(BaseModel):
    id: int
    animal_id: int
    animal_nome: str
    brinco: str
    tipo: str
    severidade: str
    mensagem: str
    lat: float | None
    lon: float | None
    criado_em: dt.datetime
    resolvido_em: dt.datetime | None


# ------------------------------------------------------------------- resumo
class ResumoOut(BaseModel):
    total_animais: int
    em_area: int
    fora_da_area: int
    imoveis: int
    sem_sinal: int
    alertas_abertos: int
    total_pastos: int
    area_total_ha: float


# --------------------------------------------------------------- simulacao
class CenarioIn(BaseModel):
    animal_id: int
    comportamento: str

    @field_validator("comportamento")
    @classmethod
    def _valido(cls, v: str) -> str:
        from app.models import COMPORTAMENTOS

        if v not in COMPORTAMENTOS:
            raise ValueError(f"comportamento deve ser um de {COMPORTAMENTOS}")
        return v


# -------------------------------------------------------------- autenticacao
class LoginIn(BaseModel):
    email: EmailStr
    # Sem `min_length` aqui de proposito: a politica de senha vale no cadastro
    # e na troca. No login, recusar por tamanho antes de conferir vazaria que a
    # senha guardada nao segue mais a politica atual.
    senha: str = Field(repr=False)


class TokenOut(BaseModel):
    """O refresh token NAO aparece aqui -- ele so viaja em cookie HttpOnly.

    Devolver o refresh no corpo obrigaria o front a guarda-lo em algum lugar
    que o JavaScript le, e um XSS levaria a sessao de longa duracao junto.
    """

    access_token: str
    token_type: str = "bearer"
    expira_em_s: int
    usuario: "UsuarioOut"


class UsuarioOut(BaseModel):
    id: int
    email: str
    nome: str
    papel: str
    ativo: bool
    fazenda_id: int | None
    ultimo_login_em: dt.datetime | None


class TrocarSenhaIn(BaseModel):
    senha_atual: str = Field(repr=False)
    senha_nova: str = Field(repr=False)


# -------------------------------------------------------------------- push
class ChavePublicaOut(BaseModel):
    chave: str


class InscricaoPushIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=2000)
    chave_p256dh: str = Field(min_length=10, max_length=255)
    chave_auth: str = Field(min_length=6, max_length=255)


class InscricaoPushOut(BaseModel):
    id: int
    endpoint: str
    criada_em: dt.datetime
    ultimo_envio: dt.datetime | None


class EsqueciSenhaIn(BaseModel):
    email: EmailStr


class RedefinirSenhaIn(BaseModel):
    token: str = Field(min_length=10, repr=False)
    senha_nova: str = Field(repr=False)


# ------------------------------------------------------------------ equipe
class UsuarioIn(BaseModel):
    email: EmailStr
    nome: str = Field(min_length=1, max_length=120)
    papel: str = "operador"

    @field_validator("papel")
    @classmethod
    def _papel_valido(cls, v: str) -> str:
        from app.models import PAPEIS

        if v not in PAPEIS:
            raise ValueError(f"papel deve ser um de {PAPEIS}")
        return v


class UsuarioCriadoOut(UsuarioOut):
    """A senha inicial e sorteada e exibida uma unica vez, na criacao.

    O dono repassa pelo canal que quiser e o novo usuario troca no primeiro
    acesso. Assim o dono nunca escolhe a senha de outra pessoa -- e portanto
    nunca fica sabendo dela depois da primeira troca.
    """

    senha_inicial: str = Field(repr=False)


class UsuarioPatch(BaseModel):
    papel: str | None = None
    ativo: bool | None = None

    @field_validator("papel")
    @classmethod
    def _papel_valido(cls, v: str | None) -> str | None:
        from app.models import PAPEIS

        if v is not None and v not in PAPEIS:
            raise ValueError(f"papel deve ser um de {PAPEIS}")
        return v


class ChaveGatewayIn(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    dias_validade: int | None = Field(default=None, ge=1, le=3650)


class ChaveGatewayOut(BaseModel):
    id: int
    nome: str
    prefixo: str
    ativa: bool
    criada_em: dt.datetime
    expira_em: dt.datetime | None
    ultima_utilizacao: dt.datetime | None


class ChaveGatewayCriadaOut(ChaveGatewayOut):
    """Resposta da criacao. Unica vez em que a chave completa e exibida."""

    chave: str = Field(repr=False)


TokenOut.model_rebuild()
