"""Chaves de API dos gateways.

O gateway nao tem usuario nem senha: carrega uma chave longa, propria, revogavel
sem mexer nas contas humanas. Formato:

    rastro_gw_<prefixo>_<segredo>
              \\_______/ \\________/
               publico     secreto

O prefixo e gravado em claro e indexado, o segredo so como hash Argon2id.
Sem o prefixo seria preciso verificar o hash de todas as chaves cadastradas a
cada leitura de telemetria -- e o Argon2 e caro de proposito.

Consequencia pratica: a chave completa aparece uma unica vez, no momento da
criacao. Perdeu, gera outra.
"""

from __future__ import annotations

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

PREFIXO_FORMATO = "rastro_gw"

# Custo menor que o das senhas: a chave tem 256 bits de entropia, entao nao ha
# dicionario a percorrer, e a telemetria e o caminho quente da aplicacao.
_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16)


def gerar() -> tuple[str, str, str]:
    """Devolve `(chave_completa, prefixo, hash)`."""
    prefixo = secrets.token_hex(4)          # 8 caracteres, publico
    segredo = secrets.token_urlsafe(32)     # 256 bits, secreto
    chave = f"{PREFIXO_FORMATO}_{prefixo}_{segredo}"
    return chave, prefixo, _hasher.hash(segredo)


def separar(chave: str) -> tuple[str, str] | None:
    """Extrai `(prefixo, segredo)` de uma chave recebida. `None` se malformada.

    O `maxsplit=3` nao e detalhe: `secrets.token_urlsafe` usa o alfabeto
    base64url, que inclui `_`. Sem o limite, todo segredo contendo underscore
    quebrava em partes demais e a chave era recusada para sempre -- cerca de um
    terco das chaves geradas.
    """
    partes = (chave or "").split("_", 3)
    if len(partes) != 4:
        return None
    if f"{partes[0]}_{partes[1]}" != PREFIXO_FORMATO:
        return None
    if not partes[2] or not partes[3]:
        return None
    return partes[2], partes[3]


def confere(segredo: str, hash_armazenado: str) -> bool:
    try:
        _hasher.verify(hash_armazenado, segredo)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:  # noqa: BLE001
        return False


# Hash descartavel, para gastar o mesmo tempo quando o prefixo nao existe.
# Sem isso, o tempo de resposta denuncia quais prefixos estao cadastrados.
_HASH_ISCA = _hasher.hash("isca-para-tempo-constante")


def consumir_tempo() -> None:
    confere("valor-que-nunca-confere", _HASH_ISCA)
