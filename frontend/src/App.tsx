import type { Map as MapaLeaflet } from "leaflet";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";
import { FeedAlertas } from "./components/FeedAlertas";
import { FolhaInferior, type Posicao as PosicaoFolha } from "./components/FolhaInferior";
import { ListaAnimais } from "./components/ListaAnimais";
import { MapaView } from "./components/MapaView";
import { PainelSimulacao } from "./components/PainelSimulacao";
import { TirasResumo } from "./components/TirasResumo";
import type { Alerta, Animal, Comportamento, Fazenda, Pasto, Posicao, Resumo } from "./types";

const INTERVALO_POLL_MS = 3000;

type Aba = "rebanho" | "alertas" | "simular";

export default function App() {
  const [fazenda, setFazenda] = useState<Fazenda | null>(null);
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [pastos, setPastos] = useState<Pasto[]>([]);
  const [animais, setAnimais] = useState<Animal[]>([]);
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [trilha, setTrilha] = useState<Posicao[]>([]);

  const [selecionadoId, setSelecionadoId] = useState<number | null>(null);
  const [online, setOnline] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const [aba, setAba] = useState<Aba>("rebanho");
  const [posicaoFolha, setPosicaoFolha] = useState<PosicaoFolha>("min");

  const [modoDesenho, setModoDesenho] = useState(false);
  const [pontosDesenho, setPontosDesenho] = useState<[number, number][]>([]);
  const [nomeNovoPasto, setNomeNovoPasto] = useState("");

  const mapaRef = useRef<MapaLeaflet | null>(null);
  const selecionadoRef = useRef<number | null>(null);
  selecionadoRef.current = selecionadoId;

  const carregar = useCallback(async () => {
    try {
      const [novoResumo, novosPastos, novosAnimais, novosAlertas] = await Promise.all([
        api.resumo(),
        api.pastos(),
        api.animais(),
        api.alertas(true),
      ]);

      setResumo(novoResumo);
      setPastos(novosPastos);
      setAnimais(novosAnimais);
      setAlertas(novosAlertas);

      const id = selecionadoRef.current;
      setTrilha(id ? await api.trilha(id, 40) : []);

      setOnline(true);
      setErro(null);
    } catch (falha) {
      setOnline(false);
      setErro(falha instanceof Error ? falha.message : String(falha));
    }
  }, []);

  useEffect(() => {
    api.fazenda().then(setFazenda).catch(() => undefined);
  }, []);

  useEffect(() => {
    carregar();
    const timer = window.setInterval(carregar, INTERVALO_POLL_MS);
    return () => window.clearInterval(timer);
  }, [carregar]);

  const selecionado = animais.find((a) => a.id === selecionadoId) ?? null;

  // ------------------------------------------------------------------ acoes
  /** Selecionar do mapa recolhe a folha para o animal ficar visivel. */
  function selecionarDoMapa(animal: Animal) {
    setSelecionadoId(animal.id);
    setPosicaoFolha("min");
  }

  function irParaAnimal(animalId: number) {
    setSelecionadoId(animalId);
    setPosicaoFolha("min");
  }

  function trocarAba(nova: Aba) {
    setAba(nova);
    if (posicaoFolha === "min") setPosicaoFolha("meio");
  }

  function enquadrarRebanho() {
    const mapa = mapaRef.current;
    const pontos = animais
      .filter((a) => a.lat !== null && a.lon !== null)
      .map((a) => [a.lat as number, a.lon as number] as [number, number]);

    if (!mapa || !pontos.length) return;
    mapa.fitBounds(pontos, { padding: [50, 50], maxZoom: 16 });
  }

  async function definirCenario(comportamento: Comportamento) {
    if (!selecionado) return;
    try {
      await api.definirCenario(selecionado.id, comportamento);
      await carregar();
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : String(falha));
    }
  }

  async function reiniciarSimulacao() {
    await api.reiniciarSimulacao().catch(() => undefined);
    await carregar();
  }

  async function resolverAlerta(alertaId: number) {
    setAlertas((atuais) => atuais.filter((a) => a.id !== alertaId));
    await api.resolverAlerta(alertaId).catch(() => undefined);
    await carregar();
  }

  function iniciarDesenho() {
    setModoDesenho(true);
    setPontosDesenho([]);
    setNomeNovoPasto("");
    setPosicaoFolha("min");
  }

  function cancelarDesenho() {
    setModoDesenho(false);
    setPontosDesenho([]);
  }

  async function salvarPasto() {
    if (pontosDesenho.length < 3) return;
    try {
      await api.criarPasto({
        nome: nomeNovoPasto.trim() || `Pasto ${pastos.length + 1}`,
        cor: "#8E6FCB",
        buffer_m: 25,
        pontos: pontosDesenho,
      });
      cancelarDesenho();
      await carregar();
    } catch (falha) {
      setErro(falha instanceof Error ? falha.message : String(falha));
    }
  }

  // ------------------------------------------------------------------ abas
  const abas = (
    <>
      <button
        className={`aba ${aba === "rebanho" ? "ativa" : ""}`}
        onClick={() => trocarAba("rebanho")}
      >
        Rebanho
      </button>
      <button
        className={`aba ${aba === "alertas" ? "ativa" : ""}`}
        onClick={() => trocarAba("alertas")}
      >
        Alertas
        {alertas.length > 0 && <span className="selo">{alertas.length}</span>}
      </button>
      <button
        className={`aba ${aba === "simular" ? "ativa" : ""}`}
        onClick={() => trocarAba("simular")}
      >
        Simular
      </button>
    </>
  );

  // ---------------------------------------------------------------- render
  return (
    <div className="app">
      <div className="mapa-fundo">
        <MapaView
          pastos={pastos}
          animais={animais}
          selecionado={selecionado}
          trilha={trilha}
          onSelecionar={selecionarDoMapa}
          modoDesenho={modoDesenho}
          pontosDesenho={pontosDesenho}
          onAdicionarPonto={(ponto) => setPontosDesenho((atuais) => [...atuais, ponto])}
          onMapaPronto={(mapa) => {
            mapaRef.current = mapa;
          }}
        />
      </div>

      <header className="barra-topo">
        <div className="marca">
          <div className="marca-nome">
            Rastro<span>.</span>
          </div>
          <div className="marca-fazenda">{fazenda?.nome ?? ""}</div>
        </div>
        <div className={`pulso ${online ? "" : "off"}`}>
          <i />
          {online ? "ao vivo" : "sem conexão"}
        </div>
      </header>

      {modoDesenho && (
        <div className="painel-desenho" style={{ top: "calc(var(--topo-seguro) + 62px)" }}>
          <div className="painel-desenho-texto">
            Toque no mapa para marcar os vértices do pasto.{" "}
            <strong>{pontosDesenho.length} ponto(s)</strong> — mínimo 3.
          </div>
          <div className="painel-desenho-linha">
            <input
              className="campo"
              placeholder="Nome do pasto"
              value={nomeNovoPasto}
              onChange={(evento) => setNomeNovoPasto(evento.target.value)}
            />
            <button
              className="botao"
              onClick={() => setPontosDesenho((p) => p.slice(0, -1))}
              disabled={!pontosDesenho.length}
            >
              Desfazer
            </button>
          </div>
          <div className="painel-desenho-linha">
            <button className="botao" onClick={cancelarDesenho} style={{ flex: 1 }}>
              Cancelar
            </button>
            <button
              className="botao primario"
              onClick={salvarPasto}
              disabled={pontosDesenho.length < 3}
              style={{ flex: 1 }}
            >
              Salvar pasto
            </button>
          </div>
        </div>
      )}

      {!modoDesenho && (
        <div className="acoes-mapa" style={{ bottom: "calc(104px + var(--base-segura) + 14px)" }}>
          <button className="fab" onClick={enquadrarRebanho} aria-label="Enquadrar rebanho">
            ⊙
          </button>
          <button
            className="fab destaque"
            onClick={iniciarDesenho}
            aria-label="Desenhar novo pasto"
          >
            ⬡
          </button>
        </div>
      )}

      <FolhaInferior
        posicao={posicaoFolha}
        onPosicao={setPosicaoFolha}
        resumo={<TirasResumo resumo={resumo} />}
        abas={abas}
      >
        {erro && <div className="erro">{erro}</div>}

        {aba === "rebanho" && (
          <ListaAnimais
            animais={animais}
            selecionado={selecionado}
            onSelecionar={(animal) => setSelecionadoId(animal.id)}
          />
        )}

        {aba === "alertas" && (
          <FeedAlertas alertas={alertas} onResolver={resolverAlerta} onIrPara={irParaAnimal} />
        )}

        {aba === "simular" && (
          <PainelSimulacao
            selecionado={selecionado}
            onCenario={definirCenario}
            onReiniciar={reiniciarSimulacao}
          />
        )}
      </FolhaInferior>
    </div>
  );
}
