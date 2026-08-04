import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";

export type Posicao = "min" | "meio" | "max";

interface Props {
  posicao: Posicao;
  onPosicao: (posicao: Posicao) => void;
  /** Faixa compacta que continua visivel com a folha recolhida. */
  resumo: ReactNode;
  abas: ReactNode;
  children: ReactNode;
}

/** Fracao da altura da janela ocupada pela folha quando aberta por completo. */
const FRACAO_FOLHA = 0.88;
/** Altura visivel em cada parada, em px ou fracao da janela. */
const VISIVEL_MIN = 104;
const FRACAO_MEIO = 0.46;

/**
 * Folha deslizante com tres paradas, arrastavel pela alca.
 *
 * Escrita a mao em vez de trazer uma biblioteca de bottom sheet: sao ~60
 * linhas, e assim o comportamento de arrasto nao briga com o pan do Leaflet
 * logo atras.
 */
export function FolhaInferior({ posicao, onPosicao, resumo, abas, children }: Props) {
  const [alturaJanela, setAlturaJanela] = useState(() => window.innerHeight);
  const [arrastando, setArrastando] = useState(false);
  const [deslocamento, setDeslocamento] = useState<number | null>(null);

  const inicio = useRef({ y: 0, deslocamento: 0 });

  useEffect(() => {
    const aoRedimensionar = () => setAlturaJanela(window.innerHeight);
    window.addEventListener("resize", aoRedimensionar);
    return () => window.removeEventListener("resize", aoRedimensionar);
  }, []);

  const alturaFolha = alturaJanela * FRACAO_FOLHA;

  const paradas: Record<Posicao, number> = {
    max: 0,
    meio: Math.max(0, alturaFolha - alturaJanela * FRACAO_MEIO),
    min: Math.max(0, alturaFolha - VISIVEL_MIN),
  };

  const deslocamentoAtual = deslocamento ?? paradas[posicao];

  function aoPressionar(evento: ReactPointerEvent<HTMLDivElement>) {
    evento.currentTarget.setPointerCapture(evento.pointerId);
    inicio.current = { y: evento.clientY, deslocamento: paradas[posicao] };
    setArrastando(true);
    setDeslocamento(paradas[posicao]);
  }

  function aoMover(evento: ReactPointerEvent<HTMLDivElement>) {
    if (!arrastando) return;
    const bruto = inicio.current.deslocamento + (evento.clientY - inicio.current.y);
    setDeslocamento(Math.min(paradas.min, Math.max(paradas.max, bruto)));
  }

  function aoSoltar() {
    if (!arrastando) return;
    setArrastando(false);

    const atual = deslocamento ?? paradas[posicao];
    const maisProxima = (Object.keys(paradas) as Posicao[]).reduce((melhor, chave) =>
      Math.abs(paradas[chave] - atual) < Math.abs(paradas[melhor] - atual) ? chave : melhor,
    );

    setDeslocamento(null);
    onPosicao(maisProxima);
  }

  return (
    <section
      className={`folha ${arrastando ? "" : "animada"}`}
      style={{ height: alturaFolha, transform: `translateY(${deslocamentoAtual}px)` }}
      aria-label="Painel do rebanho"
    >
      <div
        className="folha-alca"
        onPointerDown={aoPressionar}
        onPointerMove={aoMover}
        onPointerUp={aoSoltar}
        onPointerCancel={aoSoltar}
        // Toque na alca alterna entre recolhida e meia altura.
        onClick={() => !arrastando && onPosicao(posicao === "min" ? "meio" : "min")}
        role="button"
        tabIndex={0}
        aria-label="Arrastar painel"
      />

      <div className="folha-resumo">{resumo}</div>
      <div className="folha-abas">{abas}</div>
      <div className="folha-conteudo">{children}</div>
    </section>
  );
}
