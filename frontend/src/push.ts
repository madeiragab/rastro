/**
 * Registro de notificação push no navegador.
 *
 * Sem framework: são três passos do padrão Web Push — registrar o Service
 * Worker, pedir permissão, assinar. O resto é converter formato de chave.
 *
 * Independente do React de propósito, como `api.ts` e `types.ts`: o app React
 * Native planejado troca este módulo por notificação nativa e não toca no resto.
 */

import { api } from "./api";

export type EstadoPush =
  | "indisponivel" // navegador não suporta, ou contexto não é seguro
  | "negado" // pessoa recusou a permissão
  | "desativado" // suportado, ainda não assinou
  | "ativo";

/**
 * O navegador exige a chave como bytes; a API entrega base64url.
 *
 * O buffer é alocado explicitamente, e o tipo de retorno não é anotado, porque
 * `Uint8Array.from` produz `Uint8Array<ArrayBufferLike>` — que o TypeScript
 * recente recusa onde se espera `BufferSource` respaldado por `ArrayBuffer`.
 */
function base64UrlParaBytes(base64: string) {
  const preenchido = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), "=");
  const normalizado = preenchido.replace(/-/g, "+").replace(/_/g, "/");
  const bruto = atob(normalizado);

  const buffer = new ArrayBuffer(bruto.length);
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bruto.length; i += 1) bytes[i] = bruto.charCodeAt(i);
  return bytes;
}

function bytesParaBase64Url(buffer: ArrayBuffer | null): string {
  if (!buffer) return "";
  const bytes = new Uint8Array(buffer);
  let texto = "";
  for (const b of bytes) texto += String.fromCharCode(b);
  return btoa(texto).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function suportado(): boolean {
  // `isSecureContext` é o que separa "não dá" de "não dá aqui": HTTP em IP da
  // rede local não é contexto seguro, e Service Worker não registra.
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window &&
    window.isSecureContext
  );
}

export async function estado(): Promise<EstadoPush> {
  if (!suportado()) return "indisponivel";
  if (Notification.permission === "denied") return "negado";

  const registro = await navigator.serviceWorker.getRegistration();
  const inscricao = await registro?.pushManager.getSubscription();
  return inscricao ? "ativo" : "desativado";
}

export async function ativar(): Promise<EstadoPush> {
  if (!suportado()) return "indisponivel";

  const permissao = await Notification.requestPermission();
  if (permissao !== "granted") return permissao === "denied" ? "negado" : "desativado";

  const registro = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;

  const { chave } = await api.chavePublicaPush();

  // Se já existe inscrição, reaproveita: assinar de novo geraria um endpoint
  // novo e o servidor passaria a manter dois para o mesmo aparelho.
  const inscricao =
    (await registro.pushManager.getSubscription()) ??
    (await registro.pushManager.subscribe({
      // Obrigatório nos navegadores atuais: proíbe push silencioso, isto é,
      // usar o canal para acordar a página sem avisar a pessoa.
      userVisibleOnly: true,
      applicationServerKey: base64UrlParaBytes(chave),
    }));

  await api.inscreverPush({
    endpoint: inscricao.endpoint,
    chave_p256dh: bytesParaBase64Url(inscricao.getKey("p256dh")),
    chave_auth: bytesParaBase64Url(inscricao.getKey("auth")),
  });

  return "ativo";
}

export async function desativar(): Promise<EstadoPush> {
  const registro = await navigator.serviceWorker.getRegistration();
  const inscricao = await registro?.pushManager.getSubscription();
  if (!inscricao) return "desativado";

  // Avisa o servidor antes de cancelar no navegador: na ordem inversa, uma
  // falha de rede deixaria o servidor mandando push para um endpoint morto.
  await api
    .cancelarPush({
      endpoint: inscricao.endpoint,
      chave_p256dh: bytesParaBase64Url(inscricao.getKey("p256dh")),
      chave_auth: bytesParaBase64Url(inscricao.getKey("auth")),
    })
    .catch(() => undefined);

  await inscricao.unsubscribe();
  return "desativado";
}
