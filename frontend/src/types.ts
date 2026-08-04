export type StatusAnimal = "ok" | "fora_da_area" | "imovel" | "sem_sinal";
export type Comportamento = "normal" | "fugindo" | "imovel" | "offline";

export interface Fazenda {
  id: number;
  nome: string;
  proprietario: string;
  municipio: string;
  uf: string;
}

export interface Pasto {
  id: number;
  nome: string;
  cor: string;
  buffer_m: number;
  /** Anel externo como [lat, lon]. */
  pontos: [number, number][];
  area_ha: number;
  total_animais: number;
}

export interface Animal {
  id: number;
  brinco: string;
  nome: string;
  categoria: string;
  status: StatusAnimal;
  bateria_pct: number;
  lat: number | null;
  lon: number | null;
  ultimo_contato: string | null;
  segundos_sem_contato: number | null;
  distancia_pasto_m: number;
  pasto_id: number | null;
  pasto_nome: string | null;
  sim_comportamento: Comportamento;
}

export interface Posicao {
  lat: number;
  lon: number;
  registrada_em: string;
  atividade: number;
}

export interface Alerta {
  id: number;
  animal_id: number;
  animal_nome: string;
  brinco: string;
  tipo: "fora_da_area" | "imovel" | "sem_sinal";
  severidade: string;
  mensagem: string;
  lat: number | null;
  lon: number | null;
  criado_em: string;
  resolvido_em: string | null;
}

export interface Resumo {
  total_animais: number;
  em_area: number;
  fora_da_area: number;
  imoveis: number;
  sem_sinal: number;
  alertas_abertos: number;
  total_pastos: number;
  area_total_ha: number;
}

export const CORES_STATUS: Record<StatusAnimal, string> = {
  ok: "#2E9E63",
  fora_da_area: "#D64545",
  imovel: "#E0821A",
  sem_sinal: "#7B8794",
};

export const ROTULOS_STATUS: Record<StatusAnimal, string> = {
  ok: "Na área",
  fora_da_area: "Fora da área",
  imovel: "Parado",
  sem_sinal: "Sem sinal",
};
