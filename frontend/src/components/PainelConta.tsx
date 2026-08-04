import { useEffect, useState } from "react";
import { api, ErroApi } from "../api";
import type { ChaveGateway, Usuario } from "../types";
import { PainelEquipe } from "./PainelEquipe";
import { PainelNotificacoes } from "./PainelNotificacoes";

interface Props {
  usuario: Usuario;
  onSair: () => void;
}

const ROTULO_PAPEL: Record<Usuario["papel"], string> = {
  dono: "Dono",
  operador: "Operador",
  leitura: "Somente leitura",
};

export function PainelConta({ usuario, onSair }: Props) {
  const [senhaAtual, setSenhaAtual] = useState("");
  const [senhaNova, setSenhaNova] = useState("");
  const [mensagem, setMensagem] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const [chaves, setChaves] = useState<ChaveGateway[]>([]);
  const [chaveNova, setChaveNova] = useState<string | null>(null);
  const [nomeChave, setNomeChave] = useState("");

  const ehDono = usuario.papel === "dono";

  useEffect(() => {
    if (!ehDono) return;
    api.gateways().then(setChaves).catch(() => undefined);
  }, [ehDono]);

  async function trocarSenha() {
    setErro(null);
    setMensagem(null);
    try {
      await api.trocarSenha(senhaAtual, senhaNova);
      setSenhaAtual("");
      setSenhaNova("");
      // O servidor derruba todas as sessões ao trocar a senha — inclusive esta.
      setMensagem("Senha alterada. Entre de novo com a senha nova.");
      setTimeout(onSair, 1800);
    } catch (falha) {
      setErro(falha instanceof ErroApi ? falha.message : String(falha));
    }
  }

  async function criarChave() {
    setErro(null);
    try {
      const criada = await api.criarGateway(nomeChave.trim() || "Gateway");
      setChaveNova(criada.chave);
      setNomeChave("");
      setChaves(await api.gateways());
    } catch (falha) {
      setErro(falha instanceof ErroApi ? falha.message : String(falha));
    }
  }

  async function revogar(id: number) {
    await api.revogarGateway(id).catch(() => undefined);
    setChaves(await api.gateways().catch(() => chaves));
  }

  return (
    <>
      <div className="bloco">
        <div className="bloco-titulo">Conta</div>
        <div className="linha-dado">
          <span>{usuario.nome}</span>
          <span className="etiqueta">{ROTULO_PAPEL[usuario.papel]}</span>
        </div>
        <div className="dica">{usuario.email}</div>
        <button className="botao" onClick={onSair}>
          Sair
        </button>
      </div>

      <div className="bloco">
        <div className="bloco-titulo">Trocar senha</div>
        <input
          className="campo"
          type="password"
          placeholder="Senha atual"
          autoComplete="current-password"
          value={senhaAtual}
          onChange={(e) => setSenhaAtual(e.target.value)}
        />
        <input
          className="campo"
          type="password"
          placeholder="Senha nova (mín. 12 caracteres)"
          autoComplete="new-password"
          value={senhaNova}
          onChange={(e) => setSenhaNova(e.target.value)}
        />
        <button
          className="botao"
          onClick={trocarSenha}
          disabled={!senhaAtual || senhaNova.length < 12}
        >
          Alterar
        </button>
        <div className="dica">
          Trocar a senha encerra todas as sessões abertas, em todos os aparelhos.
        </div>
      </div>

      <PainelNotificacoes />

      {ehDono && <PainelEquipe eu={usuario} />}

      {ehDono && (
        <div className="bloco">
          <div className="bloco-titulo">Chaves de gateway</div>
          <div className="dica">
            Credencial dos dispositivos que enviam telemetria. Independente das contas de
            pessoas e revogável sozinha.
          </div>

          {chaveNova && (
            <div className="chave-nova">
              <strong>Copie agora — não é exibida de novo.</strong>
              <code>{chaveNova}</code>
              <button className="botao-mini" onClick={() => setChaveNova(null)}>
                já copiei
              </button>
            </div>
          )}

          {chaves.map((chave) => (
            <div key={chave.id} className="linha-dado">
              <span>
                {chave.nome}
                <span className="dica"> · {chave.prefixo}</span>
              </span>
              {chave.ativa ? (
                <button className="botao-mini" onClick={() => revogar(chave.id)}>
                  revogar
                </button>
              ) : (
                <span className="etiqueta">revogada</span>
              )}
            </div>
          ))}

          <input
            className="campo"
            placeholder="Nome do novo gateway"
            value={nomeChave}
            onChange={(e) => setNomeChave(e.target.value)}
          />
          <button className="botao" onClick={criarChave}>
            Gerar chave
          </button>
        </div>
      )}

      {mensagem && <div className="erro sucesso">{mensagem}</div>}
      {erro && <div className="erro">{erro}</div>}
    </>
  );
}
