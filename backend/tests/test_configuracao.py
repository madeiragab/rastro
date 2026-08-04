"""Travas de configuração de produção.

Estas verificações existem porque erro de configuração é silencioso: a
aplicação sobe, parece funcionar, e só se descobre o problema quando alguém
forja um token ou quando o link de redefinição nunca chega.

Os testes montam `Settings` diretamente, sem tocar no ambiente do processo, para
não contaminar as outras sessões de teste.
"""

from __future__ import annotations

import pytest

from app.config import SEGREDO_DEV, Settings

# Configuração de produção completa e válida, usada como base. Cada teste
# estraga exatamente um campo — assim a falha aponta o campo, não o conjunto.
VALIDA = {
    "ambiente": "producao",
    "secret_key": "k" * 48,
    "cookie_secure": True,
    "simulator_enabled": False,
    "smtp_host": "smtp.exemplo.com",
    "app_url": "https://rastro.exemplo.com",
    "cors_origins": ["https://rastro.exemplo.com"],
}


def test_producao_valida_sobe():
    config = Settings(**VALIDA)
    assert config.em_producao is True


def test_desenvolvimento_aceita_tudo_frouxo():
    """O aviso no log basta: travar o desenvolvimento não protege ninguém."""
    config = Settings(ambiente="desenvolvimento", secret_key=SEGREDO_DEV)
    assert config.em_producao is False


@pytest.mark.parametrize(
    "campo,valor,motivo",
    [
        ("secret_key", SEGREDO_DEV, "segredo de exemplo permite forjar token de administrador"),
        ("secret_key", "curto-demais", "chave curta enfraquece a assinatura HMAC"),
        ("cookie_secure", False, "cookie de sessão viajaria em texto claro"),
        ("simulator_enabled", True, "simulador escreveria posição falsa em produção"),
        ("smtp_host", "", "sem e-mail, quem esquece a senha perde a conta"),
        ("app_url", "http://rastro.exemplo.com", "link de redefinição sairia por http"),
    ],
)
def test_recusa_configuracao_insegura(campo, valor, motivo):
    with pytest.raises(RuntimeError):
        Settings(**{**VALIDA, campo: valor})


def test_recusa_cors_http_nao_local():
    with pytest.raises(RuntimeError):
        Settings(**{**VALIDA, "cors_origins": ["http://rastro.exemplo.com"]})


def test_aceita_cors_localhost_em_producao():
    """Origem local não é vetor: o navegador de outra máquina não a alcança."""
    config = Settings(**{**VALIDA, "cors_origins": ["https://rastro.exemplo.com", "http://localhost:5173"]})
    assert config.em_producao is True
