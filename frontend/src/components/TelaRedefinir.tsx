import { useState, type FormEvent } from "react";
import { api, ErroApi } from "../api";

interface Props {
  token: string;
  onConcluido: () => void;
}

const MINIMO = 12;

export function TelaRedefinir({ token, onConcluido }: Props) {
  const [senha, setSenha] = useState("");
  const [confirma, setConfirma] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [pronto, setPronto] = useState(false);

  const divergem = confirma.length > 0 && senha !== confirma;
  const podeEnviar = senha.length >= MINIMO && senha === confirma && !enviando;

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (!podeEnviar) return;

    setEnviando(true);
    setErro(null);
    try {
      await api.redefinirSenha(token, senha);
      setPronto(true);
    } catch (falha) {
      setErro(
        falha instanceof ErroApi
          ? falha.message
          : "Não foi possível redefinir. Peça um link novo.",
      );
    } finally {
      setEnviando(false);
    }
  }

  if (pronto) {
    return (
      <div className="tela-login">
        <div className="cartao-login">
          <div className="login-marca">
            Rastro<span>.</span>
          </div>
          <div className="erro sucesso" style={{ margin: 0 }} role="status">
            Senha redefinida. Todas as sessões abertas foram encerradas — entre de novo
            com a senha nova.
          </div>
          <button className="botao primario" onClick={onConcluido}>
            Ir para o login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="tela-login">
      <form className="cartao-login" onSubmit={enviar}>
        <div className="login-marca">
          Rastro<span>.</span>
        </div>
        <p className="login-sub">Escolha uma senha nova</p>

        <label className="rotulo" htmlFor="nova">
          Senha nova
        </label>
        <input
          id="nova"
          className="campo"
          type="password"
          autoComplete="new-password"
          required
          value={senha}
          onChange={(e) => setSenha(e.target.value)}
        />

        <label className="rotulo" htmlFor="confirma">
          Repita a senha
        </label>
        <input
          id="confirma"
          className="campo"
          type="password"
          autoComplete="new-password"
          required
          value={confirma}
          onChange={(e) => setConfirma(e.target.value)}
        />

        <div className="dica">
          Mínimo de {MINIMO} caracteres. Uma frase que só você usa vale mais que um
          punhado de símbolos.
        </div>

        {divergem && (
          <div className="erro" style={{ margin: 0 }} role="alert">
            As senhas não conferem.
          </div>
        )}
        {erro && (
          <div className="erro" style={{ margin: 0 }} role="alert">
            {erro}
          </div>
        )}

        <button className="botao primario" type="submit" disabled={!podeEnviar}>
          {enviando ? "Salvando..." : "Redefinir senha"}
        </button>

        <button type="button" className="link-discreto" onClick={onConcluido}>
          Cancelar
        </button>
      </form>
    </div>
  );
}
