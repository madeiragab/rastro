# Rastro

**🇬🇧 English** · [🇧🇷 Português](README.pt-BR.md)

Real-time tracking and geofencing for cattle herds.

The rancher draws the pasture boundary on a map and gets alerted when an animal
**leaves the area**, **stops moving for too long**, or **loses connectivity**.

Mobile-first web app with a built-in herd simulator — runs with no hardware at all.

> **Status: MVP / demo.** Not production-ready. See [Before production](#before-production).

---

## Quick start

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| App | http://localhost:5173 |
| API docs (Swagger) | http://localhost:8000/docs |
| Database | localhost:5432 |

First boot creates the schema, enables PostGIS and loads demo data: one farm in
Uberaba (Minas Gerais, Brazil), two pastures and 14 animals. The simulator starts
producing telemetry right away.

Reset everything:

```bash
docker compose down -v
```

> **Windows note.** Docker Desktop needs the WSL2 backend. If `docker info` reports
> `no virtualization available`, WSL is missing — run `wsl --install` in an
> Administrator PowerShell, reboot, then start Docker Desktop again.

### Open it on your phone

The app is mobile-first. To open it on a real device on the same Wi-Fi, find your
machine's LAN IP and browse to `http://<your-ip>:5173`. On Android/Chrome you can
"Add to home screen" — a web manifest is included, so it launches standalone.

---

## How to demo it

The **Simulate** tab forces a scenario on the selected animal. Pick an animal from
the list or tap it on the map, then:

| Button | What happens |
|---|---|
| **Fugir do pasto** (Escape) | The animal walks straight past the boundary. After 2 consecutive readings beyond the tolerance zone, the geofence alert fires (~25 s). |
| **Ficar parado** (Go still) | Accelerometer activity drops to zero. After 90 s, the immobility alert fires. |
| **Perder sinal** (Lose signal) | The tag stops reporting. After 60 s of silence, the signal-loss alert fires. |
| **Pastando** (Grazing) | Back to normal; open alerts resolve on their own. |

To draw a new pasture: tap the **⬡** button, tap the vertices on the map, name it
and save.

---

## Interface

Mobile-first: the map fills the screen and everything else floats above it.

- **Bottom sheet** with three snap points — drag it, or tap the handle. Collapsed,
  it still shows a compact strip of counters.
- **Tabs**: Rebanho (herd), Alertas (alerts, with an unread badge), Simular (simulate).
- Tapping an animal flies the map to it — but the map never moves on its own when a
  new position arrives. A map that jumps around on every reading is unusable on a phone.
- At ≥900 px wide the sheet becomes a fixed side panel, so the same code works on desktop.

---

## Architecture

```
phone browser (React + Leaflet)
      │  HTTP /api  (Vite dev proxy)
FastAPI
      │
PostgreSQL + PostGIS
```

```
rastro/
├── docker-compose.yml
├── backend/
│   └── app/
│       ├── main.py            # bootstrap, CORS, lifespan, simulator task
│       ├── config.py          # EVERY alert threshold lives here
│       ├── database.py        # engine, session, schema creation
│       ├── models.py          # Fazenda, Pasto, Animal, Posicao, Alerta
│       ├── schemas.py         # request/response contracts
│       ├── seed.py            # demo data
│       ├── api/
│       │   ├── serializers.py # ORM -> schema (extracts lat/lon from geometry)
│       │   └── routes/        # one module per resource
│       └── services/
│           ├── geofence.py    # point-in-polygon and distance (PostGIS)
│           ├── alertas.py     # the three alert rules
│           ├── telemetria.py  # position ingestion (single entry point)
│           └── simulador.py   # virtual herd
└── frontend/
    └── src/
        ├── App.tsx            # state and polling
        ├── api.ts             # HTTP client  ← reusable by React Native
        ├── types.ts           # mirrors the backend schemas  ← reusable
        └── components/
            ├── MapaView.tsx
            ├── FolhaInferior.tsx   # bottom sheet, hand-rolled
            ├── TirasResumo.tsx
            ├── ListaAnimais.tsx
            ├── FeedAlertas.tsx
            └── PainelSimulacao.tsx
```

### Why PostGIS

Point-in-polygon runs in the database (`ST_Contains`), not in Python. The database
already has a spatial index, and distances in metres come out correct by casting to
`geography` — no projection error. As the herd grows, this is the decision that avoids
rewriting the data layer later.

`api.ts` and `types.ts` are framework-agnostic on purpose: the planned React Native
app reuses them as-is.

---

## The three alert rules

Each one carries its false-alarm mitigation. A rancher who gets a false alert
uninstalls the app — that is the product's main adoption risk, not the technology.

**1. Out of area.** A 25 m tolerance zone around the polygon, plus 2 consecutive
readings outside. Without it, GNSS error produces a constant false alarm whenever an
animal grazes near the fence.

**2. No movement.** Decided by the accelerometer, not by GNSS standing still. GNSS
alone lies: cattle lying down and ruminating stay static for hours under perfectly
normal conditions. This is the highest commercial-value alert — it detects death,
obstructed calving, animals stuck in mud, and fractures.

**3. Signal loss.** Threshold relative to each device's own reporting cadence, not a
fixed global value, because cadence varies by animal and by terrain. Covers three
distinct causes: tag ripped off (theft), dead battery, and dead-zone terrain.

All thresholds live in [`backend/app/config.py`](backend/app/config.py), **compressed
for demo purposes**. The realistic field values are documented next to each one
(immobility 4 h, reporting every 30 min).

---

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/fazenda` | Current farm (MVP is single-tenant) |
| `GET` | `/api/resumo` | Dashboard counters |
| `GET` | `/api/pastos` | List pastures with area and animal count |
| `POST` | `/api/pastos` | Create a pasture from drawn vertices |
| `DELETE` | `/api/pastos/{id}` | Remove a pasture (refuses if animals are attached) |
| `GET` | `/api/animais` | List animals with last position and status |
| `GET` | `/api/animais/{id}` | Single animal |
| `GET` | `/api/animais/{id}/trilha` | Recent position trail |
| `GET` | `/api/alertas` | Alerts, open by default |
| `POST` | `/api/alertas/{id}/resolver` | Resolve one alert |
| `POST` | `/api/alertas/animal/{id}/resolver` | Resolve every open alert for an animal |
| `POST` | `/api/telemetria` | **Position ingestion — the hardware entry point** |
| `POST` | `/api/simulacao/cenario` | Force a scenario (demo only) |
| `POST` | `/api/simulacao/reiniciar` | Reset the simulation (demo only) |

Full interactive reference at http://localhost:8000/docs.

---

## Plugging in real hardware

The simulator and a real gateway go through the same path. The gateway just calls:

```bash
curl -X POST http://localhost:8000/api/telemetria \
  -H "Content-Type: application/json" \
  -d '{"brinco":"076000000000001","lat":-19.7480,"lon":-47.9320,"atividade":0.6,"bateria_pct":88}'
```

No business rule changes. Turn the simulator off with `SIMULATOR_ENABLED=false`.

Tag IDs use 15 digits with the `076` prefix (Brazil's country code), aligned with
**PNIB** — the Brazilian national cattle identification programme, which makes
individual identification mandatory for all cattle movement from 2033.

---

## Before production

- **Authentication.** The API is wide open, including the telemetry endpoint, which
  accepts a position from any source. Needs a per-gateway key or mTLS, plus login on
  the panel. This is blocking for anything beyond a local demo.
- **Migrations.** Schema is created via `create_all`. Move to Alembic once it settles.
- **Real-time.** The client polls every 3 s. Move to WebSocket/SSE when volume justifies it.
- **Push notifications.** Alerts only show inside the panel today. Push to the phone is
  the product's core promise and is not built yet — it is also the main reason a native
  React Native app is on the roadmap.
- **Multi-farm.** The MVP assumes a single farm (`GET /api/fazenda` returns the first one).

---

## Background

The stack choice came out of a feasibility study on cattle tracking for small
landholders in Minas Gerais. Three findings drove the design:

1. **A GPS implant is not viable** — physics, not cost. Tissue attenuates RF, the
   antenna does not fit, and a satellite uplink's energy cannot be stored safely under
   the skin. Ear tags win on every axis.
2. **LoRa does not depend on a carrier.** It runs on the free 915 MHz ISM band with the
   rancher's own gateway. "No LoRa coverage" means "no gateway installed".
3. **Direct-to-satellite works today but is expensive** (~R$ 1,600/head). It becomes
   competitive with NB-IoT NTN around 2027.

The design principle that follows: **concentrate the expensive radio link in a few
points — a gateway or a collar — instead of replicating it on every animal.**

---

## Local development without Docker

```bash
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
```

```bash
cd frontend && npm install && npm run dev
```

Requires a PostgreSQL instance with PostGIS. Adjust `DATABASE_URL`.

---

## Stack

React 18 · TypeScript · Vite · Leaflet · FastAPI · SQLAlchemy 2.0 · GeoAlchemy2 ·
PostgreSQL 16 · PostGIS 3.4 · Docker Compose
