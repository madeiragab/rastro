/**
 * Simulador e motor de alertas do modo demonstração.
 *
 * Porta das regras da API (backend/app/services/simulador.py e alertas.py),
 * com os mesmos limiares comprimidos de demonstração:
 *
 *  - geocerca: 2 leituras seguidas além da tolerância (25 m) abrem o alerta;
 *  - imobilidade: atividade <= 0,08 por 90 s;
 *  - perda de sinal: 60 s sem leitura; 60% de um lote calado vira um alerta
 *    de lote, e não um por animal.
 */

import { agoraIso, executar, salvar, todos, um, type Linha } from "./banco";
import { centroide, distanciaAoPoligono, metrosParaGraus, pontoDentro } from "./geo";

export const TICK_MS = 4000;
const PASSO_NORMAL_M = 12;
const PASSO_FUGA_M = 55;
const CONFIRMACOES_FORA = 2;
const ATIVIDADE_MAX_IMOVEL = 0.08;
const IMOVEL_S = 90;
const SILENCIO_S = 60;
const LOTE_FRACAO = 0.6;
const LOTE_MINIMO = 3;
const POSICOES_POR_ANIMAL = 80;

interface AnimalLinha extends Linha {
  id: number;
  nome: string;
  pasto_id: number | null;
  lat: number;
  lon: number;
  bateria_pct: number;
  leituras_fora: number;
  imovel_desde: string | null;
  sim_comportamento: string;
  sim_rumo: number;
  ultimo_contato: string | null;
}

interface PastoLinha extends Linha {
  id: number;
  nome: string;
  buffer_m: number;
  pontos: string;
}

const pastosCache = new Map<number, { nome: string; buffer: number; pontos: [number, number][] }>();

export function pastoGeo(id: number) {
  if (!pastosCache.has(id)) {
    const p = um<PastoLinha>("SELECT id, nome, buffer_m, pontos FROM pastos WHERE id = ?", [id]);
    if (!p) return null;
    pastosCache.set(id, { nome: p.nome, buffer: p.buffer_m, pontos: JSON.parse(p.pontos) });
  }
  return pastosCache.get(id)!;
}

export function esquecerPastos(): void {
  pastosCache.clear();
}

// ------------------------------------------------------------ alertas
function alertaAberto(animalId: number, tipo: string) {
  return um("SELECT id FROM alertas WHERE animal_id = ? AND tipo = ? AND resolvido_em IS NULL", [animalId, tipo]);
}

