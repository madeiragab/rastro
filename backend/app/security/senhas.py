"""Hash e politica de senha.

Argon2id, com custo de memoria configuravel. Escolhido no lugar do bcrypt por
ser o vencedor da Password Hashing Competition e a recomendacao atual do OWASP:
o custo de memoria e o que torna o ataque com GPU e ASIC caro, e o bcrypt usa
memoria fixa e pequena.

A politica de senha segue o NIST SP 800-63B: comprimento minimo alto e lista de
bloqueio, sem regras de composicao. Exigir "uma maiuscula e um simbolo" produz
`Senha@123` -- previsivel e curta.
"""

from __future__ import annotations

import unicodedata

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.config import settings

_hasher = PasswordHasher(
    time_cost=settings.argon2_iteracoes,
    memory_cost=settings.argon2_memoria_kib,
    parallelism=settings.argon2_paralelismo,
    hash_len=32,
    salt_len=16,
)

# Amostra de senhas muito comuns e de termos obvios deste dominio. Em producao,
# trocar por uma lista maior (por exemplo o top 100k do Have I Been Pwned) ou
# consultar a API de senhas vazadas com k-anonimato.
BLOQUEADAS = {
    "123456", "123456789", "12345678", "qwerty", "password", "senha",
    "senha123", "admin", "administrador", "12345", "1234567890", "iloveyou",
    "abc123", "111111", "123123", "brasil", "flamengo", "corinthians",
    "rastro", "rastro123", "fazenda", "fazenda123", "boi", "gado", "pasto",
    "produtor", "senhasegura", "mudar123", "trocar123",
}


class SenhaFraca(ValueError):
    """Levantada quando a senha nao atende a politica."""


def _normalizar(senha: str) -> str:
    """Normaliza para NFKC.

    Sem isso, a mesma senha digitada com acentos compostos de formas diferentes
    (teclado do celular x teclado fisico) gera hashes distintos e o usuario e
    trancado para fora sem entender por que.
    """
    return unicodedata.normalize("NFKC", senha)


def validar_forca(senha: str, email: str = "", nome: str = "") -> None:
    """Valida a politica. Levanta `SenhaFraca` com uma mensagem acionavel."""
    senha = _normalizar(senha)

    if len(senha) < settings.senha_tamanho_minimo:
        raise SenhaFraca(
            f"A senha precisa ter pelo menos {settings.senha_tamanho_minimo} caracteres."
        )

    # 128 e o limite do argon2-cffi para entrada sem truncamento problematico;
    # alem disso, senhas gigantes viram vetor de negacao de servico no hash.
    if len(senha) > 128:
        raise SenhaFraca("A senha pode ter no maximo 128 caracteres.")

    minuscula = senha.lower()

    if minuscula in BLOQUEADAS:
        raise SenhaFraca("Essa senha e comum demais. Escolha outra.")

    if email and minuscula == email.lower():
        raise SenhaFraca("A senha nao pode ser igual ao e-mail.")

    if email:
        usuario_do_email = email.split("@", 1)[0].lower()
        if len(usuario_do_email) >= 4 and usuario_do_email in minuscula:
            raise SenhaFraca("A senha nao pode conter o seu e-mail.")

    if nome:
        for parte in nome.lower().split():
            if len(parte) >= 4 and parte in minuscula:
                raise SenhaFraca("A senha nao pode conter o seu nome.")

    if len(set(senha)) < 5:
        raise SenhaFraca("A senha tem repeticao demais. Use mais variedade.")


def gerar_hash(senha: str) -> str:
    return _hasher.hash(_normalizar(senha))


def verificar(senha: str, hash_armazenado: str) -> tuple[bool, str | None]:
    """Confere a senha.

    Devolve `(confere, novo_hash)`. `novo_hash` vem preenchido quando os
    parametros de custo mudaram desde o cadastro -- o chamador deve gravar o
    valor novo, aproveitando que a senha em claro esta disponivel neste
    exato momento e em nenhum outro.
    """
    entrada = _normalizar(senha)
    try:
        _hasher.verify(hash_armazenado, entrada)
    except (VerifyMismatchError, InvalidHashError):
        return False, None
    except Exception:  # noqa: BLE001 - hash corrompido nao deve derrubar o login
        return False, None

    if _hasher.check_needs_rehash(hash_armazenado):
        return True, _hasher.hash(entrada)

    return True, None


# Hash descartavel usado para gastar o mesmo tempo quando o e-mail nao existe.
# Sem isso, o tempo de resposta denuncia quais e-mails estao cadastrados.
_HASH_ISCA = _hasher.hash("isca-para-tempo-constante")


def consumir_tempo_de_hash() -> None:
    """Simula a verificacao de senha para uniformizar o tempo de resposta."""
    try:
        _hasher.verify(_HASH_ISCA, "valor-que-nunca-confere")
    except Exception:  # noqa: BLE001
        pass
