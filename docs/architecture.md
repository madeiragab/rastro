> [🇧🇷 Português](arquitetura.md) · 🇬🇧 **English**

# Architecture

Technical document for Rastro: how the pieces fit, why they are that way, and
where the boundaries are.

- [Overview](#overview)
- [Containers](#containers)
- [Data model](#data-model)
- [Telemetry flow](#telemetry-flow)
- [Alert lifecycle](#alert-lifecycle)
- [Authentication](#authentication)
- [Backend layers](#backend-layers)
- [Frontend](#frontend)
- [Known limits](#known-limits)

---

## Overview

```mermaid
flowchart TB
    rancher(["👤 Rancher<br/>phone in pocket"])
    gateway(["📡 Farm gateway<br/>aggregates the tags"])
    tag(["🏷️ Solar ear tag<br/>GNSS + accelerometer"])

    subgraph rastro["Rastro"]
        app["Mobile-first app<br/>React + Leaflet"]
        api["API<br/>FastAPI"]
        db[("PostgreSQL<br/>+ PostGIS")]
    end

    osm(["🗺️ OpenStreetMap<br/>map tiles"])

    tag -->|"radio<br/>(LoRa / NB-IoT)"| gateway
    gateway -->|"POST /api/telemetria<br/>X-API-Key"| api
    rancher -->|HTTPS| app
    app -->|"JSON + Bearer"| api
    app -.->|tiles| osm
    api <--> db

    classDef externo fill:#1e262b,stroke:#7b8794,color:#e6edf1
    classDef interno fill:#1f4d3a,stroke:#2e9e63,color:#e6edf1
    class rancher,gateway,tag,osm externo
    class app,api,db interno
```

The hardware does not exist yet. In the MVP, tag and gateway are played by a
**simulator** running inside the API, writing through the same path a real
gateway would use.

## Containers

```mermaid
flowchart LR
    subgraph compose["docker compose"]
        direction TB
        web["<b>web</b><br/>Vite dev server<br/>port 5173"]
        api["<b>api</b><br/>Uvicorn + FastAPI<br/>port 8000"]
        db[("<b>db</b><br/>postgis/postgis:16-3.4<br/>port 5432")]
    end

    browser(["Browser"]) -->|"/"| web
    browser -->|"/api/*"| web
    web -->|proxy| api
    api -->|SQLAlchemy| db
```

The Vite proxy makes app and API share one browser origin. That is not
convenience: it is what allows `SameSite=strict` on the session cookie without
breaking anything.

`db` and `api` ports are published on `127.0.0.1`. Only `web` binds `0.0.0.0`,
so the app can be opened from a phone on the local network.

## Data model

```mermaid
erDiagram
    FARM ||--o{ PASTURE : has
    FARM ||--o{ ANIMAL : has
    FARM ||--o{ USER : has
    FARM ||--o{ GATEWAY_KEY : has
    PASTURE ||--o{ ANIMAL : holds
    ANIMAL ||--o{ POSITION : reports
    ANIMAL ||--o{ ALERT : raises
    USER ||--o{ REFRESH_SESSION : opens
    USER ||--o{ AUDIT_EVENT : records

    FARM {
        int id PK
        string nome
        string proprietario
        string municipio
        string uf
    }
    PASTURE {
        int id PK
        int fazenda_id FK
        string nome
        geometry geom "POLYGON 4326"
        float buffer_m "tolerance zone"
    }
    ANIMAL {
        int id PK
        int fazenda_id FK
        int pasto_id FK
        string brinco UK "15 digits, PNIB"
        string status
        geometry ultima_geom "POINT 4326"
        timestamp ultimo_contato
        int leituras_fora "hysteresis"
        timestamp imovel_desde
    }
    POSITION {
        int id PK
        int animal_id FK
        geometry geom "POINT 4326"
        float atividade "0..1, accelerometer"
        timestamp registrada_em
    }
    ALERT {
        int id PK
        int animal_id FK
        string tipo
        string severidade
        timestamp criado_em
        timestamp resolvido_em
    }
    USER {
        int id PK
        string email UK
        string senha_hash "Argon2id"
        string papel
        timestamp senha_alterada_em
    }
    REFRESH_SESSION {
        int id PK
        int usuario_id FK
        string familia "rotation chain"
        string token_hash UK "SHA-256"
        timestamp usada_em
        timestamp revogada_em
    }
    GATEWAY_KEY {
        int id PK
        int fazenda_id FK
        string prefixo UK "public"
        string chave_hash "Argon2id"
    }
    AUDIT_EVENT {
        int id PK
        int usuario_id FK
        string acao
        string ip
    }
```

Three decisions worth explaining:

**`ultima_geom` on the animal is deliberate denormalisation.** The map asks for
the whole herd's position every 3 s. Scanning `posicoes` for the latest row each
cycle would be expensive; keeping a copy of the last reading costs one column.

**`leituras_fora` and `imovel_desde` are alert-engine state, not animal state.**
They live here because the alternative — recomputing history on every reading —
would be more expensive without being more correct.

**`familia` on the session** groups the whole rotation chain of one login. It is
what makes revoking an entire stolen-token chain possible in one move.

## Telemetry flow

```mermaid
sequenceDiagram
    autonumber
    participant G as Gateway
    participant A as API
    participant S as Alert service
    participant D as PostGIS

    G->>A: POST /api/telemetria<br/>X-API-Key + position
    A->>D: look up key by prefix
    A->>A: Argon2.verify(secret)
    Note over A: invalid key → 401<br/>(constant time)

    A->>D: look up animal by tag id
    Note over A: animal of another farm → 404<br/>(does not confirm existence)

    A->>D: INSERT position
    A->>D: UPDATE animal (last point, last contact)

    A->>S: evaluate_position()
    S->>D: ST_Contains(pasture, point)
    S->>D: ST_Distance(pasture::geography, point::geography)

    alt outside and beyond tolerance
        S->>S: readings_outside += 1
        alt readings_outside >= 2
            S->>D: INSERT alert (out of area)
        end
    else inside
        S->>D: resolve area alert, reset counter
    end

    alt activity <= threshold for too long
        S->>D: INSERT alert (immobile)
    end

    A-->>G: 201 + animal state
```

## Alert lifecycle

```mermaid
stateDiagram-v2
    [*] --> Normal

    Normal --> OutsideSuspected: position beyond tolerance
    OutsideSuspected --> Normal: back inside (hysteresis absorbs GNSS error)
    OutsideSuspected --> OutsideConfirmed: 2nd consecutive reading outside
    OutsideConfirmed --> Normal: back inside

    Normal --> StillSuspected: activity <= 0.08
    StillSuspected --> Normal: moving again
    StillSuspected --> StillConfirmed: past the time limit
    StillConfirmed --> Normal: moving again

    Normal --> NoSignal: silence > 4x cadence
    OutsideConfirmed --> NoSignal: silence
    NoSignal --> Normal: reporting again

    note right of OutsideSuspected
        The intermediate state is
        what prevents false alarms
    end note
```

**Suspected** states raise no notification. They are what separates "GNSS
drifted" from "the animal left".

## Authentication

```mermaid
sequenceDiagram
    autonumber
    participant U as App
    participant A as API
    participant D as Database

    rect rgba(46,158,99,0.08)
        Note over U,D: login
        U->>A: POST /auth/login (email, password)
        A->>D: locked out? (by email and by IP)
        A->>A: Argon2id.verify
        A->>D: store session (SHA-256 of refresh)
        A-->>U: access token (15 min, body)<br/>+ refresh (HttpOnly cookie)<br/>+ csrf (readable cookie)
    end

    rect rgba(139,111,203,0.10)
        Note over U,D: normal use
        U->>A: GET /api/animais<br/>Authorization: Bearer
        A-->>U: 200
    end

    rect rgba(224,130,26,0.10)
        Note over U,D: renewal
        U->>A: GET /api/animais (token expired)
        A-->>U: 401
        U->>A: POST /auth/refresh<br/>cookie + X-CSRF-Token
        A->>D: token used before?
        alt reuse detected
            A->>D: revoke the whole family
            A-->>U: 401 — log in again
        else valid
            A->>D: mark used, create the next one
            A-->>U: new access + NEW refresh
        end
        U->>A: retry GET /api/animais
    end
```

Design detail: the refresh token **never** appears in a response body. If it
did, the frontend would have to store it somewhere JavaScript can read, and one
XSS would carry the 14-day session away with it.

## Backend layers

```mermaid
flowchart TD
    R["<b>api/routes/</b><br/>HTTP, status codes, input validation"]
    P["<b>api/deps.py</b><br/>who you are, what you may do"]
    S["<b>services/</b><br/>business rules"]
    M["<b>models.py</b><br/>ORM"]
    G["<b>security/</b><br/>passwords, tokens, keys, limits, audit"]
    DB[("PostGIS")]

    R --> P
    R --> S
    P --> G
    S --> M
    S --> G
    M --> DB
```

The rule behind the cut: **routes hold no business rules, and services know
nothing about HTTP.** That is what lets the simulator and the telemetry endpoint
share `services/telemetria.py` with no duplication.

Authorisation is declared in `api/routes/__init__.py`, at `include_router`, not
per route. A new route is therefore born protected — leaving something open
requires explicitly moving it into the public group, which shows up in the diff.

## Frontend

```mermaid
flowchart TD
    App["<b>App.tsx</b><br/>state, polling, session gate"]
    Api["<b>api.ts</b><br/>HTTP, in-memory token,<br/>single-flight refresh"]
    Types["<b>types.ts</b><br/>mirrors the schemas"]

    Map["MapaView"]
    Sheet["FolhaInferior"]
    List["ListaAnimais"]
    Feed["FeedAlertas"]
    Sim["PainelSimulacao"]
    Account["PainelConta"]
    Login["TelaLogin"]

    App --> Api
    App --> Map
    App --> Sheet
    Sheet --> List
    Sheet --> Feed
    Sheet --> Sim
    Sheet --> Account
    App --> Login
    Api --> Types

    style Api fill:#1f4d3a,stroke:#2e9e63,color:#e6edf1
    style Types fill:#1f4d3a,stroke:#2e9e63,color:#e6edf1
```

`api.ts` and `types.ts` import nothing from React on purpose: the planned React
Native app reuses both unchanged.

## Known limits

| Limit | Consequence | When to fix |
|---|---|---|
| `create_all` instead of migrations | Schema changes require recreating the database | Before the first pilot with real data |
| 3 s polling | Constant traffic; up to 3 s alert latency | When client count justifies WebSocket |
| Single farm | `GET /api/fazenda` returns the first one | Before the second customer |
| No push | Alerts only exist while the app is open | The product's core promise — next priority |
| Simulator inside the API | Couples demo and production | When hardware arrives |
| Single API replica | Simulator and maintenance would double with 2+ replicas | Before scaling horizontally |
