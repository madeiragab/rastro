> [🇧🇷 Português](decisoes.md) · 🇬🇧 **English**

# Decision log

Each entry follows the ADR shape: context, decision, consequence. What matters
here is the **why** — the code already shows the what.

---

## ADR-001 — Ear tag, not subcutaneous implant

**Situation:** the initial proposal was a chip implanted in the animal reporting
its position.

**Decision:** drop the implant. Use an ear tag.

**Reason:** four independent barriers, and one is enough.

1. Biological tissue attenuates RF. Civil GPS runs at 1.575 GHz and the signal
   reaching the ground is already around −130 dBm. Under the skin it falls below
   the detection threshold.
2. An efficient antenna needs roughly a quarter wavelength — ~8 cm at 915 MHz.
   That does not fit in an implantable capsule without destroying the gain.
3. A satellite uplink needs 1–2 W peaks. An implant gets no sunlight, allows no
   battery swap, and wireless power transfer through tissue is inefficient.
4. A device in muscle is a foreign body in the carcass — rejection risk at the
   packing plant. Nexa Labs works around this by placing the chip **in the ear**,
   which is removed at the start of slaughter.

**Consequence:** the whole design assumes an external device with sunlight and
serviceability. It also coincides with where PNIB already mandates identification.

---

## ADR-002 — PostGIS, not geometry in Python

**Situation:** the point-in-polygon test runs on every reading, for every animal.

**Decision:** PostGIS. `ST_Contains` and `ST_Distance` in the database.

**Rejected alternative:** Shapely in Python with the polygon stored as JSON.
Simpler to deploy — no extension image needed — but it requires loading every
polygon into memory on each evaluation, has no spatial index, and distance in
degrees is not distance in metres.

**Consequence:** a dependency on the PostGIS image. In exchange, metre distances
come out correct via `cast(geom, Geography)` with no projection error, and the
spatial index is already there when the herd grows.

---

## ADR-003 — Tolerance zone plus hysteresis on the geofence

**Situation:** low-power GNSS is off by tens of metres. An animal grazing along
the fence crosses the line constantly, in the data.

**Decision:** count "outside" only when it passes the polygon **and** is beyond
25 m of it, **and** that repeats on 2 consecutive readings.

**Consequence:** an animal that steps out and back quickly may go unnoticed —
and that is fine. The cost of a false alarm far exceeds the cost of a missed
short excursion: **a rancher who gets a false alert uninstalls the app.** That
is the product's biggest adoption risk, above any technical concern.

---

## ADR-004 — Immobility from the accelerometer, not from GNSS

**Situation:** detecting a downed animal is the highest commercial-value alert —
it catches death, obstructed calving, mud entrapment and fractures.

**Decision:** decide from the accelerometer's activity index. GNSS plays no part
in the rule.

**Reason:** a static GNSS fix, on its own, lies. Cattle lying down and
ruminating stay motionless for hours under perfectly normal conditions. A
GNSS-based rule would fire every evening.

**Consequence:** the tag **must** carry an accelerometer. Negligible component
cost, but it becomes a non-negotiable hardware requirement.

---

## ADR-005 — Relative threshold for signal loss

**Situation:** detect a ripped-off tag (theft), a dead battery, or an animal in
a radio shadow.

**Decision:** the threshold is a multiple of **that device's** expected cadence,
not a fixed global value.

**Reason:** cadence varies by animal and by terrain. A single threshold would
produce constant noise on slower devices and react too late on faster ones.

**Consequence:** each device needs a baseline. In the MVP it is a global setting;
with real hardware it becomes per-device.

---

## ADR-006 — One telemetry entry point

**Situation:** the hardware does not exist. The product still has to be
demonstrable.

**Decision:** simulator and real gateway both go through the **same**
`services/telemetria.py`. The simulator calls the function; the gateway calls
`POST /api/telemetria`, which calls the same function.

