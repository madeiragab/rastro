> [🇧🇷 Português](seguranca.md) · 🇬🇧 **English**

# Security

How Rastro defends itself, what it defends against, and — just as important —
what it does **not** defend against.

> **Notice.** This is an MVP. The design follows current good practice, but it
> has **never been externally audited or penetration tested**, and the
> application has not yet been run end to end. Do not treat it as hardened.

---

## Threat model

Who realistically attacks a system like this:

| Actor | Motivation | Capability |
|---|---|---|
| **Cattle thief** | Learn where the herd is; erase the trace of a theft | Low. But the damage is direct and immediate |
| **Curious neighbour on the same network** | Snoop on someone else's app | Low |
| **Automated scanning** | Anything exposed to the internet | Medium, and relentless |
| **Former employee** | Sabotage, access after termination | Medium. **Knows the credentials** |
| **Competitor** | Herd data, movement, fattening performance | Medium to high |

The threat that shapes the design: **the cattle thief is the adversary that
matters most**. He does not need to breach the cloud — he just rips off the tag.
That is why signal loss is a first-class alert, not an infrastructure detail.

## STRIDE

| Category | Concrete threat | Control |
|---|---|---|
| **S**poofing | Impersonate the gateway and inject fake positions to hide a theft | Per-gateway API key, Argon2id, revocable; a key only works for animals of its own farm |
| **T**ampering | Rewrite the past trail, or push the timestamp into the future to silence the signal-loss alert | Timestamp range validation (+5 min / −7 days) on input |
| **R**epudiation | "I never revoked that key" | Audit trail with user, action, IP and time |
| **I**nformation disclosure | Discover which emails exist; read another user's session | Generic login response, constant-time path, HttpOnly cookie, locked-down CSP |
| **D**enial of service | Hammer the login; oversized password to blow up Argon2 cost | Per-account and per-IP lockout; password capped at 128 characters |
| **E**levation of privilege | Operator becomes owner; forged token | Roles checked server-side; JWT with fixed algorithm and required claims |

## Implemented controls

### Passwords

Argon2id, 64 MiB memory, 3 iterations, parallelism 2 — above the OWASP minimum
(19 MiB, t=2).

Why not bcrypt: bcrypt's cost is CPU only and its memory use is small and fixed,
which makes it cheap to attack with GPUs and ASICs. Argon2id's memory cost is
precisely what makes that attack expensive.

Policy follows NIST SP 800-63B: **minimum length of 12 plus a blocklist, no
composition rules**. Demanding "one uppercase and one symbol" produces
`Senha@123` — short, predictable and terrible.

Passwords are NFKC-normalised before hashing. Without it, the same password
typed on a phone keyboard and on a physical keyboard can produce different bytes
and lock the user out with no explanation.

Automatic rehash: if cost parameters rise, the hash is rewritten on the next
login — the only moment the plaintext password exists.

### Sessions

```
access token   JWT HS256, 15 min, in the body, kept in memory only
refresh token  256 opaque bits, 14 days, HttpOnly + SameSite=strict cookie
```

**Why two tokens.** The access token is self-contained and fast to validate, but
cannot be revoked before it expires — hence the short life. The refresh token is
revocable at any time, and can therefore last.

**Why the refresh token is not in the response body.** If it were, the frontend
would have to store it where JavaScript can read it, and one XSS would carry the
14-day session away. In an HttpOnly cookie, page scripts cannot reach it.

**Why the access token stays in memory only.** `localStorage` and
`sessionStorage` are readable by any XSS. In memory, the token dies with the
tab, and the session is restored on next load from the cookie.

**Rotation with reuse detection.** Every use of the refresh token issues a new
one and marks the previous as used. If an already-used token reappears, the only
explanation is that two copies exist — and there is no way to tell which is
legitimate. The whole family is revoked and both sides must log in again. This
is the *OAuth 2.0 Security BCP* recommendation for public clients.

**Stored as SHA-256, not Argon2.** Slow hashing exists to protect *low-entropy*
secrets, which humans choose and attackers guess. A 256-bit random token has no
dictionary to walk, so a fast hash already guarantees a database dump cannot be
turned into a valid session.

**Changing the password tears everything down.** Sessions are revoked and every
access token issued before that instant is rejected (comparing `iat` against
`senha_alterada_em`). Someone changing their password because they suspect a
breach expects exactly that: the intruder loses access now, not in 14 days.

### CSRF

Two layers. `SameSite=strict` stops the browser from sending the cookie on
requests originating from another site, which already blocks most cases. On top
of that, *double submit*: a JavaScript-readable cookie whose value must be
echoed in the `X-CSRF-Token` header, compared in constant time. A third-party
site can trigger the cookie being sent, but cannot read its value to fill the
header.

