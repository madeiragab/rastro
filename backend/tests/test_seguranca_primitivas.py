"""Primitivas de segurança, isoladas do HTTP e do banco."""

from __future__ import annotations

import pytest

from app.security import chaves, senhas, tokens


# ------------------------------------------------------------------ senhas
class TestPoliticaDeSenha:
    def test_aceita_senha_longa(self):
        senhas.validar_forca("pasto-do-corrego-2026", email="jose@teste.com", nome="José")

    @pytest.mark.parametrize(
        "ruim",
        [
            "curta1",            # abaixo do mínimo
            "senha123",          # curta e da lista de bloqueio
            "aaaaaaaaaaaaaaaa",  # variedade insuficiente
            "x" * 129,           # longa demais: DoS no custo do hash
        ],
    )
    def test_rejeita(self, ruim):
        with pytest.raises(senhas.SenhaFraca):
            senhas.validar_forca(ruim)

    def test_rejeita_senha_contendo_o_email(self):
        with pytest.raises(senhas.SenhaFraca):
            senhas.validar_forca("jose.rodrigues.2026!", email="rodrigues@fazenda.com")

    def test_rejeita_senha_contendo_o_nome(self):
        with pytest.raises(senhas.SenhaFraca):
            senhas.validar_forca("mimosa-do-pasto-alto", nome="Mimosa Silva")


class TestHashDeSenha:
    def test_usa_argon2id(self):
        assert senhas.gerar_hash("pasto-do-corrego-2026").startswith("$argon2id$")

    def test_hashes_diferentes_para_a_mesma_senha(self):
        """Salt aleatório: dois cadastros com a mesma senha não se parecem."""
        a = senhas.gerar_hash("pasto-do-corrego-2026")
        b = senhas.gerar_hash("pasto-do-corrego-2026")
        assert a != b

    def test_confere_e_nao_confere(self):
        h = senhas.gerar_hash("pasto-do-corrego-2026")
        assert senhas.verificar("pasto-do-corrego-2026", h)[0] is True
        assert senhas.verificar("outra-coisa-qualquer", h)[0] is False

    def test_hash_corrompido_nao_derruba_o_login(self):
        assert senhas.verificar("qualquer-coisa", "isto-nao-e-um-hash")[0] is False

    def test_normalizacao_nfkc(self):
        """A mesma senha em NFC e NFD precisa conferir.

        Sem isso, teclado de celular e teclado físico geram bytes diferentes e
        trancam o usuário para fora sem explicação.
        """
        composta = "senão-vai-ter-problema"      # ã em um code point
        decomposta = "senão-vai-ter-problema"   # a + til
        assert senhas.verificar(decomposta, senhas.gerar_hash(composta))[0] is True


# ------------------------------------------------------------------ tokens
class TestAccessToken:
    def test_claims(self):
        token, ttl = tokens.criar_access_token(7, "dono", 3)
        claims = tokens.ler_access_token(token)

        assert claims["sub"] == "7"
        assert claims["papel"] == "dono"
        assert claims["fazenda"] == 3
        assert claims["tipo"] == tokens.TIPO_ACESSO
        assert ttl == 900

    def test_rejeita_token_adulterado(self):
        token, _ = tokens.criar_access_token(1, "dono", 1)
        with pytest.raises(tokens.TokenInvalido):
            tokens.ler_access_token(token[:-2] + "xy")

    def test_rejeita_alg_none(self):
        """O ataque clássico: trocar o algoritmo para `none` e remover a assinatura."""
        import base64
        import json

        cabecalho = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).rstrip(b"=")
        corpo = base64.urlsafe_b64encode(
            json.dumps({"sub": "1", "papel": "dono", "tipo": "access"}).encode()
        ).rstrip(b"=")
        forjado = f"{cabecalho.decode()}.{corpo.decode()}."

        with pytest.raises(tokens.TokenInvalido):
            tokens.ler_access_token(forjado)

    def test_rejeita_audiencia_errada(self):
        import jwt

        from app.config import settings

        forjado = jwt.encode(
            {
                "sub": "1",
                "tipo": "access",
                "iss": settings.jwt_emissor,
                "aud": "outro-sistema",
                "iat": 0,
                "nbf": 0,
                "exp": 99_999_999_999,
            },
            settings.secret_key,
            algorithm=settings.jwt_algoritmo,
        )
        with pytest.raises(tokens.TokenInvalido):
            tokens.ler_access_token(forjado)

    def test_rejeita_token_expirado(self):
        import jwt

        from app.config import settings

        vencido = jwt.encode(
            {
                "sub": "1",
                "tipo": "access",
                "iss": settings.jwt_emissor,
                "aud": settings.jwt_audiencia,
                "iat": 1_000,
                "nbf": 1_000,
                "exp": 2_000,
            },
            settings.secret_key,
            algorithm=settings.jwt_algoritmo,
        )
        with pytest.raises(tokens.TokenInvalido):
            tokens.ler_access_token(vencido)


class TestRefreshToken:
    def test_hash_estavel_e_token_unico(self):
        a, hash_a = tokens.gerar_refresh_token()
        b, _ = tokens.gerar_refresh_token()

        assert a != b
        assert tokens.hash_refresh(a) == hash_a
        assert len(hash_a) == 64  # SHA-256 em hexadecimal

    def test_token_em_claro_nao_aparece_no_hash(self):
        claro, hash_ = tokens.gerar_refresh_token()
        assert claro not in hash_


class TestCsrf:
    def test_confere(self):
        valor = tokens.gerar_csrf()
        assert tokens.csrf_confere(valor, valor) is True
        assert tokens.csrf_confere(valor, tokens.gerar_csrf()) is False

    def test_vazio_nao_confere(self):
        assert tokens.csrf_confere("", "") is True  # ambos ausentes
        assert tokens.csrf_confere("algo", "") is False


# ------------------------------------------------------------------ chaves
class TestChaveDeGateway:
    def test_formato_e_verificacao(self):
        chave, prefixo, hash_ = chaves.gerar()

        assert chave.startswith("rastro_gw_")
        assert prefixo in chave
        # O segredo nunca é guardado em claro.
        assert chave.split("_")[3] not in hash_

        separada = chaves.separar(chave)
        assert separada is not None
        assert separada[0] == prefixo
        assert chaves.confere(separada[1], hash_) is True

    @pytest.mark.parametrize(
        "invalida",
        ["", "rastro_gw_soprefixo", "outro_prefixo_a_b", "rastro_gw__segredo", "lixo"],
    )
    def test_separar_recusa_malformada(self, invalida):
        assert chaves.separar(invalida) is None

    def test_segredo_errado_nao_confere(self):
        _, _, hash_ = chaves.gerar()
        assert chaves.confere("segredo-que-nao-e-esse", hash_) is False
