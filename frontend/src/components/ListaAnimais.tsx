import type { Animal } from "../types";
import { CORES_STATUS, ROTULOS_STATUS } from "../types";

interface Props {
  animais: Animal[];
  selecionado: Animal | null;
  onSelecionar: (animal: Animal) => void;
}

/** Ordem: quem tem problema primeiro. O produtor abre o app para ver o que deu errado. */
const PESO: Record<Animal["status"], number> = {
  fora_da_area: 0,
  imovel: 1,
  sem_sinal: 2,
  ok: 3,
};

function descricao(animal: Animal): string {
  if (animal.status === "fora_da_area") {
    return `${animal.distancia_pasto_m.toFixed(0)} m além da divisa`;
  }
  if (animal.status === "sem_sinal" && animal.segundos_sem_contato !== null) {
    const minutos = Math.floor(animal.segundos_sem_contato / 60);
    return minutos > 0
      ? `sem contato há ${minutos} min`
      : `sem contato há ${animal.segundos_sem_contato}s`;
  }
  if (animal.status === "imovel") return "sem movimento";
  return `${animal.categoria} · ${animal.pasto_nome ?? "sem pasto"}`;
}

export function ListaAnimais({ animais, selecionado, onSelecionar }: Props) {
  const ordenados = [...animais].sort(
    (a, b) => PESO[a.status] - PESO[b.status] || a.nome.localeCompare(b.nome),
  );

  if (!animais.length) {
    return <div className="vazio">Nenhum animal cadastrado.</div>;
  }

  return (
    <div>
      {ordenados.map((animal) => (
        <button
          key={animal.id}
          className={`linha-animal ${selecionado?.id === animal.id ? "ativa" : ""}`}
          onClick={() => onSelecionar(animal)}
          aria-label={`${animal.nome} — ${ROTULOS_STATUS[animal.status]}`}
        >
          <span className="ponto-status" style={{ background: CORES_STATUS[animal.status] }} />
          <span className="linha-animal-info">
            <span className="linha-animal-nome">{animal.nome}</span>
            <span className="linha-animal-meta"> · {animal.brinco.slice(-6)}</span>
            <span className="linha-animal-meta" style={{ display: "block" }}>
              {descricao(animal)}
            </span>
          </span>
          <span className={`bateria ${animal.bateria_pct < 20 ? "baixa" : ""}`}>
            {animal.bateria_pct}%
          </span>
        </button>
      ))}
    </div>
  );
}
