/**
 * Geometria do modo demonstração — o que o PostGIS faz na API.
 *
 * As distâncias usam projeção equiretangular local: para pastos de poucos
 * quilômetros o erro é de centímetros, bem abaixo do erro de um GPS.
 */

const M_POR_GRAU_LAT = 111_320;

type Ponto = [number, number]; // [lat, lon]

function paraMetros(lat: number, lon: number, lat0: number, lon0: number): [number, number] {
  const x = (lon - lon0) * M_POR_GRAU_LAT * Math.cos((lat0 * Math.PI) / 180);
  const y = (lat - lat0) * M_POR_GRAU_LAT;
  return [x, y];
}

/** Ray casting: o ponto está dentro do polígono? (equivale a ST_Contains) */
export function pontoDentro(lat: number, lon: number, poligono: Ponto[]): boolean {
  let dentro = false;
  for (let i = 0, j = poligono.length - 1; i < poligono.length; j = i, i += 1) {
    const [yi, xi] = poligono[i];
    const [yj, xj] = poligono[j];
    const cruza = yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi;
    if (cruza) dentro = !dentro;
  }
  return dentro;
}

/** Distância em metros até a borda do polígono; 0 se estiver dentro. */
export function distanciaAoPoligono(lat: number, lon: number, poligono: Ponto[]): number {
  if (pontoDentro(lat, lon, poligono)) return 0;
  let menor = Infinity;
  for (let i = 0; i < poligono.length; i += 1) {
    const a = paraMetros(poligono[i][0], poligono[i][1], lat, lon);
    const b = paraMetros(poligono[(i + 1) % poligono.length][0], poligono[(i + 1) % poligono.length][1], lat, lon);
    // Ponto P está na origem do sistema local.
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const t = Math.max(0, Math.min(1, -(a[0] * dx + a[1] * dy) / (dx * dx + dy * dy || 1)));
    menor = Math.min(menor, Math.hypot(a[0] + t * dx, a[1] + t * dy));
  }
  return menor;
}

export function areaHectares(poligono: Ponto[]): number {
  const [lat0, lon0] = poligono[0];
  let soma = 0;
  for (let i = 0; i < poligono.length; i += 1) {
    const [x1, y1] = paraMetros(poligono[i][0], poligono[i][1], lat0, lon0);
    const [x2, y2] = paraMetros(poligono[(i + 1) % poligono.length][0], poligono[(i + 1) % poligono.length][1], lat0, lon0);
    soma += x1 * y2 - x2 * y1;
  }
  return Math.abs(soma) / 2 / 10_000;
}

export function centroide(poligono: Ponto[]): Ponto {
  const lat = poligono.reduce((s, p) => s + p[0], 0) / poligono.length;
  const lon = poligono.reduce((s, p) => s + p[1], 0) / poligono.length;
  return [lat, lon];
}

export function metrosParaGraus(metros: number, lat: number): [number, number] {
  const dLat = metros / M_POR_GRAU_LAT;
  const dLon = metros / (M_POR_GRAU_LAT * Math.max(Math.cos((lat * Math.PI) / 180), 0.01));
  return [dLat, dLon];
}
