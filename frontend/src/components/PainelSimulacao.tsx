import type { Animal, Comportamento } from "../types";

interface Props {
  selecionado: Animal | null;
  onCenario: (comportamento: Comportamento) => void;
  onReiniciar: () => void;
}

const CENARIOS: { chave: Comportamento; rotulo: string; efeito: string }[] = [
  { chave: "normal", rotulo: "Pastando", efeito: "volta ao normal" },
  { chave: "fugindo", rotulo: "Fugir do pasto", efeito: "alerta em ~25 s" },
  { chave: "imovel", rotulo: "Ficar parado", efeito: "alerta em 90 s" },
  { chave: "offline", rotulo: "Perder sinal", efeito: "alerta em 60 s" },
];

export function PainelSimulacao({ selecionado, onCenario, onReiniciar }: Props) {
  return (
    <>
      <div className="bloco">
        <div className="bloco-titulo">Forçar cenário</div>
        <div className="dica">
          {selecionado ? (
            <>
              Aplicado em <strong style={{ color: "var(--texto)" }}>{selecionado.nome}</strong>.
            </>
          ) : (
            "Selecione um animal na lista ou no mapa."
          )}
        </div>
        <div className="grade-cenarios">
          {CENARIOS.map((cenario) => (
            <button
              key={cenario.chave}
              className={`botao-cenario ${
                selecionado?.sim_comportamento === cenario.chave ? "ativo" : ""
              }`}
              disabled={!selecionado}
              onClick={() => onCenario(cenario.chave)}
            >
              {cenario.rotulo}
              <div className="dica" style={{ fontSize: 11, marginTop: 2 }}>
                {cenario.efeito}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="bloco">
        <button className="botao" onClick={onReiniciar}>
          Reiniciar simulação
        </button>
        <div className="dica">
          Os limiares estão comprimidos para demonstração. Em campo: "parado" leva 4 h e o brinco
          reporta a cada 30 min.
        </div>
      </div>
    </>
  );
}
