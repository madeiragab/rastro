/**
 * Firebase no app: login (Auth) e métricas de uso (Analytics).
 *
 * Tudo é ligado pelas variáveis `VITE_FIREBASE_*` no momento do build. Sem
 * elas, `firebaseAtivo` é falso e o app usa o login próprio da API, como
 * sempre — nada do SDK do Firebase é carregado.
 *
 * O backend precisa estar no mesmo modo (`AUTH_MODO=firebase`). O app confere
 * isso em `/api/auth/modo` e avisa se os dois discordarem.
 */

import type { FirebaseApp } from "firebase/app";
import type { Auth, User } from "firebase/auth";

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string | undefined,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET as string | undefined,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID as string | undefined,
  appId: import.meta.env.VITE_FIREBASE_APP_ID as string | undefined,
  measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID as string | undefined,
};

export const firebaseAtivo = Boolean(config.apiKey && config.projectId && config.appId);

let appPromessa: Promise<FirebaseApp> | null = null;
let authPromessa: Promise<Auth> | null = null;

function obterApp(): Promise<FirebaseApp> {
  if (!firebaseAtivo) return Promise.reject(new Error("Firebase não configurado neste build."));
  // Import dinâmico: quem não usa Firebase não baixa o SDK.
  appPromessa ??= import("firebase/app").then(({ initializeApp }) => initializeApp(config));
  return appPromessa;
}

export function obterAuth(): Promise<Auth> {
  authPromessa ??= Promise.all([obterApp(), import("firebase/auth")]).then(
    async ([app, m]) => {
      const auth = m.initializeAuth(app, {
        // IndexedDB primeiro: sobrevive a fechar o app. Diferente do token da
        // API local, quem guarda a sessão aqui é o SDK do Firebase.
        persistence: [m.indexedDBLocalPersistence, m.browserLocalPersistence],
      });
      auth.languageCode = "pt-BR";
      return auth;
    },
  );
  return authPromessa;
}

/** Espera o SDK decidir se há sessão salva. Só a primeira emissão importa. */
export async function usuarioAtual(): Promise<User | null> {
  const auth = await obterAuth();
  await auth.authStateReady();
  return auth.currentUser;
}

export async function idToken(forcar = false): Promise<string | null> {
  const auth = await obterAuth();
  return auth.currentUser ? auth.currentUser.getIdToken(forcar) : null;
}

/** Mensagens do Firebase traduzidas — e genéricas onde precisam ser. */
export function mensagemDeErro(erro: unknown): string {
  const codigo = (erro as { code?: string })?.code ?? "";
  switch (codigo) {
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
    case "auth/invalid-email":
      // Igual ao login local: não diz qual dos dois errou.
      return "e-mail ou senha incorretos";
    case "auth/user-disabled":
      return "conta desativada";
    case "auth/too-many-requests":
      return "muitas tentativas. Aguarde alguns minutos.";
    case "auth/network-request-failed":
      return "sem conexão com a internet";
    case "auth/weak-password":
    case "auth/password-does-not-meet-requirements":
      return "senha fraca demais";
    case "auth/requires-recent-login":
      return "por segurança, saia e entre de novo antes de trocar a senha";
    default:
      return erro instanceof Error ? erro.message : "falha no login";
  }
}
