> [🇧🇷 Português](requisitos.md) · 🇬🇧 **English**

# Requirements

**Product:** Rastro — real-time tracking and geofencing for cattle herds
**Version:** 0.2 (MVP)
**Date:** August 2026

---

## 1. Context and problem

Small and mid-size ranchers in Minas Gerais, Brazil, do not know where their
herd is. The consequences carry direct cost:

- **Cattle theft:** the rancher finds out days later, when counting the lot. By
  then the animal has been slaughtered or sold.
- **Unnoticed death:** an animal down from obstructed calving, mud or fracture
  dies within hours. Found in time, it survives.
- **Escape through a broken fence:** cattle reach a road or a neighbour's crop —
  accident and dispute risk.
- **Manual search:** finding one specific animal across hundreds of hectares
  burns a working day.

The feasibility study that preceded this project ([background in the
README](../README.md#background)) concluded that the barrier was never the
positioning technology, but the **cost per head** — which is dominated by where
the long-range radio sits.

## 2. Personas

| Persona | Profile | Needs | Will not tolerate |
|---|---|---|---|
| **José, rancher** | 58, 60 head, mid-range Android, unstable internet | To know something went wrong without opening the app | False alarms. Two in a row and he uninstalls |
| **Marcos, ranch hand** | 34, works in the field, one-handed phone use, wearing gloves | To find the animal on the map fast | Interfaces demanding precise taps |
| **Ana, the rancher's daughter** | 27, runs the business, comfortable with tech | Reports, history, access control | Having to teach her father to use it |

## 3. MVP scope

### In

Pasture drawing on the map, position monitoring, the three alerts,
authentication, access roles and device credentials.

### Out — and why

| Item | Reason |
|---|---|
| Tag firmware | Depends on the connectivity decision, which depends on field measurement |
| Push notifications | Needs a native app to work reliably on both platforms |
| Multi-farm | Only matters from the second customer onward |
| Weight-gain reports | Not the problem blocking the sale |
| Active virtual fencing (stimulus to the animal) | Different product, different regulation |

## 4. Functional requirements

Priority: **must** (no product without it) · **should** (expected) ·
**could** (desirable).

### 4.1 Pasture definition

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | The user draws the pasture polygon by tapping vertices on the map | must |
| FR-02 | The system computes and shows the area in hectares | should |
| FR-03 | Each pasture has a configurable tolerance zone (default 25 m) | must |
| FR-04 | A pasture with animals attached cannot be removed | should |

### 4.2 Monitoring

| ID | Requirement | Priority |
|---|---|---|
| FR-05 | Show each animal's last position on the map, coloured by state | must |
| FR-06 | Show the recent trail of the selected animal | should |
| FR-07 | List animals ordered by severity, not by name | must |
| FR-08 | Show each tag's battery level | should |
| FR-09 | Accept telemetry from an external gateway over the API | must |

### 4.3 Alerts

| ID | Requirement | Acceptance criterion |
|---|---|---|
| FR-10 | **Out of area** | Fires only after 2 consecutive readings beyond polygon + tolerance. One isolated reading outside does **not** fire |
| FR-11 | **No movement** | Based on the accelerometer. An animal lying down and ruminating with static GNSS does **not** fire |
| FR-12 | **Signal loss** | Threshold relative to the device's own cadence, not a fixed global value |
| FR-13 | An open alert is not reopened until resolved | One occurrence yields one notification, not one per reading |
| FR-14 | An alert resolves itself when the cause stops | Animal returns to the pasture → area alert closes |
| FR-15 | The user can mark an alert resolved | If the cause persists, it reopens next cycle |

### 4.4 Access

| ID | Requirement | Priority |
|---|---|---|
| FR-16 | Login with email and password | must |
| FR-17 | Three roles: read-only, operator, owner | must |
| FR-18 | Changing the password ends every session on every device | must |
| FR-19 | The owner issues and revokes gateway keys | must |
| FR-20 | Sensitive actions are written to an audit trail | should |

### 4.5 Permission matrix

| Action | read-only | operator | owner |
|---|:---:|:---:|:---:|
| View map, animals and alerts | ✅ | ✅ | ✅ |
| Resolve an alert | ✅ | ✅ | ✅ |
| Create and remove pastures | ❌ | ✅ | ✅ |
| Force a simulation scenario | ❌ | ✅ | ✅ |
| Issue and revoke gateway keys | ❌ | ❌ | ✅ |

## 5. Non-functional requirements

### 5.1 Usability

| ID | Requirement | Verification |
|---|---|---|
| NFR-01 | Mobile-first: designed for a phone screen, adapted for desktop | Single-column layout up to 900 px |
| NFR-02 | Touch targets of at least 44 px | CSS inspection |
| NFR-03 | Operable one-handed | Primary controls in the lower half |
| NFR-04 | The map does not move on its own when a position arrives | Recentres only when the selected animal changes |
| NFR-05 | Interface in Portuguese, free of technical jargon | Copy review |

### 5.2 Reliability

| ID | Requirement |
|---|---|
| NFR-06 | False-alarm rate near zero — this is the criterion that decides adoption |
| NFR-07 | A gateway outage loses no data: the tag buffers and drains later (telemetry accepted up to 7 days late) |
| NFR-08 | The API tolerates the database being unavailable at boot, with wait and retry |

### 5.3 Security

Detailed in [security](security.md).

| ID | Requirement |
|---|---|
| NFR-09 | Passwords stored with Argon2id, never plain or with a fast hash |
| NFR-10 | Long-lived session unreachable by JavaScript (HttpOnly cookie) |
| NFR-11 | Refresh token rotation with reuse detection |
| NFR-12 | Brute-force protection per account **and** per IP |
| NFR-13 | Gateways authenticate with their own credential, revocable without touching human accounts |
| NFR-14 | The application refuses to boot in production with insecure configuration |
| NFR-15 | Error responses never reveal whether an email exists |

### 5.4 Performance

| ID | Requirement | Target |
|---|---|---|
| NFR-16 | Dashboard query response time | < 300 ms with 200 animals |
| NFR-17 | Latency between reading arrival and alert opening | < 1 reading cycle |
| NFR-18 | Point-in-polygon in the database, with a spatial index | No full scan |

### 5.5 Portability

| ID | Requirement |
|---|---|
| NFR-19 | Boots with one command (`docker compose up`) on any Docker host |
| NFR-20 | Frontend network layer framework-agnostic, reusable from React Native |

## 6. Constraints

| Constraint | Source |
|---|---|
| Cost per head below R$ 150 in the entry scenario | Small rancher's ability to pay |
| 15-digit tag id with `076` prefix | PNIB — individual identification mandatory in Brazil from 2033 |
| The device may go days without coverage | Terrain of Minas Gerais |
| No paid map API key | Per-user cost; hence OpenStreetMap |
| Implants are ruled out | Physics: tissue attenuates RF, the antenna does not fit, the energy budget does not close |

## 7. Business rules

| ID | Rule |
|---|---|
| BR-01 | An animal belongs to at most one pasture at a time |
| BR-02 | A gateway may only report positions for animals of its own farm |
| BR-03 | A position timestamped in the future (> 5 min) or too old (> 7 days) is rejected |
| BR-04 | A gateway key is displayed exactly once, at creation |
| BR-05 | A revoked key is not deleted, so the audit trail stays readable |
| BR-06 | Access tokens issued before the last password change are invalid |

## 8. Glossary

| Term | Meaning |
|---|---|
| **Abigeato** | Cattle theft. A distinct offence under Brazilian criminal law |
| **Ear tag** | Identifier attached to the animal's ear. Electronic, here |
| **Geofence** | Virtual perimeter; the system warns when it is crossed |
| **GNSS** | Generic name for satellite positioning systems (GPS is one of them) |
| **Hysteresis** | Requiring confirmation before switching state, to avoid flapping at the threshold |
| **LoRa** | Long-range, low-power radio on the licence-free 915 MHz band |
| **NB-IoT** | Low-power cellular network dedicated to IoT |
| **NTN** | *Non-Terrestrial Network* — the 5G extension that lets a modem talk to satellites |
| **PNIB** | Brazil's national individual cattle identification programme |
| **Gateway** | Equipment that receives tags over radio and forwards to the internet |

## 9. MVP acceptance criteria

The MVP is demo-ready when:

1. ✅ The rancher draws a pasture from the phone and it appears on the map
2. ✅ Animals move on the map in real time
3. ✅ Forcing an escape raises an area alert in under 30 s
4. ✅ Forcing immobility raises an alert in under 2 min
5. ✅ Forcing silence raises a signal-loss alert in under 2 min
6. ✅ No false alerts during 10 min of normal grazing
7. ✅ Access requires login, and gateways require their own key
8. ✅ **Verified in a real run**

All verified with the system running, on 2026-08-04. The out-of-area alert fired
about 25 s after pressing the button in the UI, with the distance computed by
PostGIS. The 124-test suite covers items 3 to 7, including the cases that must
**not** fire (item 6).

That first run surfaced five defects static analysis had missed — one of them
invalidating roughly a third of all generated gateway keys. The note stays here
as a reminder: code that compiles, type-checks and reads well is still not code
that runs.
