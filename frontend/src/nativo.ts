/**
 * Recursos do app Android (Capacitor + Firebase nativo).
 *
 * - **Push (FCM)**: no APK não existe Web Push (a WebView não tem Service
 *   Worker de push). O alerta chega pelo Firebase Cloud Messaging.
 * - **Crashlytics**: erro de JavaScript não tratado vira relatório no console
 *   do Firebase, junto com os crashes nativos.
 * - **Analytics**: poucos eventos, sem dado pessoal — só "entrou", "saiu",
 *   "resolveu alerta".
 *
 * Tudo falha em silêncio: sem `google-services.json` no build, o Firebase
 * nativo não inicializa e o app segue funcionando, só sem esses três.
 */

import { Capacitor } from "@capacitor/core";
import { api } from "./api";
import { firebaseAtivo } from "./firebase";

export const ehNativo = Capacitor.isNativePlatform();

let tokenFcm: string | null = null;
let ouvindoToken = false;

// --------------------------------------------------------------- push
export type EstadoPushNativo = "indisponivel" | "negado" | "desativado" | "ativo";

export async function estadoPush(): Promise<EstadoPushNativo> {
  if (!ehNativo) return "indisponivel";
  try {
    const { FirebaseMessaging } = await import("@capacitor-firebase/messaging");
    const { receive } = await FirebaseMessaging.checkPermissions();
    if (receive === "denied") return "negado";
    return tokenFcm ? "ativo" : "desativado";
  } catch {
    return "indisponivel";
  }
}

/** Pede permissão, pega o token do FCM e registra na API. */
export async function ativarPush(): Promise<EstadoPushNativo> {
  if (!ehNativo) return "indisponivel";
  const { FirebaseMessaging } = await import("@capacitor-firebase/messaging");

  const { receive } = await FirebaseMessaging.requestPermissions();
  if (receive !== "granted") return receive === "denied" ? "negado" : "desativado";

  // Canal próprio com importância alta: no Android 8+, é o canal que decide
  // se a notificação faz som e aparece por cima da tela.
  await FirebaseMessaging.createChannel({
    id: "alertas",
    name: "Alertas do rebanho",
    description: "Animal fora da área, parado ou sem sinal",
    importance: 5,
    visibility: 1,
    vibration: true,
    lights: true,
    lightColor: "#2E9E63",
  }).catch(() => undefined);

  const { token } = await FirebaseMessaging.getToken();
  await api.registrarFcm(token);
  tokenFcm = token;

  if (!ouvindoToken) {
    ouvindoToken = true;
    // O FCM troca o token de tempos em tempos; o servidor precisa do novo.
    await FirebaseMessaging.addListener("tokenReceived", ({ token: novo }) => {
      tokenFcm = novo;
      api.registrarFcm(novo).catch(() => undefined);
    });
  }
  return "ativo";
}

export async function desativarPush(): Promise<EstadoPushNativo> {
  if (!ehNativo || !tokenFcm) return "desativado";
  const { FirebaseMessaging } = await import("@capacitor-firebase/messaging");
  // Servidor primeiro: na ordem inversa, uma falha de rede deixaria a API
  // mandando alerta para um token morto.
  await api.cancelarFcm(tokenFcm).catch(() => undefined);
  await FirebaseMessaging.deleteToken().catch(() => undefined);
  tokenFcm = null;
  return "desativado";
}

/** Depois do login: no app nativo o push liga sozinho (é o motivo do app). */
export async function aoEntrar(): Promise<void> {
  evento("login");
  if (!ehNativo) return;
  await ativarPush().catch((erro) => registrarErro(erro, "ativar push"));
}

export async function aoSair(): Promise<void> {
  evento("logout");
  await desativarPush().catch(() => undefined);
}

// ---------------------------------------------------------- analytics
export function evento(nome: string, parametros: Record<string, string | number> = {}): void {
  // No navegador o Analytics só liga com o Firebase configurado; no APK o
  // plugin nativo cuida disso pelo google-services.json.
  if (!ehNativo && !firebaseAtivo) return;
  import("@capacitor-firebase/analytics")
    .then(({ FirebaseAnalytics }) => FirebaseAnalytics.logEvent({ name: nome, params: parametros }))
    .catch(() => undefined);
}

// --------------------------------------------------------- crashlytics
export function registrarErro(erro: unknown, contexto = ""): void {
  if (!ehNativo) return;
  const mensagem = erro instanceof Error ? `${erro.name}: ${erro.message}` : String(erro);
  import("@capacitor-firebase/crashlytics")
    .then(({ FirebaseCrashlytics }) =>
      FirebaseCrashlytics.recordException({
        message: contexto ? `[${contexto}] ${mensagem}` : mensagem,
      }),
    )
    .catch(() => undefined);
}

/** Liga a captura global de erros. Chamado uma vez, no main. */
export function iniciarMonitoramento(): void {
  if (!ehNativo) return;
  window.addEventListener("error", (e) => registrarErro(e.error ?? e.message, "window.onerror"));
  window.addEventListener("unhandledrejection", (e) => registrarErro(e.reason, "promise"));
}
