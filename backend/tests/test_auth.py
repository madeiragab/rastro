"""Fluxo de sessão: login, rotação, reuso, logout e troca de senha."""

from __future__ import annotations

from sqlalchemy import select

from app.config import settings
from app.models import SessaoRefresh
from tests.conftest import SENHA_TESTE, auth, entrar


class TestLogin:
    def test_sucesso(self, cliente, dono):
        resposta = cliente.post(
            "/api/auth/login", json={"email": dono.email, "senha": SENHA_TESTE}
        )
        corpo = resposta.json()

        assert resposta.status_code == 200
        assert corpo["usuario"]["email"] == dono.email
        assert corpo["usuario"]["papel"] == "dono"
        assert corpo["expira_em_s"] == settings.access_token_ttl_min * 60

    def test_refresh_nao_vai_no_corpo(self, cliente, dono):
        """Se fosse, o front teria de guardá-lo onde o JavaScript lê."""
        corpo = cliente.post(
            "/api/auth/login", json={"email": dono.email, "senha": SENHA_TESTE}
        ).json()

        assert "refresh" not in str(corpo).lower()

    def test_cookies_de_sessao(self, cliente, dono):
        resposta = cliente.post(
            "/api/auth/login", json={"email": dono.email, "senha": SENHA_TESTE}
        )

        bruto = resposta.headers.get_list("set-cookie")
        refresh = next(c for c in bruto if c.startswith(settings.cookie_refresh_nome))
        csrf = next(c for c in bruto if c.startswith(settings.cookie_csrf_nome))

        assert "HttpOnly" in refresh
        assert "SameSite=strict" in refresh
        assert "Path=/api/auth" in refresh
        # O par do double-submit precisa ser legível pelo JavaScript.
        assert "HttpOnly" not in csrf

    def test_email_normalizado(self, cliente, dono):
        resposta = cliente.post(
            "/api/auth/login", json={"email": "DONO@TESTE.LOCAL", "senha": SENHA_TESTE}
        )
        assert resposta.status_code == 200

    def test_senha_errada(self, cliente, dono):
        resposta = cliente.post(
            "/api/auth/login", json={"email": dono.email, "senha": "senha-que-nao-e-essa"}
        )
        assert resposta.status_code == 401

    def test_mensagem_identica_para_email_inexistente(self, cliente, dono):
        """Enumeração de usuário: as duas respostas precisam ser indistinguíveis."""
        errada = cliente.post(
            "/api/auth/login", json={"email": dono.email, "senha": "senha-que-nao-e-essa"}
        )
        inexistente = cliente.post(
            "/api/auth/login", json={"email": "ninguem@teste.local", "senha": SENHA_TESTE}
        )

        assert errada.status_code == inexistente.status_code == 401
        assert errada.json() == inexistente.json()

    def test_conta_desativada_responde_igual(self, cliente, db, dono):
        dono.ativo = False
        db.commit()

        resposta = cliente.post(
            "/api/auth/login", json={"email": dono.email, "senha": SENHA_TESTE}
        )
        assert resposta.status_code == 401
        assert resposta.json()["detail"] == "e-mail ou senha incorretos"


class TestBloqueio:
    def test_bloqueia_apos_o_limite(self, cliente, dono):
        for _ in range(settings.login_max_tentativas):
            cliente.post("/api/auth/login", json={"email": dono.email, "senha": "errada-mesmo"})

        # Mesmo com a senha certa, agora está bloqueado.
        resposta = cliente.post(
            "/api/auth/login", json={"email": dono.email, "senha": SENHA_TESTE}
        )
        assert resposta.status_code == 429
        assert "Retry-After" in resposta.headers

    def test_bloqueio_vale_para_email_inexistente(self, cliente, dono):
        """Senão o contador denunciaria quais e-mails existem."""
        for _ in range(settings.login_max_tentativas):
            cliente.post("/api/auth/login", json={"email": "fantasma@teste.local", "senha": "x" * 12})

        resposta = cliente.post(
            "/api/auth/login", json={"email": "fantasma@teste.local", "senha": "x" * 12}
        )
        assert resposta.status_code == 429

    def test_sucesso_limpa_o_historico(self, cliente, dono):
        for _ in range(settings.login_max_tentativas - 1):
            cliente.post("/api/auth/login", json={"email": dono.email, "senha": "errada-mesmo"})

        assert cliente.post(
            "/api/auth/login", json={"email": dono.email, "senha": SENHA_TESTE}
        ).status_code == 200

        # Contador zerado: erra de novo e ainda não bloqueia.
        assert cliente.post(
            "/api/auth/login", json={"email": dono.email, "senha": "errada-mesmo"}
        ).status_code == 401


