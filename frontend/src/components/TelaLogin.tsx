import { useState, type FormEvent } from "react";
import { api, ErroApi } from "../api";
import type { Usuario } from "../types";

interface Props {
  onEntrou: (usuario: Usuario) => void;
}

type Modo = "entrar" | "esqueci";

export function TelaLogin({ onEntrou }: Props) {
  const [modo, setModo] = useState<Modo>("entrar");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  async function entrar(evento: FormEvent) {
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
        falha instanceof ErroApi ? falha.message : "Não foi possível conectar ao servidor.",
      );
    } finally {
      setEnviando(false);
    }
  }

  async function pedirLink(evento: FormEvent) {
    evento.preventDefault();
    if (enviando) return;

    setEnviando(true);
    setErro(null);
    try {
      await api.esqueciSenha(email.trim());
      // O servidor responde igual exista ou não a conta, e a interface repete
      // essa neutralidade: dizer "e-mail não encontrado" aqui transformaria a
      // tela de login num verificador de cadastro.
      setAviso(
        "Se houver conta com esse e-mail, o link de redefinição foi enviado. Ele vale por 30 minutos.",
      );
      setModo("entrar");
    } catch (falha) {
      setErro(falha instanceof ErroApi ? falha.message : "Não foi possível conectar.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="tela-login">
      <form className="cartao-login" onSubmit={modo === "entrar" ? entrar : pedirLink}>
        <div className="login-marca">
          Rastro<span>.</span>
        </div>
        <p className="login-sub">
          {modo === "entrar"
            ? "Rastreamento e geocerca de rebanho"
            : "Recuperar acesso"}
        </p>

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

        {modo === "entrar" && (
          <>
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
          </>
        )}

        {erro && (
          <div className="erro" style={{ margin: 0 }} role="alert">
            {erro}
          </div>
        )}
        {aviso && (
          <div className="erro sucesso" style={{ margin: 0 }} role="status">
            {aviso}
          </div>
        )}

        <button className="botao primario" type="submit" disabled={enviando}>
          {enviando
            ? "Enviando..."
            : modo === "entrar"
              ? "Entrar"
              : "Enviar link de redefinição"}
        </button>

        <button
          type="button"
          className="link-discreto"
          onClick={() => {
            setModo(modo === "entrar" ? "esqueci" : "entrar");
            setErro(null);
            setAviso(null);
          }}
        >
          {modo === "entrar" ? "Esqueci minha senha" : "Voltar para o login"}
        </button>
      </form>
    </div>
  );
}
