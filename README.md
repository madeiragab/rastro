# Rastro

**🇬🇧 English** · [🇧🇷 Português](README.pt-BR.md)

Real-time tracking and geofencing for cattle herds.

The rancher draws the pasture boundary on a map and gets alerted when an animal
**leaves the area**, **stops moving for too long**, or **loses connectivity**.

Mobile-first web app with a built-in herd simulator — runs with no hardware at all.

> **Status: MVP / demo.** Runs end to end and is verified: 124 tests against real
> PostGIS, plus a manual pass over login, session rotation, authenticated
> telemetry and the full geofence alert cycle. It has **not** been externally
> audited or penetration tested, and several production requirements are still
> missing — see [Before production](#before-production).

📚 **[Full documentation](docs/README.md)** — [requirements](docs/requirements.md) ·
[architecture](docs/architecture.md) · [security](docs/security.md) ·
[decision log](docs/decisions.md)

---

## Quick start

```bash
docker compose up --build
```

| Service | URL |
|---|---|
| App | http://localhost:5173 |
| API docs (Swagger) | http://localhost:8000/docs |
| Database | 127.0.0.1:5432 |

First boot creates the schema, enables PostGIS and loads demo data: one farm in
Uberaba (Minas Gerais, Brazil), two pastures and 14 animals. The simulator starts
producing telemetry right away.

**The initial credentials are printed to the API log, once.** Look for the
`ACESSO INICIAL` block in `docker compose logs api`. It contains the login email,
a randomly generated password, and a gateway API key. Nothing is hardcoded —
committed default credentials are how most exposed systems fall.

Reset everything:

```bash
docker compose down -v
```

> **Windows note.** Docker Desktop needs the WSL2 backend. If `docker info`
> reports `no virtualization available`, WSL is missing — run `wsl --install` in
> an Administrator PowerShell, reboot, then start Docker Desktop again.

### Open it on your phone

The app is mobile-first. To open it on a real device on the same Wi-Fi, find your
machine's LAN IP and browse to `http://<your-ip>:5173`. On Android/Chrome you can
"Add to home screen" — a web manifest is included, so it launches standalone.

---

## How to demo it

The **Simular** tab forces a scenario on the selected animal. Pick an animal from
the list or tap it on the map, then:

| Button | What happens |
|---|---|
| **Fugir do pasto** (Escape) | The animal walks straight past the boundary. After 2 consecutive readings beyond the tolerance zone, the geofence alert fires (~25 s). |
| **Ficar parado** (Go still) | Accelerometer activity drops to zero. After 90 s, the immobility alert fires. |
| **Perder sinal** (Lose signal) | The tag stops reporting. After 60 s of silence, the signal-loss alert fires. |
| **Pastando** (Grazing) | Back to normal; open alerts resolve on their own. |

To draw a new pasture: tap **⬡**, tap the vertices on the map, name it and save.

---

## Interface

Mobile-first: the map fills the screen and everything else floats above it.

- **Bottom sheet** with three snap points — drag it, or tap the handle. Collapsed,
  it still shows a compact strip of counters.
- **Tabs**: Rebanho (herd), Alertas (alerts, with a badge), Simular, Conta (account).
- Tapping an animal flies the map to it — but the map never moves on its own when a
  new position arrives. A map that jumps on every reading is unusable on a phone.
- At ≥900 px wide the sheet becomes a fixed side panel, so the same code works on
  desktop.

---

## Security

Full write-up in [docs/security.md](docs/security.md), including an honest list
of what is **not** covered.

| Area | Approach |
|---|---|
| Passwords | Argon2id (64 MiB, t=3), NFKC-normalised, automatic rehash on cost change. NIST SP 800-63B policy: length + blocklist, no composition rules |
| Sessions | 15-min access JWT held **in memory only** + 14-day opaque refresh token in an `HttpOnly`, `SameSite=strict` cookie |
| Token theft | Refresh rotation with reuse detection — a replayed token revokes the whole session family (OAuth 2.0 Security BCP) |
| CSRF | `SameSite=strict` plus double-submit token compared in constant time |
| Brute force | Database-backed lockout, per account **and** per IP (the latter catches password spraying) |
| Enumeration | Generic error message, constant-time path for unknown emails, lockout applies to them too |
| Devices | Per-gateway API key, Argon2id-hashed, shown once, revocable, scoped to its own farm |
| Headers | Locked-down CSP, `nosniff`, `DENY` framing, `no-referrer`, COOP/CORP, `no-store`, HSTS under HTTPS |
| Configuration | The app **refuses to boot** in production with a weak secret, insecure cookies, non-local `http://` CORS, or the simulator on |
| Authorisation | Declared at the router, so a new route is protected by default; three roles enforced server-side |
| Team | Initial password generated server-side and shown once; demoting or deactivating invalidates the token immediately; nobody edits their own account |
| Password recovery | Single-use opaque token, 30 min, 3 requests per hour; resetting revokes sessions and all other pending links |

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
├── docs/                       # requirements, architecture, security, ADRs (PT + EN)
├── backend/
│   └── app/
│       ├── main.py             # bootstrap, CORS, security headers, lifespan
│       ├── config.py           # EVERY threshold and security parameter
│       ├── database.py         # engine, session, schema creation
│       ├── models.py           # domain + users, sessions, keys, audit
│       ├── schemas.py          # request/response contracts and input ranges
│       ├── middleware.py       # security response headers
│       ├── seed.py             # demo data + initial credentials
│       ├── security/
│       │   ├── senhas.py       # Argon2id + password policy
│       │   ├── tokens.py       # access JWT, refresh, CSRF
│       │   ├── chaves.py       # gateway API keys
│       │   ├── limites.py      # brute-force lockout
│       │   └── auditoria.py    # audit trail
│       ├── api/
│       │   ├── deps.py         # authn/authz dependencies
│       │   ├── serializers.py  # ORM -> schema (extracts lat/lon from geometry)
│       │   └── routes/         # one module per resource
│       └── services/
│           ├── geofence.py     # point-in-polygon and distance (PostGIS)
│           ├── alertas.py      # the three alert rules
│           ├── telemetria.py   # position ingestion (single entry point)
│           ├── simulador.py    # virtual herd
│           └── manutencao.py   # periodic cleanup
└── frontend/
    └── src/
        ├── App.tsx             # state, polling, session gate
        ├── api.ts              # HTTP client  ← reusable by React Native
        ├── types.ts            # mirrors the backend schemas  ← reusable
        └── components/
```

### Why PostGIS

Point-in-polygon runs in the database (`ST_Contains`), not in Python. The database
already has a spatial index, and distances in metres come out correct by casting to
`geography` — no projection error. As the herd grows, this is the decision that
avoids rewriting the data layer later.

---

## The three alert rules

Each one carries its false-alarm mitigation. A rancher who gets a false alert
uninstalls the app — that is the product's main adoption risk, not the technology.

**1. Out of area.** A 25 m tolerance zone around the polygon, plus 2 consecutive
readings outside. Without it, GNSS error produces a constant false alarm whenever
an animal grazes near the fence.

**2. No movement.** Decided by the accelerometer, not by GNSS standing still. GNSS
alone lies: cattle lying down and ruminating stay static for hours under perfectly
normal conditions. This is the highest commercial-value alert — it detects death,
obstructed calving, animals stuck in mud, and fractures.

**3. Signal loss.** Threshold relative to each device's own reporting cadence, not
a fixed global value, because cadence varies by animal and by terrain. Covers three
distinct causes: tag ripped off (theft), dead battery, and dead-zone terrain.

All thresholds live in [`backend/app/config.py`](backend/app/config.py), **compressed
for demo purposes**. The realistic field values are documented next to each one
(immobility 4 h, reporting every 30 min).

---

## API

Everything under `/api` requires authentication. `/health` and the login flow are
the only public endpoints.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `POST` | `/api/auth/login` | — | Log in; sets the refresh and CSRF cookies |
| `POST` | `/api/auth/refresh` | cookie + CSRF | Rotate the session, get a new access token |
| `POST` | `/api/auth/logout` | cookie | Revoke the session family |
| `GET` | `/api/auth/eu` | user | Current user |
| `POST` | `/api/auth/senha` | user | Change password (ends every session) |
| `POST` | `/api/auth/esqueci` | — | Request a reset link (same response whether or not the account exists) |
| `POST` | `/api/auth/redefinir` | token | Consume the link and store the new password |
| `GET` `POST` `PATCH` | `/api/usuarios` | owner | Manage the team and their roles |
| `GET` | `/api/push/chave-publica` | user | VAPID key for the browser to subscribe |
| `POST` `DELETE` | `/api/push/inscricoes` | user | Register or cancel this device |
| `GET` | `/api/fazenda` | user | Current farm |
| `GET` | `/api/resumo` | user | Dashboard counters |
| `GET` | `/api/animais` | user | Animals with last position and status |
| `GET` | `/api/animais/{id}/trilha` | user | Recent position trail |
| `GET` | `/api/alertas` | user | Alerts, open by default |
| `POST` | `/api/alertas/{id}/resolver` | user | Resolve one alert |
| `GET` `POST` `DELETE` | `/api/pastos` | operator | Manage pastures |
| `GET` `POST` `DELETE` | `/api/gateways` | owner | Manage gateway keys |
| `POST` | `/api/telemetria` | **gateway key** | Position ingestion — the hardware entry point |
| `POST` | `/api/simulacao/*` | operator | Force scenarios (demo only) |

Interactive reference at http://localhost:8000/docs — disabled in production.

---

## Plugging in real hardware

The simulator and a real gateway go through the same service. The gateway
authenticates with its own key:

```bash
curl -X POST http://localhost:8000/api/telemetria \
  -H "Content-Type: application/json" \
  -H "X-API-Key: rastro_gw_<prefix>_<secret>" \
  -d '{"brinco":"076000000000001","lat":-19.7480,"lon":-47.9320,"atividade":0.6,"bateria_pct":88}'
```

No business rule changes. Turn the simulator off with `SIMULATOR_ENABLED=false`.

Tag IDs use 15 digits with the `076` prefix (Brazil's country code), aligned with
**PNIB** — the national cattle identification programme, which makes individual
identification mandatory for all cattle movement from 2033.

---

## Push notifications

Alerts reach the phone **with the app closed** — the product's core promise.
Enable it under **Conta → Notificações**.

Web Push with VAPID. The key pair is generated on first need and stored in the
database rather than in an environment variable: rotating the key would
invalidate every existing subscription, and devices would only find out by
silently not receiving alerts — the worst failure mode for an alerting system.

Sending runs in a background loop, not on the telemetry request path: push goes
out over HTTP to the browser vendor's service, and a gateway cannot wait on that
to have a position acknowledged. The `notificado_em` mark lives on the alert
itself, so restarting mid-flight neither loses nor duplicates a notification.

**Browser constraint:** Service Workers only register in a secure context —
HTTPS **or** `localhost`. On a phone over the LAN, `http://192.168.x.x` does not
qualify. Hence the TLS profile below.

## Local HTTPS

```bash
TLS_HOST=192.168.0.12 docker compose --profile tls up
```

Brings up Caddy on `https://localhost` (and on the given IP) with a certificate
from a local authority. Browsers will warn until that authority is trusted on the
device. It does not start by default and does not redirect HTTP — access over
`localhost` keeps working exactly as before.

For production, point it at a real domain and Caddy handles Let's Encrypt on its
own. Set `COOKIE_SECURE=true` alongside.

## Before production

- **Second factor.** Not implemented. TOTP at least for the `owner` role.
- **SMTP.** Password recovery works, but the link is written to the API log
  instead of emailed. A provider needs plugging into
  `services/notificacao.py` — the abstraction is already isolated there.
- **Multi-farm.** The MVP assumes a single farm.
- **Secrets management.** Secrets come from environment variables, visible in
  `docker inspect`. Move to a secrets manager.
- **General rate limiting.** Only login and password recovery are limited; the
  rest of the API is not.
- **Push on iOS.** Full support on Android/Chrome. Safari requires the app added
  to the home screen — the main argument for React Native on the roadmap.

The full list, with risk and remedy for each item, is in
[docs/security.md](docs/security.md#what-is-not-protected).

---

## Background

The stack choice came out of a feasibility study on cattle tracking for small
landholders in Minas Gerais. Three findings drove the design:

1. **A GPS implant is not viable** — physics, not cost. Tissue attenuates RF, the
   antenna does not fit, and a satellite uplink's energy cannot be stored safely
   under the skin. Ear tags win on every axis.
2. **LoRa does not depend on a carrier.** It runs on the free 915 MHz ISM band with
   the rancher's own gateway. "No LoRa coverage" means "no gateway installed".
3. **Direct-to-satellite works today but is expensive** (~R$ 1,600/head). It becomes
   competitive with NB-IoT NTN around 2027.

The design principle that follows: **concentrate the expensive radio link in a few
points — a gateway or a collar — instead of replicating it on every animal.**

---

## Tests

```bash
docker compose up -d db
cd backend
pip install -r requirements-dev.txt
pytest
```

**124 passing, 4 skipped** (the skips are the deliberately public routes in the
authorisation sweep). The run takes about 5 minutes.

The suite runs against **real PostGIS**, in a separate `rastro_test` database
that it creates on first run. The geofence rule *is* `ST_Contains` plus distance
in `geography` — testing that against a stub would only test the stub.

Argon2 cost is lowered by environment variable inside `conftest.py`. In
production the cost *is* the protection; in tests it was only wall clock.

What it covers:

| File | Focus |
|---|---|
| `test_seguranca_primitivas.py` | Argon2id, password policy, NFKC normalisation, JWT claims, `alg=none` rejection, tampered/expired tokens, gateway key format |
| `test_auth.py` | Login, generic message for unknown emails, lockout, refresh rotation, **reuse detection revoking the family**, logout, password change invalidating old tokens |
| `test_autorizacao.py` | Parametrised sweep asserting **every** route in the OpenAPI schema refuses anonymous access, plus the role matrix and security headers |
| `test_telemetria.py` | Gateway key auth, cross-farm rejection, input ranges, future/stale timestamp rejection |
| `test_alertas.py` | The three rules — including the cases that must **not** fire: one isolated reading outside, grazing inside the tolerance zone, and a static GNSS fix with normal accelerometer activity |

The sweep in `test_autorizacao.py` is the one that matters most: it fails if
anyone adds a route without protection, which is what makes ADR-007 enforceable
rather than aspirational.

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
Argon2id · PyJWT · PostgreSQL 16 · PostGIS 3.4 · Docker Compose
