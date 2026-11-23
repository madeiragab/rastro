/**
 * Banco de dados do modo demonstração: SQLite de verdade, dentro do app.
 *
 * Roda pelo sql.js (o SQLite compilado para WebAssembly). O arquivo do banco
 * é salvo no IndexedDB do aparelho, então fechar e abrir o app mantém o
 * rebanho, os pastos, os alertas e as contas criadas.
 *
 * O esquema espelha o da API (backend/app/models.py), sem a parte de
 * geometria do PostGIS: aqui os polígonos ficam como JSON e a conta de
 * geocerca é feita em `geo.ts`.
 */

import initSqlJs, { type Database, type SqlValue } from "sql.js";
import wasmUrl from "sql.js/dist/sql-wasm.wasm?url";
import { areaHectares, pontoDentro } from "./geo";

const NOME_IDB = "rastro-demo";
const CHAVE_ARQUIVO = "banco.sqlite";

export const EMAIL_DEMO = "produtor@rastro.com.br";
export const SENHA_DEMO = "rastro2026";

let banco: Database | null = null;
let iniciando: Promise<Database> | null = null;

// ------------------------------------------------------------ persistência
function abrirIdb(): Promise<IDBDatabase> {
  return new Promise((resolver, rejeitar) => {
    const req = indexedDB.open(NOME_IDB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore("arquivos");
    req.onsuccess = () => resolver(req.result);
    req.onerror = () => rejeitar(req.error);
  });
}

async function lerArquivo(): Promise<Uint8Array | null> {
  try {
    const idb = await abrirIdb();
    return await new Promise((resolver) => {
      const req = idb.transaction("arquivos").objectStore("arquivos").get(CHAVE_ARQUIVO);
      req.onsuccess = () => resolver((req.result as Uint8Array | undefined) ?? null);
      req.onerror = () => resolver(null);
    });
  } catch {
    return null;
  }
}

async function gravarArquivo(bytes: Uint8Array): Promise<void> {
  const idb = await abrirIdb();
  await new Promise<void>((resolver, rejeitar) => {
    const tx = idb.transaction("arquivos", "readwrite");
    tx.objectStore("arquivos").put(bytes, CHAVE_ARQUIVO);
    tx.oncomplete = () => resolver();
    tx.onerror = () => rejeitar(tx.error);
  });
}

let salvarAgendado: number | null = null;

/** Grava o banco no aparelho. Agrupa escritas: no máximo uma a cada 3 s. */
export function salvar(): void {
  if (salvarAgendado !== null || !banco) return;
  salvarAgendado = window.setTimeout(() => {
    salvarAgendado = null;
    if (banco) gravarArquivo(banco.export()).catch(() => undefined);
  }, 3000);
}

// ------------------------------------------------------------ consultas
export type Linha = Record<string, SqlValue>;

export function todos<T = Linha>(sql: string, params: SqlValue[] = []): T[] {
  const stmt = obter().prepare(sql);
  try {
    stmt.bind(params);
    const linhas: T[] = [];
    while (stmt.step()) linhas.push(stmt.getAsObject() as T);
    return linhas;
  } finally {
    stmt.free();
  }
}

export function um<T = Linha>(sql: string, params: SqlValue[] = []): T | null {
  return todos<T>(sql, params)[0] ?? null;
}

export function executar(sql: string, params: SqlValue[] = []): number {
  const db = obter();
  db.run(sql, params);
  salvar();
  return Number(db.exec("SELECT last_insert_rowid()")[0]?.values[0][0] ?? 0);
}

export function obter(): Database {
  if (!banco) throw new Error("banco da demonstração ainda não iniciou");
  return banco;
}

export function agoraIso(): string {
  return new Date().toISOString();
}

// ------------------------------------------------------------ esquema
const ESQUEMA = `
CREATE TABLE IF NOT EXISTS fazendas (
  id INTEGER PRIMARY KEY, nome TEXT, proprietario TEXT, municipio TEXT, uf TEXT
);
CREATE TABLE IF NOT EXISTS pastos (
  id INTEGER PRIMARY KEY, fazenda_id INTEGER, nome TEXT, cor TEXT,
  buffer_m REAL DEFAULT 25, pontos TEXT NOT NULL, ativo INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS animais (
  id INTEGER PRIMARY KEY, fazenda_id INTEGER, pasto_id INTEGER,
  brinco TEXT UNIQUE, nome TEXT, categoria TEXT,
  status TEXT DEFAULT 'ok', bateria_pct INTEGER DEFAULT 100,
  lat REAL, lon REAL, ultimo_contato TEXT,
  distancia_pasto_m REAL DEFAULT 0, leituras_fora INTEGER DEFAULT 0,
  imovel_desde TEXT, sim_comportamento TEXT DEFAULT 'normal', sim_rumo REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS posicoes (
  id INTEGER PRIMARY KEY, animal_id INTEGER, lat REAL, lon REAL,
  registrada_em TEXT, atividade REAL
);
CREATE INDEX IF NOT EXISTS ix_posicoes_animal ON posicoes(animal_id, id);
CREATE TABLE IF NOT EXISTS alertas (
  id INTEGER PRIMARY KEY, animal_id INTEGER, pasto_id INTEGER,
  tipo TEXT, severidade TEXT, mensagem TEXT, lat REAL, lon REAL,
  criado_em TEXT, resolvido_em TEXT
);
CREATE TABLE IF NOT EXISTS usuarios (
  id INTEGER PRIMARY KEY, fazenda_id INTEGER, email TEXT UNIQUE, nome TEXT,
  senha_hash TEXT, papel TEXT, ativo INTEGER DEFAULT 1, ultimo_login_em TEXT
);
CREATE TABLE IF NOT EXISTS gateways (
  id INTEGER PRIMARY KEY, fazenda_id INTEGER, nome TEXT, prefixo TEXT,
  chave_hash TEXT, ativa INTEGER DEFAULT 1, criada_em TEXT,
  expira_em TEXT, ultima_utilizacao TEXT
);
CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT);
`;

// ------------------------------------------------------------ carga inicial
// Mesmos dados da carga da API (backend/app/seed.py): Uberaba/MG.
const PASTO_SEDE: [number, number][] = [
  [-19.7508, -47.9358], [-19.7512, -47.9294], [-19.7462, -47.9286],
  [-19.7448, -47.9316], [-19.7458, -47.9354],
];
const PASTO_CORREGO: [number, number][] = [
  [-19.7446, -47.9312], [-19.7458, -47.9268], [-19.7408, -47.9256], [-19.7396, -47.9302],
];
const NOMES = [
  "Mimosa", "Estrela", "Malhada", "Formosa", "Jurema", "Serena", "Chita",
  "Boiadeiro", "Trovão", "Curió", "Pingo", "Guaraná", "Fumaça", "Rajada",
];
const CATEGORIAS = ["Novilha", "Vaca", "Bezerro", "Boi", "Garrote"];

export function pontoAleatorioDentro(pontos: [number, number][]): [number, number] {
  const lats = pontos.map((p) => p[0]);
  const lons = pontos.map((p) => p[1]);
  for (let i = 0; i < 500; i += 1) {
    const lat = Math.min(...lats) + Math.random() * (Math.max(...lats) - Math.min(...lats));
    const lon = Math.min(...lons) + Math.random() * (Math.max(...lons) - Math.min(...lons));
    if (pontoDentro(lat, lon, pontos)) return [lat, lon];
  }
  return pontos[0];
}

export async function hashSenha(senha: string): Promise<string> {
  const sal = "rastro-demo:";
  if (!crypto?.subtle) return `plano:${senha}`;
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(sal + senha));
  return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function semear(db: Database): Promise<void> {
  db.run(
    "INSERT INTO fazendas (id, nome, proprietario, municipio, uf) VALUES (1, 'Fazenda Boa Vista', 'José Rodrigues', 'Uberaba', 'MG')",
  );
  db.run("INSERT INTO pastos (id, fazenda_id, nome, cor, pontos) VALUES (1, 1, 'Pasto da Sede', '#2E7D53', ?)", [
    JSON.stringify(PASTO_SEDE),
  ]);
  db.run("INSERT INTO pastos (id, fazenda_id, nome, cor, pontos) VALUES (2, 1, 'Pasto do Córrego', '#3D6EA8', ?)", [
    JSON.stringify(PASTO_CORREGO),
  ]);

  const agora = agoraIso();
  NOMES.forEach((nome, i) => {
    const pastoId = i < 9 ? 1 : 2;
    const [lat, lon] = pontoAleatorioDentro(pastoId === 1 ? PASTO_SEDE : PASTO_CORREGO);
    db.run(
      `INSERT INTO animais (fazenda_id, pasto_id, brinco, nome, categoria, bateria_pct,
         lat, lon, ultimo_contato, sim_rumo)
       VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        pastoId,
        `076${String(i + 1).padStart(12, "0")}`,
        nome,
        CATEGORIAS[Math.floor(Math.random() * CATEGORIAS.length)],
        72 + Math.floor(Math.random() * 29),
        lat,
        lon,
        agora,
        Math.random() * 6.28,
      ],
    );
  });

  db.run(
    "INSERT INTO usuarios (fazenda_id, email, nome, senha_hash, papel) VALUES (1, ?, 'José Rodrigues', ?, 'dono')",
    [EMAIL_DEMO, await hashSenha(SENHA_DEMO)],
  );
  db.run(
    "INSERT INTO gateways (fazenda_id, nome, prefixo, chave_hash, criada_em) VALUES (1, 'Gateway da sede', 'rgw_demo', '-', ?)",
    [agora],
  );
  db.run("INSERT INTO meta (chave, valor) VALUES ('versao', '1')");
}

// ------------------------------------------------------------ início
export function iniciar(): Promise<Database> {
  iniciando ??= (async () => {
    const SQL = await initSqlJs({ locateFile: () => wasmUrl } as unknown as Parameters<typeof initSqlJs>[0]);
    const salvo = await lerArquivo();
    const db = salvo ? new SQL.Database(salvo) : new SQL.Database();
    db.run(ESQUEMA);

    const vazio = !db.exec("SELECT 1 FROM fazendas LIMIT 1")[0];
    if (vazio) await semear(db);

    banco = db;
    await gravarArquivo(db.export()).catch(() => undefined);
    return db;
  })();
  return iniciando;
}

/** Apaga tudo e recomeça da carga inicial. */
export async function zerar(): Promise<void> {
  const db = obter();
  db.run(
    "DROP TABLE IF EXISTS fazendas; DROP TABLE IF EXISTS pastos; DROP TABLE IF EXISTS animais; " +
      "DROP TABLE IF EXISTS posicoes; DROP TABLE IF EXISTS alertas; DROP TABLE IF EXISTS usuarios; " +
      "DROP TABLE IF EXISTS gateways; DROP TABLE IF EXISTS meta;",
  );
  db.run(ESQUEMA);
  await semear(db);
  await gravarArquivo(db.export());
}

export function areaDoPasto(pontosJson: string): number {
  return areaHectares(JSON.parse(pontosJson) as [number, number][]);
}
