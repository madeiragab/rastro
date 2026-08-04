"""Modelo de dados do Rastro.

Geometrias em SRID 4326 (lat/lon). Distancias em metros sao calculadas
convertendo para `geography`, o que evita erro de projecao.
"""

from __future__ import annotations

import datetime as dt

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def agora() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# --------------------------------------------------------------------- enums
# Strings simples em vez de Enum do banco: o conjunto ainda vai mudar durante
# o MVP e ALTER TYPE em Postgres e chato.

STATUS_OK = "ok"
STATUS_FORA = "fora_da_area"
STATUS_IMOVEL = "imovel"
STATUS_OFFLINE = "sem_sinal"

ALERTA_FORA = "fora_da_area"
ALERTA_IMOVEL = "imovel"
ALERTA_SEM_SINAL = "sem_sinal"

COMPORTAMENTOS = ("normal", "fugindo", "imovel", "offline")


class Fazenda(Base):
    __tablename__ = "fazendas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    proprietario: Mapped[str] = mapped_column(String(120))
    municipio: Mapped[str] = mapped_column(String(120), default="")
    uf: Mapped[str] = mapped_column(String(2), default="MG")
    criada_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora)

    pastos: Mapped[list[Pasto]] = relationship(back_populates="fazenda", cascade="all, delete-orphan")
    animais: Mapped[list[Animal]] = relationship(back_populates="fazenda", cascade="all, delete-orphan")


class Pasto(Base):
    """Area demarcada pelo produtor no mapa."""

    __tablename__ = "pastos"

    id: Mapped[int] = mapped_column(primary_key=True)
    fazenda_id: Mapped[int] = mapped_column(ForeignKey("fazendas.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    cor: Mapped[str] = mapped_column(String(9), default="#2E7D53")
    geom: Mapped[object] = mapped_column(Geometry("POLYGON", srid=4326))
    buffer_m: Mapped[float] = mapped_column(Float, default=25.0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora)

    fazenda: Mapped[Fazenda] = relationship(back_populates="pastos")
    animais: Mapped[list[Animal]] = relationship(back_populates="pasto")


class Animal(Base):
    __tablename__ = "animais"

    id: Mapped[int] = mapped_column(primary_key=True)
    fazenda_id: Mapped[int] = mapped_column(ForeignKey("fazendas.id", ondelete="CASCADE"), index=True)
    pasto_id: Mapped[int | None] = mapped_column(ForeignKey("pastos.id", ondelete="SET NULL"), index=True)

    # Numeracao no padrao do PNIB: 15 digitos, prefixo 076 (codigo do Brasil).
    brinco: Mapped[str] = mapped_column(String(15), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(80))
    categoria: Mapped[str] = mapped_column(String(40), default="Novilha")

    status: Mapped[str] = mapped_column(String(20), default=STATUS_OK, index=True)
    bateria_pct: Mapped[int] = mapped_column(Integer, default=100)

    # Ultima posicao denormalizada: o mapa precisa dela a cada poll e nao vale
    # varrer a tabela de posicoes toda vez.
    ultima_geom: Mapped[object | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    ultimo_contato: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    distancia_pasto_m: Mapped[float] = mapped_column(Float, default=0.0)

    # Estado do motor de alertas.
    leituras_fora: Mapped[int] = mapped_column(Integer, default=0)
    imovel_desde: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Estado do simulador (nao existiria no produto com hardware real).
    sim_comportamento: Mapped[str] = mapped_column(String(20), default="normal")
    sim_rumo: Mapped[float] = mapped_column(Float, default=0.0)

    fazenda: Mapped[Fazenda] = relationship(back_populates="animais")
    pasto: Mapped[Pasto | None] = relationship(back_populates="animais")


class Posicao(Base):
    __tablename__ = "posicoes"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animais.id", ondelete="CASCADE"), index=True)
    geom: Mapped[object] = mapped_column(Geometry("POINT", srid=4326))
    registrada_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)

    # Indice de atividade 0..1 vindo do acelerometro do brinco. Sem ele o
    # alerta de imobilidade e inutil: bovino deitado ruminando fica estatico.
    atividade: Mapped[float] = mapped_column(Float, default=0.5)
    bateria_pct: Mapped[int] = mapped_column(Integer, default=100)


class Alerta(Base):
    __tablename__ = "alertas"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animais.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(30), index=True)
    severidade: Mapped[str] = mapped_column(String(10), default="alta")
    mensagem: Mapped[str] = mapped_column(Text)
    geom: Mapped[object | None] = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)
    resolvido_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Marca do envio de push. Fica no alerta, e nao numa fila em memoria, para
    # que uma reinicializacao no meio do caminho nao perca nem duplique aviso.
    notificado_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    animal: Mapped[Animal] = relationship()


# ==========================================================================
# Autenticacao e auditoria
# ==========================================================================

PAPEL_DONO = "dono"
PAPEL_OPERADOR = "operador"
PAPEL_LEITURA = "leitura"

PAPEIS = (PAPEL_DONO, PAPEL_OPERADOR, PAPEL_LEITURA)

# Ordem de privilegio. Usada pela dependencia `exige_papel`.
NIVEL_PAPEL = {PAPEL_LEITURA: 0, PAPEL_OPERADOR: 1, PAPEL_DONO: 2}


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    fazenda_id: Mapped[int | None] = mapped_column(
        ForeignKey("fazendas.id", ondelete="CASCADE"), index=True, nullable=True
    )

    # Guardado sempre em minusculas, para que a unicidade nao dependa de
    # como o usuario digitou o e-mail no cadastro.
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(120))

    # Hash Argon2id. Contem o algoritmo e os parametros embutidos, o que
    # permite reidratar o hash quando os parametros de custo mudarem.
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[str] = mapped_column(String(20), default=PAPEL_OPERADOR)

    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    senha_alterada_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    ultimo_login_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Incrementado a cada troca de senha. Vai como claim no access token, e a
    # divergencia invalida o token na hora.
    #
    # Substitui a comparacao de `iat` com `senha_alterada_em`: o `iat` do JWT
    # tem resolucao de 1 segundo, entao trocar a senha no mesmo segundo do
    # login deixava o token anterior valido -- exatamente a janela que quem
    # troca a senha por suspeita de invasao quer fechar.
    token_versao: Mapped[int] = mapped_column(Integer, default=0)

    fazenda: Mapped[Fazenda | None] = relationship()