The refresh cookie is scoped `Path=/api/auth`: it does not even accompany the
other routes.

### Brute force

Counted in the database (survives restarts, works with multiple replicas), along
two independent tracks:

- **by email** — 5 failures in 15 min lock for 15 min. Blocks the attack aimed
  at one account.
- **by IP** — a 4× looser limit. Blocks *password spraying*, which tries one
  common password against many accounts and never accumulates failures on a
  single email. The looser limit exists because a whole farm may share one IP.

Lockout counts from the **last** failure: hammering during a lockout pushes the
release further out.

### User enumeration

Three defences together, because one is not enough:

1. Identical message for non-existent email, wrong password and disabled account;
2. When the email does not exist, a throwaway hash is verified anyway so response
   time matches;
3. Lockout counting applies to non-existent emails too.

### Gateways

Format `rastro_gw_<prefix>_<secret>`. The prefix is public and indexed; the
secret exists only as a hash.

The prefix is not decoration: without it, every telemetry reading would require
verifying the Argon2 hash of **every** registered key — and Argon2 is expensive
on purpose. With it, the lookup is indexed and there is one verification.

The full key is shown **once**, at creation. After that only the hash exists.
Revoking does not delete the row, so the audit trail stays readable.

Scope: the key belongs to a farm. A gateway cannot move another property's
cattle. An attempt returns 404 — not 403, which would confirm the tag's
existence to whoever is probing.

### Headers and transport

`Content-Security-Policy: default-src 'none'` on the API (which only returns
JSON), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
`Referrer-Policy: no-referrer`, COOP and CORP at `same-origin`,
`Cache-Control: no-store` on authenticated routes, HSTS when served over HTTPS.

CORS uses an explicit origin list. `allow_origins=["*"]` with credentials is
rejected by browsers — and if it weren't, it would invite session theft from any
site.

### Configuration

The application **refuses to boot** under `AMBIENTE=producao` if: `SECRET_KEY`
is the sample value or shorter than 32 bytes; `COOKIE_SECURE` is false; CORS
contains a non-local `http://` origin; or the simulator is enabled.

Outside production, a log warning makes it explicit that tokens are forgeable.

There is no default password in the code. The initial account uses `ADMIN_SENHA`
from the environment or, if empty, a random password printed to the log **once**.
Committed default credentials are how most exposed systems fall.

### Input

Ranges validated in the schema, not in the database: latitude −90..90, longitude
−180..180, activity 0..1, battery 0..100, tag id digits only, max 15. This is
network input from a field device that may be running old firmware, be faulty,
or be under someone else's control.

Queries go through SQLAlchemy with parameters — no SQL string concatenation
anywhere, including the PostGIS calls.

## What is NOT protected

An honest list. Each item is a conscious MVP trade-off, not an oversight.

| Gap | Risk | Fix before production |
|---|---|---|
| **No HTTPS in compose** | Everything in clear text on the wire | Terminate TLS at a reverse proxy (Caddy, nginx) |
| **No second factor** | A leaked password means full access | TOTP at least for the `owner` role |
| **No password recovery** | Forget it and the account is gone | Email flow with a single-use token |
| **No general rate limit** | Only login is limited; the rest of the API is not | Per-IP limit at the edge |
| **Weak password blocklist** | ~30 entries, illustrative | HIBP top 100k, or a breached-password API with k-anonymity |
| **No audit retention policy** | Grows without bound; no export path | Define retention and an external destination |
| **Secrets in environment variables** | Visible in `docker inspect` and shell history | A secrets manager (Vault, SSM, Secret Manager) |
| **No access-token revocation** | A stolen token is valid for up to 15 min | Acceptable at that lifetime; if not, a revoked-`jti` list |
| **`X-Forwarded-For` ignored** | Behind a proxy, IP lockout only sees the proxy | Enable when a **trusted** proxy is declared |
| **No email verification** | An account can be created with someone else's address | Confirmation link |
| **No backups or recovery plan** | Total database loss | Automated backups with tested restores |
| **Dependencies unscanned** | A known CVE goes unnoticed | Dependabot + `pip-audit` + `npm audit` in CI |

## If you find a vulnerability

Open an issue **without exploit details** asking for contact, or write directly
to the repository owner. This is a personal project with no bounty programme and
no response SLA.

## References

- OWASP — *Password Storage Cheat Sheet*
- OWASP — *Session Management Cheat Sheet*
- NIST SP 800-63B — *Digital Identity Guidelines: Authentication*
- RFC 9700 — *Best Current Practice for OAuth 2.0 Security*
- RFC 6819 — *OAuth 2.0 Threat Model and Security Considerations*