function abrir(a: AnimalLinha, tipo: string, mensagem: string, severidade: string, lat: number | null, lon: number | null) {
  if (alertaAberto(a.id, tipo)) return false;
  executar(
    `INSERT INTO alertas (animal_id, pasto_id, tipo, severidade, mensagem, lat, lon, criado_em)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    [a.id, a.pasto_id, tipo, severidade, mensagem, lat, lon, agoraIso()],
  );
  avisarNovoAlerta(mensagem);
  return true;
}

function resolver(animalId: number, tipo: string) {
  executar("UPDATE alertas SET resolvido_em = ? WHERE animal_id = ? AND tipo = ? AND resolvido_em IS NULL", [
    agoraIso(),
    animalId,
    tipo,
  ]);
}

export function resolverTodos(animalId: number) {
  executar("UPDATE alertas SET resolvido_em = ? WHERE animal_id = ? AND resolvido_em IS NULL", [agoraIso(), animalId]);
  executar("UPDATE animais SET status = 'ok', leituras_fora = 0, imovel_desde = NULL WHERE id = ?", [animalId]);
}

/** Vibra o aparelho quando um alerta novo abre — é o "push" da demonstração. */
function avisarNovoAlerta(_mensagem: string) {
  try {
    navigator.vibrate?.([200, 100, 200]);
  } catch {
    /* sem vibração neste aparelho */
  }
}

// ------------------------------------------------------------ leitura nova
function registrar(a: AnimalLinha, lat: number, lon: number, atividade: number) {
  const momento = agoraIso();
  executar("INSERT INTO posicoes (animal_id, lat, lon, registrada_em, atividade) VALUES (?, ?, ?, ?, ?)", [
    a.id,
    lat,
    lon,
    momento,
    atividade,
  ]);
  resolver(a.id, "sem_sinal");

  // Regra 1: geocerca.
  let fora = false;
  let distancia = 0;
  let leiturasFora = a.leituras_fora;
  const pasto = a.pasto_id ? pastoGeo(a.pasto_id) : null;
  if (pasto) {
    distancia = Math.round(distanciaAoPoligono(lat, lon, pasto.pontos) * 10) / 10;
    const dentro = pontoDentro(lat, lon, pasto.pontos) || distancia <= pasto.buffer;
    if (dentro) {
      leiturasFora = 0;
      resolver(a.id, "fora_da_area");
    } else {
      leiturasFora += 1;
      if (leiturasFora >= CONFIRMACOES_FORA) {
        fora = true;
        abrir(a, "fora_da_area", `${a.nome} saiu de ${pasto.nome} (${distancia.toFixed(0)} m além da divisa).`, "alta", lat, lon);
      }
    }
  }

  // Regra 2: imobilidade (quem decide é o acelerômetro, não o GPS).
  let imovel = false;
  let imovelDesde = a.imovel_desde;
  if (atividade <= ATIVIDADE_MAX_IMOVEL) {
    imovelDesde ??= momento;
    const parado = (Date.now() - Date.parse(imovelDesde)) / 1000;
    if (parado >= IMOVEL_S) {
      imovel = true;
      abrir(
        a,
        "imovel",
        `${a.nome} sem movimento há ${Math.floor(parado / 60)} min. Verificar: parto, queda, atolamento ou morte.`,
        "critica",
        lat,
        lon,
      );
    }
  } else {
    imovelDesde = null;
    resolver(a.id, "imovel");
  }

  const status = imovel ? "imovel" : fora ? "fora_da_area" : "ok";
  executar(
    `UPDATE animais SET lat = ?, lon = ?, ultimo_contato = ?, distancia_pasto_m = ?,
       leituras_fora = ?, imovel_desde = ?, status = ?, sim_rumo = ?, bateria_pct = ?
     WHERE id = ?`,
    [lat, lon, momento, distancia, leiturasFora, imovelDesde, status, a.sim_rumo, a.bateria_pct, a.id],
  );

  // Só o histórico recente interessa ao mapa; sem isso o banco cresce para sempre.
  executar(
    `DELETE FROM posicoes WHERE animal_id = ? AND id NOT IN
       (SELECT id FROM posicoes WHERE animal_id = ? ORDER BY id DESC LIMIT ${POSICOES_POR_ANIMAL})`,
    [a.id, a.id],
  );
}

function proximoPonto(a: AnimalLinha): [number, number, number] {
  const { lat, lon } = a;
  if (a.sim_comportamento === "imovel") return [lat, lon, Math.random() * 0.03];

  if (a.sim_comportamento === "fugindo") {
    const [dLat, dLon] = metrosParaGraus(PASSO_FUGA_M, lat);
    return [lat + dLat * Math.cos(a.sim_rumo), lon + dLon * Math.sin(a.sim_rumo), 0.55 + Math.random() * 0.4];
  }

  a.sim_rumo += (Math.random() - 0.5) * 1.4;
  const [dLat, dLon] = metrosParaGraus(PASSO_NORMAL_M * (0.4 + Math.random() * 0.9), lat);
  let nLat = lat + dLat * Math.cos(a.sim_rumo);
  let nLon = lon + dLon * Math.sin(a.sim_rumo);

  const pasto = a.pasto_id ? pastoGeo(a.pasto_id) : null;
  if (pasto && !pontoDentro(nLat, nLon, pasto.pontos)) {
    // Bateu na cerca: vira para o meio do pasto.
    const [cLat, cLon] = centroide(pasto.pontos);
    a.sim_rumo = Math.atan2(cLon - lon, cLat - lat);
    nLat = lat + dLat * Math.cos(a.sim_rumo);
    nLon = lon + dLon * Math.sin(a.sim_rumo);
  }
  return [nLat, nLon, 0.25 + Math.random() * 0.65];
}

// ------------------------------------------------------------ silêncio
function varrerSilencio() {
  const agora = Date.now();
  const animais = todos<AnimalLinha>("SELECT * FROM animais");
  const porLote = new Map<number | null, AnimalLinha[]>();
  const calados = new Map<number | null, AnimalLinha[]>();

  for (const a of animais) {
    porLote.set(a.pasto_id, [...(porLote.get(a.pasto_id) ?? []), a]);
    if (a.ultimo_contato && (agora - Date.parse(a.ultimo_contato)) / 1000 >= SILENCIO_S) {
      calados.set(a.pasto_id, [...(calados.get(a.pasto_id) ?? []), a]);
    }
  }

  for (const [pastoId, mudos] of calados) {
    const total = porLote.get(pastoId)?.length ?? 0;
    for (const a of mudos) executar("UPDATE animais SET status = 'sem_sinal' WHERE id = ?", [a.id]);

    const coletivo = pastoId !== null && total >= LOTE_MINIMO && mudos.length / total >= LOTE_FRACAO;
    if (coletivo) {
      const aberto = um(
        "SELECT id FROM alertas WHERE pasto_id = ? AND animal_id IS NULL AND tipo = 'lote_sem_comunicacao' AND resolvido_em IS NULL",
        [pastoId],
      );
      if (!aberto) {
        const nome = pastoGeo(pastoId!)?.nome ?? "lote";
        const msg = `${mudos.length} de ${total} animais de ${nome} sem comunicação. Provável falha do brinco que repassa o lote — verificar antes de sair procurando gado.`;
        executar(
          "INSERT INTO alertas (animal_id, pasto_id, tipo, severidade, mensagem, criado_em) VALUES (NULL, ?, 'lote_sem_comunicacao', 'alta', ?, ?)",
          [pastoId, msg, agoraIso()],
        );
        avisarNovoAlerta(msg);
      }
      continue;
    }

    for (const a of mudos) {
      const s = (agora - Date.parse(a.ultimo_contato!)) / 1000;
      const desde = s >= 60 ? `${Math.floor(s / 60)} min` : `${Math.floor(s)} s`;
      abrir(a, "sem_sinal", `${a.nome} sem comunicação há ${desde}. Verificar: brinco arrancado, bateria ou área sem propagação.`, "media", null, null);
    }
  }

  for (const pastoId of porLote.keys()) {
    if (pastoId === null || calados.has(pastoId)) continue;
    executar(
      "UPDATE alertas SET resolvido_em = ? WHERE pasto_id = ? AND animal_id IS NULL AND tipo = 'lote_sem_comunicacao' AND resolvido_em IS NULL",
      [agoraIso(), pastoId],
    );
  }
}

// ------------------------------------------------------------ ciclo
export function tick(): void {
  for (const a of todos<AnimalLinha>("SELECT * FROM animais")) {
    if (a.sim_comportamento === "offline" || a.lat === null) continue;
    const [lat, lon, atividade] = proximoPonto(a);
    if (Math.random() < 0.05 && a.bateria_pct > 1) a.bateria_pct -= 1;
    registrar(a, lat, lon, Math.round(atividade * 1000) / 1000);
  }
  varrerSilencio();
  salvar();
}

let timer: number | null = null;

export function ligar(): void {
  if (timer !== null) return;
  // App fechado não transmite: ao reabrir, quem estava "pastando" retoma do
  // ponto onde parou, em vez de todo o rebanho aparecer como sem sinal.
  executar("UPDATE animais SET ultimo_contato = ? WHERE sim_comportamento != 'offline'", [agoraIso()]);
  timer = window.setInterval(() => {
    try {
      tick();
    } catch (erro) {
      console.error("simulador da demonstração", erro);
    }
  }, TICK_MS);
}
