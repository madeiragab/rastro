import type { Map as MapaLeaflet } from "leaflet";
import { useEffect, useRef } from "react";
import {
  CircleMarker,
  MapContainer,
  Polygon,
  Polyline,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from "react-leaflet";
import type { Animal, Pasto, Posicao } from "../types";
import { CORES_STATUS, ROTULOS_STATUS } from "../types";

interface Props {
  pastos: Pasto[];
  animais: Animal[];
  selecionado: Animal | null;
  trilha: Posicao[];
  onSelecionar: (animal: Animal) => void;
  modoDesenho: boolean;
  pontosDesenho: [number, number][];
  onAdicionarPonto: (ponto: [number, number]) => void;
  onMapaPronto: (mapa: MapaLeaflet) => void;
}

/** Captura toques no mapa enquanto o produtor desenha o poligono do pasto. */
function CapturaToques({ ativo, onPonto }: { ativo: boolean; onPonto: (p: [number, number]) => void }) {
  useMapEvents({
    click(evento) {
      if (ativo) onPonto([evento.latlng.lat, evento.latlng.lng]);
    },
  });
  return null;
}

/**
 * Centraliza no animal recem-selecionado.
 *
 * So reage a troca de animal, nunca a chegada de uma posicao nova: no celular
 * um mapa que se move sozinho a cada leitura e insuportavel.
 */
function SeguirSelecionado({ selecionado }: { selecionado: Animal | null }) {
  const mapa = useMap();
  const ultimoId = useRef<number | null>(null);

  useEffect(() => {
    if (!selecionado || selecionado.lat === null || selecionado.lon === null) return;
    if (ultimoId.current === selecionado.id) return;

    ultimoId.current = selecionado.id;
    mapa.flyTo([selecionado.lat, selecionado.lon], Math.max(mapa.getZoom(), 16), {
      duration: 0.6,
    });
  }, [selecionado, mapa]);

  return null;
}

/** Entrega a instancia do mapa para o componente pai, para os botoes flutuantes. */
function Publicar({ onMapa }: { onMapa: (mapa: MapaLeaflet) => void }) {
  const mapa = useMap();
  useEffect(() => onMapa(mapa), [mapa, onMapa]);
  return null;
}

function raio(animal: Animal, selecionado: boolean): number {
  if (selecionado) return 12;
  return animal.status === "ok" ? 8 : 10;
}

export function MapaView({
  pastos,
  animais,
  selecionado,
  trilha,
  onSelecionar,
  modoDesenho,
  pontosDesenho,
  onAdicionarPonto,
  onMapaPronto,
}: Props) {
  const primeiro = pastos[0]?.pontos ?? [];
  const centro: [number, number] = primeiro.length
    ? [
        primeiro.reduce((soma, p) => soma + p[0], 0) / primeiro.length,
        primeiro.reduce((soma, p) => soma + p[1], 0) / primeiro.length,
      ]
    : [-19.7472, -47.9312];

  return (
    <MapContainer center={centro} zoom={15} zoomControl={false} scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      <Publicar onMapa={onMapaPronto} />
      <SeguirSelecionado selecionado={selecionado} />
      <CapturaToques ativo={modoDesenho} onPonto={onAdicionarPonto} />

      {pastos.map((pasto) => (
        <Polygon
          key={pasto.id}
          positions={pasto.pontos}
          pathOptions={{ color: pasto.cor, weight: 2, fillOpacity: 0.12 }}
        >
          <Popup>
            <div className="popup-titulo">{pasto.nome}</div>
            <div className="popup-linha">
              {pasto.area_ha} ha · {pasto.total_animais} animais
            </div>
            <div className="popup-linha">tolerância de {pasto.buffer_m} m</div>
          </Popup>
        </Polygon>
      ))}

      {/* Poligono em construcao */}
      {pontosDesenho.length > 1 && (
        <Polyline positions={pontosDesenho} pathOptions={{ color: "#2E9E63", weight: 2, dashArray: "6 6" }} />
      )}
      {pontosDesenho.map((ponto, indice) => (
        <CircleMarker
          key={`desenho-${indice}`}
          center={ponto}
          radius={6}
          pathOptions={{ color: "#2E9E63", fillColor: "#2E9E63", fillOpacity: 1 }}
        />
      ))}

      {/* Trilha do animal selecionado */}
      {selecionado && trilha.length > 1 && (
        <Polyline
          positions={trilha.map((p) => [p.lat, p.lon] as [number, number])}
          pathOptions={{ color: CORES_STATUS[selecionado.status], weight: 2, opacity: 0.65 }}
        />
      )}

      {animais
        .filter((animal) => animal.lat !== null && animal.lon !== null)
        .map((animal) => {
          const estaSelecionado = selecionado?.id === animal.id;
          const cor = CORES_STATUS[animal.status];
          return (
            <CircleMarker
              key={animal.id}
              center={[animal.lat as number, animal.lon as number]}
              radius={raio(animal, estaSelecionado)}
              pathOptions={{
                color: estaSelecionado ? "#FFFFFF" : cor,
                weight: estaSelecionado ? 3 : 2,
                fillColor: cor,
                fillOpacity: animal.status === "sem_sinal" ? 0.35 : 0.9,
              }}
              eventHandlers={{ click: () => onSelecionar(animal) }}
            >
              <Popup>
                <div className="popup-titulo">{animal.nome}</div>
                <div className="popup-linha">Brinco {animal.brinco}</div>
                <div className="popup-linha">
                  {ROTULOS_STATUS[animal.status]}
                  {animal.status === "fora_da_area" &&
                    ` · ${animal.distancia_pasto_m.toFixed(0)} m além da divisa`}
                </div>
                <div className="popup-linha">
                  {animal.pasto_nome ?? "sem pasto"} · bateria {animal.bateria_pct}%
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
    </MapContainer>
  );
}
