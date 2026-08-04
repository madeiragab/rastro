import { useState, type FormEvent } from "react";
import { api, ErroApi } from "../api";
import type { Usuario } from "../types";

interface Props {
  onEntrou: (usuario: Usuario) => void;
}

export function TelaLogin({ onEntrou }: Props) {
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (enviando) return;

    setEnviando(true);
    setErro(null);
    try {
      const resposta = await api.login(email.trim(), senha);
      onEntrou(resposta.usuario);
    } catch (falha) {
      // A mensagem do servidor já é genérica de propósito ("e-mail ou senha
      // incorretos"): não dizer qual dos dois errou é o que impede descobrir
      // quais e-mails existem.
      setErro(
        falha instanceof ErroApi
          ? falha.message
          : "Não foi possível conectar ao servidor.",
      );
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="tela-login">
      <form className="cartao-login" onSubmit={enviar}>
        <div className="login-marca">
          Rastro<span>.</span>
        </div>
        <p className="login-sub">Rastreamento e geocerca de rebanho</p>

        <label className="rotulo" htmlFor="email">
          E-mail
        </label>
        <input
          id="email"
          className="campo"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />

        <label className="rotulo" htmlFor="senha">
          Senha
        </label>
        <input
          id="senha"
          className="campo"
          type="password"
          autoComplete="current-password"
          required
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
        />

        {erro && (
          <div className="erro" style={{ margin: 0 }} role="alert">
            {erro}
          </div>
        )}

        <button className="botao primario" type="submit" disabled={enviando}>
          {enviando ? "Entrando..." : "Entrar"}
        </button>

        <p className="dica" style={{ textAlign: "center" }}>
          As credenciais iniciais aparecem no log da API na primeira subida.
        </p>
      </form>
    </div>
  );
}
