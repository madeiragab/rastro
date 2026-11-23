/**
 * "Servidor" do modo demonstração: responde às mesmas rotas da API, só que
 * lendo e gravando no SQLite do aparelho.
 *
 * `api.ts` chama `responder()` no lugar do `fetch` quando o app foi gerado
 * com VITE_MODO_DEMO=1. Nenhuma tela sabe a diferença.
 */

import { agoraIso, areaDoPasto, EMAIL_DEMO, executar, hashSenha, iniciar, todos, um, type Linha } from "./banco";
import { esquecerPastos, ligar, pastoGeo, resolverTodos } from "./simulador";
import { centroide } from "./geo";

export class ErroDemo extends Error {
  constructor(
    public status: number,
    mensagem: string,
  ) {
    super(mensagem);
  }
}

const CHAVE_SESSAO = "rastro-demo-sessao";

function lerSessao(): number | null {
  try {
    const v = localStorage.getItem(CHAVE_SESSAO);
    return v ? Number(v) : null;
  } catch {
    return null;
  }
}

function gravarSessao(id: number | null) {
  try {
    if (id === null) localStorage.removeItem(CHAVE_SESSAO);
    else localStorage.setItem(CHAVE_SESSAO, String(id));
  } catch {
    /* sem armazenamento: a sessão dura só enquanto o app está aberto */
  }
}

let sessaoEmMemoria: number | null = null;

// ------------------------------------------------------------ saídas
const bool = (v: unknown) => v === 1 || v === true;

function usuarioOut(u: Linha) {
  return {
    id: u.id as number,
    email: u.email as string,
    nome: u.nome as string,
    papel: u.papel as string,
    ativo: bool(u.ativo),
    fazenda_id: u.fazenda_id as number,
    ultimo_login_em: (u.ultimo_login_em as string) ?? null,
  };
}

function animalOut(a: Linha) {
  const pasto = a.pasto_id ? pastoGeo(a.pasto_id as number) : null;
  const contato = a.ultimo_contato as string | null;
  return {
    id: a.id,
    brinco: a.brinco,
    nome: a.nome,
    categoria: a.categoria,
    status: a.status,
    bateria_pct: a.bateria_pct,
    lat: a.lat,
    lon: a.lon,
    ultimo_contato: contato,
    segundos_sem_contato: contato ? Math.max(0, Math.round((Date.now() - Date.parse(contato)) / 1000)) : null,
    distancia_pasto_m: a.distancia_pasto_m,
    pasto_id: a.pasto_id,
    pasto_nome: pasto?.nome ?? null,
    sim_comportamento: a.sim_comportamento,
  };
}

function alertaOut(al: Linha) {
  const animal = al.animal_id ? um("SELECT nome, brinco FROM animais WHERE id = ?", [al.animal_id]) : null;
  const pasto = al.pasto_id ? pastoGeo(al.pasto_id as number) : null;
  return {
    id: al.id,
    animal_id: al.animal_id ?? null,
    animal_nome: animal?.nome ?? null,
    brinco: animal?.brinco ?? null,
    pasto_id: al.pasto_id ?? null,
    pasto_nome: pasto?.nome ?? null,
    tipo: al.tipo,
    severidade: al.severidade,
    mensagem: al.mensagem,
    lat: al.lat ?? null,
    lon: al.lon ?? null,
    criado_em: al.criado_em,
    resolvido_em: al.resolvido_em ?? null,
  };
}

function pastoOut(p: Linha) {
  const total = um<{ n: number }>("SELECT COUNT(*) AS n FROM animais WHERE pasto_id = ?", [p.id])?.n ?? 0;
  return {
    id: p.id,
    nome: p.nome,
    cor: p.cor,
    buffer_m: p.buffer_m,
    pontos: JSON.parse(p.pontos as string),
    area_ha: Math.round(areaDoPasto(p.pontos as string) * 100) / 100,
    total_animais: total,
  };
}

function gatewayOut(g: Linha) {
  return {
    id: g.id,
    nome: g.nome,
    prefixo: g.prefixo,
    ativa: bool(g.ativa),
    criada_em: g.criada_em,
    expira_em: g.expira_em ?? null,
    ultima_utilizacao: g.ultima_utilizacao ?? null,
  };
}

