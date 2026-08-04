import type {
  Alerta,
  Animal,
  ChaveGateway,
  ChaveGatewayCriada,
  Comportamento,
  Fazenda,
  Pasto,
  Posicao,
  Resumo,
  RespostaLogin,
  Usuario,
} from "./types";

const BASE = "/api";

/**
 * O access token vive **apenas em memória**.
 *
 * Nada de localStorage nem sessionStorage: qualquer XSS lê os dois. Em memória,
 * o token morre junto com a aba, e a sessão é restaurada na próxima carga pelo
 * cookie de refresh — que é HttpOnly e o JavaScript não alcança.
 */
let accessToken: string | null = null;

/** Chamado quando a sessão acaba de vez, para a UI voltar ao login. */
let aoPerderSessao: (() => void) | null = null;

export function definirToken(token: string | null): void {
  accessToken = token;
}

export function registrarPerdaDeSessao(callback: () => void): void {
  aoPerderSessao = callback;
}

function lerCookie(nome: string): string {
  const achado = document.cookie
    .split("; ")
    .find((linha) => linha.startsWith(`${nome}=`));
  return achado ? decodeURIComponent(achado.slice(nome.length + 1)) : "";
}

export class ErroApi extends Error {
  constructor(
    public status: number,
    mensagem: string,
  ) {
    super(mensagem);
  }
}

async function extrairMensagem(resposta: Response): Promise<string> {
  try {
    const corpo = await resposta.json();
    if (typeof corpo?.detail === "string") return corpo.detail;
    if (Array.isArray(corpo?.detail)) return corpo.detail[0]?.msg ?? resposta.statusText;
  } catch {
    /* corpo não é JSON */
  }
  return resposta.statusText;
}

// Uma renovação por vez. Sem isso, seis requisições paralelas expirando juntas
// disparariam seis rotações de refresh — e a detecção de reuso do servidor
// derrubaria a sessão inteira, achando que o token foi roubado.
let renovacaoEmCurso: Promise<boolean> | null = null;

async function renovar(): Promise<boolean> {
  if (!renovacaoEmCurso) {
    renovacaoEmCurso = (async () => {
      try {
        const resposta = await fetch(`${BASE}/auth/refresh`, {
          method: "POST",
          credentials: "same-origin",
          headers: { "X-CSRF-Token": lerCookie("rastro_csrf") },
        });
        if (!resposta.ok) return false;

        const dados = (await resposta.json()) as RespostaLogin;
        accessToken = dados.access_token;
        return true;
      } catch {
        return false;
      } finally {
        // Libera na próxima volta do event loop, para que chamadas que
        // chegaram durante a renovação aproveitem este mesmo resultado.
        setTimeout(() => {
          renovacaoEmCurso = null;
        }, 0);
      }
    })();
  }
  return renovacaoEmCurso;
}

async function pedir<T>(
  caminho: string,
  init: RequestInit = {},
  jaRenovou = false,
): Promise<T> {
  const cabecalhos: Record<string, string> = {
    ...(init.body ? { "Content-Type": "application/json" } : {}),
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (accessToken) cabecalhos.Authorization = `Bearer ${accessToken}`;

  const resposta = await fetch(`${BASE}${caminho}`, {
    credentials: "same-origin",
    ...init,
    headers: cabecalhos,
  });

  // Access token expirado: renova uma vez e repete. `jaRenovou` impede laço
  // infinito quando o refresh também não vale mais.
  if (resposta.status === 401 && !jaRenovou && !caminho.startsWith("/auth/")) {
    if (await renovar()) return pedir<T>(caminho, init, true);
    accessToken = null;
    aoPerderSessao?.();
    throw new ErroApi(401, "sessão expirada");
  }

  if (!resposta.ok) throw new ErroApi(resposta.status, await extrairMensagem(resposta));
  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}

export const api = {
  // ------------------------------------------------------------ sessão
  async login(email: string, senha: string): Promise<RespostaLogin> {
    const dados = await pedir<RespostaLogin>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, senha }),
    });
    accessToken = dados.access_token;
    return dados;
  },

  /** Restaura a sessão na carga da página, usando o cookie de refresh. */
  async restaurarSessao(): Promise<Usuario | null> {
    if (!(await renovar())) return null;
    try {
      return await pedir<Usuario>("/auth/eu");
    } catch {
      return null;
    }
  },

  async logout(): Promise<void> {
    try {
      await pedir<void>("/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": lerCookie("rastro_csrf") },
      });
    } finally {
      accessToken = null;
    }
  },

  trocarSenha: (senha_atual: string, senha_nova: string) =>
    pedir<void>("/auth/senha", {
      method: "POST",
      body: JSON.stringify({ senha_atual, senha_nova }),
    }),

  // ------------------------------------------------------------- dados
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

  // ---------------------------------------------------------- gateways
  gateways: () => pedir<ChaveGateway[]>("/gateways"),

  criarGateway: (nome: string, dias_validade?: number) =>
    pedir<ChaveGatewayCriada>("/gateways", {
      method: "POST",
      body: JSON.stringify({ nome, dias_validade: dias_validade ?? null }),
    }),

  revogarGateway: (id: number) => pedir<void>(`/gateways/${id}`, { method: "DELETE" }),

  // --------------------------------------------------------- simulação
  definirCenario: (animalId: number, comportamento: Comportamento) =>
    pedir<Animal>("/simulacao/cenario", {
      method: "POST",
      body: JSON.stringify({ animal_id: animalId, comportamento }),
    }),

  reiniciarSimulacao: () => pedir<Animal[]>("/simulacao/reiniciar", { method: "POST" }),
};
