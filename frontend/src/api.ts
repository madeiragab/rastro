import type { Alerta, Animal, Comportamento, Fazenda, Pasto, Posicao, Resumo } from "./types";

const BASE = "/api";

async function pedir<T>(caminho: string, init?: RequestInit): Promise<T> {
  const resposta = await fetch(`${BASE}${caminho}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!resposta.ok) {
    const corpo = await resposta.text();
    throw new Error(`${resposta.status} ${resposta.statusText} — ${corpo}`);
  }

  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}

export const api = {
  fazenda: () => pedir<Fazenda>("/fazenda"),
  resumo: () => pedir<Resumo>("/resumo"),
  pastos: () => pedir<Pasto[]>("/pastos"),
  animais: () => pedir<Animal[]>("/animais"),
  trilha: (animalId: number, limite = 40) =>
    pedir<Posicao[]>(`/animais/${animalId}/trilha?limite=${limite}`),
  alertas: (abertos = true) => pedir<Alerta[]>(`/alertas?abertos=${abertos}&limite=60`),

  criarPasto: (dados: { nome: string; cor: string; buffer_m: number; pontos: [number, number][] }) =>
    pedir<Pasto>("/pastos", { method: "POST", body: JSON.stringify(dados) }),

  resolverAlerta: (alertaId: number) =>
    pedir<Alerta>(`/alertas/${alertaId}/resolver`, { method: "POST" }),

  definirCenario: (animalId: number, comportamento: Comportamento) =>
    pedir<Animal>("/simulacao/cenario", {
      method: "POST",
      body: JSON.stringify({ animal_id: animalId, comportamento }),
    }),

  reiniciarSimulacao: () => pedir<Animal[]>("/simulacao/reiniciar", { method: "POST" }),
};