**Consequence:** swapping the simulator for hardware changes no business rule —
point the gateway at the endpoint and turn `SIMULATOR_ENABLED` off. The price is
the simulator living inside the API, coupling demo and production. Acceptable
while the hardware does not exist.

---

## ADR-007 — Authorisation declared on the router, not per route

**Situation:** a new route forgotten without protection is one of the most
common and most silent failures.

**Decision:** declare the auth dependency at `include_router`, in
`api/routes/__init__.py`, rather than on each function.

**Consequence:** a new route is born protected. Leaving something open requires
explicitly moving it into the public group — which shows up in the diff, where
it can be questioned.

---

## ADR-008 — Access token in memory, refresh in an HttpOnly cookie

**Situation:** where the browser keeps the session.

**Decision:** access token (15 min) in JavaScript memory only. Refresh token
(14 days) in an `HttpOnly` + `SameSite=strict` cookie, with rotation and reuse
detection.

**Rejected alternatives:**

| Option | Why not |
|---|---|
| Access token in `localStorage` | Any XSS reads and exfiltrates it |
| Refresh token in the response body | Forces the frontend to store it where JavaScript reads — same problem |
| Session cookie only, no JWT | Simple, but requires a database hit per request and complicates the planned native app |

**Consequence:** reloading the page loses the access token — intentionally. The
session is restored by a refresh call on load. In exchange, XSS does not carry
away the long-lived session.

---

## ADR-009 — Argon2id for passwords, SHA-256 for refresh tokens

**Situation:** two secrets stored two different ways. Looks inconsistent.

**Decision:** Argon2id for passwords, SHA-256 for refresh tokens.

**Reason:** slow hashing exists to protect **low-entropy** secrets — passwords,
which humans choose and attackers guess from dictionaries. A refresh token is
256 random bits: there is no dictionary to walk, so a fast hash already
guarantees a database dump cannot become a valid session. Using Argon2 there
would only make every renewal slower with no security gain.

---

## ADR-010 — Mobile-first now, React Native later

**Situation:** the product is for the rancher in the field, phone in hand.

**Decision:** mobile-first web (PWA) for the MVP. React Native once the product
is validated.

**Reason:** for demos, opening a URL beats installing an app. For the real
product, reliable push on both platforms requires native — and push is the core
promise.

**Consequence:** `api.ts` and `types.ts` were written without importing anything
from React, so the native app can reuse them unchanged.

---

## ADR-011 — `create_all` instead of migrations, for now

**Situation:** the schema still changes every working session.

**Decision:** create tables from metadata at boot. Defer Alembic.

**Consequence:** **schema changes require recreating the database**
(`docker compose down -v`). Acceptable while there is no real data. It becomes
debt the moment the first field pilot starts — and it is recorded as such.

---

## ADR-012 — 3-second polling, not WebSocket

**Situation:** the dashboard must reflect herd position close to real time.

**Decision:** plain polling every 3 s.

**Reason:** with few clients, polling is trivial to get right and carries no
connection state to manage — no reconnection, no heartbeat, no stuck sessions. A
badly reconnecting WebSocket is worse than polling.

**Consequence:** constant traffic and up to 3 s of latency. Replace it when the
client count justifies it, not before.

---

## ADR-013 — A version counter to invalidate tokens, not a timestamp

**Situation:** changing the password must reject every access token already
issued.

**First attempt:** compare the JWT's `iat` against the user's
`senha_alterada_em`. A token issued before the change is rejected.

**Why it was wrong:** both values have **one-second** resolution. Changing the
password in the same second the token was issued left the previous token valid —
which is precisely the situation of someone who has just realised they were
breached and is racing to change their password. The window is small, and it
sits at the worst possible moment.

**Decision:** a `token_versao` counter on the user, carried in the token as a
`ver` claim and compared for equality. Changing the password increments it.

**Consequence:** no resolution, no clock, no window. It costs one `integer`
column and one comparison. The test suite found this on the first real run — not
code review, which read the `<` and considered it correct.