class TestRotacao:
    def _csrf(self, cliente) -> dict[str, str]:
        return {"X-CSRF-Token": cliente.cookies.get(settings.cookie_csrf_nome)}

    def test_refresh_devolve_token_novo(self, cliente, dono):
        primeiro = entrar(cliente, dono.email)
        cookie_antigo = cliente.cookies.get(settings.cookie_refresh_nome)

        resposta = cliente.post("/api/auth/refresh", headers=self._csrf(cliente))

        assert resposta.status_code == 200
        assert resposta.json()["access_token"] != primeiro
        assert cliente.cookies.get(settings.cookie_refresh_nome) != cookie_antigo

    def test_refresh_sem_csrf_e_recusado(self, cliente, dono):
        entrar(cliente, dono.email)
        assert cliente.post("/api/auth/refresh").status_code == 403

    def test_refresh_com_csrf_errado_e_recusado(self, cliente, dono):
        entrar(cliente, dono.email)
        resposta = cliente.post(
            "/api/auth/refresh", headers={"X-CSRF-Token": "valor-inventado"}
        )
        assert resposta.status_code == 403

    def test_reuso_revoga_a_familia(self, cliente, db, dono):
        """O cenário de roubo: o token antigo é usado depois de já ter rodado."""
        entrar(cliente, dono.email)
        roubado = cliente.cookies.get(settings.cookie_refresh_nome)
        csrf = cliente.cookies.get(settings.cookie_csrf_nome)

        # Uso legítimo: rotaciona.
        assert cliente.post("/api/auth/refresh", headers={"X-CSRF-Token": csrf}).status_code == 200

        # O ladrão tenta com a cópia antiga.
        cliente.cookies.set(settings.cookie_refresh_nome, roubado)
        resposta = cliente.post("/api/auth/refresh", headers={"X-CSRF-Token": csrf})

        assert resposta.status_code == 401

        abertas = db.execute(
            select(SessaoRefresh).where(
                SessaoRefresh.usuario_id == dono.id, SessaoRefresh.revogada_em.is_(None)
            )
        ).scalars().all()
        assert abertas == [], "toda a família deveria estar revogada"

    def test_refresh_sem_cookie(self, cliente, dono):
        assert cliente.post("/api/auth/refresh").status_code in (401, 403)


class TestLogout:
    def test_revoga_a_sessao(self, cliente, db, dono):
        entrar(cliente, dono.email)

        assert cliente.post("/api/auth/logout").status_code == 204

        abertas = db.execute(
            select(SessaoRefresh).where(SessaoRefresh.revogada_em.is_(None))
        ).scalars().all()
        assert abertas == []

    def test_funciona_sem_access_token(self, cliente, dono):
        """Logout tem de funcionar com o access já expirado, senão o refresh
        continuaria válido pelo prazo dele."""
        entrar(cliente, dono.email)
        assert cliente.post("/api/auth/logout").status_code == 204


class TestTrocaDeSenha:
    NOVA = "corrego-fundo-da-serra-77"

    def test_troca_e_invalida_o_token_antigo(self, cliente, db, dono):
        token = entrar(cliente, dono.email)

        resposta = cliente.post(
            "/api/auth/senha",
            headers=auth(token),
            json={"senha_atual": SENHA_TESTE, "senha_nova": self.NOVA},
        )
        assert resposta.status_code == 204

        # O access emitido antes da troca precisa parar de valer na hora.
        assert cliente.get("/api/animais", headers=auth(token)).status_code == 401

        # E a senha nova funciona.
        assert cliente.post(
            "/api/auth/login", json={"email": dono.email, "senha": self.NOVA}
        ).status_code == 200

    def test_revoga_todas_as_sessoes(self, cliente, db, dono):
        token = entrar(cliente, dono.email)
        cliente.post(
            "/api/auth/senha",
            headers=auth(token),
            json={"senha_atual": SENHA_TESTE, "senha_nova": self.NOVA},
        )

        abertas = db.execute(
            select(SessaoRefresh).where(SessaoRefresh.revogada_em.is_(None))
        ).scalars().all()
        assert abertas == []

    def test_senha_atual_errada(self, cliente, dono):
        token = entrar(cliente, dono.email)
        resposta = cliente.post(
            "/api/auth/senha",
            headers=auth(token),
            json={"senha_atual": "nao-era-essa", "senha_nova": self.NOVA},
        )
        assert resposta.status_code == 400

    def test_senha_nova_fraca(self, cliente, dono):
        token = entrar(cliente, dono.email)
        resposta = cliente.post(
            "/api/auth/senha",
            headers=auth(token),
            json={"senha_atual": SENHA_TESTE, "senha_nova": "123"},
        )
        assert resposta.status_code == 422


class TestEu:
    def test_devolve_o_usuario(self, cliente, dono):
        token = entrar(cliente, dono.email)
        corpo = cliente.get("/api/auth/eu", headers=auth(token)).json()

        assert corpo["email"] == dono.email
        assert "senha_hash" not in corpo, "o hash nunca pode sair da API"
