# Rastro — documentation

**🇬🇧 English** · [🇧🇷 Português](README.pt-BR.md)

| Document | What it covers |
|---|---|
| [Requirements](requirements.md) | Problem, personas, functional and non-functional requirements, permission matrix, business rules, glossary, acceptance criteria |
| [Architecture](architecture.md) | Context and container diagrams, ER model, telemetry and auth sequence diagrams, alert state machine, layering, known limits |
| [Security](security.md) | Threat model, STRIDE, every implemented control with its rationale, and an honest list of what is **not** protected |
| [Decision log](decisions.md) | 12 ADRs: what was decided, what was rejected, and why |

Start from the [root README](../README.md) for setup and demo instructions.

---

## Reading order

**To understand the product** → Requirements, section 1 to 3.

**To review the code** → Architecture (layering), then Decision log.

**To assess the security posture** → Security, and in particular
["What is NOT protected"](security.md#what-is-not-protected).

**To pick up development** → Architecture (known limits) plus ADR-011 and
ADR-012, which describe the deliberate debt.

## Diagrams

All diagrams are Mermaid inside Markdown — GitHub renders them natively. There
are no image files to keep in sync with the code, and a diagram is edited in the
same commit as the change it describes.
