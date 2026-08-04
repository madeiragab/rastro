import type { Resumo } from "../types";

/**
 * Faixa horizontal de pilulas que continua visivel com a folha recolhida.
 * E a unica informacao que o produtor ve sem interagir, entao mostra so o
 * que exige acao: primeiro os problemas, o total por ultimo.
 */
export function TirasResumo({ resumo }: { resumo: Resumo | null }) {
  const pilulas = [
    { chave: "alertas", classe: "alerta", valor: resumo?.alertas_abertos ?? 0, rotulo: "alertas" },
    { chave: "fora", classe: "alerta", valor: resumo?.fora_da_area ?? 0, rotulo: "fora" },
    { chave: "imovel", classe: "aviso", valor: resumo?.imoveis ?? 0, rotulo: "parados" },
    { chave: "offline", classe: "neutro", valor: resumo?.sem_sinal ?? 0, rotulo: "sem sinal" },
    { chave: "ok", classe: "ok", valor: resumo?.em_area ?? 0, rotulo: "na área" },
    { chave: "total", classe: "neutro", valor: resumo?.total_animais ?? 0, rotulo: "animais" },
  ];

  return (
    <>
      {pilulas.map((pilula) => (
        <div key={pilula.chave} className={`pilula ${pilula.classe}`}>
          <b>{pilula.valor}</b>
          <span>{pilula.rotulo}</span>
        </div>
      ))}
    </>
  );
}
