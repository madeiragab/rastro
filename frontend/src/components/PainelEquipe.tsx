import { useEffect, useState } from "react";
import { api, ErroApi } from "../api";
import type { Papel, Usuario } from "../types";

const ROTULO_PAPEL: Record<Papel, string> = {
  dono: "Dono",
  operador: "Operador",
  leitura: "Leitura",
};

const PAPEIS: Papel[] = ["leitura", "operador", "dono"];

export function PainelEquipe({ eu }: { eu: Usuario }) {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  const [abrindo, setAbrindo] = useState(false);
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [papel, setPapel] = useState<Papel>("operador");
  const [senhaNova, setSenhaNova] = useState<{ email: string; senha: string } | null>(null);

  async function recarregar() {
    try {
      setUsuarios(await api.usuarios());
    } catch (falha) {
      setErro(falha instanceof ErroApi ? falha.message : String(falha));
    }
  }

  useEffect(() => {
    recarregar();
  }, []);

  async function criar() {
    setErro(null);
    try {
      const criado = await api.criarUsuario(email.trim(), nome.trim(), papel);
      // A senha inicial existe só nesta resposta. Some da tela quando o dono
      // confirmar que anotou.
      setSenhaNova({ email: criado.email, senha: criado.senha_inicial });
      setNome("");
      setEmail("");
      setAbrindo(false);
      await recarregar();
    } catch (falha) {
      setErro(falha instanceof ErroApi ? falha.message : String(falha));
    }
  }

  async function alterar(id: number, mudanca: { papel?: Papel; ativo?: boolean }) {
    setErro(null);
    try {
      await api.alterarUsuario(id, mudanca);
      await recarregar();
    } catch (falha) {
      setErro(falha instanceof ErroApi ? falha.message : String(falha));
    }
  }

  return (
    <div className="bloco">
      <div className="bloco-titulo">Equipe</div>
      <div className="dica">
        Quem entra na fazenda e com qual permissão. Leitura vê tudo mas não altera nada;
        operador mexe em pastos; dono ainda gerencia equipe e chaves.
      </div>

      {senhaNova && (
        <div className="chave-nova">
          <strong>Senha inicial de {senhaNova.email} — copie agora.</strong>
          <code>{senhaNova.senha}</code>
          <span className="dica">
            Não é exibida de novo. Peça para trocarem no primeiro acesso.
          </span>
          <button className="botao-mini" onClick={() => setSenhaNova(null)}>
            já copiei
          </button>
        </div>
      )}

      {usuarios.map((u) => {
        const souEu = u.id === eu.id;
        return (
          <div key={u.id} className="linha-equipe">
            <div className="linha-equipe-info">
              <span className="linha-animal-nome">
                {u.nome}
                {souEu && <span className="etiqueta" style={{ marginLeft: 6 }}>você</span>}
              </span>
              <span className="linha-animal-meta" style={{ display: "block" }}>
                {u.email}
              </span>
            </div>

            <select
              className="campo campo-select"
              value={u.papel}
              disabled={souEu}
              onChange={(e) => alterar(u.id, { papel: e.target.value as Papel })}
              aria-label={`Papel de ${u.nome}`}
            >
              {PAPEIS.map((p) => (
                <option key={p} value={p}>
                  {ROTULO_PAPEL[p]}
                </option>
              ))}
            </select>

            <button
              className="botao-mini"
              disabled={souEu}
              onClick={() => alterar(u.id, { ativo: !u.ativo })}
              title={souEu ? "Você não pode se desativar" : ""}
            >
              {u.ativo ? "desativar" : "reativar"}
            </button>
          </div>
        );
      })}

      {!abrindo ? (
        <button className="botao" onClick={() => setAbrindo(true)}>
          Adicionar pessoa
        </button>
      ) : (
        <>
          <input
            className="campo"
            placeholder="Nome"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
          />
          <input
            className="campo"
            type="email"
            inputMode="email"
            autoCapitalize="none"
            placeholder="E-mail"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <select
            className="campo campo-select"
            value={papel}
            onChange={(e) => setPapel(e.target.value as Papel)}
            aria-label="Papel do novo usuário"
          >
            {PAPEIS.map((p) => (
              <option key={p} value={p}>
                {ROTULO_PAPEL[p]}
              </option>
            ))}
          </select>
          <div className="painel-desenho-linha">
            <button className="botao" style={{ flex: 1 }} onClick={() => setAbrindo(false)}>
              Cancelar
            </button>
            <button
              className="botao primario"
              style={{ flex: 1 }}
              onClick={criar}
              disabled={!nome.trim() || !email.trim()}
            >
              Criar
            </button>
          </div>
        </>
      )}

      {erro && <div className="erro">{erro}</div>}
    </div>
  );
}