// ------------------------------------------------------------ sessão
function usuarioLogado(): Linha {
  const id = sessaoEmMemoria ?? lerSessao();
  const u = id ? um("SELECT * FROM usuarios WHERE id = ?", [id]) : null;
  if (!u || !bool(u.ativo)) throw new ErroDemo(401, "sessão expirada");
  return u;
}

const NIVEL: Record<string, number> = { leitura: 0, operador: 1, dono: 2 };
function exige(papel: "operador" | "dono") {
  const u = usuarioLogado();
  if ((NIVEL[u.papel as string] ?? -1) < NIVEL[papel]) throw new ErroDemo(403, "seu papel nao permite esta operacao");
  return u;
}

function senhaAleatoria() {
  const letras = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  return Array.from({ length: 12 }, () => letras[Math.floor(Math.random() * letras.length)]).join("");
}

// ------------------------------------------------------------ rotas
type Corpo = Record<string, unknown>;

export async function responder(metodo: string, caminhoCompleto: string, corpo: Corpo | null): Promise<unknown> {
  await iniciar();
  ligar();

  const [caminho, consulta = ""] = caminhoCompleto.split("?");
  const q = new URLSearchParams(consulta);
  const rota = `${metodo} ${caminho}`;
  let m: RegExpMatchArray | null;

  // --- públicas
  if (rota === "GET /auth/modo") return { modo: "local" };

  if (rota === "POST /auth/login") {
    const email = String(corpo?.email ?? "").trim().toLowerCase();
    const u = um("SELECT * FROM usuarios WHERE email = ?", [email]);
    if (!u || !bool(u.ativo) || u.senha_hash !== (await hashSenha(String(corpo?.senha ?? "")))) {
      throw new ErroDemo(401, "e-mail ou senha incorretos");
    }
    executar("UPDATE usuarios SET ultimo_login_em = ? WHERE id = ?", [agoraIso(), u.id]);
    sessaoEmMemoria = u.id as number;
    gravarSessao(sessaoEmMemoria);
    return { access_token: "demo", token_type: "bearer", expira_em_s: 86400, usuario: usuarioOut(u) };
  }

  if (rota === "POST /auth/logout") {
    sessaoEmMemoria = null;
    gravarSessao(null);
    return undefined;
  }

  if (rota === "POST /auth/esqueci") {
    return { detail: `Modo demonstração: não há envio de e-mail. Use ${EMAIL_DEMO}.` };
  }

  // --- daqui para baixo, só logado
  const eu = usuarioLogado();

  if (rota === "GET /auth/eu") return usuarioOut(eu);

  if (rota === "POST /auth/senha") {
    if (eu.senha_hash !== (await hashSenha(String(corpo?.senha_atual ?? "")))) throw new ErroDemo(400, "senha atual incorreta");
    const nova = String(corpo?.senha_nova ?? "");
    if (nova.length < 12) throw new ErroDemo(422, "a senha precisa ter pelo menos 12 caracteres");
    executar("UPDATE usuarios SET senha_hash = ? WHERE id = ?", [await hashSenha(nova), eu.id]);
    return undefined;
  }

  if (rota === "GET /fazenda") return um("SELECT * FROM fazendas ORDER BY id LIMIT 1");

  if (rota === "GET /resumo") {
    const conta = (s: string) => um<{ n: number }>("SELECT COUNT(*) AS n FROM animais WHERE status = ?", [s])?.n ?? 0;
    const pastos = todos("SELECT pontos FROM pastos WHERE ativo = 1");
    return {
      total_animais: um<{ n: number }>("SELECT COUNT(*) AS n FROM animais")?.n ?? 0,
      em_area: conta("ok"),
      fora_da_area: conta("fora_da_area"),
      imoveis: conta("imovel"),
      sem_sinal: conta("sem_sinal"),
      alertas_abertos: um<{ n: number }>("SELECT COUNT(*) AS n FROM alertas WHERE resolvido_em IS NULL")?.n ?? 0,
      total_pastos: pastos.length,
      area_total_ha: Math.round(pastos.reduce((s, p) => s + areaDoPasto(p.pontos as string), 0) * 100) / 100,
    };
  }

  if (rota === "GET /pastos") return todos("SELECT * FROM pastos WHERE ativo = 1 ORDER BY id").map(pastoOut);

  if (rota === "POST /pastos") {
    exige("operador");
    const pontos = corpo?.pontos as [number, number][] | undefined;
    if (!Array.isArray(pontos) || pontos.length < 3) throw new ErroDemo(422, "o pasto precisa de pelo menos 3 pontos");
    const id = executar("INSERT INTO pastos (fazenda_id, nome, cor, buffer_m, pontos) VALUES (1, ?, ?, ?, ?)", [
      String(corpo?.nome ?? "Pasto novo"),
      String(corpo?.cor ?? "#2E7D53"),
      Number(corpo?.buffer_m ?? 25),
      JSON.stringify(pontos),
    ]);
    esquecerPastos();
    return pastoOut(um("SELECT * FROM pastos WHERE id = ?", [id])!);
  }

  if (rota === "GET /animais") return todos("SELECT * FROM animais ORDER BY nome").map(animalOut);

  if ((m = rota.match(/^GET \/animais\/(\d+)\/trilha$/))) {
    const limite = Math.min(Number(q.get("limite") ?? 40), 200);
    return todos(
      "SELECT lat, lon, registrada_em, atividade FROM posicoes WHERE animal_id = ? ORDER BY id DESC LIMIT ?",
      [Number(m[1]), limite],
    ).reverse();
  }

  if (rota === "GET /alertas") {
    const abertos = q.get("abertos") !== "false";
    const limite = Math.min(Number(q.get("limite") ?? 50), 300);
    return todos(
      `SELECT * FROM alertas ${abertos ? "WHERE resolvido_em IS NULL" : ""} ORDER BY criado_em DESC, id DESC LIMIT ?`,
      [limite],
    ).map(alertaOut);
  }

  if ((m = rota.match(/^POST \/alertas\/(\d+)\/resolver$/))) {
    const id = Number(m[1]);
    const al = um("SELECT * FROM alertas WHERE id = ?", [id]);
    if (!al) throw new ErroDemo(404, "alerta nao encontrado");
    if (!al.resolvido_em) executar("UPDATE alertas SET resolvido_em = ? WHERE id = ?", [agoraIso(), id]);
    return alertaOut(um("SELECT * FROM alertas WHERE id = ?", [id])!);
  }

  // --- simulação
  if (rota === "POST /simulacao/cenario") {
    exige("operador");
    const id = Number(corpo?.animal_id);
    const comportamento = String(corpo?.comportamento ?? "normal");
    const a = um("SELECT * FROM animais WHERE id = ?", [id]);
    if (!a) throw new ErroDemo(404, "animal nao encontrado");

    let rumo = a.sim_rumo as number;
    const pasto = a.pasto_id ? pastoGeo(a.pasto_id as number) : null;
    if (comportamento === "fugindo" && pasto) {
      // Rumo do centro do pasto para o animal: ele segue reto para fora.
      const [cLat, cLon] = centroide(pasto.pontos);
      rumo = Math.atan2((a.lon as number) - cLon, (a.lat as number) - cLat);
    }
    executar("UPDATE animais SET sim_comportamento = ?, sim_rumo = ? WHERE id = ?", [comportamento, rumo, id]);
    if (comportamento === "normal") {
      executar("UPDATE animais SET leituras_fora = 0, imovel_desde = NULL WHERE id = ?", [id]);
      // Volta para dentro do pasto: na demonstração, "pastando" é o botão de desfazer.
      if (pasto && (a.distancia_pasto_m as number) > 0) {
        const [cLat, cLon] = centroide(pasto.pontos);
        executar("UPDATE animais SET lat = ?, lon = ? WHERE id = ?", [cLat, cLon, id]);
      }
      resolverTodos(id);
    }
    return animalOut(um("SELECT * FROM animais WHERE id = ?", [id])!);
  }

  if (rota === "POST /simulacao/reiniciar") {
    exige("operador");
    for (const a of todos("SELECT id FROM animais WHERE sim_comportamento != 'normal' OR status != 'ok'")) {
      const pasto = um("SELECT pasto_id FROM animais WHERE id = ?", [a.id]);
      const geo = pasto?.pasto_id ? pastoGeo(pasto.pasto_id as number) : null;
      executar("UPDATE animais SET sim_comportamento = 'normal', leituras_fora = 0, imovel_desde = NULL, ultimo_contato = ? WHERE id = ?", [
        agoraIso(),
        a.id,
      ]);
      if (geo) {
        const [cLat, cLon] = centroide(geo.pontos);
        executar("UPDATE animais SET lat = ?, lon = ? WHERE id = ?", [cLat, cLon, a.id]);
      }
      resolverTodos(a.id as number);
    }
    executar("UPDATE alertas SET resolvido_em = ? WHERE resolvido_em IS NULL", [agoraIso()]);
    return todos("SELECT * FROM animais ORDER BY nome").map(animalOut);
  }

  // --- equipe
  if (rota === "GET /usuarios") {
    exige("dono");
    return todos("SELECT * FROM usuarios ORDER BY id").map(usuarioOut);
  }

  if (rota === "POST /usuarios") {
    exige("dono");
    const email = String(corpo?.email ?? "").trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new ErroDemo(422, "e-mail inválido");
    if (um("SELECT id FROM usuarios WHERE email = ?", [email])) throw new ErroDemo(409, "ja existe conta com este e-mail");
    const senha = senhaAleatoria();
    const id = executar("INSERT INTO usuarios (fazenda_id, email, nome, senha_hash, papel) VALUES (1, ?, ?, ?, ?)", [
      email,
      String(corpo?.nome ?? ""),
      await hashSenha(senha),
      String(corpo?.papel ?? "leitura"),
    ]);
    return { ...usuarioOut(um("SELECT * FROM usuarios WHERE id = ?", [id])!), senha_inicial: senha };
  }

  if ((m = rota.match(/^PATCH \/usuarios\/(\d+)$/))) {
    exige("dono");
    const id = Number(m[1]);
    if (id === eu.id) throw new ErroDemo(400, "voce nao pode alterar o proprio papel nem se desativar");
    if (!um("SELECT id FROM usuarios WHERE id = ?", [id])) throw new ErroDemo(404, "usuario nao encontrado");
    if (corpo?.papel) executar("UPDATE usuarios SET papel = ? WHERE id = ?", [String(corpo.papel), id]);
    if (typeof corpo?.ativo === "boolean") executar("UPDATE usuarios SET ativo = ? WHERE id = ?", [corpo.ativo ? 1 : 0, id]);
    return usuarioOut(um("SELECT * FROM usuarios WHERE id = ?", [id])!);
  }

  // --- gateways
  if (rota === "GET /gateways") {
    exige("dono");
    return todos("SELECT * FROM gateways ORDER BY id").map(gatewayOut);
  }

  if (rota === "POST /gateways") {
    exige("dono");
    const prefixo = `rgw_${senhaAleatoria().slice(0, 8).toLowerCase()}`;
    const dias = corpo?.dias_validade ? Number(corpo.dias_validade) : null;
    const expira = dias ? new Date(Date.now() + dias * 86_400_000).toISOString() : null;
    const id = executar("INSERT INTO gateways (fazenda_id, nome, prefixo, chave_hash, criada_em, expira_em) VALUES (1, ?, ?, '-', ?, ?)", [
      String(corpo?.nome ?? "Gateway"),
      prefixo,
      agoraIso(),
      expira,
    ]);
    return { ...gatewayOut(um("SELECT * FROM gateways WHERE id = ?", [id])!), chave: `${prefixo}.${senhaAleatoria()}${senhaAleatoria()}` };
  }

  if ((m = rota.match(/^DELETE \/gateways\/(\d+)$/))) {
    exige("dono");
    executar("UPDATE gateways SET ativa = 0 WHERE id = ?", [Number(m[1])]);
    return undefined;
  }

  // --- push: na demonstração o aviso é a vibração do aparelho.
  if (caminho.startsWith("/push/")) {
    if (rota === "GET /push/chave-publica") throw new ErroDemo(404, "push indisponível no modo demonstração");
    return undefined;
  }

  throw new ErroDemo(404, `rota não existe na demonstração: ${rota}`);
}

/** Sessão salva no aparelho? Usado ao abrir o app. */
export async function restaurar(): Promise<unknown | null> {
  await iniciar();
  ligar();
  try {
    return await responder("GET", "/auth/eu", null);
  } catch {
    return null;
  }
}
