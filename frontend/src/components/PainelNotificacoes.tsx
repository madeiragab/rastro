import { useEffect, useState } from "react";
import * as pushWeb from "../push";
import * as nativo from "../nativo";

// No APK o push é nativo (FCM); no navegador, Web Push. Mesma interface.
const push = nativo.ehNativo
  ? { estado: nativo.estadoPush, ativar: nativo.ativarPush, desativar: nativo.desativarPush }
  : pushWeb;
type EstadoPush = pushWeb.EstadoPush;

const EXPLICACAO: Record<EstadoPush, string> = {
  ativo: "Este aparelho recebe alerta mesmo com o app fechado.",
  desativado: "Hoje o alerta só aparece com o app aberto.",
  negado: nativo.ehNativo
    ? "As notificações do Rastro estão bloqueadas. Libere em Configurações > Apps > Rastro > Notificações."
    : "As notificações foram bloqueadas para este site. Para reativar, libere nas configurações do navegador.",
  indisponivel: nativo.ehNativo
    ? "Push indisponível neste build: falta configurar o Firebase (google-services.json)."
    : "Este navegador não permite notificação aqui. Push exige HTTPS — em rede local, sem certificado, não funciona.",
};

export function PainelNotificacoes() {
  const [estado, setEstado] = useState<EstadoPush>("desativado");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    push.estado().then(setEstado).catch(() => setEstado("indisponivel"));
  }, []);

  async function alternar() {
    setOcupado(true);
    setErro(null);
    try {
      setEstado(estado === "ativo" ? await push.desativar() : await push.ativar());
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : String(falha));
    } finally {
      setOcupado(false);
    }
  }

  const podeAlternar = estado === "ativo" || estado === "desativado";

  return (
    <div className="bloco">
      <div className="bloco-titulo">Notificações</div>

      <div className="linha-dado">
        <span>Alerta no celular</span>
        <span className="etiqueta">{estado === "ativo" ? "ligado" : "desligado"}</span>
      </div>

      <div className="dica">{EXPLICACAO[estado]}</div>

      {podeAlternar && (
        <button className="botao" onClick={alternar} disabled={ocupado}>
          {ocupado ? "..." : estado === "ativo" ? "Desativar neste aparelho" : "Ativar neste aparelho"}
        </button>
      )}

      {erro && <div className="erro">{erro}</div>}
    </div>
  );
}