class SessaoRefresh(Base):
    """Refresh token opaco, com rotacao e deteccao de reuso.

    Guardamos apenas o SHA-256 do token. Um dump do banco nao permite se passar
    por ninguem. SHA-256 e suficiente aqui (diferente de senha) porque o token
    tem 256 bits de entropia -- nao ha dicionario a percorrer.

    `familia` agrupa toda a cadeia de rotacoes de um mesmo login. Se um token ja
    usado reaparecer, assume-se roubo e a familia inteira e revogada.
    """

    __tablename__ = "sessoes_refresh"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)

    familia: Mapped[str] = mapped_column(String(64), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    criada_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    expira_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    usada_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revogada_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Contexto para auditoria e para o usuario reconhecer sessoes suspeitas.
    ip: Mapped[str] = mapped_column(String(45), default="")
    user_agent: Mapped[str] = mapped_column(String(255), default="")

    usuario: Mapped[Usuario] = relationship()


class ChaveGateway(Base):
    """Credencial de dispositivo, para o gateway enviar telemetria.

    Gateway nao faz login com e-mail e senha: ele carrega uma chave longa,
    trocavel e revogavel de forma independente das contas humanas. A chave e
    mostrada uma unica vez, na criacao, e guardada como hash Argon2id.

    O prefixo publico permite localizar a linha sem varrer a tabela inteira
    verificando hashes -- comparar Argon2 de todas as chaves a cada requisicao
    de telemetria seria caro de proposito.
    """

    __tablename__ = "chaves_gateway"

    id: Mapped[int] = mapped_column(primary_key=True)
    fazenda_id: Mapped[int] = mapped_column(ForeignKey("fazendas.id", ondelete="CASCADE"), index=True)

    nome: Mapped[str] = mapped_column(String(120))
    prefixo: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    chave_hash: Mapped[str] = mapped_column(String(255))

    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criada_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    expira_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ultima_utilizacao: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revogada_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    fazenda: Mapped[Fazenda] = relationship()


class InscricaoPush(Base):
    """Endpoint de push de um navegador.

    O navegador entrega um `endpoint` (URL no servico de push do fabricante) e
    duas chaves usadas para cifrar a mensagem. O servidor nao consegue ler o
    conteudo de volta nem enderecar o aparelho por outro caminho.

    Uma pessoa tem uma inscricao por navegador e por aparelho, dai o endpoint
    ser a chave de unicidade em vez do usuario.
    """

    __tablename__ = "inscricoes_push"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)

    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    chave_p256dh: Mapped[str] = mapped_column(String(255))
    chave_auth: Mapped[str] = mapped_column(String(255))
    user_agent: Mapped[str] = mapped_column(String(255), default="")

    criada_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora)
    ultimo_envio: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    falhas: Mapped[int] = mapped_column(Integer, default=0)

    usuario: Mapped[Usuario] = relationship()


class ConfiguracaoPush(Base):
    """Par de chaves VAPID da instalacao, com uma linha so.

    Fica no banco, e nao em variavel de ambiente, porque precisa sobreviver a
    reinicializacao: trocar a chave invalida todas as inscricoes existentes, e
    os aparelhos so descobririam isso deixando de receber aviso -- falha
    silenciosa, que e o pior tipo num sistema de alerta.
    """

    __tablename__ = "configuracao_push"

    id: Mapped[int] = mapped_column(primary_key=True)
    chave_privada_pem: Mapped[str] = mapped_column(Text)
    chave_publica_app: Mapped[str] = mapped_column(Text)
    criada_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora)


class TokenResetSenha(Base):
    """Token de uso unico para redefinir senha esquecida.

    Guardado como SHA-256, pelo mesmo motivo do refresh: 256 bits aleatorios
    nao tem dicionario a percorrer, entao hash rapido ja impede que um dump do
    banco vire redefinicao de senha alheia.

    Vida curta de proposito. Um link de redefinicao e uma credencial completa
    circulando por e-mail, que e um canal que ninguem controla.
    """

    __tablename__ = "tokens_reset_senha"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)
    expira_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    usado_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip: Mapped[str] = mapped_column(String(45), default="")

    usuario: Mapped[Usuario] = relationship()


class TentativaLogin(Base):
    """Registro de tentativas, para bloqueio progressivo por e-mail e por IP."""

    __tablename__ = "tentativas_login"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), default="")
    ip: Mapped[str] = mapped_column(String(45), default="")
    sucesso: Mapped[bool] = mapped_column(Boolean, default=False)
    criada_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora)


Index("ix_tentativas_email_data", TentativaLogin.email, TentativaLogin.criada_em)
Index("ix_tentativas_ip_data", TentativaLogin.ip, TentativaLogin.criada_em)


class EventoAuditoria(Base):
    """Trilha de auditoria de acoes sensiveis.

    Append-only por convencao: nenhuma rota atualiza ou apaga linhas daqui.
    """

    __tablename__ = "eventos_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), index=True, nullable=True
    )
    acao: Mapped[str] = mapped_column(String(60), index=True)
    detalhe: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(45), default="")
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=agora, index=True)
