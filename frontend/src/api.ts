import type {
  Alerta,
  Animal,
  ChaveGateway,
  ChaveGatewayCriada,
  Comportamento,
  Fazenda,
  Papel,
  Pasto,
  Posicao,
  Resumo,
  RespostaLogin,
  Usuario,
  UsuarioCriado,
} from "./types";
import * as fb from "./firebase";

/**
 * Onde está a API. No navegador é a mesma origem ("/api", via proxy do Vite,
 * do nginx ou do Firebase Hosting). No APK o app roda em https://localhost,
 * então precisa do endereço completo — `VITE_API_URL` no build.
 */
const BASE = ((import.meta.env.VITE_API_URL as string | undefined) || "/api").replace(/\/$/, "");

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
  if (fb.firebaseAtivo) {
    // Login pelo Firebase: o SDK renova o ID token sozinho; `forcar` só no
    // segundo tiro, depois de um 401 (relógio do aparelho adiantado, revogação).
    const token = await fb.idToken(jaRenovou).catch(() => null);
    if (token) cabecalhos.Authorization = `Bearer ${token}`;
  } else if (accessToken) {
    cabecalhos.Authorization = `Bearer ${accessToken}`;
  }

  const resposta = await fetch(`${BASE}${caminho}`, {
    credentials: "same-origin",
    ...init,
    headers: cabecalhos,
  });

  // Access token expirado: renova uma vez e repete. `jaRenovou` impede laço
  // infinito quando o refresh também não vale mais.
  if (resposta.status === 401 && !jaRenovou && (fb.firebaseAtivo || !caminho.startsWith("/auth/"))) {
    if (fb.firebaseAtivo) return pedir<T>(caminho, init, true);
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
    if (fb.firebaseAtivo) {
      const [auth, { signInWithEmailAndPassword }] = await Promise.all([
        fb.obterAuth(),
        import("firebase/auth"),
      ]);
      try {
        await signInWithEmailAndPassword(auth, email, senha);
      } catch (erro) {
        throw new ErroApi(401, fb.mensagemDeErro(erro));
      }
      try {
        const usuario = await pedir<Usuario>("/auth/eu");
        return { access_token: "", token_type: "bearer", expira_em_s: 3600, usuario };
      } catch (erro) {
        // Entrou no Firebase mas não tem cadastro nesta fazenda.
        await auth.signOut();
        if (erro instanceof ErroApi && erro.status === 401) {
          throw new ErroApi(401, "conta sem acesso a nenhuma fazenda. Peça ao dono para cadastrar seu e-mail.");
        }
        throw erro;
      }
    }
    const dados = await pedir<RespostaLogin>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, senha }),
    });
    accessToken = dados.access_token;
    return dados;
  },

  /** Restaura a sessão na carga da página, usando o cookie de refresh. */
  async restaurarSessao(): Promise<Usuario | null> {
    if (fb.firebaseAtivo) {
      if (!(await fb.usuarioAtual().catch(() => null))) return null;
      try {
        return await pedir<Usuario>("/auth/eu");
      } catch {
        return null;
      }
    }
    if (!(await renovar())) return null;
    try {
      return await pedir<Usuario>("/auth/eu");
    } catch {
      return null;
    }
  },

  async logout(): Promise<void> {
    if (fb.firebaseAtivo) {
      const auth = await fb.obterAuth();
      await auth.signOut();
      return;
    }
    try {
      await pedir<void>("/auth/logout", {
        method: "POST",
        headers: { "X-CSRF-Token": lerCookie("rastro_csrf") },
      });
    } finally {
      accessToken = null;
    }
  },

  async trocarSenha(senha_atual: string, senha_nova: string): Promise<void> {
    if (fb.firebaseAtivo) {
      // Mesma régua do login local: 12+ caracteres.
      if (senha_nova.length < 12) throw new ErroApi(422, "a senha precisa ter pelo menos 12 caracteres");
      const auth = await fb.obterAuth();
      const m = await import("firebase/auth");
      const atual = auth.currentUser;
      if (!atual?.email) throw new ErroApi(401, "sessão expirada");
      try {
        await m.reauthenticateWithCredential(atual, m.EmailAuthProvider.credential(atual.email, senha_atual));
      } catch {
        throw new ErroApi(400, "senha atual incorreta");
      }
      try {
        await m.updatePassword(atual, senha_nova);
      } catch (erro) {
        throw new ErroApi(422, fb.mensagemDeErro(erro));
      }
      return;
    }
    return pedir<void>("/auth/senha", {
      method: "POST",
      body: JSON.stringify({ senha_atual, senha_nova }),
    });
  },

  /** Responde 202 exista ou não a conta — a resposta não confirma cadastro. */
  async esqueciSenha(email: string): Promise<{ detail: string }> {
    if (fb.firebaseAtivo) {
      const [auth, { sendPasswordResetEmail }] = await Promise.all([
        fb.obterAuth(),
        import("firebase/auth"),
      ]);
      // Erro de "conta não existe" é engolido de propósito: a resposta não
      // pode confirmar cadastro. Só falha de rede chega à pessoa.
      await sendPasswordResetEmail(auth, email).catch((erro) => {
        if ((erro as { code?: string })?.code === "auth/network-request-failed") {
          throw new ErroApi(0, fb.mensagemDeErro(erro));
        }
      });
      return { detail: "ok" };
    }
    return pedir<{ detail: string }>("/auth/esqueci", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
  },

  /** Qual login o backend espera. Público. */
  modoAuth: () => pedir<{ modo: "local" | "firebase" }>("/auth/modo"),

  redefinirSenha: (token: string, senha_nova: string) =>
    pedir<void>("/auth/redefinir", {
      method: "POST",
      body: JSON.stringify({ token, senha_nova }),
    }),

  // --------------------------------------------------------------- push
  chavePublicaPush: () => pedir<{ chave: string }>("/push/chave-publica"),

  inscreverPush: (dados: { endpoint: string; chave_p256dh: string; chave_auth: string }) =>
    pedir<unknown>("/push/inscricoes", { method: "POST", body: JSON.stringify(dados) }),

  registrarFcm: (token: string) =>
    pedir<void>("/push/fcm", { method: "POST", body: JSON.stringify({ token, plataforma: "android" }) }),

  cancelarFcm: (token: string) =>
    pedir<void>("/push/fcm", { method: "DELETE", body: JSON.stringify({ token, plataforma: "android" }) }),

  cancelarPush: (dados: { endpoint: string; chave_p256dh: string; chave_auth: string }) =>
    pedir<void>("/push/inscricoes", { method: "DELETE", body: JSON.stringify(dados) }),

  // ------------------------------------------------------------- equipe
  usuarios: () => pedir<Usuario[]>("/usuarios"),

  criarUsuario: (email: string, nome: string, papel: Papel) =>
    pedir<UsuarioCriado>("/usuarios", {
      method: "POST",
      body: JSON.stringify({ email, nome, papel }),
    }),

  alterarUsuario: (id: number, mudanca: { papel?: Papel; ativo?: boolean }) =>
    pedir<Usuario>(`/usuarios/${id}`, {
      method: "PATCH",
      body: JSON.stringify(mudanca),
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
