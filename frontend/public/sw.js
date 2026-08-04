/* Service Worker do Rastro.
 *
 * Faz uma coisa só: receber push e mostrar notificação. Sem cache offline —
 * um app de rastreamento que serve mapa velho do cache é pior que um app que
 * avisa que está sem conexão.
 *
 * Só registra em contexto seguro: HTTPS ou localhost. Para abrir no celular
 * pela rede local é preciso TLS.
 */

self.addEventListener("install", () => {
  // Assume o controle sem esperar a aba antiga fechar.
  self.skipWaiting();
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(self.clients.claim());
});

self.addEventListener("push", (evento) => {
  let dados = {};
  try {
    dados = evento.data ? evento.data.json() : {};
  } catch {
    dados = {};
  }

  const titulo = dados.titulo || "Rastro";
  const opcoes = {
    body: dados.mensagem || "Há um alerta no rebanho.",
    icon: "/icone.svg",
    badge: "/icone.svg",
    // Agrupa por tipo: três animais fora da área não viram três avisos
    // empilhados na barra de notificação.
    tag: dados.tipo || "alerta",
    renotify: true,
    // Alerta de rebanho não some sozinho — o produtor pode estar com as mãos
    // ocupadas quando chega.
    requireInteraction: true,
    data: { animal_id: dados.animal_id ?? null },
  };

  evento.waitUntil(self.registration.showNotification(titulo, opcoes));
});

self.addEventListener("notificationclick", (evento) => {
  evento.notification.close();

  const destino = "/";
  evento.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((janelas) => {
        // Reaproveita uma aba já aberta em vez de abrir outra.
        for (const janela of janelas) {
          if ("focus" in janela) return janela.focus();
        }
        return self.clients.openWindow(destino);
      }),
  );
});
