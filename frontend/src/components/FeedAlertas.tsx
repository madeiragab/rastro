import type { Alerta } from "../types";

interface Props {
  alertas: Alerta[];
  onResolver: (alertaId: number) => void;
  onIrPara: (animalId: number) => void;
}

const ROTULO_TIPO: Record<Alerta["tipo"], string> = {
  fora_da_area: "Fora da área",
  imovel: "Sem movimento",
  sem_sinal: "Sem sinal",
};

function haQuantoTempo(iso: string): string {
  const segundos = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (segundos < 60) return `há ${segundos}s`;
  const minutos = Math.floor(segundos / 60);
  if (minutos < 60) return `há ${minutos} min`;
  return `há ${Math.floor(minutos / 60)} h`;
}

export function FeedAlertas({ alertas, onResolver, onIrPara }: Props) {
  if (!alertas.length) {
    return (
      <div className="vazio">
        Nenhum alerta aberto.
        <br />
        Todo o rebanho dentro da área.
      </div>
    );
  }

  return (
    <div>
      {alertas.map((alerta) => (
        <div key={alerta.id} className={`alerta ${alerta.severidade}`}>
          <div className="alerta-corpo">
            <div className="alerta-tipo">{ROTULO_TIPO[alerta.tipo]}</div>
            <div className="alerta-msg">{alerta.mensagem}</div>
            <div className="alerta-rodape">
              <span>{haQuantoTempo(alerta.criado_em)}</span>
              <button className="botao-mini" onClick={() => onIrPara(alerta.animal_id)}>
                ver no mapa
              </button>
              <button className="botao-mini" onClick={() => onResolver(alerta.id)}>
                resolver
              </button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
